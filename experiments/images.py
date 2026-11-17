#!/usr/bin/env python3
"""Prepare a task SIF once, outside Slurm trials; Docker is only an import source."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import posixpath
import re
import shlex
import subprocess
from string import Template
import tempfile

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_IMAGES = ROOT / "images"


def docker_instructions(source):
    """Read continued instructions and RUN heredocs used by task environments."""
    lines = iter(source.splitlines())
    for line in lines:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        while line.rstrip().endswith("\\"):
            following = next(lines)
            while not following.strip() or following.lstrip().startswith("#"):
                following = next(lines)
            line = line.rstrip()[:-1] + " " + following.lstrip()
        match = re.search(r"<<(-?)[\"']?([A-Za-z_][A-Za-z0-9_]*)[\"']?", line)
        if match:
            body = []
            for raw in lines:
                body.append(raw)
                if raw.lstrip("\t") == match[2]:
                    break
            else:
                raise ValueError("unterminated Dockerfile heredoc")
            line += "\n" + "\n".join(body)
        instruction, _, value = line.strip().partition(" ")
        yield instruction.upper(), value.strip()


def shell_value(value):
    # Docker ENV expands variable names, but never shell commands. Preserve
    # those expansions and keep every other character literal.
    pieces = re.split(r"(\$\{[A-Za-z_][A-Za-z0-9_]*\}|\$[A-Za-z_][A-Za-z0-9_]*)", value)
    return '"' + "".join(part if index % 2 else part.replace("\\", "\\\\").replace('"', '\\"').replace("`", "\\`").replace("$", "\\$")
                          for index, part in enumerate(pieces)) + '"'


def task_recipe(environment):
    """Translate the single-stage environment instructions used by these tasks.

    Files are staged once, then copied at their original positions among RUN
    steps. Moving all COPY operations ahead of RUN would change build behavior.
    Unsupported Docker features require an explicit native --definition.
    """
    base = None
    args = {}
    workdir = "/"
    shell = ["/bin/sh", "-c"]
    entrypoint = []
    post, runtime, files = [], [], []
    staging = "/opt/skillcanvas/build-inputs"
    for instruction, value in docker_instructions((environment / "Dockerfile").read_text()):
        if instruction == "ARG":
            key, _, default = value.partition("=")
            args[key] = default
            post.append(f"export {key}={shell_value(default)}")
        elif instruction == "FROM":
            if base:
                raise ValueError("multi-stage Dockerfile: supply a native --definition")
            words = shlex.split(value)
            while words[0].startswith("--"):
                if words[0] != "--platform=linux/amd64":
                    raise ValueError(f"unsupported FROM option: {words[0]}")
                words.pop(0)
            base = Template(words[0]).substitute(args)
        elif instruction == "ENV":
            words = shlex.split(value)
            if "=" not in words[0]:
                words = [words[0] + "=" + " ".join(words[1:])]
            assignments = []
            for word in words:
                key, separator, content = word.partition("=")
                if not separator:
                    raise ValueError(f"invalid ENV assignment: {word}")
                assignments.append(key + "=" + shell_value(content))
            export = "export " + " ".join(assignments)
            post.append(export)
            runtime.append(export)
        elif instruction == "WORKDIR":
            # Variables in WORKDIR are uncommon in these tasks; an explicit
            # recipe is clearer than guessing a base image's environment.
            if "$" in value:
                raise ValueError("WORKDIR with variables needs a native --definition")
            workdir = posixpath.normpath(posixpath.join(workdir, value))
            post.append(f"mkdir -p {shlex.quote(workdir)} && cd {shlex.quote(workdir)}")
        elif instruction == "SHELL":
            shell = json.loads(value)
        elif instruction == "RUN":
            if value.startswith("--"):
                raise ValueError("BuildKit RUN options need a native --definition")
            if value.startswith("["):
                post.append(shlex.join(json.loads(value)))
            else:
                if value.startswith("<<"):
                    value = "\n".join(value.splitlines()[1:-1])
                post.append(shlex.join(shell + [value]))
        elif instruction == "COPY":
            if value.startswith("--"):
                raise ValueError("COPY flags need a native --definition")
            paths = json.loads(value) if value.startswith("[") else shlex.split(value)
            destination = posixpath.join(workdir, paths[-1])
            sources = [path for pattern in paths[:-1] for path in sorted(environment.glob(pattern))]
            if not sources:
                raise ValueError(f"COPY source does not exist: {value}")
            directory = destination.endswith("/") or len(sources) > 1
            for source in sources:
                staged = f"{staging}/{len(files)}/input"
                files.append(f"    {shlex.quote(str(source.resolve()))} {staged}")
                target = shlex.quote(destination)
                if source.is_dir():
                    post += [f"mkdir -p {target}", f"cp -a {staged}/. {target}/"]
                else:
                    parent = destination if directory else posixpath.dirname(destination)
                    post += [f"mkdir -p {shlex.quote(parent)}", f"cp -a {staged} {target}"]
        elif instruction == "USER":
            if value not in ("root", "0"):
                raise ValueError("non-root image USER needs a native --definition")
        elif instruction == "ENTRYPOINT":
            if not value.startswith("["):
                raise ValueError("shell-form ENTRYPOINT needs a native --definition")
            entrypoint = json.loads(value)
        elif instruction in ("CMD", "LABEL", "EXPOSE", "MAINTAINER"):
            # The image entrypoint can start task services, but BenchFlow
            # replaces CMD with an idle command and dispatches agents later.
            continue
        else:
            raise ValueError(f"unsupported Dockerfile instruction {instruction}; supply --definition")
    if not base:
        raise ValueError("Dockerfile has no FROM")
    post += [f"rm -rf {staging}"]
    sections = ["Bootstrap: docker\nFrom: " + base]
    if files:
        sections.append("%files\n" + "\n".join(files))
    sections.append("%post\nset -e\n" + "\n".join(post))
    if runtime:
        sections.append("%environment\n    " + "\n    ".join(runtime))
    sections.append("%startscript\nexec " + shlex.join(entrypoint + ["/bin/sleep", "infinity"]))
    return "\n\n".join(sections), workdir


def append_section(definition, name, body):
    """Extend an existing native section without creating duplicate sections."""
    found = re.search(r"(?m)^%" + name + r"(?:[ \t]+[^\n]*)?\n", definition)
    if found:
        following = re.search(r"(?m)^%[a-zA-Z]", definition[found.end():])
        end = found.end() + following.start() if following else len(definition)
        return definition[:end].rstrip() + "\n" + body + "\n\n" + definition[end:]
    return definition.rstrip() + "\n\n%" + name + "\n" + body + "\n"


def environment_hashes(environment):
    # Skills are deployed independently at runtime. Dockerfile-only additions
    # in prepared images (e.g. offline verifier wheels) leave task inputs intact.
    return {str(path.relative_to(environment)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(environment.rglob("*")) if path.is_file()
            and path.relative_to(environment).parts[0] != "skills" and path.name != "Dockerfile"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", required=True)
    parser.add_argument("--tasks-root", type=Path, default=ROOT / "repos/skillsbench/tasks")
    origin = parser.add_mutually_exclusive_group()
    origin.add_argument("--docker-image", help="one-time import of an existing local Docker image")
    origin.add_argument("--source", help="full task environment: docker://registry/image:tag, docker-archive:/path, or a local SIF")
    origin.add_argument("--definition", type=Path, help="explicit native recipe for task environments beyond the supported Dockerfile subset")
    parser.add_argument("--agent", choices=("opencode",), help="cache the pinned agent in the SIF too")
    parser.add_argument("--images-dir", type=Path, default=Path(os.environ.get("SKILLCANVAS_IMAGES", DEFAULT_IMAGES)))
    parser.add_argument("--workdir", default="/root", help="workspace for imported images or explicit recipes")
    parser.add_argument("--plan", action="store_true", help="print the native recipe without building or downloading")
    args = parser.parse_args()
    task = args.tasks_root.resolve() / args.task
    if Path(args.task).name != args.task or not (task / "task.md").is_file():
        parser.error("unknown task id")
    images = args.images_dir.resolve()
    images.mkdir(parents=True, exist_ok=True)
    target = images / f"{args.task}.sif"
    if not args.plan and (target.exists() or target.with_suffix(".json").exists()):
        parser.error(f"image already exists: {target}; use a different --images-dir to rebuild")
    source = args.source
    metadata = {"task": args.task, "environment_files": environment_hashes(task / "environment"),
                "agent": args.agent, "benchflow_commit": json.loads((ROOT / "sources.lock.json").read_text())["sources"]["benchflow"]["commit"]}
    with tempfile.TemporaryDirectory(prefix="skillcanvas-image-") as folder:
        temporary = Path(folder)
        if args.docker_image:
            info = json.loads(subprocess.check_output(["docker", "image", "inspect", args.docker_image], text=True))[0]
            metadata.update(docker_image_id=info["Id"], docker_image=args.docker_image)
            saved = temporary / "task.tar"
            subprocess.run(["docker", "image", "save", "--output", str(saved), info["Id"]], check=True)
            source = "docker-archive:" + str(saved)
        metadata["source"] = args.docker_image or source
        workdir = args.workdir
        if args.definition:
            header = args.definition.resolve().read_text()
        elif not source:
            header, workdir = task_recipe(task / "environment")
            metadata["source"] = "task environment/Dockerfile"
        elif source.startswith("docker://"):
            header = "Bootstrap: docker\nFrom: " + source.removeprefix("docker://")
        elif source.startswith("docker-archive:"):
            archive_path = source.split(":", 1)[1]
            if archive_path.startswith("//"):
                archive_path = archive_path[2:]
            header = "Bootstrap: docker-archive\nFrom: " + str(Path(archive_path).resolve())
        else:
            header = "Bootstrap: localimage\nFrom: " + str(Path(source).resolve())
        definition_text = header
        metadata["workdir"] = workdir
        install = ""
        if args.agent:
            from benchflow.agents.install import agent_layer_plan
            plan = agent_layer_plan(args.agent)
            metadata["agent_install_stamp"] = plan.stamp
            install = plan.recipe.install_cmd + "\n"
        definition_text = append_section(definition_text, "post", "set -e\nmkdir -p /logs /tmp /var/tmp /mnt\n" + install)
        if not re.search(r"(?m)^%startscript\b", definition_text):
            definition_text = append_section(definition_text, "startscript", "exec /bin/sleep infinity")
        definition = temporary / "task.def"
        definition.write_text(definition_text)
        metadata["definition"] = definition.read_text()
        if args.plan:
            print(json.dumps(metadata, indent=2))
            return
        subprocess.run(["singularity", "build", "--fakeroot", str(target), str(definition)], check=True)
    with target.open("rb") as stream:
        metadata["sif_sha256"] = hashlib.file_digest(stream, "sha256").hexdigest()
    target.with_suffix(".json").write_text(json.dumps(metadata, indent=2) + "\n")
    print(target)


if __name__ == "__main__":
    main()

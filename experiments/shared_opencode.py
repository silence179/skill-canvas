#!/usr/bin/env python3
"""Share the pinned OpenCode toolchain across otherwise independent Docker tasks.

The donor image contains only a checked tool archive. Task images, the native
layer cache, runtime admission, credentials and verifier setup stay independent.
"""

import argparse
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import runpy
import shlex
import subprocess
import sys
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".runtime/shared-opencode"
RECORD = STATE / "image.json"
META = "/opt/runtime/shared-opencode"
TOOLS = ("/opt/runtime/node", "/opt/runtime/js-agents",
         "/opt/runtime/bin/opencode", "/opt/runtime/bin/opencode-proxy")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def docker(*args, **kwargs):
    return subprocess.check_output(["docker", *args], **kwargs)


def inspect(ref):
    return json.loads(docker("image", "inspect", ref))[0]


def native_plan():
    from benchflow.agents.install import agent_layer_plan
    plan = agent_layer_plan("opencode")
    if plan is None:
        raise RuntimeError("the pinned OpenCode install is not cacheable")
    return plan


def load_record(*, check_image=True):
    record = json.loads(RECORD.read_text())
    if record["install_sha256"] != sha(native_plan().install.encode()):
        raise RuntimeError("OpenCode recipe changed; rebuild the shared tool image")
    if check_image and inspect(record["tag"])["Id"] != record["image_id"]:
        raise RuntimeError("shared OpenCode image changed; refusing the moved tag")
    return record


def build(source=None):
    """Repackage only tool files from a native, host-recorded install layer."""
    from benchflow.sandbox.env_layers import trusted_layer_ids
    plan = native_plan()
    if RECORD.exists():
        print(json.dumps(load_record(), indent=2))
        return
    candidates = [inspect(source)] if source else json.loads(docker(
        "image", "inspect", *docker("image", "ls", "-q", "--no-trunc",
        "--filter", "label=benchflow.layer.agent=opencode").decode().split()))
    selected = None
    for info in candidates:
        labels = info["Config"].get("Labels") or {}
        key = labels.get("benchflow.layer.key", "")
        if (labels.get("benchflow.layer") == "agent" and key
                and info["Id"] in trusted_layer_ids("agent", key)):
            selected = info
            break
    if selected is None:
        raise RuntimeError("no host-recorded OpenCode install layer; run one native setup first")
    source_id = selected["Id"]
    # This is a new, offline container of an install-only image, never a trial
    # container. Whitelist tools; never copy HOME, skills, task data or /tmp.
    checks = (
        "set -eu; "
        f"test \"$(cat {plan.stamp_path})\" = {shlex.quote(plan.stamp)}; "
        "test \"$(/opt/runtime/node/bin/node --version)\" = v22.20.0; "
        "test \"$(/opt/runtime/js-agents/bin/opencode --version)\" = 1.19.5; "
        f"mkdir -p {META}; "
        f"find {' '.join(TOOLS)} -type f -exec sha256sum {{}} + > {META}/files.sha256; "
        f"find {' '.join(TOOLS)} -type l -printf '%p\\t%l\\n' > {META}/links.tsv; "
        "tar -C / -cf - " + " ".join(p.lstrip("/") for p in (*TOOLS, META))
    )
    STATE.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="skillcanvas-opencode-") as temporary:
        context = Path(temporary)
        archive = context / "tools.tar"
        with archive.open("wb") as output:
            subprocess.run(["docker", "run", "--rm", "--network", "none",
                "--entrypoint", "/bin/sh", source_id, "-c", checks],
                stdout=output, check=True, timeout=120)
        with tarfile.open(archive) as package:
            file_hash = sha(package.extractfile(META.lstrip("/") + "/files.sha256").read())
            link_hash = sha(package.extractfile(META.lstrip("/") + "/links.tsv").read())
        with archive.open("rb") as stream:
            archive_hash = hashlib.file_digest(stream, "sha256").hexdigest()
        tag = "skillcanvas-opencode:1.19.5-" + archive_hash[:20]
        (context / "Dockerfile").write_text(
            "FROM scratch\nCOPY tools.tar /payload/tools.tar\n")
        iid = context / "image.id"
        subprocess.run(["docker", "build", "--network", "none", "--iidfile", str(iid),
            "-t", tag, str(context)], check=True, timeout=300)
        record = {"schema": 1, "version": "1.19.5", "node_version": "22.20.0",
            "tag": tag, "image_id": iid.read_text().strip(),
            "arch": selected["Architecture"], "libc": "glibc",
            "install_sha256": sha(plan.install.encode()),
            "archive_sha256": archive_hash, "files_sha256": file_hash,
            "links_sha256": link_hash, "source_layer_id": source_id,
            "adapter_sha256": sha(Path(__file__).read_bytes())}
        if inspect(tag)["Id"] != record["image_id"]:
            raise RuntimeError("shared image changed during build")
        RECORD.write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps(record, indent=2))


def verify_command(record):
    """Check pinned content in the actual task before any tool executes."""
    from benchflow._root_only import root_only_tree_check
    checks = (
        root_only_tree_check("/opt/runtime", "shared OpenCode runtime") + " && "
        f"printf '%s\\n' '{record['files_sha256']}  {META}/files.sha256' "
        f"'{record['links_sha256']}  {META}/links.tsv' | sha256sum -c --quiet && "
        f"sha256sum -c --quiet {META}/files.sha256 && "
        "( while IFS=\"$(printf '\\t')\" read -r bf_link bf_target; do "
        '[ "$(readlink "$bf_link")" = "$bf_target" ] || exit 1; '
        f"done < {META}/links.tsv )"
    )
    return "( " + checks + " ) || exit 1"


def shared_recipe(recipe, record):
    from benchflow._root_only import root_only_tree_check
    plan = native_plan()
    # Do not reinterpret a custom/native/multi-agent install recipe.
    if recipe != plan.recipe:
        return None
    command = (
        f"# shared-opencode-image={record['image_id']}\n"
        "set -eu; mkdir -p /opt/runtime; "
        + root_only_tree_check("/opt/runtime", "shared OpenCode destination") + " || exit 1; "
        "test ! -e /opt/runtime/node; test ! -L /opt/runtime/node; "
        "test ! -e /opt/runtime/js-agents; test ! -L /opt/runtime/js-agents; "
        f"printf '%s\\n' '{record['archive_sha256']}  /run/skillcanvas-tools/payload/tools.tar' "
        "| sha256sum -c --quiet; "
        "tar -C / --no-same-owner -xf /run/skillcanvas-tools/payload/tools.tar; "
        + verify_command(record) + "; "
        'test "$(/opt/runtime/node/bin/node --version)" = v22.20.0; '
        'test "$(/opt/runtime/js-agents/bin/opencode --version)" = 1.19.5; '
        f"mkdir -p {Path(plan.stamp_path).parent}; "
        f"printf '%s\\n' {shlex.quote(plan.stamp)} > {plan.stamp_path}; "
        f"chmod 0644 {plan.stamp_path}; "
        "echo 'OpenCode supplied by the shared tool image; no npm download'"
    )
    return replace(recipe, install_cmd=command)


def install_adapter(record):
    from benchflow.agents import install
    from benchflow.sandbox import env_layers as layers
    from benchflow.sandbox._exec_output import exec_raw
    original_ensure = layers.DockerLayers.ensure_agent_layer
    original_dockerfile = layers.agent_layer_dockerfile
    original_from = install.install_from_layer
    shared_keys = set()
    commands = set()

    async def ensure(self, recipe, base_ref, **kwargs):
        replacement = shared_recipe(recipe, record)
        if replacement is not None:
            base = kwargs.get("base") or await self.inspect_base(
                base_ref, pull=kwargs.get("pull", False), for_agent=True, agent_recipe=recipe)
            if base.libc == record["libc"] and base.arch == record["arch"]:
                # Inspect the exact donor immediately before every lookup/build.
                found = await self._inspect(record["tag"])
                if found is None or found["Id"] != record["image_id"]:
                    raise layers.LayerError("shared OpenCode donor missing or changed")
                commands.add(replacement.install_cmd)
                kwargs["base"] = base
                result = await original_ensure(self, replacement, base_ref, **kwargs)
                shared_keys.add(result.key)
                return result
        return await original_ensure(self, recipe, base_ref, **kwargs)

    def dockerfile(recipe, base_from, key, *, user=""):
        source = original_dockerfile(recipe, base_from, key, user=user)
        if recipe.install_cmd in commands:
            # Retain native root environment, checks, mount guard and USER restore.
            source = source.replace("\nRUN ",
                f"\nRUN --network=none --mount=type=bind,from={record['tag']},"
                "target=/run/skillcanvas-tools,readonly ", 1)
        return source

    async def from_layer(env, plan, rollout_dir, *, layer_key):
        if layer_key in shared_keys:
            checked = await exec_raw(env.exec, verify_command(record), timeout_sec=60)
            if checked.return_code:
                raise RuntimeError("shared OpenCode content failed runtime verification")
            rollout_dir = Path(rollout_dir)
            (rollout_dir / "shared-opencode.json").write_text(json.dumps(record, indent=2) + "\n")
        return await original_from(env, plan, rollout_dir, layer_key=layer_key)

    layers.DockerLayers.ensure_agent_layer = ensure
    layers.agent_layer_dockerfile = dockerfile
    install.install_from_layer = from_layer


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("build", "check", "run"))
    parser.add_argument("--source-layer")
    args, remainder = parser.parse_known_args()
    os.environ.setdefault("DOCKER_CONFIG", str(ROOT / ".runtime/docker"))
    if args.action == "build":
        build(args.source_layer)
        return 0
    record = load_record(check_image="--dry-run" not in remainder)
    if args.action == "check":
        print(json.dumps(record, indent=2))
        return 0
    if remainder[:1] == ["--"]:
        remainder = remainder[1:]
    install_adapter(record)
    os.environ.pop("BENCHFLOW_DAEMON", None)
    print("Shared OpenCode image: " + record["tag"], flush=True)
    if remainder[:1] == ["--delivery-runner"]:
        sys.argv = [str(ROOT / "experiments/uml-flowchart/delivery_runner.py"), *remainder[1:]]
        sys.path.insert(0, str(Path(sys.argv[0]).parent))
        runpy.run_path(sys.argv[0], run_name="__main__")
    else:
        from benchflow.cli.main import main as bench_main
        sys.argv = ["bench", *remainder]
        bench_main()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

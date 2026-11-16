#!/usr/bin/env python3
"""Build matched text and image-first skill bundles for one fixed task."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import struct
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
TASK = "crystallographic-wyckoff-position-analysis"
UPSTREAM = ROOT / "repos/skillsbench"
SOURCE = UPSTREAM / "tasks" / TASK / "environment/skills"
JAR = ROOT / ".runtime/plantuml/plantuml-mit-1.2026.10.jar"
JAR_SHA256 = "30a66b81a16127fd3ec560992f31964fe9ae3f1233c614ef4558a4558a21489e"
SKILLS = ("pymatgen", "sympy")


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inventory(folder):
    return {
        p.relative_to(folder).as_posix(): sha256(p)
        for p in sorted(folder.rglob("*"))
        if p.is_file()
    }


def render(source, kind):
    result = subprocess.run(
        [
            "java", "-Djava.awt.headless=true", "-jar", str(JAR),
            "-failfast2", "-nometadata", "-charset", "UTF-8",
            f"-t{kind}", "-pipe",
        ],
        input=source.read_bytes(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    return result.stdout


def entrypoint(frontmatter, image_first):
    if image_first:
        action = (
            "1. Open assets/flowchart.png with your image-viewing tool and inspect "
            "the rendered workflow before applying this skill. Resolve this path "
            "relative to this SKILL.md. Reading a filename, image bytes, or alt text "
            "is not viewing the image.\n"
            "2. Then read GUIDE.md, the complete original skill, before using "
            "its workflow, references, or scripts.\n"
            "If the image cannot be viewed, say so and continue with GUIDE.md; "
            "do not claim that the visual workflow was inspected.\n"
        )
    else:
        action = (
            "1. Read GUIDE.md, the complete original skill, before using "
            "its workflow, references, or scripts.\n"
        )
    return (
        frontmatter
        + "\n# Skill reading order\n\n"
        + action
        + "\nFollow the task's requested outputs. The original examples, code, "
        "caveats, and resource paths are preserved in GUIDE.md and the adjacent "
        "references/ and scripts/ directories.\n"
    )


def verify():
    manifest = json.loads((HERE / "manifest.json").read_text())
    actual_commit = subprocess.check_output(
        ["git", "-C", str(UPSTREAM), "rev-parse", "HEAD"], text=True
    ).strip()
    if actual_commit != manifest["skillsbench_commit"]:
        raise ValueError("Upstream commit differs from the recorded experiment")
    for skill in SKILLS:
        original = SOURCE / skill
        expected = manifest["skills"][skill]["source_files"]
        if inventory(original) != expected:
            raise ValueError(f"{skill}: source changed after preparation")
        for arm in ("text", "image"):
            bundle = HERE / "bundles" / arm / skill
            if inventory(bundle) != manifest["skills"][skill]["bundles"][arm]:
                raise ValueError(f"{skill}: {arm} bundle changed")
            if (bundle / "GUIDE.md").read_bytes() != (original / "SKILL.md").read_bytes():
                raise ValueError(f"{skill}: original skill was not preserved")
            for name, digest in expected.items():
                if name != "SKILL.md" and sha256(bundle / name) != digest:
                    raise ValueError(f"{skill}: resource changed: {name}")
        if sha256(HERE / "diagrams" / f"{skill}.puml") != manifest["skills"][skill]["uml_sha256"]:
            raise ValueError(f"{skill}: UML source changed; rebuild the bundles")
        image = HERE / "bundles/image" / skill / "assets/flowchart.png"
        raw = image.read_bytes()
        if raw[:8] != b"\x89PNG\r\n\x1a\n":
            raise ValueError(f"{skill}: invalid PNG")
        dimensions = list(struct.unpack(">II", raw[16:24]))
        if dimensions != manifest["skills"][skill]["png_dimensions"]:
            raise ValueError(f"{skill}: PNG dimensions changed")
        print(f"{skill}: original resources match; text/image bundles verified; PNG {dimensions}")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="verify existing bundles")
    parser.add_argument("--rebuild", action="store_true", help="replace generated bundles")
    args = parser.parse_args()
    if args.check:
        verify()
        return
    if not JAR.is_file() or sha256(JAR) != JAR_SHA256:
        parser.error("Missing or unverified PlantUML jar; see README.md")
    bundles = HERE / "bundles"
    if bundles.exists() and not args.rebuild:
        parser.error("Bundles already exist; use --check or --rebuild")
    manifest = {
        "task": TASK,
        "skillsbench_commit": subprocess.check_output(
            ["git", "-C", str(UPSTREAM), "rev-parse", "HEAD"], text=True
        ).strip(),
        "comparison": "original guide vs image-first plus the same original guide",
        "renderer": {
            "name": "PlantUML MIT", "version": "1.2026.10", "sha256": JAR_SHA256,
            "url": "https://github.com/plantuml/plantuml/releases/download/v1.2026.10/plantuml-mit-1.2026.10.jar",
        },
        "skills": {},
    }
    with tempfile.TemporaryDirectory(prefix=".prepare-", dir=HERE) as temporary:
        staged = Path(temporary) / "bundles"
        for skill in SKILLS:
            source = SOURCE / skill
            uml = HERE / "diagrams" / f"{skill}.puml"
            original = (source / "SKILL.md").read_bytes()
            original_text = original.decode("utf-8")
            match = re.match(r"\A---\n.*?\n---\n", original_text, re.S)
            if not match:
                raise ValueError(f"{skill}: missing frontmatter")
            for path in source.rglob("*"):
                if path.is_symlink():
                    raise ValueError(f"Resolve symlink before packaging: {path}")
            png = render(uml, "png")
            svg = render(uml, "svg")
            if not png.startswith(b"\x89PNG\r\n\x1a\n"):
                raise ValueError(f"{skill}: renderer did not produce PNG")
            if b"<svg" not in svg or b"Syntax Error" in svg:
                raise ValueError(f"{skill}: invalid SVG rendering")
            info = {
                "source_files": inventory(source),
                "uml_sha256": sha256(uml),
                "png_dimensions": list(struct.unpack(">II", png[16:24])),
                "bundles": {},
            }
            for arm in ("text", "image"):
                destination = staged / arm / skill
                shutil.copytree(source, destination)
                if (destination / "GUIDE.md").exists():
                    raise ValueError(f"{skill}: GUIDE.md would overwrite a resource")
                (destination / "GUIDE.md").write_bytes(original)
                (destination / "SKILL.md").write_text(
                    entrypoint(match.group(), arm == "image"), encoding="utf-8"
                )
                if arm == "image":
                    (destination / "assets").mkdir(exist_ok=True)
                    (destination / "assets/flowchart.png").write_bytes(png)
                info["bundles"][arm] = inventory(destination)
            previews = HERE / "previews"
            previews.mkdir(exist_ok=True)
            (previews / f"{skill}.png").write_bytes(png)
            (previews / f"{skill}.svg").write_bytes(svg)
            manifest["skills"][skill] = info
        if bundles.exists():
            shutil.rmtree(bundles)
        shutil.move(str(staged), bundles)
    (HERE / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"
    )
    verify()


if __name__ == "__main__":
    main()

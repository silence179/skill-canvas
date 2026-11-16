#!/usr/bin/env python3
"""Prepare and verify five additional paired UML/skill experiments."""

import argparse
import importlib.util
import json
from pathlib import Path
import re
import shutil
import struct
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
UPSTREAM = ROOT / "repos/skillsbench"
TASKS = (
    "llm-prefix-cache-replay", "energy-market-pricing", "r2r-mpc-control",
    "exam-block-sequencing", "manufacturing-fjsp-optimization",
)
# Reuse the already-pinned renderer and matched entrypoint format.
spec = importlib.util.spec_from_file_location("crystal_prepare", HERE.parent / "uml-flowchart/prepare.py")
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)
sha256, inventory = base.sha256, base.inventory


def skill_names(task):
    source = UPSTREAM / "tasks" / task / "environment/skills"
    return tuple(sorted(path.parent.name for path in source.glob("*/SKILL.md")))


def verify_study(study):
    study = study.resolve()
    if study.parent != (HERE / "tasks").resolve() or study.name not in TASKS:
        raise ValueError("unregistered expanded study")
    manifest = json.loads((study / "manifest.json").read_text())
    task = study.name
    if manifest["task"] != task or tuple(manifest["skills"]) != skill_names(task):
        raise ValueError("task or skill catalog changed")
    commit = subprocess.check_output(["git", "-C", str(UPSTREAM), "rev-parse", "HEAD"], text=True).strip()
    source = UPSTREAM / "tasks" / task / "environment/skills"
    if commit != manifest["skillsbench_commit"] or inventory(source) != manifest["source_files"]:
        raise ValueError("source revision/resources changed")
    for arm in ("text", "image"):
        bundle = study / "bundles" / arm
        if inventory(bundle) != manifest["bundles"][arm]:
            raise ValueError(f"{task}: {arm} bundle changed")
        for skill in manifest["skills"]:
            if (bundle / skill / "GUIDE.md").read_bytes() != (source / skill / "SKILL.md").read_bytes():
                raise ValueError("full original skill changed")
    for skill, details in manifest["skills"].items():
        if sha256(study / "diagrams" / f"{skill}.puml") != details["uml_sha256"]:
            raise ValueError("UML changed")
        png = study / "bundles/image" / skill / "assets/flowchart.png"
        data = png.read_bytes()
        if not data.startswith(b"\x89PNG\r\n\x1a\n") or sha256(png) != details["png_sha256"]:
            raise ValueError("PNG changed")
        if list(struct.unpack(">II", data[16:24])) != details["png_dimensions"]:
            raise ValueError("PNG dimensions changed")
    return manifest


def prepare(task):
    study = HERE / "tasks" / task
    if (study / "manifest.json").exists():
        verify_study(study)
        return
    if sha256(base.JAR) != base.JAR_SHA256:
        raise ValueError("renderer hash changed")
    source = UPSTREAM / "tasks" / task / "environment/skills"
    names = skill_names(task)
    manifest = {"task": task, "skillsbench_commit": subprocess.check_output(
        ["git", "-C", str(UPSTREAM), "rev-parse", "HEAD"], text=True).strip(),
        "comparison": "forced full skill text vs PNG-first plus identical full text",
        "diagram_basis": "only original SKILL.md; no oracle/verifier content",
        "renderer": {"name": "PlantUML MIT", "sha256": base.JAR_SHA256, "version": "1.2026.10"},
        "source_files": inventory(source), "skills": {}, "bundles": {}}
    with tempfile.TemporaryDirectory(prefix=".prepare-", dir=study) as directory:
        staged = Path(directory)
        for path in source.rglob("*"):
            if path.is_symlink():
                raise ValueError(f"unexpected symlink: {path}")
        for arm in ("text", "image"):
            shutil.copytree(source, staged / arm)
        for skill in names:
            original = (source / skill / "SKILL.md").read_bytes()
            front = re.match(r"\A---\n.*?\n---\n", original.decode(), re.S)
            if not front:
                raise ValueError("missing skill frontmatter")
            uml = study / "diagrams" / f"{skill}.puml"
            png, svg = base.render(uml, "png"), base.render(uml, "svg")
            if not png.startswith(b"\x89PNG\r\n\x1a\n") or b"<svg" not in svg or b"Syntax Error" in svg:
                raise ValueError("renderer failed")
            for arm in ("text", "image"):
                destination = staged / arm / skill
                if (destination / "GUIDE.md").exists():
                    raise ValueError("GUIDE resource collision")
                (destination / "GUIDE.md").write_bytes(original)
                (destination / "SKILL.md").write_text(base.entrypoint(front.group(), arm == "image"))
                if arm == "image":
                    asset = destination / "assets/flowchart.png"
                    if asset.exists():
                        raise ValueError("figure resource collision")
                    asset.parent.mkdir(exist_ok=True)
                    asset.write_bytes(png)
            (study / "previews").mkdir(exist_ok=True)
            (study / "previews" / f"{skill}.png").write_bytes(png)
            (study / "previews" / f"{skill}.svg").write_bytes(svg)
            manifest["skills"][skill] = {"guide_sha256": sha256(source / skill / "SKILL.md"),
                "uml_sha256": sha256(uml), "png_sha256": sha256(study / "previews" / f"{skill}.png"),
                "png_dimensions": list(struct.unpack(">II", png[16:24])),
                "guide_bytes": len(original)}
        (study / "bundles").mkdir(exist_ok=True)
        for arm in ("text", "image"):
            manifest["bundles"][arm] = inventory(staged / arm)
            shutil.move(str(staged / arm), str(study / "bundles" / arm))
    (study / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    verify_study(study)
    print(f"{task}: {len(names)} figures and matched bundles prepared", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    for task in TASKS:
        if args.check:
            manifest = verify_study(HERE / "tasks" / task)
            print(task, {k: v["png_dimensions"] for k, v in manifest["skills"].items()})
        else:
            prepare(task)

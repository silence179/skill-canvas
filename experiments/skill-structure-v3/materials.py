"""Skill-first source selection, rendering, freezing and one-image interventions.

Generation reads ONLY frozen local skill resources and previous figure bytes.
Task names are lookup keys for later evaluation, never content-generation inputs.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess
import sys

from diagrams import DECISIONS, BODIES, dot_source

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OLD = ROOT / "experiments/uml-expanded/full-skill-v2"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def inventory(folder):
    return {str(p.relative_to(folder)): sha(p) for p in sorted(Path(folder).rglob("*")) if p.is_file()}


def write(path, data):
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def identities():
    return {p.name: sha(p) for p in (Path(__file__), HERE / "diagrams.py")}


def check(require_frozen=True):
    m = json.loads((HERE / "manifest.json").read_text())
    if require_frozen and not m["frozen"]:
        raise ValueError("materials must be explicitly frozen after visual/source review")
    assert m["generator_sha256"] == identities(), "generator changed; use a new version"
    assert sha(OLD / "manifest.json") == m["old_manifest_sha256"]
    assert sha(HERE / "selection.json") == m["selection_sha256"]
    for task, row in m["tasks"].items():
        assert inventory(HERE / "tasks" / task / "source") == row["source_files"]
        assert inventory(OLD / "tasks" / task / "source") == row["source_files"]
        for variant, v in row["variants"].items():
            bundle = HERE / v["bundle"]
            assert inventory(bundle) == v["files"], (task, variant)
            baseline = row["variants"]["baseline"]["files"]
            differences = sorted(p for p in set(baseline) | set(v["files"]) if baseline.get(p) != v["files"].get(p))
            expected = [] if variant == "baseline" else [f"{variant}/assets/flowchart.png"]
            assert differences == expected, (variant, differences)
            for skill in row["skills"]:
                assert (bundle / skill / "GUIDE.md").read_bytes() == (HERE / "tasks" / task / "source" / skill / "SKILL.md").read_bytes()
    for skill, row in m["figures"].items():
        for rel, digest in row["artifacts"].items():
            assert sha(HERE / rel) == digest, (skill, rel)
    return m


def build(freeze=False):
    if (HERE / "manifest.json").exists() and json.loads((HERE / "manifest.json").read_text())["frozen"]:
        return check()
    old = json.loads((OLD / "manifest.json").read_text())
    catalog = {skill: task for task, row in old["tasks"].items() for skill in row["skills"]}
    assert set(catalog) == set(DECISIONS)
    assert set(BODIES) == {s for s, d in DECISIONS.items() if d[0] == "redraw"}
    selection = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "basis": "Source semantics only: complete frozen local skill closure. No task.md, instance, oracle, verifier, previous solutions or outcomes read by generation code.",
        "not_blinded": "Author has seen prior results during earlier analysis; this is a transparent post-results source-constrained redesign, not a claim of blinded selection.",
        "no_new_diagram_semantics": "No standalone experiment for no-new-diagram/keep-activity entries. Their original full texts and background v2 figures remain fixed when another skill is tested.",
        "rows": []}
    m = {"schema": 3, "frozen": freeze, "created_at_utc": datetime.now(timezone.utc).isoformat(),
         "generation_unit": "skill", "intervention": "exactly one skill PNG replaced; all other bundle bytes identical",
         "generator_sha256": identities(), "old_manifest_sha256": sha(OLD / "manifest.json"),
         "renderer": subprocess.check_output(["dot", "-V"], stderr=subprocess.STDOUT, text=True).strip(),
         "tasks": {}, "figures": {}}
    index = ["# Skill 结构图 v3", "", "按 skill 来源选图；每次只替换该 skill 的一张图。以下任务名仅用于找到原资源和后续评测。", "",
             "|skill|决定|表示／原因|预览|", "|---|---|---|---|"]
    for skill, (decision, kind, reason) in DECISIONS.items():
        task = catalog[skill]
        info = old["tasks"][task]["skills"][skill]
        src = OLD / "tasks" / task / "source"
        # Verify every source in the closure, including sibling/reference/script.
        for rel, digest in old["tasks"][task]["source_files"].items():
            assert sha(src / rel) == digest
        sources = {sid: {**row, "verified_sha256": sha(src / row["path"])} for sid, row in info["sources"].items()}
        row = dict(skill=skill, decision=decision, diagram_type=kind, reason=reason, source_map=sources,
                   evaluation_locator=task)
        selection["rows"].append(row)
        if decision != "redraw":
            index.append(f"|{skill}|{decision}|{reason}|不单独运行|")
            continue
        dest = HERE / "figures" / skill
        dest.mkdir(parents=True, exist_ok=True)
        dot = dest / "diagram.dot"
        dot.write_text(dot_source(skill))
        for fmt in ("png", "svg"):
            subprocess.run(["dot", f"-T{fmt}", str(dot), "-o", str(dest / f"diagram.{fmt}")], check=True)
        raw = (dest / "diagram.png").read_bytes()
        assert raw.startswith(b"\x89PNG\r\n\x1a\n")
        size = list(struct.unpack(">II", raw[16:24]))
        assert max(size) < 6000 and min(size) > 100, (skill, size)
        m["figures"][skill] = dict(diagram_type=kind, dimensions=size, sources=sources,
                                   artifacts={str(p.relative_to(HERE)): sha(p) for p in dest.iterdir() if p.is_file()})
        index.append(f"|{skill}|redraw|{kind}：{reason}|[PNG](figures/{skill}/diagram.png) · [SVG](figures/{skill}/diagram.svg)|")
    for task, oldrow in old["tasks"].items():
        selected = sorted(s for s in oldrow["skills"] if s in BODIES)
        if not selected:
            continue
        target = HERE / "tasks" / task
        target.mkdir(parents=True, exist_ok=True)
        if not (target / "source").exists():
            shutil.copytree(OLD / "tasks" / task / "source", target / "source")
        row = dict(source_files=oldrow["source_files"], skills=sorted(oldrow["skills"]), variants={})
        for variant in ["baseline", *selected]:
            bundle = target / "variants" / variant / "bundle"
            if bundle.exists():
                shutil.rmtree(bundle)  # draft directory only, before freezing/any trial
            shutil.copytree(OLD / "tasks" / task / "bundles/image", bundle)
            if variant != "baseline":
                shutil.copyfile(HERE / "figures" / variant / "diagram.png", bundle / variant / "assets/flowchart.png")
            row["variants"][variant] = dict(bundle=str(bundle.relative_to(HERE)), files=inventory(bundle), changed_skill=None if variant == "baseline" else variant)
        m["tasks"][task] = row
    write(HERE / "selection.json", selection)
    m["selection_sha256"] = sha(HERE / "selection.json")
    (HERE / "FIGURES.md").write_text("\n".join(index) + "\n")
    write(HERE / "manifest.json", m)
    check(require_frozen=freeze)
    print(json.dumps(dict(frozen=freeze, redraw=len(BODIES), skip=len(DECISIONS)-len(BODIES), planned_variants=sum(len(r["variants"]) for r in m["tasks"].values())), ensure_ascii=False))
    return m


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--check", action="store_true")
    p.add_argument("--freeze", action="store_true")
    args = p.parse_args()
    if args.check:
        m = check()
        print(json.dumps(dict(frozen=m["frozen"], figures=len(m["figures"]))))
    else:
        build(args.freeze)

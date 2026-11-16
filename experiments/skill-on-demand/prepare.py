"""Build new native-SKILL bundles from preserved sources; never edit old runs."""
import argparse
import base64
import json
from pathlib import Path
import re
import shutil

from protocol import METHOD, SkillDeliveryError, digest, policy_id, skill_body, validate_policy

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OLD = ROOT / "experiments/uml-expanded/full-skill-v2"
V3 = ROOT / "experiments/skill-structure-v3"
CRYSTAL = "crystallographic-wyckoff-position-analysis"
TASKS = (CRYSTAL, "llm-prefix-cache-replay", "energy-market-pricing", "r2r-mpc-control",
         "exam-block-sequencing", "manufacturing-fjsp-optimization")
FIGURES = ("uml-v1", "uml-v2", "structure-v3")


def inventory(root):
    root = Path(root)
    if any(p.is_symlink() for p in root.rglob("*")):
        raise SkillDeliveryError("symlinks not allowed in frozen bundles")
    return {str(p.relative_to(root)): digest(p.read_bytes()) for p in sorted(root.rglob("*")) if p.is_file()}


def source_for(task):
    if task == CRYSTAL:
        source = ROOT / "repos/skillsbench/tasks" / task / "environment/skills"
        # Crystal's original text bundle preserved every original SKILL byte as
        # GUIDE.md. Bind the restored native files to those historical copies.
        for name in ("pymatgen", "sympy"):
            saved = ROOT / "experiments/uml-flowchart/bundles/text" / name / "GUIDE.md"
            if (source / name / "SKILL.md").read_bytes() != saved.read_bytes():
                raise SkillDeliveryError("crystal source changed")
        return source
    source = OLD / "tasks" / task / "source"
    expected = json.loads((OLD / "manifest.json").read_text())["tasks"][task]["source_files"]
    if inventory(source) != expected:
        raise SkillDeliveryError("frozen skill source changed")
    return source


def figure_for(task, skill, figures):
    if task == CRYSTAL:
        if figures != "uml-v1":
            raise SkillDeliveryError("crystal only has the original UML materials")
        return ROOT / "experiments/uml-flowchart/bundles/image" / skill / "assets/flowchart.png"
    if figures == "structure-v3":
        candidate = V3 / "figures" / skill / "diagram.png"
        if candidate.exists():
            return candidate
        figures = "uml-v2"  # unchanged background figures, as in the v3 study
    base = ROOT / "experiments/uml-expanded" if figures == "uml-v1" else OLD
    return base / "tasks" / task / "previews" / (skill + ".png")


def build(task, arm, figures="uml-v1", *, output_root=None):
    if task not in TASKS or arm not in ("text", "image") or figures not in FIGURES:
        raise SkillDeliveryError("unsupported material selection")
    condition = "text" if arm == "text" else figures
    destination = (Path(output_root) if output_root else HERE / "materials") / task / condition
    source = source_for(task)
    skills = sorted(p.parent.name for p in source.glob("*/SKILL.md"))
    image_paths = {s: figure_for(task, s, figures) for s in skills} if arm == "image" else {}
    expected = inventory(source)
    figure_hashes = {s: digest(p.read_bytes()) for s, p in image_paths.items()}
    manifest = dict(method=METHOD, task=task, arm=arm, figures=figures if arm == "image" else None,
                    source_files=expected, figure_hashes=figure_hashes)
    bundle = destination / "skills"
    receipt = destination / "manifest.json"
    if receipt.exists():
        previous = json.loads(receipt.read_text())
        if any(previous.get(k) != v for k, v in manifest.items()) or previous["bundle_files"] != inventory(bundle):
            raise SkillDeliveryError("existing materials changed; use a new output directory")
        return bundle
    if destination.exists():
        raise SkillDeliveryError("incomplete output directory; refusing overwrite")
    destination.mkdir(parents=True)
    shutil.copytree(source, bundle)
    for name, image in image_paths.items():
        target = bundle / name / "assets/skillcanvas-diagram.png"
        if target.exists():
            raise SkillDeliveryError("source asset name collision")
        target.parent.mkdir(exist_ok=True)
        shutil.copyfile(image, target)
    manifest["bundle_files"] = inventory(bundle)
    for rel, sha in expected.items():
        if manifest["bundle_files"].get(rel) != sha:
            raise SkillDeliveryError("original source was modified")
    receipt.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    return bundle


def load_policy(bundle):
    bundle = Path(bundle).resolve()
    manifest_path = bundle.parent / "manifest.json"
    m = json.loads(manifest_path.read_text())
    if m["method"] != METHOD or m["bundle_files"] != inventory(bundle):
        raise SkillDeliveryError("bundle inventory mismatch")
    assets = []
    for p in sorted(bundle.glob("*/SKILL.md")):
        name = p.parent.name
        text = p.read_bytes().decode("utf-8")
        front_name = re.search(r"^name:\s*['\"]?([a-z0-9-]+)", text, re.M)
        if not front_name or front_name.group(1) != name or digest(p.read_bytes()) != m["source_files"][f"{name}/SKILL.md"]:
            raise SkillDeliveryError("native SKILL.md identity mismatch")
        item = dict(skill=name, skill_text=text, body=skill_body(text), skill_sha256=digest(p.read_bytes()))
        if m["arm"] == "image":
            raw = (p.parent / "assets/skillcanvas-diagram.png").read_bytes()
            if digest(raw) != m["figure_hashes"][name]:
                raise SkillDeliveryError("selected figure mismatch")
            item.update(image_data=base64.b64encode(raw).decode(), image_sha256=digest(raw))
        assets.append(item)
    policy = dict(method=METHOD, arm=m["arm"], task=m["task"], figures=m["figures"],
                  material_sha256=digest(manifest_path.read_bytes()), assets=assets,
                  adapter_sha256={p.name: digest(p.read_bytes()) for p in (HERE / "protocol.py", HERE / "runner.py")})
    policy["id"] = policy_id(policy)
    validate_policy(policy)
    return policy


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", choices=TASKS, required=True)
    parser.add_argument("--arm", choices=("text", "image"), required=True)
    parser.add_argument("--figures", choices=FIGURES, default="uml-v1")
    args = parser.parse_args()
    print(build(args.task, args.arm, args.figures))

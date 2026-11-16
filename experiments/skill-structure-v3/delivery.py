"""Select frozen skill-specific variants; reuse forced-prefix-v1 unchanged."""
import base64
import os
from pathlib import Path
import sys

from materials import HERE, ROOT, check, sha
LEGACY = ROOT / "experiments/uml-flowchart"
sys.path.insert(0, str(LEGACY))
sys.path.insert(0, str(ROOT / "experiments"))
import delivery_runner as legacy
from delivery_protocol import METHOD, SkillDeliveryError, digest, policy_id, validate_policy


def load_policy(arm, bundle):
    manifest = check()
    bundle = Path(bundle).resolve()
    matches = [(task, variant, row) for task, row in manifest["tasks"].items()
               for variant, v in row["variants"].items() if (HERE / v["bundle"]).resolve() == bundle]
    if arm != "image" or len(matches) != 1:
        raise SkillDeliveryError("unregistered frozen skill intervention")
    task, variant, row = matches[0]
    assets = []
    for skill in row["skills"]:
        guide = (bundle / skill / "GUIDE.md").read_bytes()
        png = (bundle / skill / "assets/flowchart.png").read_bytes()
        assets.append(dict(skill=skill, guide_text=guide.decode(), guide_sha256=digest(guide),
                           image_data=base64.b64encode(png).decode(), image_sha256=digest(png)))
    policy = dict(method=METHOD, arm="image", task=task, skill_names=row["skills"],
                  study_sha256=sha(HERE / "manifest.json"), assets=assets,
                  adapter_sha256={str(p.relative_to(ROOT)):sha(p) for p in
                      (Path(__file__), LEGACY/"delivery_runner.py", LEGACY/"delivery_protocol.py")})
    policy["id"] = policy_id(policy)
    validate_policy(policy)
    return policy


def main():
    from env_config import load_env
    import shared_opencode
    load_env(ROOT / ".env")
    os.environ.setdefault("DOCKER_CONFIG", str(ROOT / ".runtime/docker"))
    record = shared_opencode.load_record(check_image="--dry-run" not in sys.argv)
    shared_opencode.install_adapter(record)
    print("Shared OpenCode image: " + record["tag"], flush=True)
    legacy.load_policy = load_policy
    return legacy.main()


if __name__ == "__main__":
    raise SystemExit(main())

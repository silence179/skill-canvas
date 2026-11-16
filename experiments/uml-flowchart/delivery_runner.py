#!/usr/bin/env python3
"""Opt-in experiment adapter around the pinned BenchFlow proxy generator."""

import argparse
import base64
import json
import os
from pathlib import Path
import sys

from delivery_protocol import (
    METHOD, SKILLS, SkillDeliveryError, digest, is_helper,
    policy_id, prefix_content, public_policy, validate_delivery, validate_policy,
)
from prepare import HERE, verify


def load_policy(arm, bundle):
    study = bundle.resolve().parent.parent
    extra = {}
    if study == HERE:
        verify()
        skills = SKILLS
    else:
        expanded = HERE.parent / "uml-expanded"
        sys.path.insert(0, str(expanded))
        from study import verify_study
        manifest = verify_study(study)
        skills = tuple(manifest["skills"])
        extra = {"task": manifest["task"], "skill_names": list(skills),
                 "study_sha256": digest((study / "manifest.json").read_bytes())}
    if bundle.resolve() != (study / "bundles" / arm).resolve():
        raise SkillDeliveryError("bundle does not match the selected arm")
    assets = []
    for skill in skills:
        guide = (bundle / skill / "GUIDE.md").read_bytes()
        item = {"skill": skill, "guide_text": guide.decode(), "guide_sha256": digest(guide)}
        if arm == "image":
            raw = (bundle / skill / "assets/flowchart.png").read_bytes()
            item.update(image_data=base64.b64encode(raw).decode(), image_sha256=digest(raw))
        assets.append(item)
    policy = {"method": METHOD, "arm": arm, "assets": assets, **extra,
              "adapter_sha256": {
                  name: digest((HERE / name).read_bytes())
                  for name in ("delivery_runner.py", "delivery_protocol.py")
              }}
    policy["id"] = policy_id(policy)
    validate_policy(policy)
    return policy


def callback_source(original, policy):
    source = (HERE / "delivery_protocol.py").read_text()
    return (
        original + "\n\n" + source
        + "\n_skillcanvas_policy = " + repr(policy)
        + "\nattach_logger_hook(proxy_handler_instance, _skillcanvas_policy)\n"
    )


def install_adapter(policy):
    from benchflow.providers import litellm_logging, litellm_runtime

    original = litellm_logging.callback_module_source
    def generated():
        base = original()
        if "proxy_handler_instance = BenchFlowLiteLLMLogger()" not in base:
            raise SkillDeliveryError("unsupported BenchFlow callback version")
        result = callback_source(base, policy)
        compile(result, "<skillcanvas-proxy-callback>", "exec")
        return result

    litellm_logging.callback_module_source = generated
    litellm_runtime.callback_module_source = generated


def audit_rollout(root, policy):
    from benchflow.trajectories.types import redact_trajectory_obj

    result = {"schema": 1, "policy": public_policy(policy), "valid": False,
              "main_calls": 0, "helper_calls": 0, "redacted_guide_calls": 0,
              "audit_sha256": digest(Path(__file__).read_bytes()), "errors": []}
    trace = root / "trajectory/llm_trajectory.jsonl"
    try:
        for line_number, line in enumerate(trace.read_text().splitlines(), 1):
            row = json.loads(line)
            body = row.get("request", {}).get("body", {})
            if is_helper(body):
                result["helper_calls"] += 1
                continue
            try:
                validate_delivery(body, policy)
            except SkillDeliveryError:
                # The live gateway still checks exact raw bytes. Published
                # traces mask even public API-key placeholders inside GUIDE.
                # Match the exact native redacted representation, never strip
                # arbitrary text or relax the image/order checks.
                first_user = next((x for x in body.get("messages", [])
                                   if x.get("role") == "user"), {})
                if first_user.get("content") != redact_trajectory_obj(prefix_content(policy)):
                    raise
                result["redacted_guide_calls"] += 1
            status = row.get("response", {}).get("status_code")
            if status != 200:
                raise SkillDeliveryError(f"provider rejected main call at line {line_number}")
            result["main_calls"] += 1
        native = json.loads((root / "result.json").read_text())
        if not result["main_calls"]:
            raise SkillDeliveryError("no captured agent model requests")
        if native.get("error") or native.get("partial_trajectory"):
            raise SkillDeliveryError("run failed or trajectory is partial")
        # Bind coverage to the controller's observed agent-call count when
        # available. Never treat a shorter capture as a complete valid arm.
        expected = native.get("settings_sent", {}).get("main_calls")
        if expected is not None and expected != result["main_calls"]:
            raise SkillDeliveryError("model request capture is incomplete")
        result["valid"] = True
    except (OSError, ValueError, TypeError, KeyError, SkillDeliveryError) as error:
        result["errors"].append(str(error))
    result["trace_sha256"] = digest(trace.read_bytes()) if trace.exists() else None
    (root / "skill-delivery.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arm", choices=("text", "image"), required=True)
    parser.add_argument("--bundle", type=Path, required=True)
    args, bench_args = parser.parse_known_args()
    if bench_args[:1] == ["--"]:
        bench_args = bench_args[1:]
    policy = load_policy(args.arm, args.bundle)
    if "task" in policy:
        selected = [bench_args[i + 1] for i, value in enumerate(bench_args[:-1]) if value in {"-i", "--include"}]
        if selected != [policy["task"]]:
            parser.error("delivery bundle must match exactly one selected task")
    jobs = Path(bench_args[bench_args.index("--jobs-dir") + 1])
    dry = "--dry-run" in bench_args
    before = {p.parent for p in jobs.glob("*/*/config.json")}
    if not dry:
        marker = jobs / "skill-delivery-policy.json"
        identity = public_policy(policy)
        if marker.exists():
            if json.loads(marker.read_text()) != identity:
                parser.error("delivery policy changed; use a new --jobs-dir")
        elif jobs.exists() and any(jobs.iterdir()):
            parser.error("existing results have no delivery policy; use a new --jobs-dir")
        jobs.mkdir(parents=True, exist_ok=True)
        marker.write_text(json.dumps(identity, indent=2) + "\n")
    print(f"Skill delivery: {METHOD}, arm={args.arm}, policy={policy['id'][:12]}", flush=True)
    install_adapter(policy)
    # A daemon started without this adapter cannot inherit the generated hook.
    os.environ.pop("BENCHFLOW_DAEMON", None)
    from benchflow.cli.main import main as bench_main
    sys.argv = ["bench", *bench_args]
    code = 0
    try:
        bench_main()
    except SystemExit as error:
        code = error.code if isinstance(error.code, int) else 1
    if not dry:
        after = {p.parent for p in jobs.glob("*/*/config.json")}
        current = sorted(after - before)
        if not current and after:
            # An unchanged command can resume an already completed job.
            latest_job = max(p.parent for p in after)
            current = sorted(p for p in after if p.parent == latest_job)
        audits = [audit_rollout(path, policy) for path in current]
        valid = bool(audits) and all(x["valid"] for x in audits)
        print(f"Skill delivery audit: {'VALID' if valid else 'INVALID'} ({len(audits)} trial(s))", flush=True)
        if not valid:
            print("Exclude this run from the image/text comparison; see skill-delivery.json.", flush=True)
            code = code or 2
    return code


if __name__ == "__main__":
    raise SystemExit(main())

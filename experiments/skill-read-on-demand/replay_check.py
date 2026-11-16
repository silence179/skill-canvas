"""Offline counterfactual delivery check using saved requests, never a model run."""
import argparse
import json
import os
from pathlib import Path

os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")

from prepare import HERE, ROOT, build, load_policy
from protocol import digest, is_helper, project, validate_delivery


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign", type=Path, required=True)
    args = parser.parse_args()
    directory = args.campaign.resolve()
    original = json.loads((directory / "analysis.json").read_text())
    from benchflow.trajectories.types import redact_trajectory_obj
    rows = []
    for run in original["runs"]:
        m = run["metrics"]
        trial = ROOT / m["trial"]
        for name, sha in m["evidence_sha256"].items():
            assert digest((trial / name).read_bytes()) == sha
        image_policy = load_policy(build(m["task"], "image", "uml-v1"))
        text_policy = load_policy(build(m["task"], "text", "uml-v1"))
        events = [json.loads(line) for line in (trial / "trajectory/llm_trajectory.jsonl").read_text().splitlines()]
        unique_reads, first_image, main_calls = {}, None, 0
        for line_number, event in enumerate(events, 1):
            data = event["request"]["body"]
            if is_helper(data):
                continue
            main_calls += 1
            # Stored logs can redact public API placeholders. Live matching uses
            # the exact original source; only this offline replay transforms it.
            messages, loads = project(data, image_policy, body_transform=redact_trajectory_obj)
            simulated = dict(data, messages=messages)
            validate_delivery(simulated, image_policy, body_transform=redact_trajectory_obj)
            control, control_loads = project(data, text_policy, body_transform=redact_trajectory_obj)
            assert control == data["messages"]
            assert {(l["call_id"], l["skill"]) for l in loads} == {(l["call_id"], l["skill"]) for l in control_loads}
            assert [msg for msg in messages if msg.get("role") in ("tool", "assistant", "system")] == [
                msg for msg in data["messages"] if msg.get("role") in ("tool", "assistant", "system")]
            if main_calls == 1:
                assert messages == data["messages"] and not loads
            for load in loads:
                key = (load["call_id"], load["skill"])
                unique_reads.setdefault(key, dict(load, first_captured_request=line_number))
                if load["image_attached"] and first_image is None:
                    first_image = line_number
        for name, sha in m["evidence_sha256"].items():
            assert digest((trial / name).read_bytes()) == sha
        rows.append(dict(task=m["task"], original_arm=m["arm"], original_images_delivered=run["any_image_delivered"],
                         main_calls=main_calls, recognized_read_events=list(unique_reads.values()),
                         recognized_skills=sorted({l["skill"] for l in unique_reads.values()}),
                         would_deliver_image=first_image is not None, first_image_request=first_image,
                         trace_sha256=digest((trial / "trajectory/llm_trajectory.jsonl").read_bytes())))
    report = dict(valid=True, scope="Offline reconstruction only. No requests sent, no agent actions or scores regenerated.",
                  paid_model_calls=0, original_campaign=str(directory), rows=rows,
                  code_sha256={p.name: digest(p.read_bytes()) for p in (HERE / "protocol.py", HERE / "prepare.py", HERE / "runner.py", Path(__file__))})
    (HERE / "replay-check.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(dict(valid=True, paid_model_calls=0, rows=[dict(task=r["task"], original_arm=r["original_arm"],
        recognized_skills=r["recognized_skills"], would_deliver_image=r["would_deliver_image"]) for r in rows]), ensure_ascii=False))


if __name__ == "__main__":
    main()

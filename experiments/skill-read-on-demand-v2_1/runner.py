"""Read-triggered entry point. All historical experiment runners stay frozen."""
import argparse
import json
import os
from pathlib import Path
import sys

from prepare import HERE, ROOT, CRYSTAL, TASKS, FIGURES, build, load_policy
from protocol import METHOD, SkillDeliveryError, digest, is_helper, public_policy, validate_delivery


def callback_source(original, policy):
    return (original + "\n\n" + (HERE / "protocol.py").read_text()
            + "\n_skillcanvas_on_demand_policy = " + repr(policy)
            + "\nattach_logger_hook(proxy_handler_instance, _skillcanvas_on_demand_policy)\n")


def install_adapter(policy):
    from benchflow.providers import litellm_logging, litellm_runtime
    original = litellm_logging.callback_module_source

    def generated():
        base = original()
        if "proxy_handler_instance = BenchFlowLiteLLMLogger()" not in base:
            raise SkillDeliveryError("unsupported BenchFlow proxy callback")
        result = callback_source(base, policy)
        compile(result, "<skillcanvas-on-demand-callback>", "exec")
        return result

    litellm_logging.callback_module_source = generated
    litellm_runtime.callback_module_source = generated


def audit_rollout(trial, policy):
    from benchflow.trajectories.types import redact_trajectory_obj
    trial = Path(trial)
    trace = trial / "trajectory/llm_trajectory.jsonl"
    report = dict(method=METHOD, policy=public_policy(policy), valid=False,
                  delivery_valid=False, run_complete=False, main_calls=0, helper_calls=0,
                  activated_skills=[], activations=[], no_activation=True, errors=[])
    activations = {}
    try:
        for line_number, line in enumerate(trace.read_text().splitlines(), 1):
            record = json.loads(line)
            data = record["request"]["body"]
            if is_helper(data):
                report["helper_calls"] += 1
                continue
            try:
                loads = validate_delivery(data, policy)
            except SkillDeliveryError:
                # Native log redaction may mask API placeholders in a public
                # SKILL body. Live requests still check raw exact source text.
                loads = validate_delivery(data, policy, body_transform=redact_trajectory_obj)
            report["main_calls"] += 1
            for load in loads:
                activations.setdefault((load["call_id"], load["skill"]), dict(load,
                    first_captured_request=line_number, image_expected=policy["arm"] == "image"))
            if record.get("response", {}).get("status_code") != 200:
                raise SkillDeliveryError(f"provider request failed at trace line {line_number}")
        if not report["main_calls"]:
            raise SkillDeliveryError("no captured main requests")
        native = json.loads((trial / "result.json").read_text())
        expected = native.get("settings_sent", {}).get("main_calls")
        if expected is not None and expected != report["main_calls"]:
            raise SkillDeliveryError("request capture incomplete")
        report["delivery_valid"] = True
        report["run_complete"] = not native.get("error") and not native.get("partial_trajectory")
        report["valid"] = report["run_complete"]
    except (OSError, ValueError, KeyError, TypeError, SkillDeliveryError) as e:
        report["errors"].append(str(e))
    report["activations"] = list(activations.values())
    report["activated_skills"] = sorted({x["skill"] for x in activations.values()})
    report["no_activation"] = not bool(activations)
    report["trace_sha256"] = digest(trace.read_bytes()) if trace.exists() else None
    (trial / "skill-delivery.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", choices=TASKS, required=True)
    parser.add_argument("--arm", choices=("text", "image"), required=True)
    parser.add_argument("--figures", choices=FIGURES, default="uml-v1")
    parser.add_argument("--model")
    parser.add_argument("--effort")
    parser.add_argument("--tasks-root", type=Path)
    parser.add_argument("--jobs-dir", type=Path)
    parser.add_argument("--trials", type=int, default=1)
    parser.add_argument("--concurrency", type=int, default=1)
    parser.add_argument("--dry-run", action="store_true", help="offline plan only; no Docker, model or grader")
    args = parser.parse_args()
    if args.trials < 1 or args.concurrency < 1:
        parser.error("trials and concurrency must be positive")
    sys.path.insert(0, str(ROOT / "experiments"))
    from env_config import load_env
    load_env(ROOT / ".env")
    bundle = build(args.task, args.arm, args.figures)
    policy = load_policy(bundle)
    condition = "text" if args.arm == "text" else args.figures
    jobs = (args.jobs_dir or ROOT / "jobs/skill-read-on-demand-v2.1" / args.task / condition).resolve()
    tasks = (args.tasks_root or (ROOT / "repos/skillsbench/tasks" if args.task == CRYSTAL
                                else ROOT / ".runtime/uml-expanded/prepared-tasks")).resolve()
    model = args.model or os.environ.get("EXP_MODEL")
    if not model:
        parser.error("set --model or EXP_MODEL")
    effort = args.effort or os.environ.get("EXP_EFFORT")
    bench_args = ["run", str(tasks), "-i", args.task, "--agent", "opencode", "--sandbox", "docker",
                  "--model", model, "--skill-mode", "with-skill", "--skills-dir", str(bundle),
                  "--trials", str(args.trials), "--concurrency", str(args.concurrency),
                  "--retry-attempts", "0", "--save-outputs", "--jobs-dir", str(jobs)]
    if effort:
        bench_args += ["--reasoning-effort", effort]
    if args.dry_run:
        print(json.dumps(dict(method=METHOD, offline_plan=True, policy=public_policy(policy),
                              bench_arguments=bench_args, starts_experiment=False), ensure_ascii=False, indent=2))
        return 0
    if jobs.exists() and any(jobs.iterdir()):
        parser.error("use a new empty jobs directory; historical jobs cannot be resumed with this protocol")
    if not (tasks / args.task).is_dir():
        parser.error("task environment not found")
    import shared_opencode
    record = shared_opencode.load_record()
    shared_opencode.install_adapter(record)
    install_adapter(policy)
    os.environ.pop("BENCHFLOW_DAEMON", None)
    os.environ.setdefault("DOCKER_CONFIG", str(ROOT / ".runtime/docker"))
    jobs.mkdir(parents=True, exist_ok=True)
    (jobs / "skill-delivery-policy.json").write_text(json.dumps(public_policy(policy), indent=2) + "\n")
    from benchflow.cli.main import main as bench_main
    sys.argv = ["bench", *bench_args]
    code = 0
    try:
        bench_main()
    except SystemExit as e:
        code = e.code if isinstance(e.code, int) else 1
    trials = sorted(p.parent for p in jobs.glob("*/*/config.json"))
    audits = [audit_rollout(p, policy) for p in trials]
    print(json.dumps(dict(method=METHOD, trial_count=len(audits),
                          activated_skills=[a["activated_skills"] for a in audits],
                          delivery_valid=bool(audits) and all(a["delivery_valid"] for a in audits))))
    # No activation is a valid behavioral outcome, retained in comparison.
    return code or (0 if audits and all(a["valid"] for a in audits) else 2)


if __name__ == "__main__":
    raise SystemExit(main())

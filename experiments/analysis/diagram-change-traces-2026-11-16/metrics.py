"""Derive comparisons from archived files. No model, grader, or simulator runs."""
import hashlib
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]


def read(p):
    return json.loads(p.read_text())


def main():
    evidence = read(OUT / "evidence.json")
    complete = [r for r in evidence if r["row"]["status"] == "finished"]
    lookup = {r["key"]: r for r in complete}
    old = read(ROOT / "experiments/uml-expanded/full-skill-v2/manifest.json")
    new = read(ROOT / "experiments/skill-structure-v3/manifest.json")
    comparisons = []
    for key in (
        "llm-prefix-cache-replay__prefix-cache-replay", "energy-market-pricing__dc-power-flow",
        "energy-market-pricing__economic-dispatch", "energy-market-pricing__locational-marginal-prices",
        "r2r-mpc-control__finite-horizon-lqr", "r2r-mpc-control__combined",
    ):
        r = lookup[key]
        b = lookup[r["row"]["task"] + "__baseline"]
        item = dict(key=key, new=r["row"], baseline=b["row"], trace_new=r["extract"], trace_baseline=b["extract"])
        item["changes_pct"] = {k: 100 * (r["row"][k] / b["row"][k] - 1) for k in (
            "total_tokens", "input_tokens", "output_tokens", "estimated_cost_usd", "agent_seconds", "main_calls", "tool_calls")}
        maincalls = lambda e: [c for c in e["calls"] if c["purpose"] == "agent" and c["usage"]]
        for label, run in (("baseline", b), ("new", r)):
            calls = maincalls(run)
            first = calls[0]["usage"]["prompt_tokens"]
            item[label + "_context"] = dict(calls=len(calls), first=first,
                last=calls[-1]["usage"]["prompt_tokens"],
                average=sum(c["usage"]["prompt_tokens"] for c in calls) / len(calls),
                first_input_repeated_component=len(calls) * first,
                context_growth_component=sum(c["usage"]["prompt_tokens"] - first for c in calls),
                raw_input_tokens=sum(c["usage"]["prompt_tokens"] for c in calls))
        comparisons.append(item)
    image_stats = {}
    for skill, data in new["figures"].items():
        a = next(v["skills"][skill]["png_dimensions"] for v in old["tasks"].values() if skill in v["skills"])
        b = data["dimensions"]
        image_stats[skill] = dict(old=a, new=b, area_ratio=b[0] * b[1] / (a[0] * a[1]))
    energy = {}
    reports = {}
    bindings = {}
    for r in complete:
        for rel, expected in r["row"]["evidence_sha256"].items():
            p = ROOT / r["row"]["trial"] / rel
            assert hashlib.sha256(p.read_bytes()).hexdigest() == expected, str(p)
        if r["row"]["task"] != "energy-market-pricing":
            continue
        p = ROOT / r["row"]["trial"] / "evidence/workspace/report.json"
        reports[r["row"]["variant"]] = read(p)
        bindings[str(p.relative_to(ROOT))] = hashlib.sha256(p.read_bytes()).hexdigest()
    for variant, d in reports.items():
        energy[variant] = {}
        for case in ("base_case", "counterfactual"):
            a = {e["bus"]: e["lmp_dollars_per_MWh"] for e in reports["baseline"][case]["lmp_by_bus"]}
            b = {e["bus"]: e["lmp_dollars_per_MWh"] for e in d[case]["lmp_by_bus"]}
            energy[variant][case] = dict(cost=d[case]["total_cost_dollars_per_hour"],
                buses=len(a), sign_disagreements_vs_baseline=sum(a[i] * b[i] < 0 for i in a),
                differences_gt_005=sum(abs(a[i]-b[i]) > .05 for i in a),
                maximum_difference=max(abs(a[i]-b[i]) for i in a),
                examples={str(i): dict(baseline=a[i], new=b[i]) for i in (1, 9, 64, 629, 1266, 1501, 1709)})
    network_path = ROOT / lookup["energy-market-pricing__baseline"]["row"]["trial"] / "evidence/workspace/network.json"
    generator_buses = {int(g[0]) for g in read(network_path)["gen"]}
    for variant, cases in energy.items():
        for case, stats in cases.items():
            a = {e["bus"]: e["lmp_dollars_per_MWh"] for e in reports["baseline"][case]["lmp_by_bus"]}
            b = {e["bus"]: e["lmp_dollars_per_MWh"] for e in reports[variant][case]["lmp_by_bus"]}
            disagreements = {i for i in a if a[i] * b[i] < 0}
            stats["sign_disagreement_set_equals_generator_bus_set"] = disagreements == generator_buses
            stats["disagreements_exact_negations"] = bool(disagreements) and all(a[i] == -b[i] for i in disagreements)
    bindings[str(network_path.relative_to(ROOT))] = hashlib.sha256(network_path.read_bytes()).hexdigest()
    controls = {}
    for r in complete:
        if r["row"]["task"] != "r2r-mpc-control":
            continue
        base = ROOT / r["row"]["trial"] / "evidence/workspace"
        log = read(base / "control_log.json")["data"]
        cfg = read(base / "system_config.json")
        segment = [e for e in log if e["time"] <= 5 + 1e-6]
        tail = [e for e in segment if e["time"] >= 4 - 1e-7]
        ref = cfg["T_ref_final"]
        mae = sum(abs(e["tensions"][i] - ref[i]) for e in tail for i in range(6)) / (len(tail) * 6)

        def settle(tolerances):
            bad = [e["time"] for e in segment if e["time"] >= cfg["step_time"] - 1e-7
                   and any(abs(e["tensions"][i] - ref[i]) > tolerances[i] for i in range(6))]
            if bad and bad[-1] >= segment[-1]["time"] - 1e-7:
                return None
            return next(e["time"] - cfg["step_time"] for e in segment
                        if e["time"] > max(bad, default=cfg["step_time"] - 1e-6) + 1e-7)

        controls[r["row"].get("variant", r["row"]["arm"])] = dict(original_reported_metrics=read(base / "metrics.json"),
            original_duration=log[-1]["time"], common_duration=5,
            samples_in_4_to_5=len(tail), mean_absolute_error_4_to_5=mae,
            settling_2N_within_first_5s=settle([2] * 6),
            settling_2pct_within_first_5s=settle([max(.1, .02 * x) for x in ref]),
            max_tension_first_5s=max(v for e in segment for v in e["tensions"]),
            min_tension_first_5s=min(v for e in segment for v in e["tensions"]))
        for name in ("control_log.json", "system_config.json", "metrics.json"):
            p = base / name
            bindings[str(p.relative_to(ROOT))] = hashlib.sha256(p.read_bytes()).hexdigest()
    r2r_base = ROOT / lookup["r2r-mpc-control__baseline"]["row"]["trial"] / "evidence/workspace/controller_params.json"
    r2r_lqr = ROOT / lookup["r2r-mpc-control__finite-horizon-lqr"]["row"]["trial"] / "evidence/workspace/controller_params.json"
    result = dict(completed_runs=len(complete), completed_comparisons=len(comparisons),
                  comparisons=comparisons, image_stats=image_stats, energy_output_comparison=energy,
                  r2r_common_window=controls, r2r_baseline_lqr_controller_params_exactly_equal=read(r2r_base) == read(r2r_lqr),
                  additional_source_hashes=bindings,
                  scope="Offline analysis of archived evidence only. No new benchmark, model, solver, or simulator execution.",
                  limitations=["one observation per variant; shared controls", "different layout and emphasis along with diagram type", "no direct measurement of image attention", "partial exam and unlaunched manufacturing excluded from quality comparisons", "common-window R2R metrics compare stored traces, not independent controller robustness trials", "LMP disagreement is not by itself proof; recorded finite-difference checks support the sampled sign errors"])
    (OUT / "comparison.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    lines = ["# 已完成的新旧图对比", "", "旧→新。同轮共享旧图对照，每变体仅一次。token 包含缓存输入；费用为框架估算。", "",
             "|skill／组合|原生分数|总 token|变化|Agent 秒|主请求|工具调用|估算费用变化|",
             "|---|---|---|---:|---|---|---|---:|"]
    for x in comparisons:
        a, b = x["baseline"], x["new"]
        label = "LQR + integral-action-design" if x["key"].endswith("__combined") else b["variant"]
        lines.append(f"|{label}|{a['reward']:g}→{b['reward']:g}|{a['total_tokens']:,}→{b['total_tokens']:,}|{x['changes_pct']['total_tokens']:+.1f}%|{a['agent_seconds']:.1f}→{b['agent_seconds']:.1f}|{a['main_calls']}→{b['main_calls']}|{a['tool_calls']}→{b['tool_calls']}|{x['changes_pct']['estimated_cost_usd']:+.1f}%|")
    lines += ["", "共有 9 个完成的唯一运行，形成 6 个对比；控制不重复计入运行总数。考试运行已中断、没有原生结果，制造运行未启动，均不作为失败。", "", "## 输入与时间", "",
              "|skill／组合|首次主请求输入 token|平均每次主请求输入 token|最后主请求输入 token|服务商等待秒|其余 Agent 秒|",
              "|---|---|---|---|---|---|"]
    for x in comparisons:
        a, b = x["baseline"], x["new"]
        ca, cb = x["baseline_context"], x["new_context"]
        lines.append(f"|{b.get('variant', 'combined')}|{ca['first']:,}→{cb['first']:,}|{ca['average']:,.0f}→{cb['average']:,.0f}|{ca['last']:,}→{cb['last']:,}|{a['timing']['provider_wait']}→{b['timing']['provider_wait']}|{a['timing']['agent_without_provider_wait']}→{b['timing']['agent_without_provider_wait']}|")
    lines += ["", "其余 Agent 秒包括工具执行与编排，不等同于模型思考时间。主请求输入含全文、所有图和历史；服务商未单列可用图像 token。", "", "## R2R 保存日志统一口径", "", "只重算已有数据：共同区间 0–5 秒；误差取 4–5 秒各节张力平均绝对误差；稳定时间从阶跃 0.5 秒起算，要求此后至 5 秒所有节持续进入所列误差带。观察窗有限。", "", "|运行|4–5 秒误差 N|2N 带稳定秒|2% 带稳定秒|前 5 秒最高张力 N|", "|---|---:|---:|---:|---:|"]
    for name, x in controls.items():
        lines.append(f"|{name}|{x['mean_absolute_error_4_to_5']:.4f}|{x['settling_2N_within_first_5s']:.2f}|{x['settling_2pct_within_first_5s']:.2f}|{x['max_tension_first_5s']:.4f}|")
    (OUT / "COMPARISON.md").write_text("\n".join(lines) + "\n")
    print(json.dumps(dict(completed_runs=len(complete), comparisons=len(comparisons), evidence_hash_checks="passed")))


if __name__ == "__main__":
    main()

"""Read-only reanalysis of frozen SkillCanvas pilots; no model/API calls.

Run: python3 experiments/analysis/skill-structure-2026-11-15/analyze.py
Counts are task-level. Skill annotations are source-reviewed hypotheses, not
independent skill treatment effects. Historical campaigns are never overwritten.
"""
from pathlib import Path
import hashlib
import json
import os
import re
import statistics
import tempfile
import xml.etree.ElementTree as ET

os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "skillcanvas-analysis-mpl"))
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
V1 = ROOT / "experiments/uml-expanded/results/paired-five-v1-recovery.json"
V2 = ROOT / "jobs/uml-expanded/paired-five-full-skill-v2/comparison.json"
CRYSTAL = ROOT / "experiments/uml-flowchart/results/2026-11-14-forced-v1-180854-185918.json"
FULL = ROOT / "experiments/uml-expanded/full-skill-v2"
LABELS = {
    "llm-prefix-cache-replay": ("前缀缓存", "Cache", "状态迁移／策略比较"),
    "energy-market-pricing": ("电价分析", "Energy", "数据契约／网络约束／数值优化"),
    "r2r-mpc-control": ("R2R 控制", "R2R", "数学递推／反馈控制／参数权衡"),
    "exam-block-sequencing": ("考试排程", "Exam", "有序窗口约束／求解交付"),
    "manufacturing-fjsp-optimization": ("制造排程", "Manufacturing", "时序资源约束／局部修复"),
    "crystallographic-wyckoff-position-analysis": ("晶体分析", "Crystal", "大型 API 参考／任务入口"),
}
# These annotations are deliberately explicit, rather than inferred from scores.
# A future extractor must emit source spans before applying the same route rules.
ANNOTATIONS = {
    "prefix-cache-replay": ("state_transition", "state_machine", "event_sequence", "S/M/G 迁移、频率保留、先计命中后更新"),
    "cache-policy-comparison": ("decision", "decision_table", "state_machine", "LRU/LFU/FIFO/S3FIFO 的命中、插入、淘汰与 tie-break"),
    "power-flow-data": ("data_contract", "schema_map", "mapping_table", "bus/gen/branch 字段、非连续 ID 映射、MW/per-unit 单位"),
    "dc-power-flow": ("data_contract", "dataflow", "equation_card", "数据到 B 矩阵和线路潮流，脚本函数输入／返回值"),
    "economic-dispatch": ("mathematical_dependency", "constraint_graph", "equation_card", "Pg/Rg/theta、成本、供需、备用、容量与求解状态"),
    "locational-marginal-prices": ("mathematical_dependency", "dataflow", "unit_contract", "约束方向和单位到 dual／价格，再到反事实差分"),
    "state-space-linearization": ("mathematical_dependency", "equation_dependency", "equation_card", "非线性动力学到 Jacobian，再到离散 A/B；适用条件"),
    "finite-horizon-lqr": ("mathematical_dependency", "indexed_recurrence", "feedback_block", "P[k+1] 到 K[k]/P[k] 的逆序递推与只执行首动作"),
    "mpc-horizon-tuning": ("decision", "tradeoff_table", "validation_cycle", "N/Q/R 的权衡与独立试验后的调参"),
    "integral-action-design": ("feedback", "feedback_block", "validation_cycle", "误差、dt 积分、泄漏、限幅与控制输入的连接"),
    "mip-solver-and-solution-audit": ("audit", "artifact_gate", "activity", "solver incumbent 到落盘、重读、独立复算和证书"),
    "ordered-window-sequencing-mip": ("temporal_constraint", "window_timeline", "constraint_graph", "有序 tuple、起点 mask、后继和 active overlap"),
    "fjsp-baseline-repair-with-downtime-and-policy": ("temporal_constraint", "resource_timeline", "invariant_checklist", "停机窗口、前序、半开区间、逐整数最早可行与 MC/L1"),
}


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(name, data):
    (OUT / name).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def change(a, b):
    return 100 * (b / a - 1)


def link(path):
    return f"[{path.name}]({path.resolve()})"


def main():
    v1, v2, crystal = map(read, (V1, V2, CRYSTAL))
    pairs, rows, checks = [], [], []
    for version, ps in [("v1", v1["pairs"]), ("v2", v2["pairs"])]:
        for p in ps:
            task = p["task"]
            arms = ({a: p[a] for a in ("text", "image")} if version == "v1" else
                    {r["arm"]: r for r in v2["rows"] if r["task"] == task})
            admitted = p.get("paired_metrics_admitted", p.get("admitted"))
            pair = dict(version=version, task=task, structure=LABELS[task][2],
                        admitted=admitted, both_pass=all(r["reward"] == 1 for r in arms.values()))
            for arm, r in arms.items():
                row = dict(version=version, **r)
                row["uncached_input_tokens"] = r["input_tokens"] - r["cached_tokens"]
                rows.append(row)
                pair[arm] = {k: r.get(k) for k in ("trial", "reward", "total_tokens", "tool_calls", "main_calls", "agent_seconds", "estimated_cost_usd", "test_summary")}
                root = ROOT / r["trial"]
                raw = read(root / "result.json")
                assert raw["rewards"]["reward"] == r["reward"], root
                assert r["total_tokens"] == r["input_tokens"] + r["output_tokens"], root
                for file, expected in r["evidence_sha256"].items():
                    ok = sha(root / file) == expected
                    checks.append(dict(path=str((root / file).relative_to(ROOT)), sha256=expected, matches=ok))
                    assert ok, root / file
            for k in ("total_tokens", "tool_calls", "main_calls", "agent_seconds", "estimated_cost_usd"):
                pair[k + "_change_pct"] = change(arms["text"][k], arms["image"][k])
            pairs.append(pair)
    cp = dict(version="crystal-v1", task=crystal["task"], structure=LABELS[crystal["task"]][2], admitted=True, both_pass=True)
    for arm, r in crystal["runs"].items():
        cp[arm] = dict(trial=str(Path(r["root"]).relative_to(ROOT)), reward=r["reward"], total_tokens=r["total_tokens"], tool_calls=r["tools"], main_calls=r["main_calls"], agent_seconds=r["agent_execution_sec"], estimated_cost_usd=r["estimated_cost_usd"])
        for file, expected in r["evidence_sha256"].items():
            ok = sha(Path(r["root"]) / file) == expected
            checks.append(dict(path=str((Path(r["root"]) / file).relative_to(ROOT)), sha256=expected, matches=ok))
            assert ok, file
    for k in ("total_tokens", "tool_calls", "main_calls", "agent_seconds", "estimated_cost_usd"):
        cp[k + "_change_pct"] = change(cp["text"][k], cp["image"][k])
    pairs.append(cp)
    assert len({p[a]["trial"] for p in pairs for a in ("text", "image")}) == 22

    aggregates = {}
    for version in ("v1", "v2", "crystal-v1"):
        ps = [p for p in pairs if p["version"] == version]
        a = {"tasks": len(ps), "admitted_pairs": sum(p["admitted"] for p in ps)}
        for subset, selected in (("all_recorded", ps), ("complete", [p for p in ps if p["admitted"]]), ("both_pass_complete", [p for p in ps if p["admitted"] and p["both_pass"]])):
            totals = {arm: {k: sum(p[arm][k] for p in selected) for k in ("total_tokens", "tool_calls", "agent_seconds", "estimated_cost_usd")} for arm in ("text", "image")}
            a[subset] = dict(n=len(selected), totals=totals,
                            token_change_pct=change(totals["text"]["total_tokens"], totals["image"]["total_tokens"]),
                            median_task_token_change_pct=statistics.median(p["total_tokens_change_pct"] for p in selected))
        a["passes"] = {arm: sum(p[arm]["reward"] == 1 for p in ps) for arm in ("text", "image")}
        aggregates[version] = a
    drift = []
    for p in [x for x in pairs if x["version"] == "v1"]:
        q = next(x for x in pairs if x["version"] == "v2" and x["task"] == p["task"])
        drift.append(dict(task=p["task"], text_token_change_pct=change(p["text"]["total_tokens"], q["text"]["total_tokens"]),
                          text_reward_v1=p["text"]["reward"], text_reward_v2=q["text"]["reward"],
                          image_effect_sign_flip=(p["total_tokens_change_pct"] * q["total_tokens_change_pct"] < 0)
                          if p["admitted"] and q["admitted"] else None))

    inventory = []
    manifest = read(FULL / "manifest.json")
    for task, entry in manifest["tasks"].items():
        for skill, info in entry["skills"].items():
            stem = FULL / "tasks" / task
            guide = stem / "source" / skill / "SKILL.md"
            uml = stem / "diagrams" / f"{skill}.puml"
            png = stem / "previews" / f"{skill}.png"
            svg = stem / "previews" / f"{skill}.svg"
            text = uml.read_text()
            stype, primary, secondary, rationale = ANNOTATIONS[skill]
            with Image.open(png) as im:
                width, height = im.size
            assert [width, height] == info["png_dimensions"]
            for path in (uml, png, svg):
                assert sha(path) == info["artifacts"][str(path.relative_to(stem))]
            # SVG text is a reproducible density proxy; it is NOT semantic coverage.
            labels = ["".join(e.itertext()) for e in ET.parse(svg).iter() if e.tag.rsplit("}", 1)[-1] == "text"]
            inventory.append(dict(task=task, skill=skill, structure=stype,
                                  source_bytes=guide.stat().st_size, source_lines=len(guide.read_text().splitlines()),
                                  png_width=width, png_height=height, png_megapixels=width*height/1e6,
                                  aspect_ratio_height_width=height/width,
                                  activity_statements=len(re.findall(r"^\s*:", text, re.M)),
                                  conditional_statements=len(re.findall(r"^\s*(?:if|elseif)\s*\(", text, re.M)),
                                  loop_statements=len(re.findall(r"^\s*(?:while\s*\(|repeat\s*$)", text, re.M)),
                                  svg_text_elements=len(labels), svg_label_characters=sum(map(len, labels)),
                                  primary_candidate=primary, secondary_candidate=secondary, rationale=rationale,
                                  annotation_method="manual source-structure review; not outcome-trained",
                                  source=str(guide.relative_to(ROOT)), diagram=str(uml.relative_to(ROOT)),
                                  source_sha256=sha(guide), diagram_sha256=sha(uml)))

    r2r = []
    for r in rows:
        if r["version"] != "v2" or r["task"] != "r2r-mpc-control":
            continue
        workspace = ROOT / r["trial"] / "evidence/workspace"
        config = read(workspace / "system_config.json")
        data = read(workspace / "control_log.json")["data"]
        ts = np.array([d["time"] for d in data])
        tensions = np.array([d["tensions"] for d in data])
        refs = np.array([config["T_ref_initial"] if t < config["step_time"] else config["T_ref_final"] for t in ts])
        threshold = .05 * abs(config["T_ref_final"][2] - config["T_ref_initial"][2])
        outside = np.flatnonzero(np.abs(tensions[:, 2] - refs[:, 2]) > threshold)
        settling = float(ts[min(outside[-1]+1, len(ts)-1)]-ts[0]) if len(outside) else 0.
        params = read(workspace / "controller_params.json")
        r2r.append(dict(arm=r["arm"], reported=read(workspace / "metrics.json"),
                        recomputed_settling_seconds=settling, reference_band_N=threshold,
                        horizon=params["horizon_N"], Q_velocity=params["Q_diag"][6], R=params["R_diag"][0],
                        log=str((workspace / "control_log.json").relative_to(ROOT)),
                        note="Replicates archived evaluator definition from visible failure output, not a new controller run."))
    assert abs(next(x for x in r2r if x["arm"] == "image")["recomputed_settling_seconds"] - 5.04) < 1e-9
    save("metrics.json", dict(scope="Descriptive pilots; task is outcome unit; versions not independent randomized replicates", pairs=pairs, aggregates=aggregates, text_control_drift=drift))
    save("runs.json", rows)
    save("skill-inventory.json", inventory)
    save("r2r-metric-audit.json", r2r)
    save("audit.json", dict(source_reports=[dict(path=str(p.relative_to(ROOT)), sha256=sha(p)) for p in (V1,V2,CRYSTAL)],
                            raw_evidence_checks=checks, checks_passed=len(checks),
                            selected_unique_runs=22, historical_unique_runs=14+10+2,
                            note="The 6 v1 trials referenced by recovery are counted once. 4 superseded v1 runs remain historical, outside selected effects."))

    table = ["# 复算结果", "", "负号表示图片组更低；token=input+output，缓存输入不重复相加。超时保留原生失败和实际已记录消耗；其用量可能不完整。", "",
             "|版本|任务结构代理|得分 文/图|token 文→图|变化|工具 文→图|秒 文→图|估算费用变化|配对|", "|---|---|---|---|---:|---|---|---:|---|"]
    for p in pairs:
        a,b=p["text"],p["image"]
        flag="同分通过" if p["admitted"] and p["both_pass"] else ("异分完整" if p["admitted"] else "超时／证据不全")
        table.append(f'|{p["version"]}|{LABELS[p["task"]][0]}：{p["structure"]}|{a["reward"]:g}/{b["reward"]:g}|{a["total_tokens"]:,}→{b["total_tokens"]:,}|{p["total_tokens_change_pct"]:+.1f}%|{a["tool_calls"]}→{b["tool_calls"]}|{a["agent_seconds"]:.1f}→{b["agent_seconds"]:.1f}|{p["estimated_cost_usd_change_pct"]:+.1f}%|{flag}|')
    table += ["", "## 聚合口径", "", "|版本|配对子集|n|token 文→图|合计变化|逐任务变化中位数|", "|---|---|---:|---|---:|---:|"]
    for version,a in aggregates.items():
        for subset in ("all_recorded","complete","both_pass_complete"):
            v=a[subset]; t=v["totals"]
            table.append(f'|{version}|{subset}|{v["n"]}|{t["text"]["total_tokens"]:,}→{t["image"]["total_tokens"]:,}|{v["token_change_pct"]:+.1f}%|{v["median_task_token_change_pct"]:+.1f}%|')
    table += ["", "both_pass_complete 是事后条件描述，不是无偏处理效应；不能通过筛掉失败得出有效率的结论。", "", "## 同样文字包的跨轮波动", "", "|任务|文字 token v1→v2|文字得分 v1→v2|图像 token 效应变号|", "|---|---:|---|---|"]
    for d in drift:
        table.append(f'|{LABELS[d["task"]][0]}|{d["text_token_change_pct"]:+.1f}%|{d["text_reward_v1"]:g}→{d["text_reward_v2"]:g}|{d["image_effect_sign_flip"]}|')
    table += ["", "## 13 个 skill 的结构标注与图面指标", "", "activity/if/loop 仅统计 PlantUML 语法语句；不等于渲染节点／边数，也不等于内容保真度。", "", "|skill|结构|原文 bytes|PNG 宽×高|活动/条件/循环|候选主图＋辅图|", "|---|---|---:|---|---|---|"]
    for s in inventory:
        table.append(f'|{s["skill"]}|{s["structure"]}|{s["source_bytes"]:,}|{s["png_width"]}×{s["png_height"]}|{s["activity_statements"]}/{s["conditional_statements"]}/{s["loop_statements"]}|{s["primary_candidate"]}＋{s["secondary_candidate"]}|')
    (OUT / "metrics.md").write_text("\n".join(table)+"\n")

    fig, (ax, bx) = plt.subplots(1,2,figsize=(13,5.8),gridspec_kw={"width_ratios":[1.5,1]})
    tasks=list(LABELS)[:5]
    for j,version in enumerate(("v1","v2")):
        for i,task in enumerate(tasks):
            p=next(x for x in pairs if x["version"]==version and x["task"]==task)
            y=i+(j-.5)*.24; color=("#527aa4" if version=="v1" else "#163d65")
            ax.scatter(p["total_tokens_change_pct"],y,c=color,marker="x" if not p["admitted"] else ("s" if not p["both_pass"] else "o"),s=55)
            label=f'{p["total_tokens_change_pct"]:+.1f}%'+(" timeout" if not p["admitted"] else (" unequal score" if not p["both_pass"] else ""))
            ax.annotate(label,(p["total_tokens_change_pct"],y),xytext=(5,0),textcoords="offset points",fontsize=8,va="center")
    ax.axvline(0,color="#a5abb4",lw=1)
    ax.set_yticks(range(5),[LABELS[t][1] for t in tasks]); ax.invert_yaxis()
    ax.set_xlim(-90,245); ax.set_xlabel("Image vs text: total token change (%)")
    ax.set_title("Effect changes across tasks and versions",loc="left",fontweight="bold")
    ax.plot([],[],"o",color="#527aa4",label="v1");ax.plot([],[],"o",color="#163d65",label="v2");ax.legend(loc="lower right",frameon=False)
    xs=np.arange(5); vals=[d["text_token_change_pct"] for d in drift]
    bx.barh(xs,vals,color=["#b75b4b" if v>0 else "#557e70" for v in vals],height=.55)
    for i,v in enumerate(vals):bx.text(v+(3 if v>0 else -3),i,f"{v:+.1f}%",va="center",ha="left" if v>0 else "right",fontsize=9)
    bx.axvline(0,color="#a5abb4",lw=1);bx.set_yticks(xs,[LABELS[t][1] for t in tasks]);bx.invert_yaxis();bx.set_xlim(-85,145)
    bx.set_xlabel("Text-only total tokens: v2 vs v1 (%)");bx.set_title("Unchanged text control also drifts",loc="left",fontweight="bold")
    for axis in (ax,bx):
        axis.spines[["top","right"]].set_visible(False);axis.grid(axis="x",alpha=.15);axis.set_axisbelow(True)
    fig.suptitle("SkillCanvas pilots: descriptive observations, one run per arm per version",x=.04,ha="left",fontsize=13,fontweight="bold")
    fig.text(.04,.015,"Circles: both pass. Squares: unequal scores. Crosses: timeout (recorded usage may be incomplete). Versions are not independent randomized replicates.",fontsize=8,color="#555555")
    fig.tight_layout(rect=[0,.04,1,.93]);fig.savefig(OUT/"outcomes.png",dpi=180);fig.savefig(OUT/"outcomes.svg");plt.close(fig)
    print(json.dumps(dict(selected_runs=22, historical_runs=26,
                          admitted_pairs=sum(p["admitted"] for p in pairs),
                          evidence_checks=len(checks), skill_inventory=len(inventory),
                          outputs=str(OUT)), ensure_ascii=False))


if __name__ == "__main__":
    main()

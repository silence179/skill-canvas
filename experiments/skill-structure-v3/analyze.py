"""Build final per-skill tables/plots from existing native evidence only."""
import json
import os
from pathlib import Path
import tempfile

os.environ.setdefault("MPLCONFIGDIR",str(Path(tempfile.gettempdir())/"skillcanvas-v3-mpl"))
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
JOB=ROOT/"jobs/skill-structure-v3"


def main():
    p=json.loads((JOB/"campaign.json").read_text())
    assert all(s["status"] in ("finished","failed") for s in p["schedule"]), "wait for all scheduled runs"
    c=json.loads((JOB/"comparison.json").read_text())
    audit=json.loads((JOB/"evidence-audit.json").read_text())
    assert audit["complete"]
    material=json.loads((HERE/"manifest.json").read_text())
    old=json.loads((ROOT/"experiments/uml-expanded/full-skill-v2/manifest.json").read_text())
    selection=json.loads((HERE/"selection.json").read_text())
    out=[]
    for pair in c["pairs"]:
        skill=pair["skill"];task=pair["task"]
        base=next(r for r in c["rows"] if r["task"]==task and r["variant"]=="baseline")
        new=next(r for r in c["rows"] if r["variant"]==skill)
        ab=next(r for r in audit["rows"] if r["task"]==task and r["variant"]=="baseline")
        an=next(r for r in audit["rows"] if r["variant"]==skill)
        before=old["tasks"][task]["skills"][skill]["png_dimensions"]
        after=material["figures"][skill]["dimensions"]
        firstb=ab["first_successful_main_prompt_tokens"];firstn=an["first_successful_main_prompt_tokens"]
        quality=("原生分数改善" if pair["new_reward"]>pair["baseline_reward"] else
                 "原生分数下降" if pair["new_reward"]<pair["baseline_reward"] else
                 "双方通过" if pair["both_pass"] else "双方未通过")
        out.append(dict(**pair,quality=quality,diagram_type=material["figures"][skill]["diagram_type"],
                        baseline={k:base.get(k) for k in ("total_tokens","tool_calls","main_calls","agent_seconds","estimated_cost_usd","reward","test_summary","error")},
                        new={k:new.get(k) for k in ("total_tokens","tool_calls","main_calls","agent_seconds","estimated_cost_usd","reward","test_summary","error")},
                        baseline_pytest_cases=ab["pytest_case_summary"],new_pytest_cases=an["pytest_case_summary"],
                        old_png_dimensions=before,new_png_dimensions=after,png_area_ratio=after[0]*after[1]/(before[0]*before[1]),
                        first_main_input_tokens=dict(baseline=firstb,new=firstn,delta=firstn-firstb if firstb is not None and firstn is not None else None),
                        evidence_delivery_input_checks=dict(baseline=ab["checks"],new=an["checks"])))
    result=dict(intervention_unit="skill",unique_run_count=c["unique_runs"],redrawn_skills=len(out),
                not_individually_run=[r["skill"] for r in selection["rows"] if r["decision"]!="redraw"],
                comparisons=out,unique_runs_recorded_tokens=c["recorded_tokens"],unique_runs_estimated_cost_usd=c["estimated_cost_usd"],
                preflight_excluded_tokens=json.loads((HERE/"live-preflight.json").read_text())["usage"]["total_tokens"],
                native_score_changes={k:sum(r["quality"]==k for r in out) for k in ("原生分数改善","原生分数下降","双方通过","双方未通过")},
                limitations=p["limits"])
    (JOB/"skill-analysis.json").write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    lines=["# 单 skill 图替换：量化结果", "", "每一行只替换该 skill 的 PNG；其他完整原文、资源和背景图逐字节不变。对照是当轮旧图重跑，不是历史成绩。每变体一次，同环境的行共享一个旧图控制。", "",
           "|skill|新表示|原生分数 旧→新|用例通过 旧→新|token 旧→新|token变化|工具 旧→新|秒 旧→新|质量判断|", "|---|---|---|---|---|---:|---|---|---|"]
    for r in out:
        a,b=r["baseline"],r["new"]
        case=lambda x:f"{x.get('passed',0)}/{sum(x.values())}" if x else "未解析"
        pct=r["total_tokens_change_pct"]
        lines.append(f"|{r['skill']}|{r['diagram_type']}|{a['reward']:g}→{b['reward']:g}|{case(r['baseline_pytest_cases'])}→{case(r['new_pytest_cases'])}|{a['total_tokens']:,}→{b['total_tokens']:,}|{pct:+.1f}%|{a['tool_calls']}→{b['tool_calls']}|{a['agent_seconds']:.1f}→{b['agent_seconds']:.1f}|{r['quality']}|" if pct is not None else
                     f"|{r['skill']}|{r['diagram_type']}|{a['reward']}→{b['reward']}|{case(r['baseline_pytest_cases'])}→{case(r['new_pytest_cases'])}|{a['total_tokens']}→{b['total_tokens']}|不纳入完整效率比较|{a['tool_calls']}→{b['tool_calls']}|{a['agent_seconds']}→{b['agent_seconds']}|{r['quality']}|")
    lines += ["", "用例通过数取测试 stdout 的参数化用例汇总；原始 comparison.json 的 test_summary 来自 CTRF 按名称归并的组数，二者都保留，不修改原记录。超时／用量缺失行保留实际已记录资源，不宣称完整效率收益。", "",
              "## 图片面积与首次输入", "", "|skill|旧 PNG 宽×高|新 PNG 宽×高|面积比 新/旧|首次主请求输入 token 旧→新|", "|---|---|---|---:|---|"]
    for r in out:
        f=r["first_main_input_tokens"]
        lines.append(f"|{r['skill']}|{'×'.join(map(str,r['old_png_dimensions']))}|{'×'.join(map(str,r['new_png_dimensions']))}|{r['png_area_ratio']:.2f}|{f['baseline']}→{f['new']}|")
    lines += ["", "首次输入含整个提示／其余图／全文和入口，不是服务商单独报告的图像 token。面积未固定，因此布局、标签和像素开销不能相互归因。", "",
              f"总消耗只统计 {c['unique_runs']} 个唯一任务运行：{c['recorded_tokens']:,} token；框架估算费用 ${c['estimated_cost_usd']:.6f}。接口预检的 5,897 token 单列，不混入 benchmark。费用不是供应商账单。", "",
              "未把共享 baseline 在每个 skill 行重新加到总量。没有新增无图组，没有测不画图策略，也没有每任务同时替换所有图。"]
    (JOB/"skill-analysis.md").write_text("\n".join(lines)+"\n")
    fig,ax=plt.subplots(figsize=(13,7))
    labels=[]
    short={"fjsp-baseline-repair-with-downtime-and-policy":"FJSP baseline repair","ordered-window-sequencing-mip":"Ordered windows"}
    for i,r in enumerate(out):
        labels.append(short.get(r["skill"],r["skill"]))
        x=r["total_tokens_change_pct"]
        if x is None:
            ax.text(1,i,f"excluded complete efficiency | score {r['baseline_reward']:g}->{r['new_reward']:g}",va="center",fontsize=9,color="#666666")
            continue
        color={"原生分数改善":"#2e7b58","原生分数下降":"#b35342","双方通过":"#34658e","双方未通过":"#8c8c8c"}[r["quality"]]
        ax.barh(i,x,color=color,height=.6)
        ax.annotate(f"{x:+.1f}% | score {r['baseline_reward']:g}->{r['new_reward']:g}",(x,i),xytext=(5 if x>=0 else -5,0),textcoords="offset points",va="center",ha="left" if x>=0 else "right",fontsize=9)
    ax.axvline(0,color="#999999",lw=1);ax.set_yticks(range(len(out)),labels);ax.invert_yaxis()
    ax.spines[["top","right"]].set_visible(False);ax.grid(axis="x",alpha=.15);ax.set_axisbelow(True)
    values=[r["total_tokens_change_pct"] for r in out if r["total_tokens_change_pct"] is not None]
    ax.set_xlim(min(-100,min(values,default=0)-75),max(100,max(values,default=0)+100))
    ax.set_xlabel("Total token change vs fresh old-diagram control (%)")
    ax.set_title("Single-skill diagram replacement | one run per variant; shared controls",loc="left",fontweight="bold",pad=18)
    fig.text(.02,.02,"Green: score improved. Red: score declined. Blue: both pass. Grey: both fail. Lower tokens with a lower score is not same-quality efficiency.",fontsize=8,color="#555555")
    fig.tight_layout(rect=[0,.04,1,1]);fig.savefig(JOB/"skill-effects.png",dpi=170);fig.savefig(JOB/"skill-effects.svg");plt.close(fig)
    print(json.dumps(dict(skills=len(out),unique_runs=c["unique_runs"],native_score_changes=result["native_score_changes"],tokens=c["recorded_tokens"]),ensure_ascii=False))


if __name__=="__main__":main()

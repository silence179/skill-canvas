"""Join the closed single-skill stage and user-directed combined continuation."""
import hashlib
import json
import os
from pathlib import Path
import tempfile

os.environ.setdefault("MPLCONFIGDIR",str(Path(tempfile.gettempdir())/"skillcanvas-v3-final-mpl"))
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
A=ROOT/"jobs/skill-structure-v3"
B=ROOT/"jobs/skill-structure-v3-combined"


def read(path):return json.loads(path.read_text())
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def pct(a,b):return 100*(b/a-1) if a and b is not None else None


def main():
    pa,pb=read(A/"campaign.json"),read(B/"campaign.json")
    assert all(s["status"] in ("finished","failed","cancelled_by_user") for s in pa["schedule"])
    assert all(s["status"] in ("finished","failed") for s in pb["schedule"])
    ca,cb=read(A/"comparison.json"),read(B/"comparison.json")
    aa,ab=read(A/"evidence-audit.json"),read(B/"evidence-audit.json")
    assert aa["complete"] and ab["complete"]
    old=read(ROOT/"jobs/uml-expanded/paired-five-full-skill-v2/comparison.json")
    defs=read(ROOT/"experiments/skill-structure-v3/manifest.json")
    original=[r for r in ca["rows"] if r.get("trial")]
    combined=[r for r in cb["rows"] if r.get("trial")]
    assert len(original)==8 and len(combined)==3
    assert len({r["trial"] for r in original+combined})==11
    records=[]
    for skill in ("prefix-cache-replay","dc-power-flow","economic-dispatch","locational-marginal-prices"):
        r=next(r for r in original if r["variant"]==skill)
        base=next(x for x in original if x["task"]==r["task"] and x["variant"]=="baseline")
        records.append(dict(label=skill,stage="single_skill",changed_skills=[skill],new=r,reference=base,reference_kind="same_round_shared_control"))
    for r in combined:
        task=r["task"]
        if task=="r2r-mpc-control":
            base=next(x for x in original if x["task"]==task and x["variant"]=="baseline");kind="same_round_shared_control"
        else:
            base=next(x for x in old["rows"] if x["task"]==task and x["arm"]=="image");kind="historical_v2_image"
        records.append(dict(label=" + ".join(r["changed_skills"]),stage="combined",changed_skills=r["changed_skills"],new=r,reference=base,reference_kind=kind))
    for r in records:
        a,b=r["reference"],r["new"]
        r["comparison_complete"]=bool(a.get("metric_admitted") and b.get("metric_admitted") and a.get("task_digest")==b.get("task_digest"))
        r["both_native_pass"]=a.get("reward")==1 and b.get("reward")==1
        r["native_score_change"]=b["reward"]-a["reward"]
        for key in ("total_tokens","tool_calls","agent_seconds","estimated_cost_usd"):
            r[key+"_change_pct"]=pct(a[key],b[key]) if r["comparison_complete"] else None
        r["diagram_types"]={s:defs["figures"][s]["diagram_type"] for s in r["changed_skills"]}
    lqr=next(r for r in original if r["variant"]=="finite-horizon-lqr")
    lqrbase=next(r for r in original if r["task"]==lqr["task"] and r["variant"]=="baseline")
    result=dict(primary_comparisons=records,supplemental_presteering_lqr=dict(new=lqr,reference=lqrbase,token_change_pct=pct(lqrbase["total_tokens"],lqr["total_tokens"])),
                actual_unique_runs=11,cancelled_unlaunched_slots=5,
                actual_new_run_tokens=sum(r.get("total_tokens") or 0 for r in original+combined),
                actual_new_run_estimated_cost_usd=sum(r.get("estimated_cost_usd") or 0 for r in original+combined),
                preflight_separate_tokens=read(ROOT/"experiments/skill-structure-v3/live-preflight.json")["usage"]["total_tokens"],
                audit_rows=aa["rows"]+ab["rows"],
                bindings={str(p.relative_to(ROOT)):sha(p) for p in
                    (A/"campaign.json",B/"campaign.json",A/"comparison.json",B/"comparison.json",A/"evidence-audit.json",B/"evidence-audit.json",A/"user-steering-amendment.json",ROOT/"experiments/skill-structure-v3/manifest.json",HERE/"manifest.json")},
                limits=["one observation per variant", "first-stage comparisons share controls", "final exam/manufacturing references are historical", "combined R2R cannot identify individual diagram contributions", "layout, summary emphasis and pixel area change together", "post-results source-constrained authoring, not blinded", "no-figure policy not tested", "native rewards are not a complete scientific-correctness/integrity certificate"])
    (B/"final-analysis.json").write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    rows=["# 本轮最终量化结果", "", "按 skill 源结构选图；前半段单图替换，用户调整后每个剩余 task 一次组合图运行。每变体一次。", "",
          "|图／组合|对照|分数 旧→新|token 旧→新|token变化|工具 旧→新|Agent秒 旧→新|", "|---|---|---|---|---:|---|---|"]
    for r in records:
        a,b=r["reference"],r["new"];delta=r["total_tokens_change_pct"]
        display=f"{delta:+.1f}%" if delta is not None else "不纳入完整效率比较"
        ref="当轮旧图" if r["reference_kind"]=="same_round_shared_control" else "历史 v2 旧图"
        rows.append(f"|{r['label']}|{ref}|{a['reward']:g}→{b['reward']:g}|{a['total_tokens']:,}→{b['total_tokens']:,}|{display}|{a['tool_calls']}→{b['tool_calls']}|{a['agent_seconds']:.1f}→{b['agent_seconds']:.1f}|")
    rows += ["",f"变更前已启动的 LQR 单图补充记录：{lqrbase['reward']:g}→{lqr['reward']:g}，{lqrbase['total_tokens']:,}→{lqr['total_tokens']:,} token（{pct(lqrbase['total_tokens'],lqr['total_tokens']):+.1f}%），{lqrbase['agent_seconds']:.1f}→{lqr['agent_seconds']:.1f}s。它不是组合运行，也不是计划外补跑。", "",
             f"本轮实际 11 个唯一运行，共 {result['actual_new_run_tokens']:,} 已记录 token、框架估算费用 ${result['actual_new_run_estimated_cost_usd']:.6f}；单列的接口预检 5,897 token 未混入。历史引用不计入本轮新消耗，共享控制也不重复计数。", "",
             "低分／超时保留。不同分数的 token 下降不叫同质量节省。历史对照即使完整也只作描述，不作随机配对因果解释。", "",
             "原始 CTRF 按测试名称合并参数化用例，测试 stdout 可能有更多用例；evidence-audit.json 同时保存两种计数。"]
    (B/"final-analysis.md").write_text("\n".join(rows)+"\n")
    fig,ax=plt.subplots(figsize=(12,6.2));labels=[];values=[]
    short={"prefix-cache-replay":"Cache state machine","dc-power-flow":"DC dataflow","economic-dispatch":"Dispatch constraints","locational-marginal-prices":"Price dependency"}
    for i,r in enumerate(records):
        label=short.get(r["label"],{"r2r-mpc-control":"LQR + integral feedback","exam-block-sequencing":"Ordered windows","manufacturing-fjsp-optimization":"Repair timeline"}.get(r["new"]["task"],r["label"]))
        historical=r["reference_kind"]=="historical_v2_image";labels.append(label+(" *" if historical else ""))
        x=r["total_tokens_change_pct"]
        if x is None:
            ax.text(4,i,f"no complete efficiency comparison | score {r['reference']['reward']:g}->{r['new']['reward']:g}",va="center",fontsize=9,color="#666666");continue
        values.append(x);color="#2e7b58" if r["native_score_change"]>0 else "#b35342" if r["native_score_change"]<0 else "#34658e" if r["both_native_pass"] else "#888888"
        ax.barh(i,x,height=.58,color=color,hatch="//" if historical else None,alpha=.8 if historical else 1)
        ax.annotate(f"{x:+.1f}% | score {r['reference']['reward']:g}->{r['new']['reward']:g}",(x,i),xytext=(5 if x>=0 else -5,0),textcoords="offset points",va="center",ha="left" if x>=0 else "right",fontsize=9)
    ax.axvline(0,color="#999999",lw=1);ax.set_yticks(range(len(records)),labels);ax.invert_yaxis();ax.set_xlim(min(-100,min(values,default=0)-90),max(140,max(values,default=0)+100))
    ax.spines[["top","right"]].set_visible(False);ax.grid(axis="x",alpha=.15);ax.set_axisbelow(True)
    ax.set_title("Skill-derived diagram replacements | final executed matrix",loc="left",fontweight="bold",pad=15);ax.set_xlabel("Total token change vs stated old-diagram reference (%)")
    fig.text(.015,.015,"* Historical reference, not a fresh pair. Green: score improved; blue: both pass. One observation per variant; shared controls; no pure diagram-type causal claim.",fontsize=8,color="#555555")
    fig.tight_layout(rect=[0,.04,1,1]);fig.savefig(B/"final-effects.png",dpi=170);fig.savefig(B/"final-effects.svg");plt.close(fig)
    print(json.dumps(dict(unique_runs=11,tokens=result["actual_new_run_tokens"],estimated_cost_usd=result["actual_new_run_estimated_cost_usd"]),ensure_ascii=False))


if __name__=="__main__":main()

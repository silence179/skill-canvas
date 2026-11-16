"""Read preserved evidence only; never launch benchmark or model calls."""
from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent


def load(p):
    return json.loads(p.read_text())


def main():
    completed = []
    for stage in ("skill-structure-v3", "skill-structure-v3-combined"):
        comparison = load(ROOT / "jobs" / stage / "comparison.json")
        audit = load(ROOT / "jobs" / stage / "evidence-audit.json")
        for row in comparison["rows"]:
            if row.get("status") != "finished" or not row.get("trial"):
                continue
            entry = dict(row, stage=stage)
            entry["evidence_checks"] = next(x for x in audit["rows"] if x["trial"] == row["trial"])
            completed.append(entry)
    partial = next(x for x in load(ROOT / "jobs/skill-structure-v3-combined/campaign.json")["schedule"] if x["task"] == "exam-block-sequencing")
    trials = [(r, ROOT / r["trial"]) for r in completed]
    partial_trials = list((ROOT / partial["jobs_dir"]).glob("*/*/trajectory/acp_trajectory.jsonl"))
    for p in partial_trials:
        trials.append((dict(task="exam-block-sequencing", variant="combined", stage="skill-structure-v3-combined", status=partial["status"], trial=str(p.parent.parent.relative_to(ROOT))), p.parent.parent))
    records = []
    for row, trial in trials:
        key = row["task"] + "__" + row.get("variant", row["arm"]) if "arm" in row else row["task"] + "__" + row["variant"]
        trace = trial / "trajectory/acp_trajectory.jsonl"
        lines = [f"# {key}", "", f"Status: {row['status']}", f"Native source: {trace}", ""]
        tools = []
        events = [json.loads(s) for s in trace.read_text().splitlines() if s.strip()]
        for line_num, event in enumerate(events, 1):
            kind = event["type"]
            if kind == "tool_call":
                n = len(tools) + 1
                inp = event.get("raw_input") or {}
                output = event.get("raw_output") or {}
                if isinstance(output, dict):
                    text = output.get("output", output.get("text", ""))
                    meta = output.get("metadata") or {}
                    exit_code = meta.get("exit")
                else:
                    text = str(output)
                    exit_code = None
                tools.append(dict(n=n, source_line=line_num, title=event.get("title"), input=inp,
                                  output=text, exit_code=exit_code, status=event.get("status"),
                                  started_at=event.get("started_at"), finished_at=event.get("finished_at")))
                lines += [f"## T{n:02d} · native line {line_num}", "", f"{event.get('started_at')} → {event.get('finished_at')} · status={event.get('status')} · exit={exit_code}", "", "Input:", "```json", json.dumps(inp, ensure_ascii=False, indent=2), "```", "", "Output:", "```text", str(text), "```", ""]
            elif kind in ("agent_message", "agent_thought"):
                lines += [f"### {kind} · native line {line_num}", "", event.get("text", ""), ""]
        calls = []
        llm = trial / "trajectory/llm_trajectory.jsonl"
        for line_num, s in enumerate(llm.open(), 1):
            e = json.loads(s)
            body = e.get("response", {}).get("body", {})
            purpose = e.get("metadata", {}).get("call_purpose")
            calls.append(dict(source_line=line_num, purpose=purpose, status=e.get("response", {}).get("status_code"),
                              usage=body.get("usage"), duration_ms=e.get("duration_ms")))
        md = OUT / "traces" / (key + ".md")
        md.parent.mkdir(exist_ok=True)
        md.write_text("\n".join(lines) + "\n")
        records.append(dict(row=row, key=key, tools=tools, calls=calls, extract=str(md.relative_to(ROOT)),
                            bindings={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (trace, llm)}))
    (OUT / "evidence.json").write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n")
    for r in records:
        print('\n' + r['key'])
        for t in r['tools']:
            first = str(t['input'].get('command', t['input'])).splitlines()[0]
            last = str(t['output'])[-600:].replace('\n', ' | ')
            print(f"T{t['n']:02d} exit={t['exit_code']} {first[:160]} => {last}")
        main_calls = [c for c in r['calls'] if c['purpose'] == 'agent' and c['usage']]
        print('MAIN USAGE', [(x['usage'].get('prompt_tokens'), x['usage'].get('completion_tokens'), round(x['duration_ms']/1000, 1)) for x in main_calls])


if __name__ == "__main__":
    main()

"""Compact read-only progress, without printing provider secrets or prompts."""
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2]
directory=Path(sys.argv[1]).resolve() if len(sys.argv)>1 else ROOT/"jobs/skill-structure-v3"
p=json.loads((directory/"campaign.json").read_text())
out={"terminal":sum(s["status"] in ("finished","failed") for s in p["schedule"]),"planned_total":len(p["schedule"]),"cancelled":sum(s["status"]=="cancelled_by_user" for s in p["schedule"])}
for s in p["schedule"]:
    if s["status"]!="launched":continue
    out["running"]=s["variant"]
    out["evaluation_locator"]=s["task"]
    out["slot_elapsed_seconds"]=round((datetime.now(timezone.utc)-datetime.fromisoformat(s["started_at_utc"])).total_seconds())
    for f in Path(s["jobs_dir"]).glob("*/*/trajectory/acp_trajectory.jsonl"):
        events=[json.loads(l) for l in f.read_text().splitlines()]
        out["tool_calls"]=sum(e.get("type")=="tool_call" for e in events)
        out["events"]=len(events)
        out["last_event_type"]=events[-1].get("type") if events else None
    log=directory/f"{s['task']}-{s['variant']}.log"
    if not log.exists():log=directory/f"{s['task']}.log"
    txt=log.read_text() if log.exists() else ""
    out["phase"]="verifying" if "Running verifier" in txt else "agent" if "Prompt 1/1" in txt else "setup"
print(json.dumps(out,ensure_ascii=False))

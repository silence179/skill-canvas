"""Exercise all 13 exact image-first payloads on localhost, without provider calls."""
import asyncio
import importlib.util
import json
import sys
from materials import HERE, ROOT, check, write
from delivery import load_policy

sys.path.insert(0, str(ROOT / "experiments/uml-expanded"))
spec = importlib.util.spec_from_file_location("v3_wire_smoke", ROOT / "experiments/uml-expanded/smoke.py")
wire = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wire)


async def main():
    m = check()
    rows = []
    for task, row in m["tasks"].items():
        for variant, v in row["variants"].items():
            policy = load_policy("image", HERE / v["bundle"])
            wire.load_policy = lambda *args, p=policy: p
            checked = await wire.check(task, False)
            checked["variant"] = variant
            rows.append(checked)
    write(HERE / "wire-check.json", rows)
    assert all(r["valid"] for r in rows)
    print(json.dumps(dict(valid=True, payloads=len(rows))))


if __name__ == "__main__":
    asyncio.run(main())

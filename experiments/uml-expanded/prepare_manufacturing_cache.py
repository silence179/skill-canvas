#!/usr/bin/env python3
"""Pre-trial amendment: retain signed apt indexes and a root-owned uv cache."""

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import threading

from prepare_environments import ROOT, STATE, COPIES, Server, Relay
from study import inventory

task = "manufacturing-fjsp-optimization"
campaign = ROOT / "jobs/uml-expanded/paired-five-v1"
plan = json.loads((campaign / "campaign.json").read_text())
assert all(slot["status"] == "planned" for slot in plan["schedule"] if slot["task"] == task)
source = COPIES / task / "environment/Dockerfile"
addition = """
# SkillCanvas pre-trial amendment: keep indexes so verifier apt update is conditional.
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates
RUN pip3 install --break-system-packages --no-cache-dir uv==0.9.7
ENV UV_CACHE_DIR=/opt/skillcanvas/uv-cache
RUN uvx --with pytest==8.4.1 --with pytest-json-ctrf==0.3.5 pytest --version
"""
previous = source.read_text()
if "# SkillCanvas pre-trial amendment:" not in previous:
    shutil.copy2(source, STATE / "manufacturing-Dockerfile.before-apt-cache")
    source.write_text(previous + addition)
    amendment = {"created_at_utc": datetime.now(timezone.utc).isoformat(), "task": task,
        "before_first_model_trial_for_this_task": True,
        "reason": "official verifier remained in apt-get update; retain signed indexes and prewarm its uv dependencies",
        "changes": ["environment/Dockerfile"], "prompt_data_skills_oracle_verifier_unchanged": True,
        "previous_dockerfile_sha256": hashlib.sha256(previous.encode()).hexdigest(),
        "amended_dockerfile_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    (campaign / "manufacturing-environment-amendment.json").write_text(json.dumps(amendment, indent=2) + "\n")
os.environ.setdefault("DOCKER_CONFIG", str(ROOT / ".runtime/docker"))
server = Server(("172.17.0.1", 0), Relay)
threading.Thread(target=server.serve_forever, daemon=True).start()
proxy = f"http://172.17.0.1:{server.server_address[1]}"
try:
    command = ["docker", "build", "--progress=plain", "--build-arg", "http_proxy=" + proxy,
        "--build-arg", "https_proxy=" + proxy, "--build-arg", "HTTP_PROXY=" + proxy,
        "--build-arg", "HTTPS_PROXY=" + proxy, "-t", "skillcanvas-expanded:" + task,
        str(source.parent)]
    with (STATE / "manufacturing-cache-build.log").open("w") as output:
        subprocess.run(command, stdout=output, stderr=subprocess.STDOUT, check=True, timeout=1200)
    (campaign / "manufacturing-amended-files.json").write_text(json.dumps(inventory(COPIES / task), indent=2) + "\n")
    print("Manufacturing apt/uv cache prepared")
finally:
    server.shutdown()
    server.server_close()

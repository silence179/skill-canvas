#!/usr/bin/env python3
"""Preinstall unchanged task/verifier dependencies in explicit experiment copies."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import threading
import socketserver
import socket
import select

from study import ROOT, TASKS, inventory

STATE = ROOT / ".runtime/uml-expanded"
COPIES = STATE / "prepared-tasks"
REQUIREMENTS = {
    "llm-prefix-cache-replay": "pytest==8.4.1 pytest-json-ctrf==0.3.5",
    "energy-market-pricing": "numpy==1.26.4 scipy==1.11.4 cvxpy==1.4.2 pytest==8.4.1 pytest-json-ctrf==0.3.5",
    "r2r-mpc-control": "pytest==8.4.1 pytest-json-ctrf==0.3.5",
    "exam-block-sequencing": "pytest==8.3.3 pytest-json-ctrf==0.3.5",
    "manufacturing-fjsp-optimization": "pytest==8.4.1 pytest-json-ctrf==0.3.5",
}


class Relay(socketserver.BaseRequestHandler):
    def handle(self):
        try:
            with socket.create_connection(("127.0.0.1", 7890), timeout=15) as remote:
                self.request.settimeout(None)
                remote.settimeout(None)
                while True:
                    ready, _, _ = select.select([self.request, remote], [], [], 120)
                    if not ready:
                        return
                    for source in ready:
                        data = source.recv(65536)
                        if not data:
                            return
                        (remote if source is self.request else self.request).sendall(data)
        except OSError:
            return


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def main():
    os.environ.setdefault("DOCKER_CONFIG", str(ROOT / ".runtime/docker"))
    COPIES.mkdir(parents=True, exist_ok=True)
    server = Server(("172.17.0.1", 0), Relay)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    proxy = f"http://172.17.0.1:{server.server_address[1]}"
    records = {}
    try:
        for task in TASKS:
            original = ROOT / "repos/skillsbench/tasks" / task
            copy = COPIES / task
            if not copy.exists():
                shutil.copytree(original, copy)
            dockerfile = copy / "environment/Dockerfile"
            addition = ("\n# SkillCanvas: same pinned runtime/test dependencies, prepared before trial.\n"
                    f"RUN pip3 install --break-system-packages --no-cache-dir --retries 6 --timeout 120 {REQUIREMENTS[task]}\n"
                    "RUN mkdir -p /opt/skillcanvas/wheels && "
                    f"pip3 wheel --wheel-dir /opt/skillcanvas/wheels --retries 6 --timeout 120 {REQUIREMENTS[task]}\n"
                    "ENV PIP_FIND_LINKS=/opt/skillcanvas/wheels\n"
                    "ENV UV_FIND_LINKS=/opt/skillcanvas/wheels\n")
            dockerfile.write_text((original / "environment/Dockerfile").read_text() + addition)
            expected, actual = inventory(original), inventory(copy)
            for name, digest in expected.items():
                if name != "environment/Dockerfile" and actual.get(name) != digest:
                    raise RuntimeError(f"non-environment task material changed: {task}/{name}")
            tag = "skillcanvas-expanded:" + task
            command = ["docker", "build", "--progress=plain", "--build-arg", "http_proxy=" + proxy,
                "--build-arg", "https_proxy=" + proxy, "--build-arg", "HTTP_PROXY=" + proxy,
                "--build-arg", "HTTPS_PROXY=" + proxy, "-t", tag, str(copy / "environment")]
            print("PREPARE " + task, flush=True)
            with (STATE / f"prepared-{task}.log").open("w") as log:
                subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=2400)
            info = json.loads(subprocess.check_output(["docker", "image", "inspect", tag]))[0]
            if any(value.startswith(("http_proxy=", "https_proxy=", "HTTP_PROXY=", "HTTPS_PROXY=")) for value in info["Config"].get("Env", [])):
                raise RuntimeError("temporary build proxy leaked into task runtime")
            records[task] = {"source_files": expected, "prepared_files": actual,
                "image_id": info["Id"], "tag": tag, "requirements": REQUIREMENTS[task],
                "changes": ["environment/Dockerfile"],
                "temporary_proxy_not_in_runtime": True}
            (STATE / "prepared-environments.json").write_text(json.dumps(records, indent=2) + "\n")
            print("READY " + task, flush=True)
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    main()

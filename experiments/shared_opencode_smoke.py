#!/usr/bin/env python3
"""Offline integration check: two bases share OpenCode, reject a bad archive pin."""

import asyncio
from dataclasses import replace
import json
import os
from pathlib import Path
import subprocess
import time
import uuid

import shared_opencode as shared


async def main():
    os.environ.setdefault("DOCKER_CONFIG", str(shared.ROOT / ".runtime/docker"))
    from benchflow.sandbox.env_layers import DockerLayers, LayerError
    from benchflow.sandbox._base import ExecResult
    from benchflow.agents import install
    record = shared.load_record()
    shared.install_adapter(record)
    layers = DockerLayers()
    rows = []
    for image in ("skillcanvas-crystal-env:preflight", "python:3.12-slim"):
        start = time.monotonic()
        result = await layers.ensure_agent_layer(shared.native_plan().recipe, image, prune=False)
        class Environment:
            async def exec(self, command, **kwargs):
                process = await asyncio.create_subprocess_exec(
                    "docker", "run", "--rm", "--network", "none", "--entrypoint", "sh",
                    result.image, "-c", command,
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
                stdout, stderr = await process.communicate()
                return ExecResult(stdout=stdout.decode(), stderr=stderr.decode(),
                                  return_code=process.returncode)
        row = {"base": image, "cache": result.status, "key": result.key,
               "seconds": round(time.monotonic() - start, 3), "build_seconds": result.build_sec}
        try:
            directory = shared.STATE / "checks" / uuid.uuid4().hex
            directory.mkdir(parents=True)
            why = await install.install_from_layer(Environment(), shared.native_plan(),
                                                   directory, layer_key=result.key)
            if why:
                raise RuntimeError(why)
            output = shared.docker("run", "--rm", "--network", "none", "--user", "65534:65534",
                "--env", "HOME=/tmp", "--entrypoint", "sh", result.image, "-c",
                "/opt/runtime/js-agents/bin/opencode --version; "
                "/opt/runtime/node/bin/node --version; "
                "python3 -c 'import importlib.util; print(\"pymatgen=\"+str(importlib.util.find_spec(\"pymatgen\") is not None))'")
            row.update(output=output.decode().strip(), runtime_verified=True)
            second = await layers.ensure_agent_layer(shared.native_plan().recipe, image, prune=False)
            row["second_lookup"] = second.status
            DockerLayers.release(second.key, daemon=second.daemon_id)
            if second.status != "hit":
                raise RuntimeError("second lookup did not reuse the native cache")
        finally:
            DockerLayers.release(result.key, daemon=result.daemon_id)
        rows.append(row)
        print(json.dumps(row), flush=True)
    # Differential through the actual builder: only the expected archive hash
    # differs. No network, installation or successful stamp may follow failure.
    bad = dict(record, archive_sha256="0" * 64)
    recipe = shared.shared_recipe(shared.native_plan().recipe, bad)
    # Register this synthetic canary with the same Dockerfile generation path.
    # Calling the original generator directly keeps it outside production keys.
    from benchflow.sandbox.env_layers import agent_layer_dockerfile
    key = "0" * 64
    source = agent_layer_dockerfile(recipe, "python:3.12-slim", key)
    source = source.replace("\nRUN ", f"\nRUN --network=none --mount=type=bind,from={record['tag']},target=/run/skillcanvas-tools,readonly ", 1)
    tag = "skillcanvas-opencode-check:bad-" + uuid.uuid4().hex[:10]
    run = subprocess.run(["docker", "build", "--network", "none", "-t", tag, "-"],
                         input=source.encode(), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if run.returncode == 0:
        raise RuntimeError("corrupt archive pin unexpectedly built")
    if b"checksum did NOT match" not in run.stderr and b"FAILED" not in run.stderr:
        raise RuntimeError("negative canary failed for an unrelated reason: " + run.stderr.decode()[-1200:])
    report = {"shared_image": record, "bases": rows, "bad_archive_rejected": True,
              "adapter_sha256": shared.sha(Path(shared.__file__).read_bytes()),
              "scope": "offline real Docker/layer/runtime checks; no model calls or task scores"}
    (shared.STATE / "smoke.json").write_text(json.dumps(report, indent=2) + "\n")
    print("PASS: both task environments reuse the donor; bad archive rejected")


if __name__ == "__main__":
    asyncio.run(main())

#!/usr/bin/env python3
"""Fetch pinned upstream sources and install the project Singularity backend."""

import argparse
import json
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def insert_once(path, marker, anchor, addition):
    source = path.read_text()
    if marker in source:
        return
    if source.count(anchor) != 1:
        raise RuntimeError(f"upstream integration point changed: {path}")
    path.write_text(source.replace(anchor, addition + anchor))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-sync", action="store_true", help="prepare sources only; keep the existing Python environment")
    args = parser.parse_args()
    sources = json.loads((ROOT / "sources.lock.json").read_text())["sources"]
    for name in ("skillsbench", "benchflow"):
        source = sources[name]
        repo = ROOT / "repos" / name
        if not repo.exists():
            repo.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(["git", "init", str(repo)], check=True)
            subprocess.run(["git", "-C", str(repo), "remote", "add", "origin", source["url"]], check=True)
            subprocess.run(["git", "-C", str(repo), "fetch", "--depth=1", "origin", source["commit"]], check=True)
            subprocess.run(["git", "-C", str(repo), "checkout", "--detach", "FETCH_HEAD"], check=True)
        commit = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
        if commit != source["commit"]:
            raise RuntimeError(f"{name}: expected {source['commit']}, found {commit}")

    package = ROOT / "repos/benchflow/src/benchflow"
    insert_once(
        package / "_utils/sandbox_providers.py", '"singularity",',
        '    SandboxProvider(\n        "apple-container",',
        '    SandboxProvider(\n        "singularity",\n        extra=None,\n'
        '        model_proxy=ModelProxyLocation.HOST,\n'
        '        supports_live_process=True,\n        enforces_no_network=False,\n    ),\n',
    )
    insert_once(
        package / "sandbox/setup.py", 'elif sandbox_type == "singularity":',
        '    elif sandbox_type == "apple-container":',
        '    elif sandbox_type == "singularity":\n'
        '        from benchflow.sandbox.singularity import SingularitySandbox\n\n'
        '        SingularitySandbox.preflight()\n'
        '        return SingularitySandbox(\n'
        '            environment_dir=environment_dir,\n'
        '            environment_name=task_path.name,\n'
        '            session_id=rollout_name,\n'
        '            rollout_paths=rollout_paths,\n'
        '            task_env_config=env_config,\n'
        '            persistent_env=manifest_env or None,\n        )\n',
    )
    insert_once(
        package / "sandbox/setup.py", 'SingularitySandbox = SingularitySandbox.selected()',
        '        SingularitySandbox.preflight()\n',
        '        SingularitySandbox = SingularitySandbox.selected()\n',
    )
    insert_once(
        package / "providers/litellm_runtime.py", '"expose_host_model_proxy"',
        '    from benchflow.providers.runtime import ProviderRuntime\n\n    new_runtime = ProviderRuntime(',
        '    if not sandbox_local and (expose := getattr(type(sandbox), "expose_host_model_proxy", None)) is not None:\n'
        '        try:\n'
        '            await expose(sandbox, server.base_url)\n'
        '        except BaseException:\n'
        '            await server.stop()\n'
        '            raise\n\n',
    )
    shutil.copyfile(ROOT / "experiments/singularity_backend.py", package / "sandbox/singularity.py")
    shutil.copyfile(ROOT / "experiments/singularity_relay.py", package / "sandbox/singularity_relay.py")
    if not args.no_sync:
        subprocess.run(["uv", "sync", "--locked", "--no-dev", "--python", "3.12"], cwd=ROOT / "repos/benchflow", check=True)
    print("Pinned sources ready; BenchFlow now accepts --sandbox singularity.")


if __name__ == "__main__":
    main()

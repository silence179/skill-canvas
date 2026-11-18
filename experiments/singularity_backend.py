"""Native SingularityCE 4.1 backend, copied into pinned BenchFlow by setup.py.

One writable filesystem and one instance per trial. SIF images are prepared
before submission; Slurm owns CPU/memory limits and array concurrency.
"""

from __future__ import annotations

import asyncio
import contextlib
from functools import partial
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import shlex
import shutil
import tarfile
import tempfile
import uuid
from urllib.parse import urlsplit

from benchflow._root_only import root_only_path_check
from benchflow._runtime_tree import RUN_DIR
from benchflow.sandbox._base import (
    BaseSandbox, ExecResult, SYSTEM_SHELL_EMPTY_VARS, _root_exec_command,
    capture_pid1_image_env, env_file_body, env_stdin_body, restore_image_env,
    with_system_path, wrap_command_with_env_stdin,
)
from benchflow.sandbox._download import RemoteFileAbsentError, private_download
from benchflow.sandbox._exec_output import exec_raw
from benchflow.sandbox._root_launch import (
    inert_task_env, launch_bash, launch_path, launch_route,
    root_launch_argv, root_launch_script,
)
from benchflow.sandbox._su import su_command
from benchflow.sandbox._transport import fit, reader_cat
from benchflow.sandbox.process._base import SubprocessLiveProcess, _BUFFER_LIMIT
from benchflow.sandbox.protocol import ExecTimeoutError


class SingularityProcess(SubprocessLiveProcess):
    def __init__(self, sandbox):
        self.sandbox = sandbox

    async def start(self, command, env=None, cwd=None):
        route = await launch_route(self.sandbox)
        environment = inert_task_env(env)
        env_path = None
        if environment:
            env_path = f"{RUN_DIR}/env-{uuid.uuid4().hex}"
            script = (
                f"umask 077; mkdir -p {shlex.quote(RUN_DIR)} && "
                f"chmod 700 {shlex.quote(RUN_DIR)} && "
                + root_only_path_check(RUN_DIR, "BenchFlow's private staging folder")
                + f" && (set -C; cat > {shlex.quote(env_path)})"
            )
            result = await self.sandbox._cli(
                *self.sandbox._exec_prefix(), route.shell, "-c", with_system_path(script, launch_path(route)),
                input=env_file_body(environment).encode(), timeout=30,
            )
            self.sandbox._checked(result, "stage agent environment")
        script = root_launch_script(command, env_path=env_path, loader_cleared=True, path=launch_path(route))
        argv = [*self.sandbox._exec_prefix(cwd=cwd), *root_launch_argv(script, launch_bash(route))]
        process = await asyncio.create_subprocess_exec(
            "singularity", *argv, env=self.sandbox._host_env(),
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE, limit=_BUFFER_LIMIT,
        )
        self._set_process(process)


class SingularitySandbox(BaseSandbox):
    _instance = None
    _state = None
    _agent_recipe = None
    agent_layer = None
    exec_env_is_private = True

    @classmethod
    def preflight(cls):
        if not shutil.which("singularity"):
            raise RuntimeError("singularity is not installed; use SingularityCE 4.1.1 on the server")

    @classmethod
    def selected(cls):
        return IsolatedSingularitySandbox if os.environ.get("SKILLCANVAS_ISOLATED_NETWORK") == "1" else cls

    def _instance_network_args(self):
        return []

    def _validate_definition(self):
        project = Path(__file__).resolve().parents[5]
        self._images = Path(os.environ.get("SKILLCANVAS_IMAGES", project / "images")).resolve()
        self._image = self._images / f"{self.environment_name}.sif"
        if not self._image.is_file():
            raise FileNotFoundError(f"Prepare or download the task SIF before submitting: {self._image}")
        if not self.task_env_config.allow_internet:
            raise ValueError("this Singularity backend shares the host network and cannot enforce no-network")

    @property
    def sandbox_id(self):
        return self._instance

    @property
    def supports_system_shell(self):
        return True

    @property
    def supports_runtime_kit(self):
        return True

    def trust_host_mount_sources(self):
        return [self._state] if self._state else []

    def use_agent_layer(self, recipe):
        self._agent_recipe = recipe

    def _host_env(self):
        # Runtime options belong to this trial, never to a login shell's
        # Singularity bind or environment settings. The native starter
        # registers instances in the default directory.
        return {key: value for key, value in os.environ.items()
                if not key.startswith(("SINGULARITY_", "SINGULARITYENV_", "APPTAINER_", "APPTAINERENV_"))}

    @staticmethod
    def _checked(result, operation):
        if result.return_code:
            raise RuntimeError(f"Singularity {operation} failed ({result.return_code}): {result.stderr or result.stdout}")

    async def _cli(self, *args, input=None, timeout=None, binary=False):
        process = await asyncio.create_subprocess_exec(
            "singularity", *args, env=self._host_env(),
            stdin=asyncio.subprocess.PIPE if input is not None else asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(input), timeout=timeout)
        except BaseException:
            with contextlib.suppress(ProcessLookupError):
                process.kill()
            await process.wait()
            raise
        if binary:
            if process.returncode:
                raise RuntimeError(f"Singularity transfer failed: {stderr.decode(errors='replace')}")
            return stdout
        return ExecResult(return_code=process.returncode, stdout=stdout.decode(errors="replace"), stderr=stderr.decode(errors="replace"))

    def _exec_prefix(self, cwd=None):
        flags = ["exec", "--cleanenv", "--no-eval"]
        for name in SYSTEM_SHELL_EMPTY_VARS:
            flags += ["--env", name + "="]
        if os.environ.get("SLURM_CPUS_PER_TASK"):
            for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
                flags += ["--env", name + "=" + os.environ["SLURM_CPUS_PER_TASK"]]
        flags += ["--pwd", cwd or self._cwd]
        return [*flags, "instance://" + self._instance]

    async def start(self, force_build=False):
        from benchflow.trust import state as trust_state

        if force_build:
            raise ValueError("SIF builds are separate from trials; rebuild with experiments/images.py first")
        metadata = json.loads(self._image.with_suffix(".json").read_text())
        self._cwd = metadata["workdir"]
        with self._image.open("rb") as stream:
            digest = await asyncio.to_thread(hashlib.file_digest, stream, "sha256")
        if digest.hexdigest() != metadata["sif_sha256"]:
            raise RuntimeError(f"SIF checksum mismatch: {self._image}")
        # Check task inputs against the preparation receipt. Skills and
        # Dockerfile-only dependency additions are independent of these bytes.
        for name, expected in metadata["environment_files"].items():
            path = self.environment_dir / name
            if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                raise RuntimeError(f"task environment changed since SIF preparation: {name}")
        self._state = Path(tempfile.mkdtemp(prefix="skillcanvas-", dir=os.environ.get("SLURM_TMPDIR")))
        for name in ("tmp", "var-tmp"):
            directory = self._state / name
            directory.mkdir()
            directory.chmod(0o1777)
        (self._state / "logs").mkdir()
        self._rootfs = self._state / "rootfs"
        try:
            trust_state.begin_fresh(self)
            result = await self._cli("build", "--fakeroot", "--sandbox", str(self._rootfs), str(self._image),
                                     timeout=self.task_env_config.build_timeout_sec)
            self._checked(result, "unpack SIF; --fakeroot must be enabled for your account")
            instance = "sc-" + uuid.uuid4().hex[:20]
            args = ["instance", "start", "--fakeroot", "--writable", "--cleanenv", "--no-eval",
                    "--no-home", "--no-mount", "cwd,hostfs,bind-paths,tmp", "--ipc"]
            args += self._instance_network_args()
            for source, target in (("tmp", "/tmp"), ("var-tmp", "/var/tmp"), ("logs", "/logs")):
                args += ["--bind", f"{self._state / source}:{target}"]
            result = await self._cli(*args, str(self._rootfs), instance,
                                     timeout=self.task_env_config.build_timeout_sec)
            self._checked(result, "start instance; --fakeroot must be enabled for your account")
            self._instance = instance
            result = await exec_raw(self.exec, "test \"$(id -u)\" = 0 && mkdir -p /logs/agent /logs/verifier", user="root", timeout_sec=30)
            self._checked(result, "check container root identity")
            if self._agent_recipe and metadata.get("agent") == self._agent_recipe.agent:
                from benchflow.sandbox.env_layers import BaseImage, LayerResult

                image_digest = "sha256:" + metadata["sif_sha256"]
                base = BaseImage(ref=str(self._image), image_id=image_digest, digest=image_digest,
                                 arch=platform.machine(), libc="glibc")
                self.agent_layer = LayerResult(kind="agent", key=metadata["sif_sha256"], tag=str(self._image),
                                               image=image_digest, status="hit", base=base, seconds=0)
            self.layer_records = {"singularity": {"image": self._image.name, "sha256": metadata["sif_sha256"]}}
            if self.rollout_paths:
                (self.rollout_paths.rollout_dir / "singularity-image.json").write_text(json.dumps(metadata, indent=2) + "\n")
        except BaseException:
            try:
                await asyncio.shield(self.stop(delete=True))
            except Exception:
                self.logger.exception("Could not remove failed Singularity trial at %s", self._state)
            raise

    async def exec(self, command, cwd=None, env=None, timeout_sec=None, user=None, service="main", system_shell=False):
        from benchflow.sandbox.agent_exec import AgentExecCommand, native_agent_argv

        if service != "main":
            raise ValueError("Singularity supports a single-container task; service must be main")
        route = await self.exec_route(user, system_shell=system_shell)
        merged = self._merge_env(env, user, plumbing=route.pin is not None, explicit_root=route.explicit_root)
        bootstrap = isinstance(command, AgentExecCommand)
        env_line = json.dumps(merged, ensure_ascii=True).encode() + b"\n" if bootstrap and merged else None
        wrapped = command
        if not bootstrap:
            if route.task_root:
                command = restore_image_env(merged or (), tools=route.tools if route.kit else None) + command
            wrapped = command
            if merged:
                wrapped = wrap_command_with_env_stdin(wrapped)
        resolved = self._resolve_user(user)

        def argv_for(inner):
            if bootstrap:
                if env_line is not None:
                    from benchflow.sandbox.native_agent_env import restore_command
                    inner = restore_command(inner, stdin=True)
                if not route.root:
                    inner = su_command(inner, resolved, shell="/bin/sh", trusted_tools=True,
                                       su=route.tools.split(":")[0] + "/su" if route.kit else "/bin/su")
                executable = native_agent_argv(inner)
            else:
                if route.pin is not None:
                    inner = with_system_path(inner, route.pin)
                else:
                    inner = _root_exec_command(inner, route.explicit_root, route.root_path)
                    if route.task_root:
                        inner = capture_pid1_image_env(route.tools) + inner
                if not route.root:
                    inner = su_command(inner, resolved, shell=route.shell,
                                       su=route.tools.split(":")[0] + "/su" if route.kit else "/bin/su")
                executable = [route.shell, "-c", inner]
            return [*self._exec_prefix(cwd), *executable]

        fitted = fit(argv_for, wrapped, cat=reader_cat(route), agent=command if bootstrap else None)
        stdin = env_line or (env_stdin_body(merged) if merged else None)
        if fitted.payload is not None:
            stdin = ((env_line or b"") + fitted.payload if bootstrap else
                     fitted.frame((env_file_body(merged).encode() if merged else b"") + command.encode()))
        try:
            return await self._cli(*fitted.sent, input=stdin, timeout=timeout_sec)
        except TimeoutError:
            await self.stop(delete=False)
            raise ExecTimeoutError(timeout_sec) from None

    async def upload_file(self, source_path, target_path, *, mode=None):
        body = io.BytesIO()
        with tarfile.open(fileobj=body, mode="w") as archive:
            archive.add(source_path, arcname=Path(target_path).name)
        parent = shlex.quote(str(Path(target_path).parent))
        route = await self.exec_route("root", system_shell=True)
        result = await self._cli(*self._exec_prefix(), route.shell, "-c",
                                 with_system_path(f"mkdir -p {parent} && tar -C {parent} -xf -", route.pin),
                                 input=body.getvalue(), timeout=120)
        self._checked(result, "upload file")
        await self._apply_upload_mode(target_path, mode)

    async def upload_dir(self, source_dir, target_dir, service="main"):
        if service != "main":
            raise ValueError("Singularity service must be main")
        body = io.BytesIO()
        with tarfile.open(fileobj=body, mode="w") as archive:
            for child in Path(source_dir).iterdir():
                archive.add(child, arcname=child.name)
        target = shlex.quote(target_dir)
        route = await self.exec_route("root", system_shell=True)
        result = await self._cli(*self._exec_prefix(), route.shell, "-c",
                                 with_system_path(f"mkdir -p {target} && tar -C {target} -xf -", route.pin),
                                 input=body.getvalue(), timeout=120)
        self._checked(result, "upload directory")

    async def _download(self, source, target):
        found = await exec_raw(self.exec, f"test -e {shlex.quote(source)} || test -L {shlex.quote(source)}", user="root", timeout_sec=30)
        if found.return_code:
            raise RemoteFileAbsentError(source)
        path = Path(source)
        route = await self.exec_route("root", system_shell=True)
        script = with_system_path(shlex.join(["tar", "-C", str(path.parent), "-cf", "-", path.name]), route.pin)
        body = await self._cli(*self._exec_prefix(), route.shell, "-c", script, timeout=120, binary=True)
        target = Path(target)
        with tempfile.TemporaryDirectory(dir=target.parent, prefix="capture-") as folder:
            with tarfile.open(fileobj=io.BytesIO(body)) as archive:
                archive.extractall(folder, filter="data")
            shutil.move(str(Path(folder) / path.name), target)

    @private_download(directory=False)
    async def download_file(self, source_path, target_path):
        await self._download(source_path, target_path)

    @private_download(directory=True)
    async def download_dir(self, source_dir, target_dir, service="main"):
        if service != "main":
            raise ValueError("Singularity service must be main")
        await self._download(source_dir, target_dir)

    async def live_process(self, *, agent=None):
        return SingularityProcess(self)

    async def stop(self, delete=True):
        if self._instance:
            result = await self._cli("instance", "stop", self._instance, timeout=30)
            self._checked(result, "stop instance")
            self._instance = None
        if delete and self._state:
            # Files owned by subordinate UIDs must be removed inside the same
            # fakeroot mapping. No sudo or host-wide instance cleanup.
            if self._rootfs.exists():
                result = await self._cli("exec", "--fakeroot", "--no-home", "--cleanenv",
                                         "--no-mount", "cwd,hostfs,bind-paths,tmp",
                                         "--bind", f"{self._state}:/mnt", str(self._image),
                                         "/bin/sh", "-c", "find /mnt -mindepth 1 -type d -exec chmod u+rwx {} + && "
                                         "find /mnt -mindepth 1 ! -type l -exec chown 0:0 {} +", timeout=120)
                self._checked(result, "release trial filesystem ownership")
            shutil.rmtree(self._state)
            self._state = None


class IsolatedSingularitySandbox(SingularitySandbox):
    # Run BenchFlow's own reachability proof from the agent user before launch.
    cloud_metadata_unreachable = True
    _model_server = None
    _model_relay = None
    _model_port = None
    _relay_mount = "/opt/skillcanvas-model"

    def _instance_network_args(self):
        self._relay_dir = self._state / "model"
        self._relay_dir.mkdir(mode=0o700)
        (self._rootfs / self._relay_mount.lstrip("/")).mkdir(mode=0o700)
        return ["--net", "--network", "none", "--bind", f"{self._relay_dir}:{self._relay_mount}:ro"]

    async def expose_host_model_proxy(self, url):
        from benchflow.sandbox import singularity_relay

        endpoint = urlsplit(url)
        if endpoint.scheme != "http" or endpoint.hostname != "127.0.0.1" or not endpoint.port:
            raise ValueError("isolated Singularity requires a host model proxy on 127.0.0.1")
        if endpoint.port == self._model_port and self._model_relay.returncode is None:
            return
        await self._stop_model_relay()
        host_socket = self._relay_dir / "proxy.sock"
        connect = partial(asyncio.open_connection, "127.0.0.1", endpoint.port)
        connections = self._model_connections = set()

        def forward(reader, writer):
            task = asyncio.create_task(singularity_relay.relay(reader, writer, connect=connect))
            connections.add(task)
            task.add_done_callback(connections.discard)

        self._model_server = await asyncio.start_unix_server(forward, path=host_socket)
        try:
            route = await self.exec_route("root", system_shell=True)
            python = shlex.join(["python3", "-I", "-S", "-c", Path(singularity_relay.__file__).read_text(),
                                 self._relay_mount + "/proxy.sock", str(endpoint.port)])
            self._model_relay = await asyncio.create_subprocess_exec(
                "singularity", *self._exec_prefix(), route.shell, "-c",
                with_system_path("exec " + python, route.pin), env=self._host_env(),
                stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            ready = await asyncio.wait_for(self._model_relay.stdout.readline(), timeout=30)
            if ready != b"ready\n":
                raise RuntimeError("could not start model relay inside isolated Singularity")
            self._model_port = endpoint.port
        except BaseException:
            await self._stop_model_relay()
            raise

    async def _stop_model_relay(self):
        if self._model_relay is not None:
            with contextlib.suppress(ProcessLookupError):
                self._model_relay.kill()
            await self._model_relay.communicate()
            self._model_relay = None
        if self._model_server is not None:
            self._model_server.close()
            connections = tuple(self._model_connections)
            for connection in connections:
                connection.cancel()
            await asyncio.gather(*connections, return_exceptions=True)
            await self._model_server.wait_closed()
            (self._relay_dir / "proxy.sock").unlink(missing_ok=True)
            self._model_server = None
        self._model_port = None

    async def stop(self, delete=True):
        await self._stop_model_relay()
        await super().stop(delete=delete)

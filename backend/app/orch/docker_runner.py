"""Sandbox container lifecycle: create with Section 3 flags, stream events, kill and wipe.

Only the control plane (and the developer CLI acting as one) talks to the Docker socket.
The sandbox never gets the socket, host env, or volume mounts.
"""

from __future__ import annotations

import json
import struct
import time
from collections.abc import Iterator
from datetime import datetime
from typing import Any

import docker
from docker.errors import APIError, NotFound
from docker.models.containers import Container

from app.config import Settings
from app.models.schemas import ContainmentReceipt, SandboxJob, TriggerReason

FORBIDDEN_ENV_KEYS = ("VULTR_INFERENCE_API_KEY", "VULTR_API_KEY")
SANDBOX_LABEL = "safepilot.role"
MEM_BYTES = 512 * 1024 * 1024
STDOUT_STREAM = 1  # Docker attach multiplexing: 8-byte header, byte 0 is the stream id
RUNNER_COMMAND = ["python", "/app/runner.py", "-"]


class WallClockExceeded(Exception):
    """The box ran past its wall-clock budget."""


def sandbox_container_kwargs(
    run_id: str, box_id: str, settings: Settings, command: list[str] | None = None
) -> dict[str, Any]:
    """Exact Section 3.2 flags. Tests pin these; do not loosen them to make anything pass."""
    return {
        "image": settings.sandbox_image,
        "name": f"safepilot-{run_id}-{box_id}",
        "detach": True,
        "environment": {},  # empty. No secrets. No inherited host env.
        "mem_limit": "512m",
        "memswap_limit": "512m",
        "nano_cpus": 1_000_000_000,
        "pids_limit": 128,
        "read_only": True,
        "tmpfs": {"/tmp": f"rw,noexec,nosuid,size={settings.sandbox_tmpfs_size}"},
        "cap_drop": ["ALL"],
        "security_opt": ["no-new-privileges:true"],
        "network": settings.sandbox_network,  # custom bridge, never "host"
        "extra_hosts": {},
        "privileged": False,
        "stdin_open": True,
        "command": command or RUNNER_COMMAND,
        "labels": {
            SANDBOX_LABEL: "sandbox",
            "safepilot.run_id": run_id,
            "safepilot.box_id": box_id,
        },
    }


def isolation_problems(attrs: dict[str, Any]) -> list[str]:
    """Check a `docker inspect` result against Section 3 / 8.4. Empty list means compliant."""
    host = attrs.get("HostConfig", {})
    config = attrs.get("Config", {})
    problems: list[str] = []
    expected = {
        "ReadonlyRootfs": True,
        "Memory": MEM_BYTES,
        "MemorySwap": MEM_BYTES,
        "NanoCpus": 1_000_000_000,
        "PidsLimit": 128,
        "Privileged": False,
    }
    for key, want in expected.items():
        if host.get(key) != want:
            problems.append(f"HostConfig.{key} is {host.get(key)!r}, expected {want!r}")
    if host.get("CapDrop") != ["ALL"]:
        problems.append(f"HostConfig.CapDrop is {host.get('CapDrop')!r}, expected ['ALL']")
    if host.get("CapAdd"):
        problems.append(f"HostConfig.CapAdd is {host.get('CapAdd')!r}, expected none")
    if "no-new-privileges:true" not in (host.get("SecurityOpt") or []):
        problems.append("HostConfig.SecurityOpt is missing no-new-privileges:true")
    if host.get("NetworkMode") in {"host", "default", "bridge"}:
        problems.append(f"HostConfig.NetworkMode is {host.get('NetworkMode')!r}, expected custom")
    if host.get("Binds"):
        problems.append(f"HostConfig.Binds is {host.get('Binds')!r}, expected none")
    for mount in attrs.get("Mounts") or []:
        problems.append(f"unexpected mount {mount.get('Source')} -> {mount.get('Destination')}")
    tmp_opts = (host.get("Tmpfs") or {}).get("/tmp", "")
    if "noexec" not in tmp_opts:
        problems.append(f"HostConfig.Tmpfs /tmp is {tmp_opts!r}, expected noexec tmpfs")
    problems.extend(
        f"Config.Env contains {key}" for key in env_secret_keys(config.get("Env") or [])
    )
    return problems


def env_secret_keys(env: list[str] | dict[str, str]) -> list[str]:
    names = env.keys() if isinstance(env, dict) else [item.split("=", 1)[0] for item in env]
    return [name for name in names if name in FORBIDDEN_ENV_KEYS]


def cpu_mem_from_stats(stats: dict[str, Any]) -> tuple[float, float]:
    """(cpu_pct of one vCPU-capped box, mem_mb) from a `container.stats` sample."""
    cpu, pre = stats.get("cpu_stats", {}), stats.get("precpu_stats", {})
    cpu_delta = cpu.get("cpu_usage", {}).get("total_usage", 0) - pre.get("cpu_usage", {}).get(
        "total_usage", 0
    )
    sys_delta = cpu.get("system_cpu_usage", 0) - pre.get("system_cpu_usage", 0)
    online = cpu.get("online_cpus") or len(cpu.get("cpu_usage", {}).get("percpu_usage") or [1])
    cpu_pct = (cpu_delta / sys_delta) * online * 100.0 if sys_delta > 0 and cpu_delta > 0 else 0.0
    mem = stats.get("memory_stats", {})
    usage = mem.get("usage", 0) - (mem.get("stats", {}) or {}).get("inactive_file", 0)
    return round(cpu_pct, 1), round(max(usage, 0) / (1024 * 1024), 1)


def ensure_network(client: docker.DockerClient, name: str) -> None:
    # TODO(deploy): black-hole 169.254.169.254 with a DOCKER-USER iptables rule on the VM.
    # A Docker network flag cannot block it on its own (Section 3.3).
    try:
        client.networks.get(name)
    except NotFound:
        client.networks.create(name, driver="bridge", labels={SANDBOX_LABEL: "network"})


def sweep_leftovers(client: docker.DockerClient) -> list[str]:
    """Remove every sandbox container left behind by a crashed run (Section 3.8)."""
    removed = []
    sandboxes = client.containers.list(all=True, filters={"label": f"{SANDBOX_LABEL}=sandbox"})
    for container in sandboxes:
        container.remove(force=True)
        removed.append(container.name)
    return removed


def dump_sandbox_env(client: docker.DockerClient, settings: Settings) -> tuple[dict, dict]:
    """Start a throwaway sandbox with the real flags and return (its env, its inspect attrs)."""
    ensure_network(client, settings.sandbox_network)
    kwargs = sandbox_container_kwargs(
        f"verify-{int(time.time())}",
        "box0",
        settings,
        command=["python", "-c", "import json, os; print(json.dumps(dict(os.environ)))"],
    )
    kwargs.pop("detach")
    container = client.containers.create(**kwargs)
    try:
        attrs = client.api.inspect_container(container.id)
        container.start()
        container.wait(timeout=30)
        output = container.logs(stdout=True, stderr=False).decode().strip().splitlines()
        return json.loads(output[-1]), attrs
    finally:
        container.remove(force=True)


class SandboxSession:
    """One box's container for one run. Always destroyed on exit."""

    def __init__(
        self,
        client: docker.DockerClient,
        job: SandboxJob,
        settings: Settings,
        timeout_seconds: float | None = None,
    ) -> None:
        self.client = client
        self.job = job
        self.settings = settings
        self.timeout_seconds = timeout_seconds or settings.sandbox_timeout_seconds
        self.container: Container | None = None
        self.destroyed = False
        self.peak_cpu_pct = 0.0
        self.peak_mem_mb = 0.0
        self._sock: Any = None
        self._buffer = b""
        self._started = 0.0

    # lifecycle -----------------------------------------------------------------

    def start(self) -> None:
        ensure_network(self.client, self.settings.sandbox_network)
        kwargs = sandbox_container_kwargs(self.job.run_id, self.job.box_id, self.settings)
        kwargs.pop("detach")
        self.container = self.client.containers.create(**kwargs)
        # Attach before start so no early stdout is lost.
        self._sock = self.client.api.attach_socket(
            self.container.id, params={"stdin": 1, "stdout": 1, "stderr": 1, "stream": 1}
        )
        self.container.start()
        self._started = time.monotonic()
        self.send(self.job.model_dump())

    def __enter__(self) -> SandboxSession:
        self.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self.destroy()

    @property
    def elapsed_ms(self) -> int:
        return int((time.monotonic() - self._started) * 1000) if self._started else 0

    def remaining_seconds(self) -> float:
        return self.timeout_seconds - (time.monotonic() - self._started)

    def destroy(self) -> bool:
        """kill() then remove(force=True). True once the container is gone."""
        if self.container is None or self.destroyed:
            return self.destroyed
        try:
            self.container.kill()
        except (APIError, NotFound):
            pass  # already exited
        try:
            self.container.remove(force=True)
        except NotFound:
            pass
        try:
            self.client.containers.get(self.container.id)
        except NotFound:
            self.destroyed = True
        if self._sock is not None:
            self._sock.close()
        return self.destroyed

    def sample_stats(self) -> tuple[float, float]:
        if self.container is None:
            return 0.0, 0.0
        try:
            cpu, mem = cpu_mem_from_stats(self.container.stats(stream=False))
        except (APIError, NotFound):
            return self.peak_cpu_pct, self.peak_mem_mb
        self.peak_cpu_pct = max(self.peak_cpu_pct, cpu)
        self.peak_mem_mb = max(self.peak_mem_mb, mem)
        return cpu, mem

    def contain(self, reason: TriggerReason, notes: str | None = None) -> ContainmentReceipt:
        """Forced containment: sample stats, SIGKILL, wipe, and return the receipt."""
        self.sample_stats()
        elapsed = self.elapsed_ms
        container_id = self.container.id[:12] if self.container else ""
        destroyed = self.destroy()
        return ContainmentReceipt(
            container_id=container_id,
            box_name=self.job.box_name,
            box_id=self.job.box_id,
            run_id=self.job.run_id,
            trigger_reason=reason,
            elapsed_ms=elapsed,
            peak_cpu_pct=self.peak_cpu_pct,
            peak_mem_mb=self.peak_mem_mb,
            container_destroyed=destroyed,
            timestamp_iso=datetime.now().astimezone().isoformat(timespec="seconds"),
            notes=notes,
        )

    # I/O -----------------------------------------------------------------------

    def send(self, payload: dict[str, Any]) -> None:
        self._sock._sock.sendall((json.dumps(payload) + "\n").encode())

    def events(self) -> Iterator[dict[str, Any]]:
        """Yield runner events until the container closes stdout.

        Raises WallClockExceeded when the box runs past its budget. The caller must then
        call `contain("timeout")`.
        """
        while True:
            while b"\n" in self._buffer:
                line, self._buffer = self._buffer.split(b"\n", 1)
                if line.strip():
                    yield _parse_line(line)
            header = self._recv_exactly(8)
            if header is None:
                return
            stream, size = header[0], struct.unpack(">I", header[4:8])[0]
            data = self._recv_exactly(size) if size else b""
            if data is None:
                return
            if stream == STDOUT_STREAM:
                self._buffer += data
            # stderr is Playwright/Chromium debug: it stays in the container log stream.

    def _recv_exactly(self, n: int) -> bytes | None:
        """Read n bytes, honouring the wall clock. None on EOF.

        docker-py's own frame reader polls without a timeout, which would let a hung box
        block the watchdog forever, so read the raw socket here instead.
        """
        raw = self._sock._sock
        chunks = b""
        while len(chunks) < n:
            remaining = self.remaining_seconds()
            if remaining <= 0:
                raise WallClockExceeded(f"{self.job.box_id} exceeded {self.timeout_seconds}s")
            raw.settimeout(remaining)
            try:
                data = raw.recv(n - len(chunks))
            except TimeoutError as exc:
                raise WallClockExceeded(
                    f"{self.job.box_id} exceeded {self.timeout_seconds}s"
                ) from exc
            if not data:
                return None
            chunks += data
        return chunks


def _parse_line(line: bytes) -> dict[str, Any]:
    try:
        event = json.loads(line)
        if isinstance(event, dict):
            return event
    except json.JSONDecodeError:
        pass
    return {"type": "runner_log", "message": line.decode(errors="replace")[:500]}

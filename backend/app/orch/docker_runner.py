"""Docker sandbox lifecycle (BUILD_SPEC Section 3).

One container per box per run. The control plane talks to the runner over the
container's stdin (actions) and stdout (events). No ports are opened inside the
sandbox, so a hostile page in one box cannot reach another box's runner.
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any

import docker
from docker.errors import APIError, NotFound

from ..config import SECRET_ENV_NAMES, settings

log = logging.getLogger("safepilot.docker")

SANDBOX_LABEL = "safepilot.role"

_client: docker.DockerClient | None = None


def client() -> docker.DockerClient:
    global _client
    if _client is None:
        _client = docker.from_env(timeout=30)
    return _client


def ping() -> str | None:
    try:
        client().ping()
        return None
    except Exception as exc:  # noqa: BLE001
        return str(exc)[:200]


def sweep_leftovers() -> int:
    """Remove sandboxes left behind by a crashed control plane."""
    removed = 0
    for c in client().containers.list(all=True, filters={"label": f"{SANDBOX_LABEL}=sandbox"}):
        try:
            c.remove(force=True)
            removed += 1
        except APIError:
            pass
    return removed


def ensure_network() -> None:
    try:
        client().networks.get(settings.sandbox_network)
    except NotFound:
        client().networks.create(settings.sandbox_network, driver="bridge")


def sandbox_run_kwargs(*, name: str, labels: dict[str, str]) -> dict[str, Any]:
    """Host config for one disposable Playwright sandbox.

    These flags are the hackathon boundary: a container on the Stockholm Cloud
    Compute VM, never Playwright inside the control-plane process. The image
    user is pinned to pwuser so a rebuilt image cannot silently become root.
    shm_size is /dev/shm only; it is not a host directory mount.
    """
    return {
        "image": settings.sandbox_image,
        "name": name,
        "detach": True,
        "environment": {},
        "user": "pwuser",
        "mem_limit": settings.sandbox_mem_limit,
        "memswap_limit": settings.sandbox_memswap_limit,
        "nano_cpus": settings.sandbox_nano_cpus,
        "pids_limit": settings.sandbox_pids_limit,
        "read_only": True,
        "tmpfs": {"/tmp": f"rw,noexec,nosuid,size={settings.sandbox_tmpfs_size}"},
        "cap_drop": ["ALL"],
        "security_opt": ["no-new-privileges:true"],
        "network": settings.sandbox_network,
        "privileged": False,
        "stdin_open": True,
        "shm_size": "256m",
        "labels": labels,
    }


def assert_sandbox_kwargs(kwargs: dict[str, Any]) -> None:
    """Refuse a spawn that would weaken the Section 3 boundary."""
    if kwargs.get("privileged") or kwargs.get("network") in {None, "host", "none"}:
        raise RuntimeError("sandbox network must be the dedicated bridge, never host or none")
    if kwargs.get("network") != settings.sandbox_network:
        raise RuntimeError("sandbox network must be the dedicated bridge")
    if kwargs.get("environment") not in ({}, None):
        raise RuntimeError("sandbox environment must be empty")
    if kwargs.get("user") in {None, "", "0", "root", "0:0"}:
        raise RuntimeError("sandbox user must be non-root")
    if not kwargs.get("read_only"):
        raise RuntimeError("sandbox root must be read-only")
    if "ALL" not in (kwargs.get("cap_drop") or []):
        raise RuntimeError("sandbox must drop all capabilities")
    if "no-new-privileges:true" not in (kwargs.get("security_opt") or []):
        raise RuntimeError("sandbox must set no-new-privileges")
    if not kwargs.get("mem_limit") or not kwargs.get("memswap_limit"):
        raise RuntimeError("sandbox must set a memory cap with no extra swap")
    if not kwargs.get("pids_limit") or not kwargs.get("nano_cpus"):
        raise RuntimeError("sandbox must set pid and cpu caps")
    mounts = list(kwargs.get("volumes") or []) + list(kwargs.get("binds") or [])
    for mount in mounts:
        text = str(mount)
        if "docker.sock" in text or text.startswith("/") or text.startswith("/:"):
            raise RuntimeError("sandbox must not mount the host or the docker socket")
    tmpfs = kwargs.get("tmpfs") or {}
    if list(tmpfs) != ["/tmp"]:
        raise RuntimeError("sandbox may only tmpfs-mount /tmp")


@dataclass
class Stats:
    cpu_pct: float = 0.0
    mem_mb: float = 0.0
    pids: int = 0
    peak_cpu_pct: float = 0.0
    peak_mem_mb: float = 0.0
    hot_since: float | None = None  # monotonic time CPU went above the trip threshold


@dataclass
class Sandbox:
    run_id: str
    box_id: str
    loop: asyncio.AbstractEventLoop
    container: Any = None
    events: asyncio.Queue = field(default_factory=asyncio.Queue)
    stats: Stats = field(default_factory=Stats)
    started_at: float = 0.0
    destroyed: bool = False
    exited: bool = False
    _sock: Any = None
    _stop: threading.Event = field(default_factory=threading.Event)

    @property
    def name(self) -> str:
        return f"safepilot-{self.run_id[:8]}-{self.box_id}"

    @property
    def short_id(self) -> str:
        return (self.container.id if self.container else "")[:12]

    # ---- lifecycle -------------------------------------------------------
    def start(self, job: dict[str, Any]) -> None:
        """Blocking: create the capped container, attach stdin, send the job."""
        kwargs = sandbox_run_kwargs(
            name=self.name,
            labels={SANDBOX_LABEL: "sandbox", "safepilot.run": self.run_id, "safepilot.box": self.box_id},
        )
        assert_sandbox_kwargs(kwargs)
        self.container = client().containers.run(**kwargs)
        self.started_at = time.monotonic()
        self._sock = client().api.attach_socket(self.container.id, params={"stdin": 1, "stream": 1})
        threading.Thread(target=self._pump_stdout, name=f"{self.name}-out", daemon=True).start()
        threading.Thread(target=self._pump_stats, name=f"{self.name}-stats", daemon=True).start()
        self.send(job)

    def send(self, payload: dict[str, Any]) -> None:
        if self.destroyed or self._sock is None:
            return
        data = (json.dumps(payload) + "\n").encode()
        try:
            raw = getattr(self._sock, "_sock", self._sock)
            raw.sendall(data)
        except OSError as exc:
            log.warning("stdin write failed for %s: %s", self.name, exc)

    def destroy(self) -> bool:
        """Blocking: SIGKILL then force-remove. Returns True only when removal succeeded."""
        self._stop.set()
        if self.container is None:
            return False
        try:
            try:
                self.container.kill(signal="SIGKILL")
            except APIError:
                pass  # already exited
            self.container.remove(force=True)
            self.destroyed = True
        except NotFound:
            self.destroyed = True
        except APIError as exc:
            log.error("remove failed for %s: %s", self.name, exc)
        try:
            if self._sock is not None:
                self._sock.close()
        except Exception:  # noqa: BLE001
            pass
        return self.destroyed

    def inspect_env(self) -> dict[str, Any]:
        """Proof for the UI: env var names inside the sandbox and whether any host secret leaked in."""
        try:
            attrs = client().api.inspect_container(self.container.id)
        except APIError:
            return {}
        env = attrs.get("Config", {}).get("Env") or []
        names = [e.split("=", 1)[0] for e in env]
        values = [e.split("=", 1)[1] if "=" in e else "" for e in env]
        secrets = settings.secret_values()
        exposed = sum(1 for n in names if n in SECRET_ENV_NAMES) + sum(1 for v in values if v and v in secrets)
        hc = attrs.get("HostConfig", {})
        return {
            "env_names": names,
            "secrets_exposed": exposed,
            "readonly_rootfs": hc.get("ReadonlyRootfs"),
            "memory_bytes": hc.get("Memory"),
            "nano_cpus": hc.get("NanoCpus"),
            "pids_limit": hc.get("PidsLimit"),
            "cap_drop": hc.get("CapDrop"),
            "privileged": hc.get("Privileged"),
            "network_mode": hc.get("NetworkMode"),
            "security_opt": hc.get("SecurityOpt"),
            "user": attrs.get("Config", {}).get("User"),
        }

    def oom_killed(self) -> bool:
        try:
            return bool(client().api.inspect_container(self.container.id)["State"].get("OOMKilled"))
        except Exception:  # noqa: BLE001
            return False

    # ---- background pumps (threads) ---------------------------------------
    def _push(self, item: dict[str, Any]) -> None:
        self.loop.call_soon_threadsafe(self.events.put_nowait, item)

    def _pump_stdout(self) -> None:
        buf = b""
        try:
            for chunk in self.container.logs(stream=True, follow=True, stdout=True, stderr=False):
                if self._stop.is_set():
                    break
                buf += chunk
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        self._push(json.loads(line))
                    except json.JSONDecodeError:
                        self._push({"type": "console", "level": "info", "message": line.decode(errors="replace")[:300]})
        except Exception as exc:  # noqa: BLE001
            if not self._stop.is_set():
                log.info("stdout pump ended for %s: %s", self.name, exc)
        finally:
            self.exited = True
            self._push({"type": "_container_exited"})

    def _pump_stats(self) -> None:
        try:
            for s in client().api.stats(self.container.id, stream=True, decode=True):
                if self._stop.is_set():
                    break
                try:
                    cpu = s["cpu_stats"]
                    pre = s["precpu_stats"]
                    cpu_delta = cpu["cpu_usage"]["total_usage"] - pre["cpu_usage"]["total_usage"]
                    sys_delta = cpu.get("system_cpu_usage", 0) - pre.get("system_cpu_usage", 0)
                    online = cpu.get("online_cpus") or 1
                    pct = (cpu_delta / sys_delta) * online * 100.0 if sys_delta > 0 else 0.0
                    # Express as % of the 1 vCPU quota.
                    pct = pct / (settings.sandbox_nano_cpus / 1e9)
                    mem = s.get("memory_stats", {})
                    usage = mem.get("usage", 0) - mem.get("stats", {}).get("inactive_file", 0)
                    st = self.stats
                    st.cpu_pct = round(min(pct, 100.0), 1)
                    st.mem_mb = round(usage / 1048576, 1)
                    st.pids = s.get("pids_stats", {}).get("current", 0)
                    st.peak_cpu_pct = max(st.peak_cpu_pct, st.cpu_pct)
                    st.peak_mem_mb = max(st.peak_mem_mb, st.mem_mb)
                    if st.cpu_pct >= settings.cpu_trip_pct:
                        st.hot_since = st.hot_since or time.monotonic()
                    else:
                        st.hot_since = None
                    self._push({"type": "_stats"})
                except (KeyError, TypeError, ZeroDivisionError):
                    continue
        except Exception:  # noqa: BLE001
            pass

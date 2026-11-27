"""Judge a sandbox's isolation from `Sandbox.inspect_env()` (BUILD_SPEC Sections 3.2 and 8.4)."""

from __future__ import annotations

from typing import Any

from ..config import Settings

_UNITS = {"k": 1024, "m": 1024**2, "g": 1024**3}


def mem_bytes(limit: str) -> int:
    """Docker-style size ("512m") to bytes."""
    limit = limit.strip().lower()
    if limit[-1:] in _UNITS:
        return int(float(limit[:-1]) * _UNITS[limit[-1]])
    return int(limit)


def isolation_problems(info: dict[str, Any], cfg: Settings) -> list[str]:
    """Every way `info` falls short of the Section 3 sandbox contract. Empty means compliant."""
    if not info:
        return ["no inspect data (container gone or Docker unreachable)"]
    problems: list[str] = []
    expected = {
        "readonly_rootfs": True,
        "memory_bytes": mem_bytes(cfg.sandbox_mem_limit),
        "memory_swap_bytes": mem_bytes(cfg.sandbox_memswap_limit),
        "nano_cpus": cfg.sandbox_nano_cpus,
        "pids_limit": cfg.sandbox_pids_limit,
        "cap_drop": ["ALL"],
        "privileged": False,
        "secrets_exposed": 0,
    }
    for key, want in expected.items():
        if info.get(key) != want:
            problems.append(f"{key} is {info.get(key)!r}, expected {want!r}")
    if "no-new-privileges:true" not in (info.get("security_opt") or []):
        problems.append("security_opt is missing no-new-privileges:true")
    if info.get("network_mode") in ("host", "default", "bridge", None):
        problems.append(f"network_mode is {info.get('network_mode')!r}, expected the sandbox network")
    if (info.get("user") or "root") in ("root", "0", "0:0"):
        problems.append(f"user is {info.get('user')!r}, expected a non-root user")
    return problems

from dataclasses import replace

import pytest

from app.config import Settings
from app.orch.isolation import isolation_problems, mem_bytes

CFG = Settings()


def compliant() -> dict:
    return {
        "env_names": ["PATH", "HOME"],
        "secrets_exposed": 0,
        "readonly_rootfs": True,
        "memory_bytes": 512 * 1024**2,
        "memory_swap_bytes": 512 * 1024**2,
        "nano_cpus": 1_000_000_000,
        "pids_limit": 128,
        "cap_drop": ["ALL"],
        "privileged": False,
        "network_mode": "safepilot-sandbox",
        "security_opt": ["no-new-privileges:true"],
        "user": "pwuser",
    }


def test_mem_bytes():
    assert mem_bytes("512m") == 512 * 1024**2
    assert mem_bytes("1g") == 1024**3
    assert mem_bytes("2048") == 2048


def test_compliant_sandbox_has_no_problems():
    cfg = replace(CFG, sandbox_mem_limit="512m", sandbox_memswap_limit="512m",
                  sandbox_nano_cpus=1_000_000_000, sandbox_pids_limit=128)
    assert isolation_problems(compliant(), cfg) == []


@pytest.mark.parametrize(
    ("key", "value", "needle"),
    [
        ("readonly_rootfs", False, "readonly_rootfs"),
        ("memory_bytes", 0, "memory_bytes"),
        ("memory_swap_bytes", -1, "memory_swap_bytes"),
        ("nano_cpus", 4_000_000_000, "nano_cpus"),
        ("pids_limit", None, "pids_limit"),
        ("cap_drop", None, "cap_drop"),
        ("privileged", True, "privileged"),
        ("secrets_exposed", 1, "secrets_exposed"),
        ("security_opt", [], "no-new-privileges"),
        ("network_mode", "host", "network_mode"),
        ("user", "root", "non-root"),
        ("user", "", "non-root"),
    ],
)
def test_each_weakening_is_reported(key, value, needle):
    info = {**compliant(), key: value}
    cfg = replace(CFG, sandbox_mem_limit="512m", sandbox_memswap_limit="512m",
                  sandbox_nano_cpus=1_000_000_000, sandbox_pids_limit=128)
    problems = isolation_problems(info, cfg)
    assert len(problems) == 1 and needle in problems[0]


def test_missing_inspect_data_is_a_problem():
    assert isolation_problems({}, CFG)

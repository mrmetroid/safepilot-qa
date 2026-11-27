"""Section 3.2 flags and the isolation checker. Do not loosen these to make tests pass."""

from app.orch.docker_runner import (
    MEM_BYTES,
    cpu_mem_from_stats,
    env_secret_keys,
    isolation_problems,
    sandbox_container_kwargs,
)


def test_container_kwargs_match_spec(settings):
    kw = sandbox_container_kwargs("run1", "box3", settings)
    assert kw["name"] == "safepilot-run1-box3"
    assert kw["environment"] == {}
    assert kw["mem_limit"] == "512m"
    assert kw["memswap_limit"] == "512m"
    assert kw["nano_cpus"] == 1_000_000_000
    assert kw["pids_limit"] == 128
    assert kw["read_only"] is True
    assert kw["tmpfs"] == {"/tmp": "rw,noexec,nosuid,size=128m"}
    assert kw["cap_drop"] == ["ALL"]
    assert kw["security_opt"] == ["no-new-privileges:true"]
    assert kw["network"] == "safepilot-sandbox"
    assert kw["privileged"] is False
    assert kw["extra_hosts"] == {}
    for forbidden in ("volumes", "mounts", "network_mode", "cap_add", "devices", "env_file"):
        assert forbidden not in kw


def _good_attrs():
    return {
        "HostConfig": {
            "ReadonlyRootfs": True,
            "Memory": MEM_BYTES,
            "MemorySwap": MEM_BYTES,
            "NanoCpus": 1_000_000_000,
            "PidsLimit": 128,
            "Privileged": False,
            "CapDrop": ["ALL"],
            "CapAdd": None,
            "SecurityOpt": ["no-new-privileges:true"],
            "NetworkMode": "safepilot-sandbox",
            "Binds": None,
            "Tmpfs": {"/tmp": "rw,noexec,nosuid,size=128m"},
        },
        "Config": {"Env": ["PATH=/usr/bin", "HOME=/tmp"]},
        "Mounts": [],
    }


def test_isolation_checker_accepts_compliant_container():
    assert isolation_problems(_good_attrs()) == []


def test_isolation_checker_flags_every_weakening():
    attrs = _good_attrs()
    attrs["HostConfig"].update(
        ReadonlyRootfs=False,
        Privileged=True,
        NetworkMode="host",
        CapAdd=["SYS_ADMIN"],
        Binds=["/var/run/docker.sock:/var/run/docker.sock"],
        PidsLimit=None,
    )
    attrs["Config"]["Env"].append("VULTR_INFERENCE_API_KEY=x")
    text = "\n".join(isolation_problems(attrs))
    for needle in (
        "ReadonlyRootfs",
        "Privileged",
        "NetworkMode",
        "CapAdd",
        "Binds",
        "PidsLimit",
        "VULTR_INFERENCE_API_KEY",
    ):
        assert needle in text


def test_env_secret_keys_handles_list_and_dict():
    assert env_secret_keys(["VULTR_API_KEY=1", "PATH=/x"]) == ["VULTR_API_KEY"]
    assert env_secret_keys({"HOME": "/tmp"}) == []


def test_cpu_mem_from_stats():
    stats = {
        "cpu_stats": {
            "cpu_usage": {"total_usage": 2_000},
            "system_cpu_usage": 10_000,
            "online_cpus": 4,
        },
        "precpu_stats": {"cpu_usage": {"total_usage": 1_000}, "system_cpu_usage": 6_000},
        "memory_stats": {"usage": 300 * 1024 * 1024, "stats": {"inactive_file": 100 * 1024 * 1024}},
    }
    assert cpu_mem_from_stats(stats) == (100.0, 200.0)
    assert cpu_mem_from_stats({}) == (0.0, 0.0)

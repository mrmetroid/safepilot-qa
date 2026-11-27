"""The three-box spawn contract. No Docker daemon required."""

from __future__ import annotations

import pytest

from app.orch.docker_runner import assert_sandbox_kwargs, sandbox_run_kwargs
from app.orch.run_manager import DEMO_CONFIG, plan_boxes


def test_demo_preset_is_three_distinct_playwright_personas() -> None:
    boxes = plan_boxes(DEMO_CONFIG)
    assert [box[0] for box in boxes] == ["box1", "box2", "box3"]
    viewports = {box[0]: box[3] for box in boxes}
    assert viewports["box1"] == {"width": 1280, "height": 800}
    assert viewports["box2"] == {"width": 390, "height": 844}
    assert viewports["box3"]["width"] >= 1280


def test_each_box_gets_its_own_disposable_container() -> None:
    boxes = plan_boxes(DEMO_CONFIG)
    run_id = "8f1c6a2e-2c3b-4d9a-9b1e-1d2c3b4a5e6f"
    names = []
    for box_id, _name, _persona, _viewport in boxes:
        kwargs = sandbox_run_kwargs(
            name=f"safepilot-{run_id[:8]}-{box_id}",
            labels={"safepilot.role": "sandbox", "safepilot.box": box_id},
        )
        assert_sandbox_kwargs(kwargs)
        names.append(kwargs["name"])
        assert kwargs["user"] == "pwuser"
        assert kwargs["environment"] == {}
        assert kwargs["network"] == "safepilot-sandbox"
        assert kwargs["read_only"] is True
        assert kwargs["cap_drop"] == ["ALL"]
        assert kwargs["privileged"] is False
        assert "volumes" not in kwargs
        assert kwargs["mem_limit"] == "512m"
        assert kwargs["memswap_limit"] == "512m"
        assert kwargs["nano_cpus"] == 1_000_000_000
        assert kwargs["pids_limit"] == 128
    assert len(set(names)) == 3


def test_host_mounts_and_root_are_refused() -> None:
    kwargs = sandbox_run_kwargs(name="safepilot-test-box1", labels={})
    kwargs["network"] = "host"
    with pytest.raises(RuntimeError):
        assert_sandbox_kwargs(kwargs)

    kwargs = sandbox_run_kwargs(name="safepilot-test-box1", labels={})
    kwargs["environment"] = {"VULTR_INFERENCE_API_KEY": "secret"}
    with pytest.raises(RuntimeError):
        assert_sandbox_kwargs(kwargs)

    kwargs = sandbox_run_kwargs(name="safepilot-test-box1", labels={})
    kwargs["volumes"] = {"/var/run/docker.sock": {"bind": "/var/run/docker.sock", "mode": "rw"}}
    with pytest.raises(RuntimeError):
        assert_sandbox_kwargs(kwargs)

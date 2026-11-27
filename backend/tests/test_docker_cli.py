"""Real Docker. Skipped without Docker unless SAFEPILOT_REQUIRE_DOCKER=1."""

import uuid

import pytest
from typer.testing import CliRunner

from app.cli import app
from app.config import settings

pytestmark = pytest.mark.docker


def test_sandbox_verify_passes_and_leaves_nothing(docker_ready):
    result = CliRunner().invoke(app, ["sandbox", "verify"])
    assert result.exit_code == 0, result.output
    assert "PASS" in result.output
    leftovers = docker_ready.client().containers.list(
        all=True, filters={"label": "safepilot.role=sandbox"})
    assert not [c for c in leftovers if c.name.startswith("safepilot-verify")]


def test_remove_run_sandboxes_only_touches_that_run(docker_ready):
    client = docker_ready.client()
    mine, other = f"run-{uuid.uuid4().hex[:6]}", f"run-{uuid.uuid4().hex[:6]}"
    made = [
        client.containers.create(
            settings.sandbox_image, ["-c", "import time; time.sleep(60)"], entrypoint="python",
            labels={"safepilot.role": "sandbox", "safepilot.run": run_id}, network_disabled=True,
        )
        for run_id in (mine, other)
    ]
    try:
        assert docker_ready.remove_run_sandboxes(mine) == 1
        left = client.containers.list(all=True, filters={"label": f"safepilot.run={other}"})
        assert len(left) == 1
        assert not client.containers.list(all=True, filters={"label": f"safepilot.run={mine}"})
    finally:
        for c in made:
            try:
                c.remove(force=True)
            except Exception:  # noqa: BLE001
                pass

import pytest
from typer.testing import CliRunner

from app.cli import app
from app.inference.client import make_client
from app.models.schemas import SandboxJob


def test_cli_help_lists_commands():
    result = CliRunner().invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "health" in result.output and "sandbox" in result.output
    sandbox = CliRunner().invoke(app, ["sandbox", "--help"])
    for cmd in ("build", "run", "verify", "sweep"):
        assert cmd in sandbox.output


def test_cli_run_rejects_non_http_url():
    result = CliRunner().invoke(app, ["sandbox", "run", "file:///etc/passwd"])
    assert result.exit_code != 0


def test_box2_job_is_mobile_and_carries_no_secrets():
    job = SandboxJob.for_box("r1", "box2", "https://example.com")
    assert (job.viewport.width, job.viewport.height) == (390, 844)
    assert job.persona == "mobile_vision"
    dumped = job.model_dump_json().lower()
    for word in ("api_key", "model", "token", "secret"):
        assert word not in dumped


def test_inference_client_refuses_missing_key(settings):
    with pytest.raises(RuntimeError):
        make_client(settings)


def test_inference_client_refuses_non_vultr_endpoint(settings):
    from dataclasses import replace

    bad = replace(settings, inference_api_key="k", inference_base_url="https://api.openai.com/v1")
    with pytest.raises(RuntimeError):
        make_client(bad)

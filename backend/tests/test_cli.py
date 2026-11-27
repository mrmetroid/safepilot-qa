import asyncio
import json

from typer.testing import CliRunner

from app import main
from app.cli import app
from app.health import health_report

runner = CliRunner()


def test_help_lists_commands():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for cmd in ("health", "run", "sandbox"):
        assert cmd in result.output


def test_run_needs_exactly_one_target():
    assert runner.invoke(app, ["run"]).exit_code == 2
    assert runner.invoke(app, ["run", "https://example.com", "--preset"]).exit_code == 2


def test_run_rejects_unsafe_urls_before_touching_docker():
    for url in ("file:///etc/passwd", "http://127.0.0.1:8000/", "http://169.254.169.254/latest/"):
        result = runner.invoke(app, ["run", url])
        assert result.exit_code == 2, url
        assert "URL rejected" in result.output


def test_run_has_no_auto_approve_option():
    result = runner.invoke(app, ["run", "--help"])
    assert "--block-approvals" in result.output
    assert "auto-approve" not in result.output.lower()
    assert "--approve" not in result.output


def test_api_route_and_cli_share_one_health_report():
    route = json.loads(asyncio.run(main.health()).body)
    direct = asyncio.run(health_report())
    assert set(route) == set(direct)
    assert {"ok", "control_plane", "docker", "inference", "sandbox_image"} <= set(route)

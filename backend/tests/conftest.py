import os

import pytest


def pytest_configure(config):
    config.addinivalue_line("markers", "docker: needs a Docker daemon and the sandbox image")


@pytest.fixture(scope="session")
def docker_ready():
    """Skip Docker tests when Docker is missing, unless SAFEPILOT_REQUIRE_DOCKER=1 (then fail)."""
    from app.config import settings
    from app.orch import docker_runner

    err = docker_runner.ping()
    if err is None:
        try:
            docker_runner.client().images.get(settings.sandbox_image)
        except Exception as exc:  # noqa: BLE001
            err = f"image {settings.sandbox_image} missing: {exc}"
    if err:
        if os.environ.get("SAFEPILOT_REQUIRE_DOCKER") == "1":
            pytest.fail(f"Docker required but unavailable: {err}")
        pytest.skip(f"Docker unavailable: {err}")
    return docker_runner

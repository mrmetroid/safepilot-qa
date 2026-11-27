import importlib.util
from pathlib import Path

import pytest

from app.config import Settings

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def settings() -> Settings:
    return Settings(
        inference_api_key=None,
        inference_base_url="https://api.vultrinference.com/v1",
        inference_model="qwen3.8-flash-next",
        inference_timeout_seconds=45,
        sandbox_image="safepilot-sandbox:latest",
        sandbox_network="safepilot-sandbox",
        sandbox_timeout_seconds=60,
        sandbox_tmpfs_size="128m",
    )


@pytest.fixture(scope="session")
def runner_module():
    """Load sandbox-runner/runner.py without Playwright (it is imported lazily)."""
    path = REPO_ROOT / "sandbox-runner" / "runner.py"
    spec = importlib.util.spec_from_file_location("sandbox_runner", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

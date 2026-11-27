"""Control-plane settings, read from the environment (and `.env` on the control plane only)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Settings:
    inference_api_key: str | None
    inference_base_url: str
    inference_model: str
    inference_timeout_seconds: float
    sandbox_image: str
    sandbox_network: str
    sandbox_timeout_seconds: int
    sandbox_tmpfs_size: str


def load_settings(env_file: Path | None = None) -> Settings:
    # Never overrides real env vars. The values stay in this process only.
    load_dotenv(env_file or REPO_ROOT / ".env", override=False)
    env = os.environ
    return Settings(
        inference_api_key=env.get("VULTR_INFERENCE_API_KEY") or None,
        inference_base_url=env.get("VULTR_INFERENCE_BASE_URL", "https://api.vultrinference.com/v1"),
        inference_model=env.get("VULTR_INFERENCE_MODEL", "qwen3.8-flash-next"),
        inference_timeout_seconds=float(env.get("VULTR_INFERENCE_TIMEOUT_SECONDS", "45")),
        sandbox_image=env.get("SANDBOX_IMAGE", "safepilot-sandbox:latest"),
        sandbox_network=env.get("SANDBOX_NETWORK", "safepilot-sandbox"),
        sandbox_timeout_seconds=int(env.get("SANDBOX_TIMEOUT_SECONDS", "60")),
        sandbox_tmpfs_size=env.get("SANDBOX_TMPFS_SIZE", "128m"),
    )

"""Control-plane settings. Loaded from the repo-root .env (control plane ONLY)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(REPO_ROOT / ".env")


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    inference_api_key: str = os.environ.get("VULTR_INFERENCE_API_KEY", "").strip()
    inference_base_url: str = os.environ.get("VULTR_INFERENCE_BASE_URL", "https://api.vultrinference.com/v1")
    inference_model: str = os.environ.get("VULTR_INFERENCE_MODEL", "qwen3.8-flash-next")
    inference_fallback_model: str = os.environ.get("VULTR_INFERENCE_FALLBACK_MODEL", "glm-5.3-flash")
    inference_timeout: int = _int("VULTR_INFERENCE_TIMEOUT_SECONDS", 45)
    inference_max_retries: int = _int("VULTR_INFERENCE_MAX_RETRIES", 4)

    # Internal URL the sandboxes use (Docker DNS on the sandbox network).
    demo_target_sandbox_url: str = os.environ.get("DEMO_TARGET_SANDBOX_URL", "http://demo-target:8081/demo-target/")
    # URL a human can open in a browser tab.
    demo_target_public_url: str = os.environ.get("DEMO_TARGET_PUBLIC_URL", "http://localhost:8081/demo-target/")
    demo_target_host: str = os.environ.get("DEMO_TARGET_HOST", "demo-target")

    sandbox_image: str = os.environ.get("SANDBOX_IMAGE", "safepilot-sandbox:latest")
    sandbox_network: str = os.environ.get("SANDBOX_NETWORK", "safepilot-sandbox")
    sandbox_mem_limit: str = os.environ.get("SANDBOX_MEM_LIMIT", "512m")
    sandbox_memswap_limit: str = os.environ.get("SANDBOX_MEMSWAP_LIMIT", "512m")
    sandbox_nano_cpus: int = _int("SANDBOX_NANO_CPUS", 1_000_000_000)
    sandbox_pids_limit: int = _int("SANDBOX_PIDS_LIMIT", 128)
    sandbox_tmpfs_size: str = os.environ.get("SANDBOX_TMPFS_SIZE", "128m")
    sandbox_timeout: int = _int("SANDBOX_TIMEOUT_SECONDS", 60)
    max_concurrent_runs: int = _int("MAX_CONCURRENT_RUNS", 2)
    # Total agent sandboxes across all runs (each is capped at 512 MiB / 1 vCPU).
    max_active_sandboxes: int = _int("MAX_ACTIVE_SANDBOXES", 9)
    run_timeout: int = _int("RUN_TIMEOUT_SECONDS", 300)
    max_steps: int = _int("SANDBOX_MAX_STEPS", 14)
    step_timeout: int = _int("SANDBOX_STEP_TIMEOUT_SECONDS", 8)

    # CPU watchdog: sustained usage of the 1 vCPU quota after first page load.
    cpu_trip_pct: float = float(os.environ.get("CPU_TRIP_PCT", "90"))
    cpu_trip_seconds: float = float(os.environ.get("CPU_TRIP_SECONDS", "2.5"))

    @property
    def inference_enabled(self) -> bool:
        return bool(self.inference_api_key)

    def secret_values(self) -> list[str]:
        """Host secrets that must never appear inside a sandbox."""
        vals = [self.inference_api_key, os.environ.get("VULTR_API_KEY", "")]
        return [v for v in vals if v]


SECRET_ENV_NAMES = ("VULTR_INFERENCE_API_KEY", "VULTR_API_KEY")

settings = Settings()

"""Real-container tests. Skipped when Docker or the safepilot-sandbox image is missing.

Build the image first: `uv run safepilot sandbox build`.
"""

import uuid

import pytest

docker = pytest.importorskip("docker")

from app.models.schemas import SandboxJob  # noqa: E402
from app.orch.docker_runner import (  # noqa: E402
    SandboxSession,
    WallClockExceeded,
    dump_sandbox_env,
    ensure_network,
    isolation_problems,
)

pytestmark = pytest.mark.docker

TARGET_HTML = """<!doctype html><title>t</title><h1>Fixture shop</h1>
<button id="buy" onclick="document.querySelector('h1').textContent='Bought'">Buy</button>
<button id="spin" onclick="while (true) {}">Mystery discount</button>"""

SERVER = f"""
import http.server
HTML = {TARGET_HTML!r}.encode()
class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200); self.send_header('Content-Type', 'text/html')
        self.end_headers(); self.wfile.write(HTML)
http.server.HTTPServer(('0.0.0.0', 8081), H).serve_forever()
"""


@pytest.fixture(scope="module")
def client(request):
    try:
        c = docker.from_env()
        c.ping()
        c.images.get("safepilot-sandbox:latest")
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"docker or sandbox image unavailable: {exc}")
    return c


@pytest.fixture(scope="module")
def target_url(client):
    """A plain fixture site on the sandbox network. Not a sandbox, so no hardened flags."""
    ensure_network(client, "safepilot-sandbox")
    name = f"sp-test-target-{uuid.uuid4().hex[:6]}"
    container = client.containers.run(
        "safepilot-sandbox:latest",
        ["python", "-c", SERVER],
        name=name,
        detach=True,
        network="safepilot-sandbox",
    )
    yield f"http://{name}:8081/"
    container.remove(force=True)


def _gone(client, session):
    with pytest.raises(docker.errors.NotFound):
        client.containers.get(session.container.id)


def test_sandbox_env_has_no_host_secrets(client, settings, monkeypatch):
    monkeypatch.setenv("VULTR_INFERENCE_API_KEY", "host-secret-must-not-leak")
    monkeypatch.setenv("VULTR_API_KEY", "host-secret-must-not-leak")
    env, attrs = dump_sandbox_env(client, settings)
    assert "VULTR_INFERENCE_API_KEY" not in env
    assert "VULTR_API_KEY" not in env
    assert "host-secret-must-not-leak" not in str(env)
    assert isolation_problems(attrs) == []


def test_session_runs_actions_and_is_destroyed(client, settings, target_url):
    job = SandboxJob.for_box(
        uuid.uuid4().hex[:8],
        "box1",
        target_url,
        initial_action={"action": "goto", "url": target_url},
    )
    script = [{"action": "click", "selector": "#buy"}, {"action": "done"}]
    seen = []
    with SandboxSession(client, job, settings, timeout_seconds=45) as session:
        assert isolation_problems(client.api.inspect_container(session.container.id)) == []
        for event in session.events():
            seen.append(event)
            if event["type"] == "awaiting_action":
                session.send(script.pop(0))
            if event["type"] == "runner_finished":
                break
    steps = [e for e in seen if e["type"] == "step_result"]
    assert [s["action"] for s in steps] == ["goto", "click"]
    assert all(s["ok"] for s in steps)
    assert "Bought" in steps[-1]["extracted_text"]
    assert sum(e["type"] == "screenshot" for e in seen) == 2
    assert session.destroyed
    _gone(client, session)


def test_wall_clock_timeout_kills_and_wipes(client, settings, target_url):
    job = SandboxJob.for_box(uuid.uuid4().hex[:8], "box3", target_url)
    with SandboxSession(client, job, settings, timeout_seconds=4) as session:
        with pytest.raises(WallClockExceeded):
            for _ in session.events():
                pass  # never send an action: the box idles until the watchdog fires
        receipt = session.contain("timeout")
    assert receipt.trigger_reason == "timeout"
    assert receipt.container_destroyed is True
    assert receipt.secrets_exposed == 0 and receipt.host_impact == "none"
    _gone(client, session)


def test_runaway_page_script_pins_the_cpu_cap(client, settings, target_url):
    """Retires the Box 3 premise: a page `while (true) {}` shows up in container stats."""
    job = SandboxJob.for_box(
        uuid.uuid4().hex[:8],
        "box3",
        target_url,
        initial_action={"action": "goto", "url": target_url},
        step_timeout_seconds=2,
    )
    with SandboxSession(client, job, settings, timeout_seconds=40) as session:
        for event in session.events():
            if event["type"] == "awaiting_action":
                session.send({"action": "click", "selector": "#spin"})
                break
        session.sample_stats()
        session.sample_stats()
        receipt = session.contain("cpu_limit_exceeded")
    assert receipt.peak_cpu_pct > 60, receipt
    assert receipt.container_destroyed is True
    _gone(client, session)

#!/usr/bin/env bash
# SafePilot QA local dev server.
#
#   scripts/dev.sh              control plane with auto-reload on :8000 (serves the dashboard at /)
#   scripts/dev.sh --react      also start the React dashboard (Vite) on :5173
#   scripts/dev.sh --rebuild    rebuild the sandbox and demo-target images first
#
# Env: PORT (default 8000), HOST (default 127.0.0.1).
# Needs Docker. The inference key is read from the repo-root .env by the control plane only;
# it is never passed to the sandbox or demo-target containers.
# The egress firewall (deploy/sandbox-firewall.sh) is NOT applied here; that is a VM concern.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PORT="${PORT:-8000}"
HOST="${HOST:-127.0.0.1}"
SANDBOX_NET=safepilot-sandbox
SANDBOX_SUBNET=172.30.0.0/24
REACT=0
REBUILD=0
for arg in "$@"; do
  case "$arg" in
    --react) REACT=1 ;;
    --rebuild) REBUILD=1 ;;
    -h|--help) sed -n 2,12p "$0"; exit 0 ;;
    *) echo "unknown option: $arg" >&2; exit 2 ;;
  esac
done

say() { printf '\033[1;36m==> %s\033[0m\n' "$*"; }

docker info >/dev/null 2>&1 || { echo "Docker is not reachable. Start the Docker daemon first." >&2; exit 1; }

if ss -ltn "sport = :$PORT" 2>/dev/null | grep -q LISTEN; then
  echo "Port $PORT is already in use (another control plane running?). Stop it or set PORT=..." >&2
  exit 1
fi

say "sandbox network"
docker network inspect "$SANDBOX_NET" >/dev/null 2>&1 || \
  docker network create --driver bridge --subnet "$SANDBOX_SUBNET" "$SANDBOX_NET" >/dev/null

say "images"
build_if_needed() {
  local tag="$1" dir="$2"
  if [ "$REBUILD" = 1 ] || ! docker image inspect "$tag" >/dev/null 2>&1; then
    docker build -t "$tag" "$dir"
  else
    echo "  $tag present (use --rebuild to rebuild)"
  fi
}
build_if_needed safepilot-sandbox:latest "$ROOT/sandbox-runner"
build_if_needed safepilot-demo-target:latest "$ROOT/demo-target"

say "demo target on http://localhost:8081/demo-target/"
if [ "$REBUILD" = 1 ] || [ "$(docker inspect -f '{{.State.Running}}' safepilot-demo-target 2>/dev/null)" != "true" ]; then
  docker rm -f safepilot-demo-target >/dev/null 2>&1 || true
  docker run -d --name safepilot-demo-target --restart unless-stopped \
    --network "$SANDBOX_NET" --network-alias demo-target \
    -p 127.0.0.1:8081:8081 --read-only --cap-drop ALL \
    safepilot-demo-target:latest >/dev/null
fi

say "python venv"
VENV="$ROOT/backend/.venv"
# The backend needs Python >= 3.12 (PEP 604 unions in pydantic models). macOS ships 3.9 as python3,
# so prefer uv-managed 3.12 and rebuild a venv that was created with an older interpreter.
py_ok() { "$1" -c 'import sys; sys.exit(sys.version_info < (3, 12))' 2>/dev/null; }
if [ -x "$VENV/bin/python" ] && ! py_ok "$VENV/bin/python"; then
  echo "  backend venv uses $("$VENV/bin/python" -V 2>&1); rebuilding with Python 3.12"
  rm -rf "$VENV"
fi
if [ ! -x "$VENV/bin/uvicorn" ]; then
  if command -v uv >/dev/null 2>&1; then
    uv venv -q --python 3.12 "$VENV"
    uv pip install -q -p "$VENV/bin/python" -r "$ROOT/backend/requirements.txt"
  elif py_ok python3; then
    python3 -m venv "$VENV"; "$VENV/bin/pip" install -q -r "$ROOT/backend/requirements.txt"
  else
    echo "Python >= 3.12 is required for the backend. Install uv (https://docs.astral.sh/uv/) or python3.12." >&2
    exit 1
  fi
fi

if [ ! -f "$ROOT/.env" ]; then
  cp "$ROOT/.env.example" "$ROOT/.env"
  echo "!! created .env from .env.example: set VULTR_INFERENCE_API_KEY for live inference"
fi
chmod 600 "$ROOT/.env"

PIDS=()
cleanup() { for p in "${PIDS[@]:-}"; do [ -n "$p" ] && kill "$p" 2>/dev/null || true; done; }
trap cleanup EXIT INT TERM

if [ "$REACT" = 1 ]; then
  say "React dashboard on http://localhost:5173/"
  [ -d "$ROOT/frontend/node_modules" ] || (cd "$ROOT/frontend" && npm install --no-fund --no-audit)
  (cd "$ROOT/frontend" && CONTROL_PLANE_URL="http://127.0.0.1:$PORT" npx vite) &
  PIDS+=($!)
fi

say "control plane on http://$HOST:$PORT/  (dashboard at /, health at /api/health)"
cd "$ROOT/backend"
"$VENV/bin/uvicorn" app.main:app --host "$HOST" --port "$PORT" --reload --reload-dir app &
PIDS+=($!)
wait -n "${PIDS[@]}"

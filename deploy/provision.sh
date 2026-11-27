#!/usr/bin/env bash
# SafePilot QA: idempotent bootstrap for an Ubuntu 24.04 Vultr Cloud Compute VM (region sto).
# Run as root on the VM from the repo checkout: sudo bash deploy/provision.sh
# Optional env: SITE_ADDRESS (e.g. 1-2-3-4.sslip.io for automatic HTTPS; default ":80")
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SITE_ADDRESS="${SITE_ADDRESS:-:80}"
SANDBOX_NET=safepilot-sandbox
SANDBOX_SUBNET=172.30.0.0/24

echo "==> packages"
export DEBIAN_FRONTEND=noninteractive
apt-get -o DPkg::Lock::Timeout=600 update -y
apt-get -o DPkg::Lock::Timeout=600 install -y ca-certificates curl git ufw docker.io docker-buildx caddy python3-venv python3-pip
systemctl enable --now docker

echo "==> firewall: only 22/80/443 public"
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

echo "==> sandbox network ($SANDBOX_SUBNET)"
docker network inspect "$SANDBOX_NET" >/dev/null 2>&1 || \
  docker network create --driver bridge --subnet "$SANDBOX_SUBNET" \
    -o com.docker.network.bridge.name=br-safepilot "$SANDBOX_NET"

echo "==> egress policy for sandboxes"
SANDBOX_SUBNET="$SANDBOX_SUBNET" bash "$APP_DIR/deploy/sandbox-firewall.sh"

echo "==> images"
docker build -t safepilot-sandbox:latest "$APP_DIR/sandbox-runner"
docker build -t safepilot-demo-target:latest "$APP_DIR/demo-target"
docker rm -f safepilot-demo-target >/dev/null 2>&1 || true
docker run -d --name safepilot-demo-target --restart unless-stopped \
  --network "$SANDBOX_NET" --network-alias demo-target \
  -p 127.0.0.1:8081:8081 --read-only --cap-drop ALL \
  safepilot-demo-target:latest

echo "==> control plane venv"
python3 -m venv "$APP_DIR/backend/.venv"
"$APP_DIR/backend/.venv/bin/pip" install -q -r "$APP_DIR/backend/requirements.txt"

if [ ! -f "$APP_DIR/.env" ]; then
  cp "$APP_DIR/.env.example" "$APP_DIR/.env"
  echo "!! created $APP_DIR/.env from template: set VULTR_INFERENCE_API_KEY"
fi
chmod 600 "$APP_DIR/.env"

# Public URLs for the demo target (what a human opens in a tab).
PUBLIC_HOST="${SITE_ADDRESS#:80}"
if [ -z "$PUBLIC_HOST" ]; then PUBLIC_HOST="$(curl -4 -s ifconfig.me || hostname -I | awk '{print $1}')"; SCHEME=http; else SCHEME=https; fi
sed -i "s|^DEMO_TARGET_PUBLIC_URL=.*|DEMO_TARGET_PUBLIC_URL=${SCHEME}://${PUBLIC_HOST}/demo-target/|" "$APP_DIR/.env"
sed -i "s|^PUBLIC_BASE_URL=.*|PUBLIC_BASE_URL=${SCHEME}://${PUBLIC_HOST}|" "$APP_DIR/.env"
grep -q '^DEMO_TARGET_SANDBOX_URL=' "$APP_DIR/.env" || echo "DEMO_TARGET_SANDBOX_URL=http://demo-target:8081/demo-target/" >> "$APP_DIR/.env"

echo "==> systemd: control plane on 127.0.0.1:8000"
cat > /etc/systemd/system/safepilot.service <<EOF
[Unit]
Description=SafePilot QA control plane
After=docker.service network-online.target
Requires=docker.service

[Service]
ExecStartPre=/usr/bin/env SANDBOX_SUBNET=$SANDBOX_SUBNET /bin/bash $APP_DIR/deploy/sandbox-firewall.sh
WorkingDirectory=$APP_DIR/backend
ExecStart=$APP_DIR/backend/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --proxy-headers
Restart=always
RestartSec=2

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable safepilot
systemctl restart safepilot

echo "==> caddy ($SITE_ADDRESS)"
sed "s|{\$SITE_ADDRESS::80}|$SITE_ADDRESS|" "$APP_DIR/deploy/Caddyfile" > /etc/caddy/Caddyfile
systemctl enable caddy
systemctl restart caddy

sleep 3
curl -sS http://127.0.0.1:8000/api/health || true
echo
echo "==> done. Dashboard: ${SCHEME}://${PUBLIC_HOST}/"

#!/usr/bin/env bash
# Push this checkout to the Vultr VM and (re)provision it.
# Usage: deploy/deploy.sh root@<vm-ip> [site-address]
#   site-address defaults to "<ip-with-dashes>.sslip.io" (automatic HTTPS via Caddy).
set -euo pipefail
TARGET="${1:?usage: deploy/deploy.sh root@<vm-ip> [site-address]}"
HOST="${TARGET#*@}"
SITE="${2:-$(echo "$HOST" | tr . -).sslip.io}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SSH_OPTS="${SSH_OPTS:--o StrictHostKeyChecking=accept-new}"

rsync -az --delete -e "ssh $SSH_OPTS" \
  --exclude .git --exclude .venv --exclude node_modules --exclude __pycache__ --exclude .env \
  "$ROOT/" "$TARGET:/opt/safepilot-qa/"
# .env goes separately with tight perms (control plane only, never into images or sandboxes).
if [ -f "$ROOT/.env" ]; then
  # Strip the Vultr account key: the VM only needs the inference key.
  grep -v '^VULTR_API_KEY=' "$ROOT/.env" | ssh $SSH_OPTS "$TARGET" "cat > /opt/safepilot-qa/.env"
  ssh $SSH_OPTS "$TARGET" "chmod 600 /opt/safepilot-qa/.env"
fi
ssh $SSH_OPTS "$TARGET" "SITE_ADDRESS='$SITE' bash /opt/safepilot-qa/deploy/provision.sh"
echo "Dashboard: https://$SITE/"

#!/usr/bin/env bash
# Egress policy for Canary Swarm sandboxes. Idempotent; re-applied on every control-plane start
# (Docker recreates its chains on restart, so this is not a one-shot).
set -euo pipefail
SUBNET="${SANDBOX_SUBNET:-172.30.0.0/24}"
add() { local chain=$1; shift; iptables -C "$chain" "$@" 2>/dev/null || iptables -I "$chain" "$@"; }
# Cloud metadata (169.254.169.254) and all link-local: never reachable from a sandbox.
add DOCKER-USER -s "$SUBNET" -d 169.254.0.0/16 -j DROP
# Other private networks (VPC, carrier NAT). The sandbox bridge itself stays reachable (demo-target).
for net in 10.0.0.0/8 192.168.0.0/16 100.64.0.0/10; do add DOCKER-USER -s "$SUBNET" -d "$net" -j DROP; done
# The host itself (control plane :8000, Caddy, Docker API, sshd).
# New connections are dropped; replies to host-initiated connections (Caddy -> demo-target
# via docker-proxy) must still flow, so ESTABLISHED is accepted above the DROP (-I = top).
add INPUT -s "$SUBNET" -j DROP
add INPUT -s "$SUBNET" -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT
echo "sandbox firewall applied for $SUBNET"

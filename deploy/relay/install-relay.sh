#!/usr/bin/env bash
# Deploy the dcc-mcp relay on a public Linux server.
#
# The relay is the public rendezvous point where your home daemon and a
# cloud agent both dial IN (see docs/registration-model.md and the tunnel
# section of the README). It executes no DCC code — it only pairs
# authenticated daemons + agents and forwards frames.
#
# This installs the relay into an isolated venv, provisions a systemd
# service, and (optionally) sets up TLS via Caddy.
#
# Usage (run as root, or with sudo):
#   ./install-relay.sh
#   DCC_RELAY_DOMAIN=relay.example.com ./install-relay.sh   # + Caddy TLS
#
# Idempotent-ish: safe to re-run to update the code / restart the service.
set -euo pipefail

# ── config (override via env) ────────────────────────────────────────
REPO_URL="${DCC_RELAY_REPO:-https://github.com/OtakuSquirrel/dcc-mcp.git}"
REPO_REF="${DCC_RELAY_REF:-daemon-rearch}"
PREFIX="${DCC_RELAY_PREFIX:-/opt/dcc-relay}"
PORT="${DCC_RELAY_PORT:-8787}"
BIND="${DCC_RELAY_BIND:-0.0.0.0}"          # 127.0.0.1 if fronting with Caddy
DOMAIN="${DCC_RELAY_DOMAIN:-}"             # set to enable Caddy TLS
SERVICE_USER="${DCC_RELAY_USER:-dccrelay}"
TOKENS="${DCC_RELAY_TOKENS:-$PREFIX/tokens.json}"

log() { printf '\033[36m[relay]\033[0m %s\n' "$*"; }
die() { printf '\033[31m[relay] ERROR:\033[0m %s\n' "$*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || die "run as root (or: sudo $0)"

# ── deps ─────────────────────────────────────────────────────────────
log "installing system packages (git, python3, venv)"
if command -v apt-get >/dev/null 2>&1; then
  apt-get update -qq
  apt-get install -y -qq git python3 python3-venv >/dev/null
elif command -v dnf >/dev/null 2>&1; then
  dnf install -y -q git python3 >/dev/null
else
  die "unsupported distro (need apt or dnf); install git + python3.11 manually"
fi

PYVER=$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])')
log "python $PYVER"
python3 - <<'PY' || die "Python 3.11+ required (websockets/asyncio APIs)"
import sys
raise SystemExit(0 if sys.version_info[:2] >= (3, 11) else 1)
PY

# ── service user ─────────────────────────────────────────────────────
if ! id "$SERVICE_USER" >/dev/null 2>&1; then
  log "creating service user $SERVICE_USER"
  useradd --system --home "$PREFIX" --shell /usr/sbin/nologin "$SERVICE_USER"
fi

# ── code ─────────────────────────────────────────────────────────────
if [ -d "$PREFIX/src/.git" ]; then
  log "updating repo in $PREFIX/src ($REPO_REF)"
  git -C "$PREFIX/src" fetch --depth 1 origin "$REPO_REF"
  git -C "$PREFIX/src" checkout -q FETCH_HEAD
else
  log "cloning $REPO_URL@$REPO_REF into $PREFIX/src"
  mkdir -p "$PREFIX"
  git clone --depth 1 --branch "$REPO_REF" "$REPO_URL" "$PREFIX/src"
fi

# ── venv + install (only the daemon package; it carries dcc-relay) ───
log "creating venv and installing dcc-daemon"
python3 -m venv "$PREFIX/venv"
"$PREFIX/venv/bin/pip" install --quiet --upgrade pip
"$PREFIX/venv/bin/pip" install --quiet "$PREFIX/src/packages/daemon"

# ── token store ──────────────────────────────────────────────────────
if [ ! -f "$TOKENS" ]; then
  log "initializing empty token store at $TOKENS"
  echo '{"daemons": {}}' > "$TOKENS"
fi
chown -R "$SERVICE_USER:$SERVICE_USER" "$PREFIX"
chmod 600 "$TOKENS"

# ── TLS mode: are we fronting with Caddy? ────────────────────────────
if [ -n "$DOMAIN" ]; then
  # Relay stays plaintext on localhost; Caddy terminates wss:// publicly.
  BIND="127.0.0.1"
  log "TLS mode: relay binds 127.0.0.1:$PORT, Caddy fronts wss://$DOMAIN"
fi

# ── systemd unit ─────────────────────────────────────────────────────
UNIT=/etc/systemd/system/dcc-relay.service
log "writing $UNIT"
cat > "$UNIT" <<EOF
[Unit]
Description=dcc-mcp relay (agent <-> daemon tunnel rendezvous)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$SERVICE_USER
ExecStart=$PREFIX/venv/bin/dcc-relay serve --tokens $TOKENS --host $BIND --port $PORT
Restart=on-failure
RestartSec=3
# Hardening: the relay needs no elevated access.
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
PrivateTmp=true
ReadWritePaths=$PREFIX

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now dcc-relay
log "relay service started (systemctl status dcc-relay)"

# ── optional Caddy for TLS ───────────────────────────────────────────
if [ -n "$DOMAIN" ]; then
  if ! command -v caddy >/dev/null 2>&1; then
    log "installing Caddy for automatic HTTPS"
    if command -v apt-get >/dev/null 2>&1; then
      apt-get install -y -qq debian-keyring debian-archive-keyring apt-transport-https curl >/dev/null
      curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
        | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
      curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
        > /etc/apt/sources.list.d/caddy-stable.list
      apt-get update -qq && apt-get install -y -qq caddy >/dev/null
    else
      die "auto-Caddy only scripted for apt; install Caddy manually then re-run without DOMAIN"
    fi
  fi
  CADDYFILE=/etc/caddy/Caddyfile
  log "configuring Caddy reverse proxy for $DOMAIN -> 127.0.0.1:$PORT"
  cat > "$CADDYFILE" <<EOF
$DOMAIN {
    reverse_proxy 127.0.0.1:$PORT
}
EOF
  systemctl restart caddy
  log "Caddy running; relay reachable at wss://$DOMAIN/"
fi

# ── summary ──────────────────────────────────────────────────────────
echo
log "DONE. Next steps:"
if [ -n "$DOMAIN" ]; then
  echo "  relay URL for daemon/agent:  wss://$DOMAIN/"
else
  PUBIP=$(curl -s ifconfig.me 2>/dev/null || echo "<server-ip>")
  echo "  relay URL (PLAINTEXT — dev only):  ws://$PUBIP:$PORT/"
  echo "  Open port $PORT in your firewall/security group."
  echo "  For production, re-run with DCC_RELAY_DOMAIN=your.domain for TLS."
fi
echo
echo "  Provision a daemon + agent token:"
echo "    sudo -u $SERVICE_USER $PREFIX/venv/bin/dcc-relay add-daemon --tokens $TOKENS"
echo "    sudo -u $SERVICE_USER $PREFIX/venv/bin/dcc-relay add-agent  --tokens $TOKENS --daemon-id dccbox-XXXX"
echo
echo "  Then on your home machine:"
echo "    dcc-daemon --relay-url <URL> --daemon-id dccbox-XXXX --pair-token <PAIR_TOKEN>"

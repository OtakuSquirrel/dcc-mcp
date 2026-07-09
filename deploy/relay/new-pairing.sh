#!/usr/bin/env bash
# Provision a new daemon + one agent token on the relay, in one step.
# Run this ON THE RELAY SERVER after install-relay.sh.
#
#   sudo ./new-pairing.sh [daemon-id]
#
# Prints the three values you need:
#   - daemon_id   + pair_token   -> configure on the HOME machine's daemon
#   - access_token               -> configure on the CLOUD agent
set -euo pipefail

PREFIX="${DCC_RELAY_PREFIX:-/opt/dcc-relay}"
TOKENS="${DCC_RELAY_TOKENS:-$PREFIX/tokens.json}"
USER_="${DCC_RELAY_USER:-dccrelay}"
RELAY="$PREFIX/venv/bin/dcc-relay"

[ -x "$RELAY" ] || { echo "relay not installed at $RELAY — run install-relay.sh first" >&2; exit 1; }

DAEMON_ID_ARG=()
[ $# -ge 1 ] && DAEMON_ID_ARG=(--daemon-id "$1")

echo "== registering daemon =="
OUT=$(sudo -u "$USER_" "$RELAY" add-daemon --tokens "$TOKENS" "${DAEMON_ID_ARG[@]}")
echo "$OUT"
DID=$(echo "$OUT" | awk '/daemon_id/ {print $3}')

echo
echo "== issuing agent access token =="
sudo -u "$USER_" "$RELAY" add-agent --tokens "$TOKENS" --daemon-id "$DID"

echo
echo "Configure the HOME daemon with:  --daemon-id $DID --pair-token <pair_token above>"
echo "Configure the CLOUD agent with:  daemon_id=$DID  access_token=<access_token above>"

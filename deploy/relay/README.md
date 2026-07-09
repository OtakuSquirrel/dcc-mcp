# Deploying the relay

The **relay** is the public rendezvous where your home daemon and a cloud
agent both dial IN — so a remote agent can reach a daemon that sits behind
NAT with no public IP and no open ports. The relay executes no DCC code;
it only pairs authenticated daemons + agents and forwards frames. See the
"Remote agents" section of the top-level README and
[../../docs/registration-model.md](../../docs/registration-model.md).

You do **not** need the relay for local use (Claude Code on the same
machine talks to the daemon at `127.0.0.1:8765` directly). It is only for
the "drive my home DCC from the cloud" case.

## What you need

- A server with a **public IP or domain** (a $5 VPS is plenty — 1 vCPU /
  512 MB).
- One inbound port open (default **8787**). This is safe to expose: the
  relay runs no code.
- **Python 3.11+** (the installer checks).
- For production: a **domain name** so the installer can set up TLS
  (`wss://`) via Caddy. Without a domain you get plaintext `ws://` —
  fine for a quick test, not for real traffic.

## Install

On the server, as root:

```bash
git clone -b daemon-rearch https://github.com/OtakuSquirrel/dcc-mcp.git
cd dcc-mcp/deploy/relay

# Quick test (plaintext ws://<ip>:8787):
sudo ./install-relay.sh

# Production (auto HTTPS via Caddy for your domain):
sudo DCC_RELAY_DOMAIN=relay.example.com ./install-relay.sh
```

The installer:
1. installs git + python3, creates a `dccrelay` system user,
2. clones the repo into `/opt/dcc-relay/src` and installs the daemon
   package (which provides the `dcc-relay` CLI) into an isolated venv,
3. writes a hardened **systemd** service `dcc-relay` and starts it,
4. if `DCC_RELAY_DOMAIN` is set, installs **Caddy** and reverse-proxies
   `wss://<domain>/` → the relay on localhost (automatic certs).

Re-run it any time to update the code and restart the service.

### Env overrides

| Var | Default | Meaning |
|-----|---------|---------|
| `DCC_RELAY_DOMAIN` | — | Domain for Caddy TLS. Set it → `wss://`, unset → `ws://`. |
| `DCC_RELAY_PORT` | `8787` | Relay listen port. |
| `DCC_RELAY_REF` | `daemon-rearch` | Git branch/tag to deploy. |
| `DCC_RELAY_PREFIX` | `/opt/dcc-relay` | Install dir. |

## Provision a pairing

Each home machine needs a `daemon_id` + `pair_token`; each cloud agent an
`access_token`. Generate a full set with the helper:

```bash
sudo ./new-pairing.sh                 # auto id (dccbox-xxxx)
sudo ./new-pairing.sh dccbox-studio1  # named id
```

It prints:
- `daemon_id` + `pair_token` → put on the **home** machine's daemon,
- `access_token` → put on the **cloud** agent.

(Or call the CLI directly: `dcc-relay add-daemon …` / `add-agent …`.)

## Wire up the two ends

**Home machine** (where the DCCs run) — start the daemon with the tunnel:

```bash
dcc-daemon \
  --relay-url wss://relay.example.com/ \
  --daemon-id dccbox-studio1 \
  --pair-token <PAIR_TOKEN>
# or via env: DCC_RELAY_URL / DCC_DAEMON_ID / DCC_PAIR_TOKEN
```

**Cloud agent** — configure it with `daemon_id` + `access_token` and point
it at `wss://relay.example.com/`. (The agent-side integration is the
next piece to build; the relay + daemon halves are done.)

## Operate

```bash
systemctl status dcc-relay      # health
journalctl -u dcc-relay -f      # live logs
systemctl restart dcc-relay     # restart
```

## Security notes — read before public use

This relay path is **functional but not hardened** (see
[../../docs/tunnel-hardening.md](../../docs/tunnel-hardening.md)):

- Always use TLS in production (`DCC_RELAY_DOMAIN=…`); never run real
  traffic over plaintext `ws://`.
- Tokens are static in `tokens.json` — no expiry/rotation/revocation yet.
  Keep that file readable only by the `dccrelay` user (the installer
  `chmod 600`s it) and back it up out-of-band.
- `execute_python` over the tunnel is arbitrary remote code execution
  inside your DCC. Only hand `access_token`s to agents you fully trust.
- No rate limiting / lockout yet — don't expose to untrusted callers.

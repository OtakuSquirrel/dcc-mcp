# Tunnel hardening — deferred

> **Marker only.** The cloud reverse tunnel (`dcc_daemon/tunnel/`) works
> and is auth-gated (pair_token / access_token over WSS), but it has not
> been hardened for untrusted/production exposure. This file records what
> to do before a real deployment; none of it is implemented yet.

## Before exposing the relay publicly, address:

- **TLS everywhere.** Terminate WSS at the relay (`--certfile/--keyfile`)
  or a fronting proxy; never run the tunnel over plain `ws://` off-box.
- **Token rotation & revocation.** Tokens are currently static in the
  JSON store. Add expiry, rotation, and a revocation path.
- **Rate limiting & quotas.** Per-agent and per-daemon limits on
  connection attempts and request volume; the relay currently forwards
  freely.
- **Abuse controls on `execute_python`.** Remote access grants arbitrary
  code execution inside the DCC — scope who can call it, consider an
  allow/deny or approval step for remote (vs local) callers.
- **Auth attempt logging / lockout.** Log and back off repeated bad
  handshakes; alert on anomalies.
- **Relay resource limits.** Max agents per daemon, max frame size,
  idle-connection timeouts, backpressure.
- **Daemon identity hygiene.** One pair_token per machine; store it
  outside the repo; support re-pairing if leaked.
- **Payload confidentiality (optional).** The relay routes frames in the
  clear (within TLS). If the relay host is not fully trusted, consider
  end-to-end encryption so it can't read `execute_python` bodies.

## Not a concern for local use

Local MCP-over-HTTP on `127.0.0.1` is out of scope here — this is only
about the outbound tunnel + relay path used by remote agents.

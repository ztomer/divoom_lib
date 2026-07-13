# Round 19 — daemon as a headless network server (TCP + token + binary blobs)

> **Input (user):** "Why are we using JSON for on-device RPC? I also want the
> daemon to run as a headless server over the network."

## The JSON question (answered)

The daemon RPC is a **control plane** — small, infrequent commands at human
rates. NDJSON is the right tool there: human-readable, debuggable (`nc`-able),
language-agnostic, trivial newline framing, no schema/codegen. The **device data
plane** (pixels/GIFs) is binary and deliberately kept *out* of JSON — that's why
`sync_artwork` runs inside the daemon rather than shipping bytes over the socket.
JSON's only real weakness is binary (needs base64, ~33% overhead). Going to the
network *and* wanting remote media push is exactly when that overhead shows up —
handled here with an explicit `blobs` field rather than a protocol rewrite.

## Decisions (user)

1. **Transport:** add a TCP listener **alongside** the existing Unix socket.
2. **Exposure/auth:** **LAN + token** — bind a TCP host (e.g. `0.0.0.0`), require
   a shared secret on every TCP request.
3. **Media:** **ship image bytes over the wire** (remote clients don't share the
   daemon's filesystem, so path-based image push would break).

## What shipped

### Transport + auth
- `DivoomDaemon(host, port, token)`; `serve_forever` binds the Unix socket
  (always) **and** an `AF_INET` listener when `host`+`port` are set. One accept
  thread per listener; the per-conn handler is shared.
- **Fail-closed:** a TCP listener without a token refuses to start (logs an
  error) — the daemon won't expose notifications + device control unauthenticated.
- TCP requests carry `"token"`; the daemon checks it with
  `hmac.compare_digest`. **Unix connections stay trusted** (local fs perms
  already gate them) — no token required, so the local GUI is unchanged.
- `token` falls back to `DIVOOM_DAEMON_TOKEN`.
- CLI: `divoom-control daemon --host 0.0.0.0 --port 9009 --token …`.

### Binary blobs over the wire
- `device_call` gained an optional `blobs` field: `{arg_index: base64(bytes)}`.
  The daemon base64-decodes each, writes a temp file, and substitutes the path
  into that positional arg before dispatch — generic for `show_image` and any
  future binary method.
- `DaemonClient.device_call(..., blobs={i: bytes})` encodes them.
- `DaemonDeviceProxy`: when the client `is_remote` (TCP), it auto-detects
  positional args that are **local file paths** and ships them as blobs — so
  media_sync / gallery / cover-art "just work" against a remote daemon with no
  call-site changes. Local Unix clients pass the path directly (shared fs).

### Client targeting
- `DaemonClient(host, port, token)` + `DaemonClient.from_env()` (reads
  `DIVOOM_DAEMON_HOST`/`PORT`/`TOKEN`); `.is_remote` property.
- `ensure_daemon()`: if `DIVOOM_DAEMON_HOST` is set, target that **remote**
  daemon over TCP and never spawn; otherwise local Unix + auto-spawn as before.

## Tests
`tests/test_daemon_network.py` (7): TCP round-trip with a valid token; wrong /
missing token rejected; Unix still trusted without a token; blob materialized +
substituted (daemon writes the exact bytes); remote proxy auto-blobifies a local
file. Suite **986 / 0 / 75**.

## §outcome
- **SHIPPED.** The daemon is now usable as a headless LAN server:
  `divoom-control daemon --host 0.0.0.0 --token <secret>`, and any client (set
  `DIVOOM_DAEMON_HOST/PORT/TOKEN`) drives it remotely, including image push.
- **Not hardware-verified** (no device in CI) and **not network-pen-tested**.
  Token travels in plaintext over TCP (LAN + token, per the user's choice); for
  untrusted networks add TLS — left as a follow-up.

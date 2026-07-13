# Socket Interface Hardening — workstream plan — **SHIPPED (2026-06-11)**

All of H1–H7 + the client reply cap landed; +11 real-socket tests
(`tests/test_socket_hardening.py`). Limits are `SocketServer.__init__` params
(`max_message_bytes`/`read_deadline`/`max_connections`/`max_subscribers`) with
safe module defaults (16 MiB / 30 s / 32 / 16). The TCP token auth is unchanged.
Spec below.


The daemon's socket (Unix + opt-in TCP, NDJSON) is a privilege boundary: the
daemon owns the BLE device and reads notification content. Goals: survive
untrusted/buggy clients and resource exhaustion; don't crash a handler thread or
leak internals in error replies.

## Threat model
- **Local (primary):** other processes/users on the same machine. The Unix
  socket file permissions are the boundary — today it's created with the
  process umask (potentially group/world accessible).
- **Remote (opt-in):** the TCP listener (`DIVOOM_DAEMON_HOST`/`--host`) is
  token-gated (`hmac.compare_digest`, constant-time) but otherwise faces the
  network and needs the DoS rails most.
- **Buggy clients:** a wedged or malformed client shouldn't be able to OOM the
  daemon, wedge a handler thread, or starve legitimate callers.

## Weaknesses (in `divoom_daemon/socket_server.py`, `daemon_protocol.py`)
- **S1 — Unix socket world-accessible.** `server.bind(path)` uses the umask; on
  a shared box any local user can drive the daemon (push to device, read
  notifications). No `chmod`.
- **S2 — unbounded read buffer (memory DoS).** `_handle_conn` loops
  `recv(4096)` until `\n` with no size cap → a client that never sends a newline
  (or one huge line) grows `buf` until OOM. Same shape in the client read loop.
- **S3 — slow-loris.** The 5s timeout is per-`recv`, not a total deadline; a
  byte-every-4s client keeps the connection (and buffer) alive indefinitely.
- **S4 — handler exception kills the thread silently.** `_handle_conn` catches
  only `OSError`; any other exception from `command_handler` propagates out, the
  daemon thread dies, and the client gets a reset (no reply → hang/"no reply").
- **S5 — unbounded thread-per-connection (flood DoS).** `_accept_loop` spawns a
  new daemon thread per accept with no cap → a connection flood exhausts
  threads/memory.
- **S6 — unbounded subscribers.** A subscribe flood holds threads + sockets for
  the session with no cap.
- **S7 — no request validation.** `command` may be non-string and `args` a
  non-dict; both reach the handler unchecked.

## Hardening (this workstream)
- **H1 (S1):** `os.chmod(socket_path, 0o600)` immediately after bind; warn (not
  fail) if it can't.
- **H2 (S2):** `max_message_bytes` cap on the server request read and the client
  reply read → reject oversized frames with a typed error instead of buffering.
  Sized for the largest legitimate frame (base64 image blobs in `device_call`).
- **H3 (S3):** a total read deadline for one request line (separate from the
  daemon's own processing time, which starts only after the full line arrives).
- **H4 (S4):** wrap the handler call in a catch-all → log the detail, return a
  generic `{"success": False, "error": "internal error"}` (don't leak internals
  to a remote client).
- **H5 (S5):** a `BoundedSemaphore(max_connections)`; if full, reject the new
  connection with a "server busy" reply instead of blocking the accept loop.
- **H6 (S6):** cap concurrent subscribers; reject beyond the cap.
- **H7 (S7):** validate `command` is a non-empty string and coerce `args` to a
  dict; malformed → typed error reply.

Limits are `SocketServer.__init__` params (small values in tests) with safe
module defaults. Everything is unit-tested against a real in-process server over
a real socket — no mocks of the transport.

## Non-goals
- Re-doing auth (the TCP token + constant-time compare stays).
- TLS for the TCP path (out of scope; bind to loopback or tunnel for now).
- Per-client rate limiting / brute-force lockout (token entropy is the control).

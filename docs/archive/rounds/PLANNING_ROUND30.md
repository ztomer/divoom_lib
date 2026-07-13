# Round 30 — Animation streaming (0x8B) through the daemon

**Goal**: wrap the 0x8B multi-phase animation push in exclusive mode so it's
safe when called through any path (MCP, GUI, CLI), and add first-class MCP
tooling for animation push.

## Context

The 0x8B 3-phase protocol (StartSeeding → SendingData → TerminateSending)
is implemented at the library level and works through the daemon via
`show_image()` (a single coroutine → single queue submit → atomic).

Two gaps remain:

1. **`monthly_best_daemon.stream_raw_bin_payload()`** bypasses the daemon's
   queue when called outside `sync_artwork` — its multi-phase BLE writes
   can interleave with other operations. It should use exclusive mode.

2. **MCP has no dedicated animation tool** — only `show_image` (which works
   but the name doesn't signal GIF/animation support). An explicit
   `push_animation` tool is clearer for clients.

## Scope

### 1. Exclusive-mode wrap for stream_raw_bin_payload

`monthly_best_daemon.stream_raw_bin_payload()` acquires the queue's
exclusive token during its multi-phase 0x8B loop so no other operation
interleaves. Add a `token` parameter; when the caller (sync_artwork) runs
inside `_run_device(_do())`, it passes a token for belt-and-suspenders
protection.

Changes:
- `stream_raw_bin_payload()` gets optional `token` param
- When set, wraps the 0x8B loop in `divoom.animation.app_new_send_gif_cmd(..., exclusive_token=token)` — actually just uses the queue's existing exclusive mode via `DaemonDeviceProxy.exclusive()`
- Actually: `stream_raw_bin_payload` is called with a raw `Divoom` object. To use exclusive mode through the daemon, the caller needs to use `DaemonDeviceProxy` instead. But `sync_artwork` already has the real device object from `_ensure_device_async()`.

**Simpler approach**: `sync_artwork` already runs inside `_run_device(_do())` — the queue already protects against interleaving. The exclusive-mode MCP tool is the real deliverable.

### 2. MCP `push_animation` tool

Add a new MCP tool `push_animation` that:
- Accepts a `file` path (local) OR `data` (base64-encoded blob)
- Calls the daemon's `display.show_image` (which does 0x8B internally)
- Returns success/failure

The `show_image` tool already exists but takes only a file path. The new tool
adds base64 data for remote clients.

### 3. `DaemonDeviceProxy` gets `push_animation` convenience method

`proxy.push_animation(path_or_data)` — wraps `proxy.display.show_image(path)`
inside `proxy.exclusive(token)` for atomicity when called from MCP tools.

### 4. Tests

- Exclusive-mode wrapping for the 0x8B path (mock device)
- MCP `push_animation` tool test
- Proxy `push_animation` convenience method test

## Non-goals

- Cloud gallery scraping — handled by `sync_artwork`/monthly-best
- The 0x8B protocol itself — already implemented and tested
- File format conversion — PIL handles this

## Verification

- Existing suite green (1085 → ~1092 expected)
- Mock-device E2E test asserts 0x8B phases go through the daemon without interleaving

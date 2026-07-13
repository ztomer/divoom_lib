# Round 29 — Wire exclusive mode through device_call

**Goal**: make the daemon RPC path support exclusive-mode multi-phase operations
(CommandQueue exclusive mode was built in R27 but no caller uses it yet).

## Why

The command queue supports exclusive-mode scopes (`acquire(token)` /
`release(token)`) where only items with a matching token are dispatched,
but nothing above the queue level exposes this. Callers that need atomic
multi-phase access (e.g. animation streaming with the 0x8B protocol,
multi-step display setups) must bypass the RPC layer.

## Scope

Four changes, strictly additive:

1. **`DaemonClient.device_call()`** gets a `token` param (optional) that
   ships in the payload. New `exclusive_start(token)` / `exclusive_end(token)`
   methods on `DaemonClient`.

2. **`DeviceOwner.device_call()`** extracts `token` from the payload dict
   and passes it through to `_run_device(coro, token=token)`. New
   `exclusive_start(args)` / `exclusive_end(args)` handlers that call
   `self._cmd_queue.acquire(token)` / `.release(token)` on the queue's loop.

3. **Daemon command registry** (`daemon.py`) registers exclusive_start /
   exclusive_end → `DeviceOwner` handlers.

4. **`DaemonDeviceProxy.exclusive(token)`** context manager issues the
   two RPCs and tags its nested calls with the token.

5. **Tests**: exclusive session through a fake daemon (verifies acquire →
   exclusive dispatch → release), token-through-device_call, proxy
   exclusive context.

## Non-goals

- Animation streaming itself (0x8B protocol) — this just unlocks it.
- No API changes to `divoom_lib.Divoom` or existing callers.

## Verification

- Exclusive dispatch verified through mock daemon (fake `CommandQueue`
   with exclusive-state assertions).
- Full suite green (1079 → ~1085 expected).

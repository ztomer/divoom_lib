# Round 46 — Native Port Event Subscription & Device Name

**Agent**: Claude/Gemini (Antigravity)  
**Date**: 2026-06-23

## Outcome / what shipped

Implemented client subscription and broadcasting support in the native Rust daemon socket server, alongside friendly device name caching and get/set commands:

1. **Event Subscription & Broadcast**:
   - Extended `socket_server.rs` (`serve_connection`) to handle the `"subscribe"` command.
   - When a client subscribes, the server sends the initial status event (`{"type":"status", "state":"idle"}` or `"active"`) and holds the connection open.
   - Multiplexed via `tokio::select!`, incoming broadcast events from a `tokio::sync::broadcast::Sender` channel are streamed to the client, while socket EOF/disconnects automatically clean up the subscription.
   - Connected/disconnected events in `connect` and `disconnect` command dispatch broadcast state changes.

2. **Device Name Cache**:
   - Added a thread-safe `device_name` cache (`std::sync::Mutex<Option<String>>`) inside `BleTransport` (`ble.rs`).
   - Populated from peripheral properties on connection.

3. **New Device Commands**:
   - Ported `"device.get_device_name"` (returns cached name, or queries 0x76 BLE name command as fallback) and `"device.set_device_name"` (updates name via 0x75 and updates cache).

4. **Integration & Parity Tests**:
   - Added `subscription_and_event_broadcast` integration test to `tests/socket_server_behavior.rs`.
   - Added `device_name_commands_route_to_device_call` and updated `device_commands_are_honestly_unimplemented` in `tests/daemon_behavior.rs`.
   - All Rust tests pass (with and without `ble` feature).
   - E2E-verified event broadcasting against real Divoom hardware via a custom python client.
   - Python test suite: 1706 passed, 87 skipped.

## Open / deferred

- Porting the remaining `device_call` command surface.
- Porting the macOS notification monitor / SQLite reader.
- Porting the live widget loops (sysmon, weather, stock, etc.).

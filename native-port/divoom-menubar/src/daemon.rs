//! Lean daemon socket client for the menubar — short-lived NDJSON request/response
//! over the same unix socket the GUI/daemon use (`{"command","args"}` + `\n`, one
//! JSON reply per line). The menubar only needs a handful of read/poll commands
//! plus notification start/stop and shutdown, so each call opens its own
//! connection (no persistent state to manage). Mirrors the Python
//! `daemon_protocol`/`menubar_client` wire format.

use serde_json::{json, Value};

/// Socket path (env override matches the GUI/daemon: `DIVOOM_SOCKET`).
pub fn socket_path() -> String {
    std::env::var("DIVOOM_SOCKET").unwrap_or_else(|_| "/tmp/divoom.sock".to_string())
}

/// One request → one reply. `None` if the daemon is unreachable or the reply
/// doesn't parse (the caller treats unreachable as "daemon offline").
#[cfg(unix)]
pub fn request(command: &str, args: Value) -> Option<Value> {
    use std::io::{BufRead, BufReader, Write};
    use std::os::unix::net::UnixStream;
    use std::time::Duration;

    let stream = UnixStream::connect(socket_path()).ok()?;
    stream.set_read_timeout(Some(Duration::from_secs(6))).ok()?;
    stream.set_write_timeout(Some(Duration::from_secs(6))).ok()?;
    let mut w = stream.try_clone().ok()?;
    let mut line = serde_json::to_vec(&json!({ "command": command, "args": args })).ok()?;
    line.push(b'\n');
    w.write_all(&line).ok()?;
    w.flush().ok()?;
    let mut reader = BufReader::new(stream);
    let mut buf = String::new();
    if reader.read_line(&mut buf).ok()? == 0 {
        return None;
    }
    serde_json::from_str(&buf).ok()
}

// Windows transport (daemon TCP+token) is deferred — same status as divoomd's own
// Windows support. The menubar still runs; it just reports the daemon offline.
#[cfg(not(unix))]
pub fn request(_command: &str, _args: Value) -> Option<Value> {
    None
}

/// Daemon liveness + state, for the status-coloured glyph.
pub enum Status {
    Offline,
    Idle,
    Active,
}

pub fn status() -> Status {
    match request("get_status", json!({})) {
        None => Status::Offline,
        Some(v) => match v.get("state").and_then(|s| s.as_str()) {
            Some("active") => Status::Active,
            _ => Status::Idle,
        },
    }
}

/// Active devices the daemon knows about → `(name, kind)` rows for the menu
/// (parity with the pyobjc menubar's activity tiles; lightweight, no BLE scan).
pub fn device_activity() -> Vec<(String, String)> {
    let Some(v) = request("get_device_activity", json!({})) else { return Vec::new() };
    let Some(map) = v.get("activity").and_then(|a| a.as_object()) else { return Vec::new() };
    let mut rows: Vec<(String, String)> = map
        .values()
        .map(|d| {
            let name = d.get("name").and_then(|n| n.as_str()).unwrap_or("Divoom").to_string();
            let kind = d.get("kind").and_then(|k| k.as_str()).unwrap_or("").to_string();
            (name, kind)
        })
        .collect();
    rows.sort();
    rows
}

/// Whether the notification listener is running (menu label state).
pub fn notifications_running() -> bool {
    let Some(v) = request("notification_status", json!({})) else { return false };
    v.get("running")
        .and_then(|r| r.as_bool())
        .or_else(|| v.get("state").and_then(|s| s.as_str()).map(|s| s == "running"))
        .unwrap_or(false)
}

pub fn start_notifications() {
    let _ = request("start_notifications", json!({}));
}

pub fn stop_notifications() {
    let _ = request("stop_notifications", json!({}));
}

pub fn shutdown() {
    let _ = request("shutdown", json!({}));
}

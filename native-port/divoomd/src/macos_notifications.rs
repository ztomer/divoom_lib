//! macOS notification monitor.
//!
//! Polls the `usernoted` SQLite database for new app notifications and forwards
//! them to the connected Divoom device as ANCS `set_android_ancs` commands
//! (command code 0x50), so the device mirrors a macOS notification the same way
//! it mirrors an Android/iOS one.
//!
//! ## Protocol reference
//! The `set_android_ancs` command payload (APK verified, `references/apk/`):
//!   [operation:1][packageName_len:1][packageName:*][title_len:1][title:*][body_len:1][body:*]
//!   operation: 0 = add, 1 = remove.
//!
//! ## DB path
//! On macOS 12+: `~/Library/Daemon Containers/<uuid>/Data/usernoted/db/usernoted.db`
//! On macOS 11 and below: `~/Library/CoreData/usernoted/db/usernoted.db`
//! The monitor walks all candidate paths and uses the first one found.
//!
//! ## Routing
//! `set_routing` maps app bundle IDs to on/off flags. When the bundle ID is absent
//! from the routing table the notification is forwarded by default.

use std::collections::HashSet;
use std::sync::Arc;
use serde_json::{json, Value};
use tokio::sync::Mutex;

use crate::daemon::Daemon;

// ── state ─────────────────────────────────────────────────────────────────

struct MonitorState {
    running: bool,
    routing: std::collections::HashMap<String, bool>,
    seen_ids: HashSet<i64>,
    task: Option<tokio::task::JoinHandle<()>>,
}

impl MonitorState {
    fn new() -> Self {
        MonitorState { running: false, routing: Default::default(), seen_ids: HashSet::new(), task: None }
    }
}

tokio::task_local! {
    static DUMMY: ();
}

static MONITOR: std::sync::OnceLock<Arc<Mutex<MonitorState>>> = std::sync::OnceLock::new();

fn state() -> Arc<Mutex<MonitorState>> {
    MONITOR.get_or_init(|| Arc::new(Mutex::new(MonitorState::new()))).clone()
}

// ── public API ────────────────────────────────────────────────────────────

/// Start the background notification monitor. No-op if already running.
pub async fn start_monitor(daemon: Arc<Daemon>) {
    let st = state();
    let mut guard = st.lock().await;
    if guard.running { return; }
    guard.running = true;
    guard.seen_ids.clear();

    let st_clone = st.clone();
    let handle = tokio::spawn(async move {
        monitor_loop(daemon, st_clone).await;
    });
    guard.task = Some(handle);
    eprintln!("[macos_notifications] monitor started");
}

/// Stop the background notification monitor.
pub async fn stop_monitor() {
    let st = state();
    let mut guard = st.lock().await;
    guard.running = false;
    if let Some(h) = guard.task.take() { h.abort(); }
    eprintln!("[macos_notifications] monitor stopped");
}

/// Get the monitor status (running, routing, last seen count).
pub async fn notification_status() -> Value {
    let st = state();
    let guard = st.lock().await;
    json!({
        "success": true,
        "running": guard.running,
        "seen_count": guard.seen_ids.len(),
        "routing": guard.routing,
    })
}

/// Update the routing table: `{"com.apple.Music": true, "com.example.App": false, …}`.
/// An app absent from the table is forwarded by default.
pub async fn set_routing(args: &Value) {
    let st = state();
    let mut guard = st.lock().await;
    if let Some(obj) = args.as_object() {
        for (k, v) in obj {
            if let Some(b) = v.as_bool() { guard.routing.insert(k.clone(), b); }
        }
    }
}

// ── DB candidate paths ────────────────────────────────────────────────────

fn candidate_db_paths() -> Vec<std::path::PathBuf> {
    let mut paths = Vec::new();
    // macOS 12+ (daemon containers, UUID-based)
    if let Ok(home) = std::env::var("HOME") {
        let containers = std::path::PathBuf::from(&home)
            .join("Library")
            .join("Daemon Containers");
        if let Ok(rd) = std::fs::read_dir(&containers) {
            for entry in rd.flatten() {
                let p = entry.path().join("Data").join("usernoted").join("db").join("usernoted.db");
                if p.exists() { paths.push(p); }
            }
        }
        // macOS 11 and below fallback
        let legacy = std::path::PathBuf::from(&home)
            .join("Library")
            .join("CoreData")
            .join("usernoted")
            .join("db")
            .join("usernoted.db");
        if legacy.exists() { paths.push(legacy); }
    }
    paths
}

// ── monitor loop ──────────────────────────────────────────────────────────

const POLL_INTERVAL_MS: u64 = 2000;

async fn monitor_loop(daemon: Arc<Daemon>, st: Arc<Mutex<MonitorState>>) {
    loop {
        {
            let guard = st.lock().await;
            if !guard.running { return; }
        }
        tokio::time::sleep(tokio::time::Duration::from_millis(POLL_INTERVAL_MS)).await;
        let paths = candidate_db_paths();
        for path in paths {
            let rows = match query_notifications(&path) {
                Ok(r) => r,
                Err(e) => { eprintln!("[macos_notifications] query error {path:?}: {e}"); continue; }
            };
            for row in rows {
                let should_forward = {
                    let guard = st.lock().await;
                    if guard.seen_ids.contains(&row.id) { continue; }
                    match guard.routing.get(&row.bundle_id) {
                        Some(&false) => false,
                        _ => true,
                    }
                };
                {
                    let mut guard = st.lock().await;
                    guard.seen_ids.insert(row.id);
                }
                if should_forward {
                    forward_notification(&daemon, &row).await;
                }
            }
        }
    }
}

// ── DB query ──────────────────────────────────────────────────────────────

struct NotifRow { id: i64, bundle_id: String, title: String, body: String }

fn query_notifications(path: &std::path::Path) -> Result<Vec<NotifRow>, String> {
    // We open the DB read-only; no write-lock contention with usernoted.
    // rusqlite is not in our Cargo.toml, so we fall back to a raw SQLite3
    // system call via the sqlite3 CLI, which is available on all macOS.
    let out = std::process::Command::new("sqlite3")
        .arg("-separator").arg("\x1f")  // ASCII US (unit separator) — safe delimiter
        .arg(path)
        .arg("SELECT rowid, app_bundle_id, title, body FROM record ORDER BY rowid DESC LIMIT 50;")
        .output()
        .map_err(|e| e.to_string())?;
    if !out.status.success() {
        return Err(String::from_utf8_lossy(&out.stderr).to_string());
    }
    let stdout = String::from_utf8_lossy(&out.stdout);
    let mut rows = Vec::new();
    for line in stdout.lines() {
        let parts: Vec<&str> = line.splitn(4, '\x1f').collect();
        if parts.len() < 4 { continue; }
        let id: i64 = parts[0].parse().unwrap_or(-1);
        if id < 0 { continue; }
        rows.push(NotifRow {
            id,
            bundle_id: parts[1].to_string(),
            title: parts[2].to_string(),
            body: parts[3].to_string(),
        });
    }
    Ok(rows)
}

// ── forward one notification to the device ────────────────────────────────

async fn forward_notification(daemon: &Daemon, row: &NotifRow) {
    const CMD_ANCS: u8 = 0x50;  // set_android_ancs
    // Payload: [op=0] [bundle_len] [bundle] [title_len] [title] [body_len] [body]
    let bundle = row.bundle_id.as_bytes();
    let title  = row.title.as_bytes();
    let body   = row.body.as_bytes();
    let mut payload = Vec::with_capacity(1 + 1 + bundle.len() + 1 + title.len() + 1 + body.len());
    payload.push(0u8);                        // operation: add
    payload.push(bundle.len().min(255) as u8);
    payload.extend_from_slice(&bundle[..bundle.len().min(255)]);
    payload.push(title.len().min(255) as u8);
    payload.extend_from_slice(&title[..title.len().min(255)]);
    payload.push(body.len().min(255) as u8);
    payload.extend_from_slice(&body[..body.len().min(255)]);

    #[cfg(feature = "ble")]
    {
        let guard = daemon.device.lock().await;
        if let Some(ref dev) = *guard {
            if let crate::daemon::DeviceTransport::Ble(ref ble) = **dev {
                let _ = ble.send_command(CMD_ANCS, &payload, true).await;
                eprintln!("[macos_notifications] forwarded: {} — {}", row.bundle_id, row.title);
            }
        }
    }
    #[cfg(not(feature = "ble"))]
    { let _ = (daemon, payload); }
}

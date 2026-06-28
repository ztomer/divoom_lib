//! macOS notification monitor.
//!
//! Polls the macOS Notification Center SQLite database for new app notifications,
//! parses binary plists using the `plist` crate, routes app bundle IDs to slots 1-14,
//! and forwards them to the connected Divoom device via ANCS `0x50` command.
//!
//! Exposes status events and counters to match Python parity.

use std::collections::HashSet;
use std::sync::Arc;
use serde_json::{json, Value};
use tokio::sync::Mutex;

use crate::daemon::Daemon;

// ── state ─────────────────────────────────────────────────────────────────

struct MonitorState {
    running: bool,
    seen_ids: HashSet<String>,
    task: Option<tokio::task::JoinHandle<()>>,
    seen_count: usize,
    routed_count: usize,
    dropped_count: usize,
    last_seen_date: f64,
    db_error_streak: usize,
    last_db_error: Option<String>,
    rules: Vec<(String, u8)>,
}

impl MonitorState {
    fn new() -> Self {
        MonitorState {
            running: false,
            seen_ids: HashSet::new(),
            task: None,
            seen_count: 0,
            routed_count: 0,
            dropped_count: 0,
            last_seen_date: 0.0,
            db_error_streak: 0,
            last_db_error: None,
            rules: load_routing_rules(),
        }
    }
}

static MONITOR: std::sync::OnceLock<Arc<Mutex<MonitorState>>> = std::sync::OnceLock::new();

fn state() -> Arc<Mutex<MonitorState>> {
    MONITOR.get_or_init(|| Arc::new(Mutex::new(MonitorState::new()))).clone()
}

// ── routing helper ────────────────────────────────────────────────────────

const DEFAULT_ROUTING: &[(&str, u8)] = &[
    ("whatsapp", 6),
    ("facebook", 4),
    ("messenger", 13),
    ("instagram", 2),
    ("twitter", 5),
    ("snapchat", 3),
    ("line", 9),
    ("wechat", 10),
    ("kakao", 1),
    ("qq", 11),
    ("viber", 12),
    ("skype", 8),
    ("mobilesms", 7),
    ("messages", 7),
    ("mail", 7),
    ("com.apple.mail", 7),
];

fn get_routing_path() -> std::path::PathBuf {
    if let Ok(p) = std::env::var("DIVOOM_CONTROL_ROUTING") {
        std::path::PathBuf::from(p)
    } else if let Ok(home) = std::env::var("HOME") {
        std::path::PathBuf::from(home)
            .join(".config")
            .join("divoom-control")
            .join("notification_routing.json")
    } else {
        std::path::PathBuf::from("notification_routing.json")
    }
}

fn load_routing_rules() -> Vec<(String, u8)> {
    let p = get_routing_path();
    if !p.exists() {
        return DEFAULT_ROUTING.iter().map(|(s, t)| (s.to_string(), *t)).collect();
    }
    let data = match std::fs::read_to_string(&p) {
        Ok(s) => s,
        Err(_) => return DEFAULT_ROUTING.iter().map(|(s, t)| (s.to_string(), *t)).collect(),
    };
    let raw: Result<Vec<Vec<serde_json::Value>>, _> = serde_json::from_str(&data);
    match raw {
        Ok(entries) => {
            let mut rules = Vec::new();
            for entry in entries {
                if entry.len() == 2 {
                    if let (Some(s), Some(t)) = (entry[0].as_str(), entry[1].as_u64()) {
                        rules.push((s.to_lowercase(), t as u8));
                    }
                }
            }
            if rules.is_empty() {
                DEFAULT_ROUTING.iter().map(|(s, t)| (s.to_string(), *t)).collect()
            } else {
                rules
            }
        }
        Err(_) => DEFAULT_ROUTING.iter().map(|(s, t)| (s.to_string(), *t)).collect(),
    }
}

fn save_routing_rules(rules: &[(String, u8)]) -> Result<(), String> {
    let p = get_routing_path();
    if let Some(parent) = p.parent() {
        let _ = std::fs::create_dir_all(parent);
    }
    let mut sorted = rules.to_vec();
    sorted.sort_by(|a, b| a.0.cmp(&b.0));

    let json_val = serde_json::Value::Array(
        sorted.iter()
            .map(|(s, t)| serde_json::json!([s, t]))
            .collect()
    );
    let serialized = serde_json::to_string_pretty(&json_val).map_err(|e| e.to_string())? + "\n";
    std::fs::write(&p, serialized).map_err(|e| e.to_string())?;
    Ok(())
}

fn route_app(app_id: &str, rules: &[(String, u8)]) -> Option<u8> {
    if app_id.is_empty() { return None; }
    let a = app_id.to_lowercase();
    for (substr, app_type) in rules {
        if a.contains(substr) {
            return Some(*app_type);
        }
    }
    None
}

// ── DB candidate paths ────────────────────────────────────────────────────

pub fn find_notification_db_path() -> Option<std::path::PathBuf> {
    let home = std::env::var("HOME").ok()?;
    let home_path = std::path::PathBuf::from(&home);

    // 1. Probing DARWIN_USER_DIR
    if let Ok(out) = std::process::Command::new("getconf").arg("DARWIN_USER_DIR").output() {
        if out.status.success() {
            let base_str = String::from_utf8_lossy(&out.stdout).trim().to_string();
            let base = std::path::PathBuf::from(base_str);
            for rel in &["com.apple.notificationcenter/db2/db", "com.apple.usernotifications/db2/db"] {
                let p = base.join(rel);
                if p.exists() {
                    return Some(p);
                }
            }
        }
    }

    // 2. Probing Group Containers path
    let p = home_path.join("Library/Group Containers/group.com.apple.usernoted/db2/db");
    if p.exists() {
        return Some(p);
    }

    None
}

// ── public API ────────────────────────────────────────────────────────────

/// Start the background notification monitor.
pub async fn start_monitor(daemon: Arc<Daemon>) {
    let st = state();
    let mut guard = st.lock().await;
    if guard.running { return; }
    
    // Probe database existence and accessibility
    let db_path = match find_notification_db_path() {
        Some(p) => p,
        None => {
            guard.last_db_error = Some("macOS Notification Center DB not found".to_string());
            guard.db_error_streak = 5;
            let _ = daemon.tx.send(status_event_payload(&guard));
            return;
        }
    };
    
    // Test if we can open and read
    match rusqlite::Connection::open_with_flags(&db_path, rusqlite::OpenFlags::SQLITE_OPEN_READ_ONLY) {
        Ok(conn) => {
            if let Err(e) = conn.execute("SELECT 1", []) {
                guard.last_db_error = Some(format!("Database read failed (FDA permission?): {e}"));
                guard.db_error_streak = 5;
                let _ = daemon.tx.send(status_event_payload(&guard));
                return;
            }
        }
        Err(e) => {
            guard.last_db_error = Some(format!("Database open failed: {e}"));
            guard.db_error_streak = 5;
            let _ = daemon.tx.send(status_event_payload(&guard));
            return;
        }
    }

    guard.running = true;
    guard.seen_ids.clear();
    guard.last_seen_date = initial_max_delivered_date(&db_path);
    guard.db_error_streak = 0;
    guard.last_db_error = None;

    let st_clone = st.clone();
    let daemon_clone = daemon.clone();
    let handle = tokio::spawn(async move {
        monitor_loop(daemon_clone, st_clone, db_path).await;
    });
    guard.task = Some(handle);
    eprintln!("[macos_notifications] monitor started");

    let _ = daemon.tx.send(status_event_payload(&guard));
}

/// Stop the background notification monitor.
pub async fn stop_monitor() {
    let st = state();
    let mut guard = st.lock().await;
    guard.running = false;
    if let Some(h) = guard.task.take() { h.abort(); }
    eprintln!("[macos_notifications] monitor stopped");
}

fn status_event_payload(guard: &MonitorState) -> Value {
    let state_str = if guard.running {
        if guard.db_error_streak >= 5 { "error" } else { "active" }
    } else {
        "idle"
    };
    let mut ev = json!({
        "type": "status",
        "state": state_str,
        "counters": {
            "seen": guard.seen_count,
            "routed": guard.routed_count,
            "dropped": guard.dropped_count,
        }
    });
    if let Some(ref err) = guard.last_db_error {
        if guard.db_error_streak >= 5 {
            ev["error"] = json!(err);
        }
    }
    ev
}

pub async fn status_event() -> Value {
    let st = state();
    let guard = st.lock().await;
    status_event_payload(&guard)
}

pub async fn notification_status() -> Value {
    let st = state();
    let guard = st.lock().await;
    let mut res = status_event_payload(&guard);
    res["success"] = json!(true);
    res
}

pub async fn set_routing(args: &Value) -> Value {
    let rules_val = match args.get("rules") {
        Some(v) => v,
        None => return json!({"success": false, "error": "set_routing requires 'rules'"}),
    };
    let mut new_rules = Vec::new();
    if let Some(arr) = rules_val.as_array() {
        for entry in arr {
            if let Some(pair) = entry.as_array() {
                if pair.len() == 2 {
                    if let (Some(s), Some(t)) = (pair[0].as_str(), pair[1].as_u64()) {
                        new_rules.push((s.to_lowercase(), t as u8));
                    }
                }
            }
        }
    }

    if let Err(e) = save_routing_rules(&new_rules) {
        return json!({"success": false, "error": format!("failed to save routing: {}", e)});
    }

    let st = state();
    let mut guard = st.lock().await;
    guard.rules = new_rules;

    json!({"success": true})
}

// ── DB query helpers ──────────────────────────────────────────────────────

fn initial_max_delivered_date(db_path: &std::path::Path) -> f64 {
    let conn = match rusqlite::Connection::open_with_flags(
        db_path,
        rusqlite::OpenFlags::SQLITE_OPEN_READ_ONLY,
    ) {
        Ok(c) => c,
        Err(_) => return 0.0,
    };
    let mut stmt = match conn.prepare("SELECT MAX(delivered_date) FROM record") {
        Ok(s) => s,
        Err(_) => return 0.0,
    };
    let res: Result<f64, _> = stmt.query_row([], |row| row.get(0));
    res.unwrap_or(0.0)
}

fn fetch_new_records(db_path: &std::path::Path, last_seen: f64) -> Result<Vec<(Vec<u8>, f64)>, String> {
    let conn = rusqlite::Connection::open_with_flags(
        db_path,
        rusqlite::OpenFlags::SQLITE_OPEN_READ_ONLY,
    ).map_err(|e| e.to_string())?;

    let mut stmt = conn.prepare(
        "SELECT data, delivered_date FROM record WHERE delivered_date > ? ORDER BY delivered_date ASC"
    ).map_err(|e| e.to_string())?;

    let rows = stmt.query_map([last_seen], |row| {
        Ok((row.get::<_, Vec<u8>>(0)?, row.get::<_, f64>(1)?))
    }).map_err(|e| e.to_string())?;

    let mut res = Vec::new();
    for r in rows {
        if let Ok(item) = r {
            res.push(item);
        }
    }
    Ok(res)
}

fn parse_notification_record(raw: &[u8]) -> Option<(String, String, String)> {
    let val: plist::Value = plist::from_bytes(raw).ok()?;
    let dict = val.as_dictionary()?;
    
    let app = dict.get("app").and_then(|v| v.as_string()).unwrap_or("").to_string();
    
    let req = dict.get("req").and_then(|v| v.as_dictionary());
    let title = req.and_then(|d| d.get("titl")).and_then(|v| v.as_string()).unwrap_or("").to_string();
    let body = req.and_then(|d| d.get("body")).and_then(|v| v.as_string()).unwrap_or("").to_string();
    
    Some((app, title, body))
}

// ── monitor loop ──────────────────────────────────────────────────────────

const POLL_INTERVAL_MS: u64 = 1000;

async fn monitor_loop(daemon: Arc<Daemon>, st: Arc<Mutex<MonitorState>>, db_path: std::path::PathBuf) {
    loop {
        {
            let guard = st.lock().await;
            if !guard.running { return; }
        }
        tokio::time::sleep(tokio::time::Duration::from_millis(POLL_INTERVAL_MS)).await;

        let (last_seen, rules) = {
            let guard = st.lock().await;
            (guard.last_seen_date, guard.rules.clone())
        };

        match fetch_new_records(&db_path, last_seen) {
            Ok(records) => {
                let mut guard = st.lock().await;
                guard.db_error_streak = 0;
                guard.last_db_error = None;

                for (raw, delivered) in records {
                    if delivered > guard.last_seen_date {
                        guard.last_seen_date = delivered;
                    }
                    guard.seen_count += 1;

                    let parsed = match parse_notification_record(&raw) {
                        Some(p) => p,
                        None => {
                            guard.dropped_count += 1;
                            continue;
                        }
                    };

                    let (app, title, body) = parsed;
                    let app_type = match route_app(&app, &rules) {
                        Some(t) => t,
                        None => {
                            guard.dropped_count += 1;
                            continue;
                        }
                    };

                    let dup_key = format!("{}:{}:{}", delivered, app, title);
                    if guard.seen_ids.contains(&dup_key) {
                        guard.dropped_count += 1;
                        continue;
                    }
                    guard.seen_ids.insert(dup_key);

                    let text = if !title.is_empty() {
                        title.split('\n').next().unwrap_or("").trim().to_string()
                    } else if !body.is_empty() {
                        body.split('\n').next().unwrap_or("").trim().to_string()
                    } else {
                        "".to_string()
                    };

                    let routed = forward_notification(&daemon, app_type, &text).await;
                    if routed {
                        guard.routed_count += 1;
                    } else {
                        guard.dropped_count += 1;
                    }

                    let notif_ev = json!({
                        "type": "notification",
                        "app_type": app_type as u64,
                        "title": title,
                        "body": body,
                        "routed": routed
                    });
                    let _ = daemon.tx.send(notif_ev);

                    let _ = daemon.tx.send(status_event_payload(&guard));
                }
            }
            Err(e) => {
                let mut guard = st.lock().await;
                guard.db_error_streak += 1;
                guard.last_db_error = Some(e.clone());
                if guard.db_error_streak == 1 {
                    eprintln!("[macos_notifications] query error (streak 1): {e}");
                }
                if guard.db_error_streak >= 5 {
                    let _ = daemon.tx.send(status_event_payload(&guard));
                }
            }
        }
    }
}

// ── forward one notification to the device ────────────────────────────────

async fn forward_notification(daemon: &Daemon, app_type: u8, text: &str) -> bool {
    let mut payload = Vec::new();
    if text.is_empty() {
        let wire = if app_type >= 8 { app_type + 1 } else { app_type };
        payload.push(wire);
    } else {
        let mut text_bytes = text.as_bytes().to_vec();
        if text_bytes.len() > 128 {
            text_bytes.truncate(128);
        }
        payload.push(app_type);
        payload.push(text_bytes.len() as u8);
        payload.extend_from_slice(&text_bytes);
    }

    #[cfg(feature = "ble")]
    {
        let guard = daemon.device.lock().await;
        if let Some(ref dev) = *guard {
            match &**dev {
                crate::daemon::DeviceTransport::Ble(ref ble) => {
                    return ble.send_command(0x50, &payload, true).await.is_ok();
                }
                crate::daemon::DeviceTransport::Spp(ref spp) => {
                    return spp.send_command(0x50, &payload, true).await.is_ok();
                }
                crate::daemon::DeviceTransport::Lan(_) => {}
            }
        }
    }
    #[cfg(not(feature = "ble"))]
    { let _ = (daemon, payload); }
    false
}

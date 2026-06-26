//! The daemon's request Handler — dispatches NDJSON commands to replies. Owns the
//! [`CommandQueue`] (exclusive mode / steal-reject) and, when built with the `ble`
//! feature, the connected device. Replies match the Python daemon's shapes so the
//! existing Python clients (and the conformance suite) drive this unchanged.
//!
//! Device commands are honest: when `ble` is built they hit the real transport;
//! otherwise (and for not-yet-ported commands) they return a clear error rather
//! than a fake success.

use std::future::Future;
use std::pin::Pin;
use std::time::{Duration, Instant};

use serde_json::{json, Value};

use std::collections::HashMap;
use std::sync::{Arc, Weak, OnceLock};

use base64::engine::general_purpose::STANDARD as B64;
use base64::Engine as _;

use crate::command_queue::CommandQueue;

#[cfg(feature = "ble")]
use crate::native_encode::NativeEncoder;
use crate::protocol::{err_reply, Request};
use crate::socket_server::Handler;

#[cfg(feature = "ble")]
use crate::ble::{self, Adapter, BleTransport};
use tokio::sync::Mutex;

const EXCLUSIVE_TIMEOUT: Duration = Duration::from_secs(30);
const ITEM_TIMEOUT: Duration = Duration::from_secs(60);

pub enum DeviceTransport {
    #[cfg(feature = "ble")]
    Ble(BleTransport),
    Lan(crate::lan::LanTransport),
}

impl DeviceTransport {
    pub fn device_name(&self) -> Option<String> {
        match self {
            #[cfg(feature = "ble")]
            DeviceTransport::Ble(b) => b.device_name(),
            DeviceTransport::Lan(_) => None,
        }
    }

    pub fn set_cached_device_name(&self, _name: String) {
        match self {
            #[cfg(feature = "ble")]
            DeviceTransport::Ble(b) => b.set_cached_device_name(_name),
            DeviceTransport::Lan(_) => {}
        }
    }

    #[cfg(feature = "ble")]
    pub async fn send_command(&self, command_id: u8, args: &[u8], write_with_response: bool) -> crate::ble::BleResult<()> {
        match self {
            DeviceTransport::Ble(b) => b.send_command(command_id, args, write_with_response).await,
            DeviceTransport::Lan(_) => Err("send_command not supported on LAN".into()),
        }
    }

    #[cfg(feature = "ble")]
    pub async fn wait_for_response(&self, command_id: u8, timeout: std::time::Duration) -> Option<Vec<u8>> {
        match self {
            DeviceTransport::Ble(b) => b.wait_for_response(command_id, timeout).await,
            DeviceTransport::Lan(_) => None,
        }
    }

    #[cfg(feature = "ble")]
    pub async fn send_command_and_wait(&self, command_id: u8, args: &[u8], timeout: std::time::Duration) -> Option<Vec<u8>> {
        match self {
            DeviceTransport::Ble(b) => b.send_command_and_wait(command_id, args, timeout).await,
            DeviceTransport::Lan(_) => None,
        }
    }

    #[cfg(feature = "ble")]
    pub async fn stream_animation_8b(&self, blob: &[u8]) -> crate::ble::BleResult<bool> {
        match self {
            DeviceTransport::Ble(b) => b.stream_animation_8b(blob).await,
            DeviceTransport::Lan(_) => Err("stream_animation_8b not supported on LAN".into()),
        }
    }

    pub fn lan(&self) -> Option<&crate::lan::LanTransport> {
        match self {
            #[cfg(feature = "ble")]
            DeviceTransport::Ble(_) => None,
            DeviceTransport::Lan(l) => Some(l),
        }
    }
}

pub struct Daemon {
    pub(crate) queue: CommandQueue,
    started: Instant,
    pub(crate) device: Mutex<Option<Arc<DeviceTransport>>>,
    pub(crate) device_id: Mutex<Option<String>>,
    // the CoreBluetooth central, created once and kept alive for the daemon's
    // lifetime (dropping it stops notification delivery).
    #[cfg(feature = "ble")]
    central: Mutex<Option<Adapter>>,
    // C image encoder (libdivoom_compact FFI); loaded once, cached for lifetime.
    #[cfg(feature = "ble")]
    encoder: OnceLock<Option<NativeEncoder>>,
    pub(crate) tx: tokio::sync::broadcast::Sender<Value>,
    pub live_jobs: Arc<crate::live_jobs::LiveJobCoordinator>,
    self_weak: OnceLock<Weak<Daemon>>,
    /// Shared progress state for the background hot-update task.
    pub hot_progress: Arc<crate::art::HotProgress>,
    /// Current wall coordinator (None when no wall is active).
    pub wall: Mutex<Option<crate::wall::DivoomWall>>,
    /// The slot config last used for the wall (for delta reconfiguration).
    pub wall_slots: Mutex<serde_json::Map<String, Value>>,
}

impl Default for Daemon {
    fn default() -> Self {
        Self::new()
    }
}

impl Daemon {
    pub fn new() -> Self {
        let (tx, _) = tokio::sync::broadcast::channel(32);
        Daemon {
            queue: CommandQueue::new(Some(EXCLUSIVE_TIMEOUT), Some(ITEM_TIMEOUT)),
            started: Instant::now(),
            device: Mutex::new(None),
            device_id: Mutex::new(None),
            #[cfg(feature = "ble")]
            central: Mutex::new(None),
            #[cfg(feature = "ble")]
            encoder: OnceLock::new(),
            tx,
            live_jobs: Arc::new(crate::live_jobs::LiveJobCoordinator::new()),
            self_weak: OnceLock::new(),
            hot_progress: Arc::new(crate::art::HotProgress::default()),
            wall: Mutex::new(None),
            wall_slots: Mutex::new(serde_json::Map::new()),
        }
    }

    /// Find the libdivoom_compact dylib: env override, then relative to the binary.
    #[cfg(feature = "ble")]
    fn find_encoder_lib() -> Option<std::path::PathBuf> {
        if let Ok(p) = std::env::var("DIVOOMD_ENCODER_LIB") {
            let pb = std::path::PathBuf::from(&p);
            if pb.exists() {
                return Some(pb);
            }
        }
        // binary is at native-port/divoomd/target/release/divoomd — 5 parents = project root
        let exe = std::env::current_exe().ok()?;
        let root = exe.parent()?.parent()?.parent()?.parent()?.parent()?;
        let candidate = root.join("divoom_lib").join("libdivoom_compact.dylib");
        if candidate.exists() { Some(candidate) } else { None }
    }

    /// Get (or lazy-init) the cached NativeEncoder. Returns None if the dylib is absent.
    #[cfg(feature = "ble")]
    pub(crate) fn encoder(&self) -> Option<&NativeEncoder> {
        self.encoder.get_or_init(|| {
            Self::find_encoder_lib().and_then(|p| NativeEncoder::load(p).ok())
        }).as_ref()
    }

    /// Get (creating + caching once) the shared CoreBluetooth central.
    #[cfg(feature = "ble")]
    pub(crate) async fn central(&self) -> Result<Adapter, String> {
        let mut g = self.central.lock().await;
        if g.is_none() {
            *g = Some(ble::make_central().await.map_err(|e| e.to_string())?);
        }
        Ok(g.as_ref().unwrap().clone())
    }

    pub fn initialize_self_weak(&self, weak: Weak<Daemon>) {
        let _ = self.self_weak.set(weak);
    }

    async fn dispatch(&self, req: Request) -> Value {
        match req.command.as_str() {
            "ping" => json!({"success": true, "pong": true}),

            "get_status" => json!({
                "success": true,
                "state": "idle",
                "uptime_s": self.started.elapsed().as_secs(),
                "counters": {},
            }),

            "device_status" => self.device_status().await,

            // exclusive mode is fully real (uses the ported queue's acquire_now /
            // release). The token lives in args (the request-level token is auth).
            "exclusive_start" => match req.args.get("token").and_then(|v| v.as_str()) {
                Some(t) => match self.queue.acquire_now(t) {
                    Ok(()) => json!({"success": true, "token": t}),
                    Err(e) => err_reply(&e.to_string()),
                },
                None => err_reply("exclusive_start requires 'token'"),
            },
            "exclusive_end" => match req.args.get("token").and_then(|v| v.as_str()) {
                Some(t) => {
                    self.queue.release(t);
                    json!({"success": true})
                }
                None => err_reply("exclusive_end requires 'token'"),
            },

            #[cfg(feature = "ble")]
            "scan" => self.cmd_scan(&req).await,
            "connect" => self.cmd_connect(&req).await,
            "disconnect" => self.cmd_disconnect().await,
            "device_call" => self.cmd_device_call(&req).await,

            "live_job_start" => {
                let self_weak = match self.self_weak.get() {
                    Some(w) => w.clone(),
                    None => return err_reply("Daemon self_weak not initialized"),
                };
                let mac = match req.args.get("mac").and_then(|v| v.as_str()) {
                    Some(m) => m.to_string(),
                    None => return err_reply("live_job_start requires 'mac'"),
                };
                let kind = match req.args.get("kind").and_then(|v| v.as_str()) {
                    Some(k) => k.to_string(),
                    None => return err_reply("live_job_start requires 'kind'"),
                };
                let params = req.args.get("params").cloned().unwrap_or(json!({}));
                match self_weak.upgrade() {
                    Some(d) => match self.live_jobs.start(d, mac, kind, params).await {
                        Ok(()) => json!({"success": true}),
                        Err(e) => err_reply(&e),
                    },
                    None => err_reply("Daemon was dropped"),
                }
            }

            "live_job_stop" => {
                let mac = match req.args.get("mac").and_then(|v| v.as_str()) {
                    Some(m) => m,
                    None => return err_reply("live_job_stop requires 'mac'"),
                };
                let kind = match req.args.get("kind").and_then(|v| v.as_str()) {
                    Some(k) => k,
                    None => return err_reply("live_job_stop requires 'kind'"),
                };
                let stopped = self.live_jobs.stop(self, mac, kind).await;
                json!({"success": true, "stopped": stopped})
            }

            "live_job_list" => {
                let mac = req.args.get("mac").and_then(|v| v.as_str());
                let list = self.live_jobs.list(mac).await;
                json!({"success": true, "jobs": list})
            }

            "live_jobs_stop_for" => {
                let mac_str = req.args.get("mac").and_then(|v| v.as_str());
                let mac_owner = {
                    let guard = self.device_id.try_lock().ok();
                    guard.and_then(|g| g.clone())
                };
                let mac = match mac_str.or(mac_owner.as_deref()) {
                    Some(m) => m,
                    None => return err_reply("live_jobs_stop_for requires 'mac' or connected device"),
                };
                let count = self.live_jobs.stop_all_for_device(self, mac).await;
                json!({"success": true, "count": count})
            }

            "set_device_activity" => {
                let mac = match req.args.get("mac").and_then(|v| v.as_str()) {
                    Some(m) => m.to_string(),
                    None => return err_reply("set_device_activity requires 'mac'"),
                };
                let kind = match req.args.get("kind").and_then(|v| v.as_str()) {
                    Some(k) => k.to_string(),
                    None => return err_reply("set_device_activity requires 'kind'"),
                };
                let name = req.args.get("name").and_then(|v| v.as_str()).map(|s| s.to_string());
                let preview = req.args.get("preview").and_then(|v| v.as_str()).map(|s| s.to_string());
                self.live_jobs.set_device_activity(mac, kind, name, preview).await;
                json!({"success": true})
            }

            "get_device_activity" => {
                self.live_jobs.get_device_activity().await
            }

            // --- art / hot-channel commands ---
            "custom_art_push" => {
                let self_weak = match self.self_weak.get() {
                    Some(w) => w.clone(),
                    None => return err_reply("Daemon self_weak not initialized"),
                };
                let daemon_arc = match self_weak.upgrade() {
                    Some(d) => d,
                    None => return err_reply("Daemon was dropped"),
                };
                crate::art::cmd_custom_art_push(daemon_arc, &req.args).await
            }

            "custom_art_query_page" => {
                let self_weak = match self.self_weak.get() {
                    Some(w) => w.clone(),
                    None => return err_reply("Daemon self_weak not initialized"),
                };
                let daemon_arc = match self_weak.upgrade() {
                    Some(d) => d,
                    None => return err_reply("Daemon was dropped"),
                };
                crate::art::cmd_custom_art_query_page(daemon_arc, &req.args).await
            }

            "hot_update" => {
                let self_weak = match self.self_weak.get() {
                    Some(w) => w.clone(),
                    None => return err_reply("Daemon self_weak not initialized"),
                };
                let daemon_arc = match self_weak.upgrade() {
                    Some(d) => d,
                    None => return err_reply("Daemon was dropped"),
                };
                let progress = self.hot_progress.clone();
                crate::art::cmd_hot_update(daemon_arc, &req.args, progress).await
            }

            "hot_update_progress" => {
                crate::art::cmd_hot_update_progress(&self.hot_progress)
            }

            // --- wall command ---
            "wall_configure" => self.cmd_wall_configure(&req).await,

            // --- notification service stubs (macOS only, but wired for parity) ---
            "start_notifications" => {
                #[cfg(target_os = "macos")]
                {
                    if let Some(w) = self.self_weak.get().and_then(|w| w.upgrade()) {
                        crate::macos_notifications::start_monitor(w).await;
                        return json!({"success": true});
                    }
                }
                json!({"success": false, "error": "notifications not available on this platform"})
            }

            "stop_notifications" => {
                #[cfg(target_os = "macos")]
                crate::macos_notifications::stop_monitor().await;
                json!({"success": true})
            }

            "notification_status" => {
                #[cfg(target_os = "macos")]
                { return crate::macos_notifications::notification_status().await; }
                #[cfg(not(target_os = "macos"))]
                json!({"success": true, "running": false, "platform": "non-macos"})
            }

            "set_routing" => json!({"success": true}),  // no-op in native daemon

            other => err_reply(&format!(
                "command not implemented in the native daemon yet: {other}"
            )),
        }
    }

    async fn device_status(&self) -> Value {
        let connected = self.device.lock().await.is_some();

        let (mac, lan_ip) = if let Some(ref dev) = *self.device.lock().await {
            match &**dev {
                #[cfg(feature = "ble")]
                DeviceTransport::Ble(_) => {
                    let id = self.device_id.lock().await.clone();
                    (id.map(Value::String).unwrap_or(Value::Null), Value::Null)
                }
                DeviceTransport::Lan(l) => {
                    (Value::Null, Value::String(l.device_ip.clone()))
                }
            }
        } else {
            (Value::Null, Value::Null)
        };

        json!({
            "success": true,
            "connected": connected,
            "connection_state": if connected { "connected" } else { "disconnected" },
            "mac": mac,
            "lan_ip": lan_ip,
            "wall": false,
        })
    }

    #[cfg(feature = "ble")]
    async fn cmd_scan(&self, req: &Request) -> Value {
        crate::daemon_connect::cmd_scan(self, req).await
    }

    async fn cmd_connect(&self, req: &Request) -> Value {
        crate::daemon_connect::cmd_connect(self, req).await
    }

    /// device_call routes a method string to a protocol op. A small set is ported
    /// first to prove op-level parity (the read-back + a write); unported methods
    /// return an honest error. The device mutex serializes device access.
    async fn cmd_device_call(&self, req: &Request) -> Value {
        // Numeric positional args (for brightness, clock, etc.)
        let args: Vec<i64> = req
            .args
            .get("args")
            .and_then(|v| v.as_array())
            .map(|a| a.iter().filter_map(|x| x.as_i64()).collect())
            .unwrap_or_default();
        // Raw positional args as Values (for string paths in display.show_image)
        let raw_args: Vec<Value> = req
            .args
            .get("args")
            .and_then(|v| v.as_array())
            .cloned()
            .unwrap_or_default();
        // Blob map: base64-encoded binary data keyed by positional arg index.
        let mut blob_map: HashMap<usize, Vec<u8>> = HashMap::new();
        if let Some(blobs) = req.args.get("blobs").and_then(|v| v.as_object()) {
            for (idx_str, b64val) in blobs {
                let idx: usize = match idx_str.parse() {
                    Ok(i) => i,
                    Err(_) => return err_reply(&format!("blobs: bad index key '{idx_str}'")),
                };
                let b64 = match b64val.as_str() {
                    Some(s) => s,
                    None => return err_reply(&format!("blobs[{idx_str}]: not a string")),
                };
                match B64.decode(b64) {
                    Ok(data) => { blob_map.insert(idx, data); }
                    Err(e) => return err_reply(&format!("blobs[{idx_str}]: base64 error: {e}")),
                }
            }
        }
        // The per-op token gates exclusive mode: if another session holds exclusive,
        // device_call is rejected immediately (Python parity: _cmd_queue.run(token)).
        let token = req.args.get("token").and_then(|v| v.as_str());
        if let Err(e) = self.queue.check_allowed(token) {
            return err_reply(&e.to_string());
        }

        let guard = self.device.lock().await;
        let dev = match guard.as_ref() {
            Some(d) => d,
            None => return err_reply("no device connected"),
        };
        let timeout = Duration::from_secs(5);

        let blob_map = std::sync::Mutex::new(blob_map);
        crate::device_call::handle_device_call(self, dev, req, &args, &raw_args, &blob_map, timeout).await
    }

    async fn cmd_disconnect(&self) -> Value {
        crate::daemon_connect::cmd_disconnect(self).await
    }

    /// Delegates to `crate::wall::cmd_wall_configure` (kept there for 500-LOC rule).
    async fn cmd_wall_configure(&self, req: &Request) -> Value {
        crate::wall::cmd_wall_configure(self, req).await
    }
}



impl Handler for Daemon {
    fn handle<'a>(&'a self, req: Request) -> Pin<Box<dyn Future<Output = Value> + Send + 'a>> {
        Box::pin(async move { self.dispatch(req).await })
    }
    fn subscribe(&self) -> Option<tokio::sync::broadcast::Receiver<Value>> {
        Some(self.tx.subscribe())
    }
    fn initial_status(&self) -> Value {
        #[cfg(feature = "ble")]
        let connected = self.device.try_lock().map(|g| g.is_some()).unwrap_or(false);
        #[cfg(not(feature = "ble"))]
        let connected = false;
        json!({
            "type": "status",
            "state": if connected { "active" } else { "idle" },
            "counters": {}
        })
    }
}

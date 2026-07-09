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

use std::sync::{Arc, Weak, OnceLock};

use crate::command_queue::CommandQueue;

use crate::native_encode::NativeEncoder;
use crate::protocol::{err_reply, Request};
use crate::socket_server::Handler;

#[cfg(feature = "ble")]
use crate::ble::{self, Adapter};
use tokio::sync::Mutex;

const EXCLUSIVE_TIMEOUT: Duration = Duration::from_secs(30);
const ITEM_TIMEOUT: Duration = Duration::from_secs(60);

pub use crate::transport::DeviceTransport;

pub struct Daemon {
    pub(crate) queue: CommandQueue,
    started: Instant,
    pub(crate) device: Mutex<Option<Arc<DeviceTransport>>>,
    pub(crate) device_id: Mutex<Option<String>>,
    // the CoreBluetooth central, created once and kept alive for the daemon's
    // lifetime (dropping it stops notification delivery).
    #[cfg(feature = "ble")]
    central: Mutex<Option<Adapter>>,
    /// True while a scan is running. A scan drives the one shared adapter's
    /// start/stop; two overlapping scans would clobber each other (one's
    /// stop_scan ends the other early → truncated results), so cmd_scan rejects
    /// a concurrent scan. Mirrors the Python daemon's single-scan model.
    #[cfg(feature = "ble")]
    pub(crate) scanning: std::sync::atomic::AtomicBool,
    /// Last scan's completion time + result. A scan within `MIN_RESCAN_INTERVAL`
    /// of the last returns this cached list instead of hitting the radio —
    /// back-to-back scans trip CoreBluetooth's scan-frequency throttle (which
    /// silently returns 0 devices until it resets).
    #[cfg(feature = "ble")]
    pub(crate) last_scan: Mutex<Option<(Instant, Vec<Value>)>>,
    // C image encoder (libdivoom_compact FFI); loaded once, cached for lifetime.
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
    /// Fired by the `shutdown` command; the main loop awaits this to exit cleanly
    /// (socket unlink) the same way it does for SIGINT/SIGTERM.
    pub shutdown: Arc<tokio::sync::Notify>,
}

impl Default for Daemon {
    fn default() -> Self {
        Self::new()
    }
}

impl Daemon {
    pub fn new() -> Self {
        Self::new_with_mac(None)
    }

    pub fn new_with_mac(default_mac: Option<String>) -> Self {
        let (tx, _) = tokio::sync::broadcast::channel(32);
        Daemon {
            queue: CommandQueue::new(Some(EXCLUSIVE_TIMEOUT), Some(ITEM_TIMEOUT)),
            started: Instant::now(),
            device: Mutex::new(None),
            device_id: Mutex::new(default_mac),
            #[cfg(feature = "ble")]
            central: Mutex::new(None),
            #[cfg(feature = "ble")]
            scanning: std::sync::atomic::AtomicBool::new(false),
            #[cfg(feature = "ble")]
            last_scan: Mutex::new(None),
            encoder: OnceLock::new(),
            tx,
            live_jobs: Arc::new(crate::live_jobs::LiveJobCoordinator::new()),
            self_weak: OnceLock::new(),
            hot_progress: Arc::new(crate::art::HotProgress::default()),
            wall: Mutex::new(None),
            wall_slots: Mutex::new(serde_json::Map::new()),
            shutdown: Arc::new(tokio::sync::Notify::new()),
        }
    }

    /// Get (or lazy-init) the cached NativeEncoder. Returns None if the dylib is absent.
    pub(crate) fn encoder(&self) -> Option<&NativeEncoder> {
        self.encoder.get_or_init(|| {
            crate::native_encode::find_encoder_lib().and_then(|p| NativeEncoder::load(p).ok())
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

    /// On shutdown, stop any BLE scan still running on the cached central so we
    /// don't leave a leaked scan session with bluetoothd. Left uncleaned across
    /// rapid restarts, those stale sessions trip the OS scan-frequency throttle
    /// (scans then silently return 0 devices until Bluetooth is toggled).
    #[cfg(feature = "ble")]
    pub async fn stop_scan_cleanup(&self) {
        use btleplug::api::Central;
        if let Some(adapter) = self.central.lock().await.as_ref() {
            let _ = adapter.stop_scan().await;
        }
    }

    pub fn initialize_self_weak(&self, weak: Weak<Daemon>) {
        let _ = self.self_weak.set(weak);
    }

    pub(crate) async fn dispatch(&self, req: Request) -> Value {
        match req.command.as_str() {
            "ping" => json!({"success": true, "pong": true}),

            "get_status" => {
                #[cfg(target_os = "macos")]
                let status = crate::macos_notifications::status_event().await;
                #[cfg(not(target_os = "macos"))]
                let status = json!({
                    "state": "idle",
                    "counters": {"seen": 0, "routed": 0, "dropped": 0}
                });

                let mut res = json!({
                    "success": true,
                    "uptime_s": self.started.elapsed().as_secs(),
                });
                if let Some(obj) = res.as_object_mut() {
                    if let Some(st_obj) = status.as_object() {
                        for (k, v) in st_obj {
                            obj.insert(k.clone(), v.clone());
                        }
                    }
                }
                res
            },

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

            // Graceful stop (Python-daemon parity): signal the main loop, which
            // unlinks the socket and exits after letting this reply flush.
            "shutdown" => {
                self.shutdown.notify_one();
                json!({"success": true, "shutting_down": true})
            }

            "probe_lan" => crate::daemon_connect::probe_lan(self).await,

            "sync_artwork" => crate::sync_artwork::sync_artwork(self, &req.args).await,

            "get_animated_preview" => crate::sync_artwork::get_animated_preview(&req.args).await,

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
                        let mut status = crate::macos_notifications::status_event().await;
                        status["success"] = json!(true);
                        return status;
                    }
                }
                json!({
                    "success": false,
                    "error": "notifications not available on this platform",
                    "state": "idle",
                    "counters": {"seen": 0, "routed": 0, "dropped": 0},
                    "unsupported": true
                })
            }

            "stop_notifications" => {
                #[cfg(target_os = "macos")]
                {
                    crate::macos_notifications::stop_monitor().await;
                    let mut status = crate::macos_notifications::status_event().await;
                    status["success"] = json!(true);
                    return status;
                }
                #[cfg(not(target_os = "macos"))]
                json!({
                    "success": true,
                    "state": "idle",
                    "counters": {"seen": 0, "routed": 0, "dropped": 0}
                })
            }

            "notification_status" => {
                #[cfg(target_os = "macos")]
                { return crate::macos_notifications::notification_status().await; }
                #[cfg(not(target_os = "macos"))]
                json!({
                    "success": true,
                    "state": "idle",
                    "counters": {"seen": 0, "routed": 0, "dropped": 0}
                })
            }

            "set_routing" => {
                #[cfg(target_os = "macos")]
                { return crate::macos_notifications::set_routing(&req.args).await; }
                #[cfg(not(target_os = "macos"))]
                json!({"success": true})
            }

            "fetch_gallery" | "save_credentials" | "get_credentials"
            | "get_cached_credentials" => {
                crate::cloud_cmds::handle(&req.command, &req).await
            }

            other => err_reply(&format!(
                "command not implemented in the native daemon yet: {other}"
            )),
        }
    }

    async fn device_status(&self) -> Value {
        let connected = self.device.lock().await.is_some();
        let id_val = self.device_id.lock().await.clone();

        let (mac, lan_ip) = if let Some(ref dev) = *self.device.lock().await {
            match &**dev {
                #[cfg(feature = "ble")]
                DeviceTransport::Ble(_) => {
                    (id_val.map(Value::String).unwrap_or(Value::Null), Value::Null)
                }
                DeviceTransport::Spp(_) => {
                    (id_val.map(Value::String).unwrap_or(Value::Null), Value::Null)
                }
                DeviceTransport::Lan(l) => {
                    (Value::Null, Value::String(l.device_ip.clone()))
                }
                DeviceTransport::Mock(_) => {
                    (id_val.map(Value::String).unwrap_or(Value::Null), Value::Null)
                }
            }
        } else {
            (id_val.map(Value::String).unwrap_or(Value::Null), Value::Null)
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

        crate::device_call::handle_device_call(self, dev, req, timeout).await
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

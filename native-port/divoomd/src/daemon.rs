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

use std::sync::OnceLock;

use crate::command_queue::CommandQueue;
use crate::native_encode::NativeEncoder;
use crate::protocol::{err_reply, Request};
use crate::socket_server::Handler;

#[cfg(feature = "ble")]
use crate::ble::{self, Adapter, BleTransport};
#[cfg(feature = "ble")]
use tokio::sync::Mutex;

const EXCLUSIVE_TIMEOUT: Duration = Duration::from_secs(30);
const ITEM_TIMEOUT: Duration = Duration::from_secs(60);

pub struct Daemon {
    queue: CommandQueue,
    started: Instant,
    #[cfg(feature = "ble")]
    device: Mutex<Option<BleTransport>>,
    #[cfg(feature = "ble")]
    device_id: Mutex<Option<String>>,
    // the CoreBluetooth central, created once and kept alive for the daemon's
    // lifetime (dropping it stops notification delivery).
    #[cfg(feature = "ble")]
    central: Mutex<Option<Adapter>>,
    // C image encoder (libdivoom_compact FFI); loaded once, cached for lifetime.
    encoder: OnceLock<Option<NativeEncoder>>,
}

impl Default for Daemon {
    fn default() -> Self {
        Self::new()
    }
}

impl Daemon {
    pub fn new() -> Self {
        Daemon {
            queue: CommandQueue::new(Some(EXCLUSIVE_TIMEOUT), Some(ITEM_TIMEOUT)),
            started: Instant::now(),
            #[cfg(feature = "ble")]
            device: Mutex::new(None),
            #[cfg(feature = "ble")]
            device_id: Mutex::new(None),
            #[cfg(feature = "ble")]
            central: Mutex::new(None),
            encoder: OnceLock::new(),
        }
    }

    /// Find the libdivoom_compact dylib: env override, then relative to the binary.
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
    fn encoder(&self) -> Option<&NativeEncoder> {
        self.encoder.get_or_init(|| {
            Self::find_encoder_lib().and_then(|p| NativeEncoder::load(p).ok())
        }).as_ref()
    }

    /// Get (creating + caching once) the shared CoreBluetooth central.
    #[cfg(feature = "ble")]
    async fn central(&self) -> Result<Adapter, String> {
        let mut g = self.central.lock().await;
        if g.is_none() {
            *g = Some(ble::make_central().await.map_err(|e| e.to_string())?);
        }
        Ok(g.as_ref().unwrap().clone())
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
            #[cfg(feature = "ble")]
            "connect" => self.cmd_connect(&req).await,
            #[cfg(feature = "ble")]
            "disconnect" => self.cmd_disconnect().await,
            #[cfg(feature = "ble")]
            "device_call" => self.cmd_device_call(&req).await,

            other => err_reply(&format!(
                "command not implemented in the native daemon yet: {other}"
            )),
        }
    }

    async fn device_status(&self) -> Value {
        #[cfg(feature = "ble")]
        {
            let connected = self.device.lock().await.is_some();
            let id = self.device_id.lock().await.clone();
            return json!({
                "success": true,
                "connected": connected,
                "connection_state": if connected { "connected" } else { "disconnected" },
                "mac": id,
                "lan_ip": Value::Null,
                "wall": false,
            });
        }
        #[cfg(not(feature = "ble"))]
        json!({
            "success": true,
            "connected": false,
            "connection_state": "disconnected",
            "mac": Value::Null,
            "lan_ip": Value::Null,
            "wall": false,
        })
    }

    #[cfg(feature = "ble")]
    async fn cmd_scan(&self, req: &Request) -> Value {
        let timeout = req.args.get("timeout").and_then(|v| v.as_f64()).unwrap_or(8.0);
        let central = match self.central().await {
            Ok(c) => c,
            Err(e) => return err_reply(&format!("scan failed: {e}")),
        };
        match ble::scan(&central, Duration::from_secs_f64(timeout)).await {
            Ok(devs) => json!({
                "success": true,
                "devices": devs.iter()
                    .map(|d| json!({"name": d.name, "address": d.id}))
                    .collect::<Vec<_>>(),
            }),
            Err(e) => err_reply(&format!("scan failed: {e}")),
        }
    }

    #[cfg(feature = "ble")]
    async fn cmd_connect(&self, req: &Request) -> Value {
        let id = req.args.get("mac").or_else(|| req.args.get("id")).and_then(|v| v.as_str());
        let id = match id {
            Some(i) => i.to_string(),
            None => return err_reply("connect_device requires 'mac'"),
        };
        let central = match self.central().await {
            Ok(c) => c,
            Err(e) => return err_reply(&format!("connect failed: {e}")),
        };
        match BleTransport::connect(&central, &id).await {
            Ok(t) => {
                *self.device.lock().await = Some(t);
                *self.device_id.lock().await = Some(id.clone());
                json!({
                    "success": true,
                    "connected": true,
                    "connection_state": "connected",
                    "mac": id,
                })
            }
            Err(e) => err_reply(&format!("connect failed: {e}")),
        }
    }

    /// device_call routes a method string to a protocol op. A small set is ported
    /// first to prove op-level parity (the read-back + a write); unported methods
    /// return an honest error. The device mutex serializes device access.
    #[cfg(feature = "ble")]
    async fn cmd_device_call(&self, req: &Request) -> Value {
        let method = match req.args.get("method").and_then(|v| v.as_str()) {
            Some(m) => m,
            None => return err_reply("device_call requires 'method'"),
        };
        let args: Vec<i64> = req
            .args
            .get("args")
            .and_then(|v| v.as_array())
            .map(|a| a.iter().filter_map(|x| x.as_i64()).collect())
            .unwrap_or_default();
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

        match method {
            // get-light-mode (0x46): brightness is payload[6] (matches _read_brightness_once)
            "device.get_brightness" | "get_brightness" => {
                match dev.send_command_and_wait(0x46, &[], timeout).await {
                    Some(p) if p.len() >= 7 => json!({"success": true, "result": p[6] as i64}),
                    // honest null on a short/absent reply (matches the Python read path)
                    _ => json!({"success": true, "result": Value::Null}),
                }
            }
            // set brightness (0x74), arg is the value 0..100
            "device.set_brightness" | "set_brightness" => {
                let val = args.first().copied().unwrap_or(0).clamp(0, 100) as u8;
                match dev.send_command(0x74, &[val], true).await {
                    Ok(()) => json!({"success": true, "result": true}),
                    Err(e) => err_reply(&format!("set_brightness failed: {e}")),
                }
            }
            // show clock face via set-light-mode (0x45): the 10-byte environmental
            // packet [env=0, 24h=1, clock_mode, clock_active=1, weather, temp,
            // calendar, R, G, B], matching display.show_clock (clock 0..15, white).
            "device.show_clock" | "show_clock" => {
                let clock = args.first().copied().unwrap_or(0).clamp(0, 15) as u8;
                let payload = [0u8, 1, clock, 1, 0, 0, 0, 0xFF, 0xFF, 0xFF];
                match dev.send_command(0x45, &payload, true).await {
                    Ok(()) => json!({"success": true, "result": true}),
                    Err(e) => err_reply(&format!("show_clock failed: {e}")),
                }
            }
            // Push a single-frame animation via the 0x8B 3-phase streaming protocol.
            // Args: w (int), h (int), time_ms (int, default 100),
            //       rgb (array of u8 integers, length w*h*3).
            // The RGB bytes are encoded via the C FFI encoder (libdivoom_compact) into
            // the AA-format blob, then streamed to the device matching stream_animation_8b.
            "device.show_image" | "show_image" => {
                let w = req.args.get("w").and_then(|v| v.as_i64()).unwrap_or(16) as i32;
                let h = req.args.get("h").and_then(|v| v.as_i64()).unwrap_or(16) as i32;
                let time_ms =
                    req.args.get("time_ms").and_then(|v| v.as_i64()).unwrap_or(100) as u16;
                let rgb: Vec<u8> = match req.args.get("rgb").and_then(|v| v.as_array()) {
                    Some(a) => a.iter().filter_map(|x| x.as_u64().map(|n| n as u8)).collect(),
                    None => return err_reply("show_image requires 'rgb' (array of u8)"),
                };
                let expected = (w * h * 3) as usize;
                if rgb.len() != expected {
                    return err_reply(&format!(
                        "show_image: rgb.len()={} expected w*h*3={expected}",
                        rgb.len()
                    ));
                }
                let enc = match self.encoder() {
                    Some(e) => e,
                    None => return err_reply(
                        "encoder not available (set DIVOOMD_ENCODER_LIB or ensure \
                         divoom_lib/libdivoom_compact.dylib is in the project root)"
                    ),
                };
                let blob = match enc.encode_animation_frame(&rgb, w, h, time_ms) {
                    Some(b) => b,
                    None => return err_reply("encode_animation_frame failed"),
                };
                match dev.stream_animation_8b(&blob).await {
                    Ok(true) => json!({"success": true, "result": true}),
                    Ok(false) => err_reply("stream_animation_8b: empty blob"),
                    Err(e) => err_reply(&format!("stream_animation_8b failed: {e}")),
                }
            }
            m => err_reply(&format!("device_call method not ported yet: {m}")),
        }
    }

    #[cfg(feature = "ble")]
    async fn cmd_disconnect(&self) -> Value {
        if let Some(t) = self.device.lock().await.take() {
            let _ = t.disconnect().await;
        }
        *self.device_id.lock().await = None;
        json!({"success": true})
    }
}

impl Handler for Daemon {
    fn handle<'a>(&'a self, req: Request) -> Pin<Box<dyn Future<Output = Value> + Send + 'a>> {
        Box::pin(async move { self.dispatch(req).await })
    }
}

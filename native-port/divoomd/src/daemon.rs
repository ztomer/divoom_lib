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
use std::sync::OnceLock;

use base64::engine::general_purpose::STANDARD as B64;
use base64::Engine as _;

use crate::command_queue::CommandQueue;
use crate::image_proc;
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
    tx: tokio::sync::broadcast::Sender<Value>,
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
            #[cfg(feature = "ble")]
            device: Mutex::new(None),
            #[cfg(feature = "ble")]
            device_id: Mutex::new(None),
            #[cfg(feature = "ble")]
            central: Mutex::new(None),
            encoder: OnceLock::new(),
            tx,
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
                let _ = self.tx.send(json!({
                    "type": "status",
                    "state": "active",
                    "counters": {}
                }));
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
        // Mirrors Python device_call's blobs mechanism: the client encodes binary
        // payloads (e.g. image files) as base64 here rather than writing temp files
        // on the server side.
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

        match method {
            "device.get_device_name" | "get_device_name" => {
                if let Some(name) = dev.device_name() {
                    if !name.trim().is_empty() {
                        return json!({"success": true, "result": name});
                    }
                }
                match dev.send_command_and_wait(0x76, &[], timeout).await {
                    Some(p) if p.len() >= 1 => {
                        let name_len = p[0] as usize;
                        if p.len() >= 1 + name_len {
                            let name_bytes = &p[1..1 + name_len];
                            match std::str::from_utf8(name_bytes) {
                                Ok(name) => {
                                    dev.set_cached_device_name(name.to_string());
                                    json!({"success": true, "result": name})
                                }
                                Err(_) => json!({"success": true, "result": Value::Null}),
                            }
                        } else {
                            json!({"success": true, "result": Value::Null})
                        }
                    }
                    _ => json!({"success": true, "result": Value::Null}),
                }
            }
            "device.set_device_name" | "set_device_name" => {
                let name = raw_args.first()
                    .and_then(|v| v.as_str())
                    .or_else(|| req.args.get("kwargs").and_then(|v| v.get("name")).and_then(|v| v.as_str()))
                    .unwrap_or("");
                let mut name_bytes = name.as_bytes().to_vec();
                if name_bytes.len() > 16 {
                    name_bytes.truncate(16);
                }
                let mut payload = Vec::with_capacity(1 + name_bytes.len());
                payload.push(name_bytes.len() as u8);
                payload.extend_from_slice(&name_bytes);
                match dev.send_command(0x75, &payload, true).await {
                    Ok(()) => {
                        if let Ok(utf8_name) = std::str::from_utf8(&name_bytes) {
                            dev.set_cached_device_name(utf8_name.to_string());
                        }
                        json!({"success": true, "result": true})
                    }
                    Err(e) => err_reply(&format!("set_device_name failed: {e}")),
                }
            }
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
            // display.show_image(path_or_blob, [time_ms]) — the DaemonDeviceProxy path.
            // The Python DaemonClient sends image bytes as blobs["0"] (base64); the
            // daemon decodes in-memory and processes via the image_proc module (port of
            // Python process_image). show_design (0x45 [0x05,0×9]) runs first, matching
            // Python's show_image which always calls self.show_design() before streaming.
            "display.show_image" => {
                let size = req.args
                    .get("kwargs").and_then(|v| v.get("size")).and_then(|v| v.as_u64())
                    .unwrap_or(16) as u32;
                let default_time_ms = raw_args.get(1)
                    .and_then(|v| v.as_u64())
                    .unwrap_or(100) as u16;

                // Resolve image bytes: prefer blob[0], fall back to reading the path arg.
                let img_data: Vec<u8> = if let Some(data) = blob_map.remove(&0) {
                    data
                } else {
                    let path = match raw_args.get(0).and_then(|v| v.as_str()) {
                        Some(p) => p,
                        None => return err_reply("display.show_image requires a path or blob[0]"),
                    };
                    match std::fs::read(path) {
                        Ok(d) => d,
                        Err(e) => return err_reply(&format!("display.show_image: read {path}: {e}")),
                    }
                };

                // show_design first: switch device to custom-art / design channel (0x45 [0x05,0×9])
                if let Err(e) = dev.send_command(0x45, &[0x05, 0, 0, 0, 0, 0, 0, 0, 0, 0], false).await {
                    return err_reply(&format!("show_design failed: {e}"));
                }

                // Decode and resize frames (CPU-bound; run off the async thread)
                let frames = match tokio::task::spawn_blocking(move || {
                    image_proc::process_image_bytes(img_data, size, default_time_ms)
                }).await {
                    Ok(Ok(f)) => f,
                    Ok(Err(e)) => return err_reply(&format!("image decode: {e}")),
                    Err(e) => return err_reply(&format!("image decode task: {e}")),
                };

                // Build animation blob: concatenate encoded frame bodies
                let enc = match self.encoder() {
                    Some(e) => e,
                    None => return err_reply("encoder not available (DIVOOMD_ENCODER_LIB)"),
                };
                let mut blob = Vec::new();
                for (rgb, w, h, t) in &frames {
                    let frame_body = if *w == 32 && *h == 32 {
                        enc.encode_animation_frame_32(rgb, *w, *h, *t)
                    } else {
                        enc.encode_animation_frame(rgb, *w, *h, *t)
                    };
                    match frame_body {
                        Some(b) => blob.extend_from_slice(&b),
                        None => return err_reply(&format!("encode_animation_frame failed (frame {w}x{h})")),
                    }
                }

                match dev.stream_animation_8b(&blob).await {
                    Ok(true) => json!({"success": true, "result": true}),
                    Ok(false) => err_reply("stream_animation_8b: empty blob"),
                    Err(e) => err_reply(&format!("stream_animation_8b failed: {e}")),
                }
            }
            // display.show_clock(clock=0, twentyfour=True, weather=False, temp=False,
            //   calendar=False, color=None) — proxy path for show_clock.
            // Maps to the same 0x45 environmental packet as device.show_clock, with
            // optional kwargs for 24h mode, weather/temp/calendar overlays, and color.
            "display.show_clock" => {
                let kw = req.args.get("kwargs");
                let clock = kw.and_then(|v| v.get("clock")).and_then(|v| v.as_i64())
                    .or_else(|| args.first().copied())
                    .unwrap_or(0).clamp(0, 15) as u8;
                let twentyfour = kw.and_then(|v| v.get("twentyfour")).and_then(|v| v.as_bool()).unwrap_or(true);
                let weather = kw.and_then(|v| v.get("weather")).and_then(|v| v.as_bool()).unwrap_or(false);
                let temp = kw.and_then(|v| v.get("temp")).and_then(|v| v.as_bool()).unwrap_or(false);
                let calendar = kw.and_then(|v| v.get("calendar")).and_then(|v| v.as_bool()).unwrap_or(false);
                let [r, g, b] = kw
                    .and_then(|v| v.get("color")).and_then(|v| v.as_str())
                    .and_then(parse_hex_color)
                    .unwrap_or([0xFF, 0xFF, 0xFF]);
                let payload = [
                    0u8, // env = 0 (clock channel)
                    twentyfour as u8,
                    clock,
                    1u8, // clock_active
                    weather as u8,
                    temp as u8,
                    calendar as u8,
                    r, g, b,
                ];
                match dev.send_command(0x45, &payload, true).await {
                    Ok(()) => json!({"success": true, "result": true}),
                    Err(e) => err_reply(&format!("display.show_clock failed: {e}")),
                }
            }
            // display.show_design() — switch to custom-art / design channel.
            // 0x45 [0x05, 0×9]: payload[0]=0x05 selects the "design" channel.
            "display.show_design" => {
                match dev.send_command(0x45, &[0x05, 0, 0, 0, 0, 0, 0, 0, 0, 0], false).await {
                    Ok(()) => json!({"success": true, "result": true}),
                    Err(e) => err_reply(&format!("display.show_design failed: {e}")),
                }
            }
            // display.get_brightness / display.set_brightness — aliases to device.*
            "display.get_brightness" => {
                match dev.send_command_and_wait(0x46, &[], timeout).await {
                    Some(p) if p.len() >= 7 => json!({"success": true, "result": p[6] as i64}),
                    _ => json!({"success": true, "result": Value::Null}),
                }
            }
            "display.set_brightness" => {
                let val = args.first().copied()
                    .or_else(|| req.args.get("kwargs").and_then(|v| v.get("brightness")).and_then(|v| v.as_i64()))
                    .unwrap_or(50).clamp(0, 100) as u8;
                match dev.send_command(0x74, &[val], true).await {
                    Ok(()) => json!({"success": true, "result": true}),
                    Err(e) => err_reply(&format!("display.set_brightness failed: {e}")),
                }
            }
            // display.show_light(color, brightness, power) — solid-color light mode.
            // 0x45 payload: [0x01, R, G, B, brightness, 0x00, power_byte, 0x00, 0x00, 0x00].
            // color: JSON array [R,G,B] or hex string "#RRGGBB". power defaults to True.
            "display.show_light" | "light.show_light" | "show_light" => {
                let [r, g, b] = color_from_arg(&raw_args, &req.args).unwrap_or([0xFF, 0xFF, 0xFF]);
                let brightness = args.get(1).copied()
                    .or_else(|| req.args.get("kwargs").and_then(|v| v.get("brightness")).and_then(|v| v.as_i64()))
                    .unwrap_or(100).clamp(0, 100) as u8;
                let power = req.args.get("kwargs").and_then(|v| v.get("power")).and_then(|v| v.as_bool()).unwrap_or(true);
                let payload = [0x01u8, r, g, b, brightness, 0x00, power as u8, 0x00, 0x00, 0x00];
                match dev.send_command(0x45, &payload, true).await {
                    Ok(()) => json!({"success": true, "result": true}),
                    Err(e) => err_reply(&format!("display.show_light failed: {e}")),
                }
            }
            // music.set_volume / set_volume
            "music.set_volume" | "set_volume" => {
                let val = args.first().copied()
                    .or_else(|| req.args.get("kwargs").and_then(|v| v.get("volume")).and_then(|v| v.as_i64()))
                    .unwrap_or(0).clamp(0, 15) as u8;
                match dev.send_command(0x08, &[val], true).await {
                    Ok(()) => json!({"success": true, "result": true}),
                    Err(e) => err_reply(&format!("set_volume failed: {e}")),
                }
            }
            // music.get_volume / get_volume
            "music.get_volume" | "get_volume" => {
                match dev.send_command_and_wait(0x09, &[], timeout).await {
                    Some(p) if p.len() >= 1 => json!({"success": true, "result": p[0] as i64}),
                    _ => json!({"success": true, "result": Value::Null}),
                }
            }
            // radio.set_radio_frequency / set_radio_frequency / set_radio / radio.set_radio
            "radio.set_radio_frequency" | "set_radio_frequency" | "radio.set_radio" | "set_radio" => {
                let freq = args.first().copied()
                    .or_else(|| req.args.get("kwargs").and_then(|v| v.get("frequency")).and_then(|v| v.as_i64()))
                    .or_else(|| req.args.get("kwargs").and_then(|v| v.get("freq_x10")).and_then(|v| v.as_i64()))
                    .unwrap_or(875) as u16;
                let payload = freq.to_le_bytes();
                match dev.send_command(0x61, &payload, true).await {
                    Ok(()) => json!({"success": true, "result": true}),
                    Err(e) => err_reply(&format!("set_radio_frequency failed: {e}")),
                }
            }
            // device.set_low_power_switch / set_low_power_switch / device.set_low_power / set_low_power
            "device.set_low_power_switch" | "set_low_power_switch" | "device.set_low_power" | "set_low_power" => {
                let on_off_val = raw_args.first()
                    .or_else(|| req.args.get("kwargs").and_then(|v| v.get("on_off")))
                    .or_else(|| req.args.get("kwargs").and_then(|v| v.get("enabled")));
                let on_off = match on_off_val {
                    Some(Value::Bool(b)) => if *b { 1 } else { 0 },
                    Some(Value::Number(n)) => n.as_i64().unwrap_or(0).clamp(0, 1) as u8,
                    _ => args.first().copied().unwrap_or(0).clamp(0, 1) as u8,
                };
                match dev.send_command(0xb2, &[on_off], true).await {
                    Ok(()) => json!({"success": true, "result": true}),
                    Err(e) => err_reply(&format!("set_low_power_switch failed: {e}")),
                }
            }
            // device.get_low_power_switch / get_low_power_switch / device.get_low_power / get_low_power
            "device.get_low_power_switch" | "get_low_power_switch" | "device.get_low_power" | "get_low_power" => {
                match dev.send_command_and_wait(0xb3, &[], timeout).await {
                    Some(p) if p.len() >= 1 => json!({"success": true, "result": p[0] as i64}),
                    _ => json!({"success": true, "result": Value::Null}),
                }
            }
            // device.set_auto_power_off / set_auto_power_off / sound.set_auto_power_off
            "device.set_auto_power_off" | "set_auto_power_off" | "sound.set_auto_power_off" => {
                let minutes = args.first().copied()
                    .or_else(|| req.args.get("kwargs").and_then(|v| v.get("minutes")).and_then(|v| v.as_i64()))
                    .unwrap_or(0) as u16;
                let payload = minutes.to_le_bytes();
                match dev.send_command(0xab, &payload, true).await {
                    Ok(()) => json!({"success": true, "result": true}),
                    Err(e) => err_reply(&format!("set_auto_power_off failed: {e}")),
                }
            }
            // device.get_auto_power_off / get_auto_power_off / sound.get_auto_power_off
            "device.get_auto_power_off" | "get_auto_power_off" | "sound.get_auto_power_off" => {
                match dev.send_command_and_wait(0xac, &[], timeout).await {
                    Some(p) if p.len() >= 2 => {
                        let minutes = u16::from_le_bytes([p[0], p[1]]) as i64;
                        json!({"success": true, "result": minutes})
                    }
                    _ => json!({"success": true, "result": Value::Null}),
                }
            }
            // scoreboard.set_scoreboard / set_scoreboard
            "scoreboard.set_scoreboard" | "set_scoreboard" => {
                let on_off = args.first().copied()
                    .or_else(|| req.args.get("kwargs").and_then(|v| v.get("on_off")).and_then(|v| v.as_i64()))
                    .unwrap_or(0) as u8;
                let red_score = args.get(1).copied()
                    .or_else(|| req.args.get("kwargs").and_then(|v| v.get("red_score")).and_then(|v| v.as_i64()))
                    .unwrap_or(0).clamp(0, 999) as u16;
                let blue_score = args.get(2).copied()
                    .or_else(|| req.args.get("kwargs").and_then(|v| v.get("blue_score")).and_then(|v| v.as_i64()))
                    .unwrap_or(0).clamp(0, 999) as u16;
                let mut payload = Vec::with_capacity(6);
                payload.push(1u8); // TOOL_TYPE_SCORE
                payload.push(on_off);
                payload.extend_from_slice(&red_score.to_le_bytes());
                payload.extend_from_slice(&blue_score.to_le_bytes());
                match dev.send_command(0x72, &payload, true).await {
                    Ok(()) => json!({"success": true, "result": true}),
                    Err(e) => err_reply(&format!("set_scoreboard failed: {e}")),
                }
            }
            // scoreboard.get_scoreboard / get_scoreboard
            "scoreboard.get_scoreboard" | "get_scoreboard" => {
                match dev.send_command_and_wait(0x71, &[1], timeout).await {
                    Some(p) if p.len() >= 5 => json!({
                        "success": true,
                        "result": {
                            "on_off": p[0] as i64,
                            "red_score": u16::from_le_bytes([p[1], p[2]]) as i64,
                            "blue_score": u16::from_le_bytes([p[3], p[4]]) as i64,
                        }
                    }),
                    _ => json!({"success": true, "result": Value::Null}),
                }
            }
            // timer.set_timer / set_timer
            "timer.set_timer" | "set_timer" => {
                let ctrl_flag = args.first().copied()
                    .or_else(|| req.args.get("kwargs").and_then(|v| v.get("ctrl_flag")).and_then(|v| v.as_i64()))
                    .unwrap_or(0) as u8;
                let payload = [0u8, ctrl_flag]; // TOOL_TYPE_TIMER = 0
                match dev.send_command(0x72, &payload, true).await {
                    Ok(()) => json!({"success": true, "result": true}),
                    Err(e) => err_reply(&format!("set_timer failed: {e}")),
                }
            }
            // timer.get_timer / get_timer
            "timer.get_timer" | "get_timer" => {
                match dev.send_command_and_wait(0x71, &[0], timeout).await {
                    Some(p) if p.len() >= 1 => json!({
                        "success": true,
                        "result": {
                            "status": p[0] as i64,
                        }
                    }),
                    _ => json!({"success": true, "result": Value::Null}),
                }
            }
            // countdown.set_countdown / set_countdown
            "countdown.set_countdown" | "set_countdown" => {
                let ctrl_flag = args.first().copied()
                    .or_else(|| req.args.get("kwargs").and_then(|v| v.get("ctrl_flag")).and_then(|v| v.as_i64()))
                    .unwrap_or(0) as u8;
                let minutes = args.get(1).copied()
                    .or_else(|| req.args.get("kwargs").and_then(|v| v.get("minutes")).and_then(|v| v.as_i64()))
                    .unwrap_or(0) as u8;
                let seconds = args.get(2).copied()
                    .or_else(|| req.args.get("kwargs").and_then(|v| v.get("seconds")).and_then(|v| v.as_i64()))
                    .unwrap_or(0) as u8;
                let payload = [3u8, ctrl_flag, minutes, seconds]; // TOOL_TYPE_COUNTDOWN = 3
                match dev.send_command(0x72, &payload, true).await {
                    Ok(()) => json!({"success": true, "result": true}),
                    Err(e) => err_reply(&format!("set_countdown failed: {e}")),
                }
            }
            // countdown.get_countdown / get_countdown
            "countdown.get_countdown" | "get_countdown" => {
                match dev.send_command_and_wait(0x71, &[3], timeout).await {
                    Some(p) if p.len() >= 3 => json!({
                        "success": true,
                        "result": {
                            "status": p[0] as i64,
                            "minutes": p[1] as i64,
                            "seconds": p[2] as i64,
                        }
                    }),
                    _ => json!({"success": true, "result": Value::Null}),
                }
            }
            // noise.set_noise / set_noise
            "noise.set_noise" | "set_noise" => {
                let ctrl_flag = args.first().copied()
                    .or_else(|| req.args.get("kwargs").and_then(|v| v.get("ctrl_flag")).and_then(|v| v.as_i64()))
                    .unwrap_or(0) as u8;
                let payload = [2u8, ctrl_flag]; // TOOL_TYPE_NOISE = 2
                match dev.send_command(0x72, &payload, true).await {
                    Ok(()) => json!({"success": true, "result": true}),
                    Err(e) => err_reply(&format!("set_noise failed: {e}")),
                }
            }
            // noise.get_noise / get_noise
            "noise.get_noise" | "get_noise" => {
                match dev.send_command_and_wait(0x71, &[2], timeout).await {
                    Some(p) if p.len() >= 1 => json!({
                        "success": true,
                        "result": {
                            "status": p[0] as i64,
                        }
                    }),
                    _ => json!({"success": true, "result": Value::Null}),
                }
            }
            // device.show_notification / show_notification
            "device.show_notification" | "show_notification" | "notification.show_notification" => {
                let app_type = args.first().copied()
                    .or_else(|| req.args.get("kwargs").and_then(|v| v.get("app_type")).and_then(|v| v.as_i64()))
                    .unwrap_or(1) as u8;
                let wire = if app_type >= 8 { app_type + 1 } else { app_type };
                match dev.send_command(0x50, &[wire], true).await {
                    Ok(()) => json!({"success": true, "result": true}),
                    Err(e) => err_reply(&format!("show_notification failed: {e}")),
                }
            }
            // device.show_notification_text / show_notification_text
            "device.show_notification_text" | "show_notification_text" | "notification.show_notification_text" => {
                let app_type = args.first().copied()
                    .or_else(|| req.args.get("kwargs").and_then(|v| v.get("app_type")).and_then(|v| v.as_i64()))
                    .unwrap_or(1) as u8;
                let text = raw_args.get(1)
                    .and_then(|v| v.as_str())
                    .or_else(|| req.args.get("kwargs").and_then(|v| v.get("text")).and_then(|v| v.as_str()))
                    .unwrap_or("");
                let mut text_bytes = text.as_bytes().to_vec();
                if text_bytes.len() > 128 {
                    text_bytes.truncate(128);
                }
                let mut payload = Vec::with_capacity(2 + text_bytes.len());
                payload.push(app_type);
                payload.push(text_bytes.len() as u8);
                payload.extend_from_slice(&text_bytes);
                match dev.send_command(0x50, &payload, true).await {
                    Ok(()) => json!({"success": true, "result": true}),
                    Err(e) => err_reply(&format!("show_notification_text failed: {e}")),
                }
            }
            // alarm.get_alarm_time / get_alarm_time
            "alarm.get_alarm_time" | "get_alarm_time" => {
                match dev.send_command_and_wait(0x42, &[], timeout).await {
                    Some(p) => {
                        let record_len = 10;
                        let count = std::cmp::min(10, p.len() / record_len);
                        let mut alarms = Vec::with_capacity(count);
                        for i in 0..count {
                            let start = i * record_len;
                            let block = &p[start..start + record_len];
                            alarms.push(json!({
                                "status": block[1] as i64,
                                "hour": block[2] as i64,
                                "minute": block[3] as i64,
                                "week": block[4] as i64,
                                "mode": block[5] as i64,
                                "trigger_mode": block[6] as i64,
                                "fm_freq": u16::from_le_bytes([block[7], block[8]]) as i64,
                                "volume": block[9] as i64,
                            }));
                        }
                        json!({"success": true, "result": alarms})
                    }
                    _ => json!({"success": true, "result": Value::Null}),
                }
            }
            // alarm.set_alarm / set_alarm
            "alarm.set_alarm" | "set_alarm" => {
                let alarm_index = args.first().copied()
                    .or_else(|| req.args.get("kwargs").and_then(|v| v.get("alarm_index")).and_then(|v| v.as_i64()))
                    .unwrap_or(0) as u8;
                let status = args.get(1).copied()
                    .or_else(|| req.args.get("kwargs").and_then(|v| v.get("status")).and_then(|v| v.as_i64()))
                    .unwrap_or(0) as u8;
                let hour = args.get(2).copied()
                    .or_else(|| req.args.get("kwargs").and_then(|v| v.get("hour")).and_then(|v| v.as_i64()))
                    .unwrap_or(0) as u8;
                let minute = args.get(3).copied()
                    .or_else(|| req.args.get("kwargs").and_then(|v| v.get("minute")).and_then(|v| v.as_i64()))
                    .unwrap_or(0) as u8;
                let week = args.get(4).copied()
                    .or_else(|| req.args.get("kwargs").and_then(|v| v.get("week")).and_then(|v| v.as_i64()))
                    .unwrap_or(0) as u8;
                let mode = args.get(5).copied()
                    .or_else(|| req.args.get("kwargs").and_then(|v| v.get("mode")).and_then(|v| v.as_i64()))
                    .unwrap_or(0) as u8;
                let trigger_mode = args.get(6).copied()
                    .or_else(|| req.args.get("kwargs").and_then(|v| v.get("trigger_mode")).and_then(|v| v.as_i64()))
                    .unwrap_or(0) as u8;
                let fm_freq = args.get(7).copied()
                    .or_else(|| req.args.get("kwargs").and_then(|v| v.get("fm_freq")).and_then(|v| v.as_i64()))
                    .unwrap_or(0) as u16;
                let volume = args.get(8).copied()
                    .or_else(|| req.args.get("kwargs").and_then(|v| v.get("volume")).and_then(|v| v.as_i64()))
                    .unwrap_or(0) as u8;

                let mut payload = Vec::with_capacity(10);
                payload.push(alarm_index);
                payload.push(status);
                payload.push(hour);
                payload.push(minute);
                payload.push(week);
                payload.push(mode);
                payload.push(trigger_mode);
                payload.extend_from_slice(&fm_freq.to_le_bytes());
                payload.push(volume);

                match dev.send_command(0x43, &payload, true).await {
                    Ok(()) => json!({"success": true, "result": true}),
                    Err(e) => err_reply(&format!("set_alarm failed: {e}")),
                }
            }
            // alarm.set_alarm_gif / set_alarm_gif
            "alarm.set_alarm_gif" | "set_alarm_gif" => {
                let alarm_index = args.first().copied()
                    .or_else(|| req.args.get("kwargs").and_then(|v| v.get("alarm_index")).and_then(|v| v.as_i64()))
                    .unwrap_or(0) as u8;
                let total_length = args.get(1).copied()
                    .or_else(|| req.args.get("kwargs").and_then(|v| v.get("total_length")).and_then(|v| v.as_i64()))
                    .unwrap_or(0) as u16;
                let gif_id = args.get(2).copied()
                    .or_else(|| req.args.get("kwargs").and_then(|v| v.get("gif_id")).and_then(|v| v.as_i64()))
                    .unwrap_or(0) as u8;
                let data: Vec<u8> = raw_args.get(3)
                    .and_then(|v| v.as_array())
                    .or_else(|| req.args.get("kwargs").and_then(|v| v.get("data")).and_then(|v| v.as_array()))
                    .map(|a| a.iter().filter_map(|x| x.as_u64().map(|n| n as u8)).collect())
                    .unwrap_or_default();

                let mut payload = Vec::with_capacity(4 + data.len());
                payload.push(alarm_index);
                payload.extend_from_slice(&total_length.to_le_bytes());
                payload.push(gif_id);
                payload.extend_from_slice(&data);

                match dev.send_command(0x51, &payload, true).await {
                    Ok(()) => json!({"success": true, "result": true}),
                    Err(e) => err_reply(&format!("set_alarm_gif failed: {e}")),
                }
            }
            // alarm.get_memorial_time / get_memorial_time
            "alarm.get_memorial_time" | "get_memorial_time" => {
                match dev.send_command_and_wait(0x53, &[], timeout).await {
                    Some(p) => {
                        let record_len = 39;
                        let count = std::cmp::min(10, p.len() / record_len);
                        let mut memorials = Vec::with_capacity(count);
                        for i in 0..count {
                            let start = i * record_len;
                            let block = &p[start..start + record_len];
                            let title = String::from_utf8_lossy(&block[7..39])
                                .trim_end_matches('\0')
                                .to_string();
                            memorials.push(json!({
                                "dialy_id": block[0] as i64,
                                "on_off": block[1] as i64,
                                "month": block[2] as i64,
                                "day": block[3] as i64,
                                "hour": block[4] as i64,
                                "minute": block[5] as i64,
                                "have_flag": block[6] as i64,
                                "title_name": title,
                            }));
                        }
                        json!({"success": true, "result": memorials})
                    }
                    _ => json!({"success": true, "result": Value::Null}),
                }
            }
            // alarm.set_memorial_time / set_memorial_time
            "alarm.set_memorial_time" | "set_memorial_time" => {
                let dialy_id = args.first().copied()
                    .or_else(|| req.args.get("kwargs").and_then(|v| v.get("dialy_id")).and_then(|v| v.as_i64()))
                    .unwrap_or(0) as u8;
                let on_off = args.get(1).copied()
                    .or_else(|| req.args.get("kwargs").and_then(|v| v.get("on_off")).and_then(|v| v.as_i64()))
                    .unwrap_or(0) as u8;
                let month = args.get(2).copied()
                    .or_else(|| req.args.get("kwargs").and_then(|v| v.get("month")).and_then(|v| v.as_i64()))
                    .unwrap_or(0) as u8;
                let day = args.get(3).copied()
                    .or_else(|| req.args.get("kwargs").and_then(|v| v.get("day")).and_then(|v| v.as_i64()))
                    .unwrap_or(0) as u8;
                let hour = args.get(4).copied()
                    .or_else(|| req.args.get("kwargs").and_then(|v| v.get("hour")).and_then(|v| v.as_i64()))
                    .unwrap_or(0) as u8;
                let minute = args.get(5).copied()
                    .or_else(|| req.args.get("kwargs").and_then(|v| v.get("minute")).and_then(|v| v.as_i64()))
                    .unwrap_or(0) as u8;
                let have_flag = args.get(6).copied()
                    .or_else(|| req.args.get("kwargs").and_then(|v| v.get("have_flag")).and_then(|v| v.as_i64()))
                    .unwrap_or(0) as u8;
                let title_name = raw_args.get(7)
                    .and_then(|v| v.as_str())
                    .or_else(|| req.args.get("kwargs").and_then(|v| v.get("title_name")).and_then(|v| v.as_str()))
                    .unwrap_or("");

                let mut title_bytes = title_name.as_bytes().to_vec();
                if title_bytes.len() > 32 {
                    title_bytes.truncate(32);
                }
                while title_bytes.len() < 32 {
                    title_bytes.push(0);
                }

                let mut payload = Vec::with_capacity(39);
                payload.push(dialy_id);
                payload.push(on_off);
                payload.push(month);
                payload.push(day);
                payload.push(hour);
                payload.push(minute);
                payload.push(have_flag);
                payload.extend_from_slice(&title_bytes);

                match dev.send_command(0x54, &payload, true).await {
                    Ok(()) => json!({"success": true, "result": true}),
                    Err(e) => err_reply(&format!("set_memorial_time failed: {e}")),
                }
            }
            // alarm.set_memorial_gif / set_memorial_gif
            "alarm.set_memorial_gif" | "set_memorial_gif" => {
                let memorial_index = args.first().copied()
                    .or_else(|| req.args.get("kwargs").and_then(|v| v.get("memorial_index")).and_then(|v| v.as_i64()))
                    .unwrap_or(0) as u8;
                let total_length = args.get(1).copied()
                    .or_else(|| req.args.get("kwargs").and_then(|v| v.get("total_length")).and_then(|v| v.as_i64()))
                    .unwrap_or(0) as u16;
                let gif_id = args.get(2).copied()
                    .or_else(|| req.args.get("kwargs").and_then(|v| v.get("gif_id")).and_then(|v| v.as_i64()))
                    .unwrap_or(0) as u8;
                let data: Vec<u8> = raw_args.get(3)
                    .and_then(|v| v.as_array())
                    .or_else(|| req.args.get("kwargs").and_then(|v| v.get("data")).and_then(|v| v.as_array()))
                    .map(|a| a.iter().filter_map(|x| x.as_u64().map(|n| n as u8)).collect())
                    .unwrap_or_default();

                let mut payload = Vec::with_capacity(4 + data.len());
                payload.push(memorial_index);
                payload.extend_from_slice(&total_length.to_le_bytes());
                payload.push(gif_id);
                payload.extend_from_slice(&data);

                match dev.send_command(0x55, &payload, true).await {
                    Ok(()) => json!({"success": true, "result": true}),
                    Err(e) => err_reply(&format!("set_memorial_gif failed: {e}")),
                }
            }
            // alarm.set_alarm_listen / set_alarm_listen
            "alarm.set_alarm_listen" | "set_alarm_listen" => {
                let on_off = args.first().copied()
                    .or_else(|| req.args.get("kwargs").and_then(|v| v.get("on_off")).and_then(|v| v.as_i64()))
                    .unwrap_or(0) as u8;
                let mode = args.get(1).copied()
                    .or_else(|| req.args.get("kwargs").and_then(|v| v.get("mode")).and_then(|v| v.as_i64()))
                    .unwrap_or(0) as u8;
                let volume = args.get(2).copied()
                    .or_else(|| req.args.get("kwargs").and_then(|v| v.get("volume")).and_then(|v| v.as_i64()))
                    .unwrap_or(0) as u8;
                match dev.send_command(0xa5, &[on_off, mode, volume], true).await {
                    Ok(()) => json!({"success": true, "result": true}),
                    Err(e) => err_reply(&format!("set_alarm_listen failed: {e}")),
                }
            }
            // alarm.set_alarm_volume / set_alarm_volume
            "alarm.set_alarm_volume" | "set_alarm_volume" => {
                let volume = args.first().copied()
                    .or_else(|| req.args.get("kwargs").and_then(|v| v.get("volume")).and_then(|v| v.as_i64()))
                    .unwrap_or(0) as u8;
                match dev.send_command(0xa6, &[volume], true).await {
                    Ok(()) => json!({"success": true, "result": true}),
                    Err(e) => err_reply(&format!("set_alarm_volume failed: {e}")),
                }
            }
            // alarm.set_alarm_volume_control / set_alarm_volume_control
            "alarm.set_alarm_volume_control" | "set_alarm_volume_control" => {
                let control = args.first().copied()
                    .or_else(|| req.args.get("kwargs").and_then(|v| v.get("control")).and_then(|v| v.as_i64()))
                    .unwrap_or(0) as u8;
                let index = args.get(1).copied()
                    .or_else(|| req.args.get("kwargs").and_then(|v| v.get("index")).and_then(|v| v.as_i64()))
                    .unwrap_or(0) as u8;
                match dev.send_command(0x82, &[control, index], true).await {
                    Ok(()) => json!({"success": true, "result": true}),
                    Err(e) => err_reply(&format!("set_alarm_volume_control failed: {e}")),
                }
            }
            // sleep.show_sleep / show_sleep
            "sleep.show_sleep" | "show_sleep" => {
                let kw = req.args.get("kwargs");
                let sleeptime = kw.and_then(|v| v.get("sleeptime")).and_then(|v| v.as_i64())
                    .or_else(|| args.first().copied())
                    .unwrap_or(60) as u8;
                let sleepmode = kw.and_then(|v| v.get("sleepmode")).and_then(|v| v.as_i64())
                    .or_else(|| args.get(1).copied())
                    .unwrap_or(0) as u8;
                let on = kw.and_then(|v| v.get("on")).and_then(|v| v.as_i64())
                    .or_else(|| args.get(2).copied())
                    .unwrap_or(1) as u8;
                let frequency = kw.and_then(|v| v.get("frequency")).and_then(|v| v.as_i64())
                    .or_else(|| args.get(3).copied())
                    .unwrap_or(0) as u16;
                let volume = kw.and_then(|v| v.get("volume")).and_then(|v| v.as_i64())
                    .or_else(|| args.get(4).copied())
                    .unwrap_or(16) as u8;
                let color_val = kw.and_then(|v| v.get("color"))
                    .or_else(|| raw_args.get(5));
                let [r, g, b] = if let Some(cv) = color_val {
                    if let Some(arr) = cv.as_array() {
                        let ns: Vec<u8> = arr.iter().filter_map(|x| x.as_u64().map(|n| n as u8)).collect();
                        if ns.len() >= 3 { [ns[0], ns[1], ns[2]] } else { [255, 255, 255] }
                    } else if let Some(s) = cv.as_str() {
                        parse_hex_color(s).unwrap_or([255, 255, 255])
                    } else {
                        [255, 255, 255]
                    }
                } else {
                    [255, 255, 255]
                };
                let brightness = kw.and_then(|v| v.get("brightness")).and_then(|v| v.as_i64())
                    .or_else(|| args.get(6).copied())
                    .unwrap_or(100) as u8;

                let mut payload = Vec::with_capacity(10);
                payload.push(sleeptime);
                payload.push(sleepmode);
                payload.push(on);
                payload.extend_from_slice(&frequency.to_le_bytes());
                payload.push(volume);
                payload.push(r);
                payload.push(g);
                payload.push(b);
                payload.push(brightness);

                match dev.send_command(0x40, &payload, true).await {
                    Ok(()) => json!({"success": true, "result": true}),
                    Err(e) => err_reply(&format!("show_sleep failed: {e}")),
                }
            }
            // sleep.get_sleep_scene / get_sleep_scene
            "sleep.get_sleep_scene" | "get_sleep_scene" => {
                match dev.send_command_and_wait(0xa2, &[], timeout).await {
                    Some(p) if p.len() >= 10 => json!({
                        "success": true,
                        "result": {
                            "time": p[0] as i64,
                            "mode": p[1] as i64,
                            "on": p[2] as i64,
                            "fm_freq": u16::from_le_bytes([p[3], p[4]]) as i64,
                            "volume": p[5] as i64,
                            "color_r": p[6] as i64,
                            "color_g": p[7] as i64,
                            "color_b": p[8] as i64,
                            "light": p[9] as i64,
                        }
                    }),
                    _ => json!({"success": true, "result": Value::Null}),
                }
            }
            // sleep.set_sleep_scene_listen / set_sleep_scene_listen
            "sleep.set_sleep_scene_listen" | "set_sleep_scene_listen" => {
                let on_off = args.first().copied()
                    .or_else(|| req.args.get("kwargs").and_then(|v| v.get("on_off")).and_then(|v| v.as_i64()))
                    .unwrap_or(0) as u8;
                let mode = args.get(1).copied()
                    .or_else(|| req.args.get("kwargs").and_then(|v| v.get("mode")).and_then(|v| v.as_i64()))
                    .unwrap_or(0) as u8;
                let volume = args.get(2).copied()
                    .or_else(|| req.args.get("kwargs").and_then(|v| v.get("volume")).and_then(|v| v.as_i64()))
                    .unwrap_or(0) as u8;
                match dev.send_command(0xa3, &[on_off, mode, volume], true).await {
                    Ok(()) => json!({"success": true, "result": true}),
                    Err(e) => err_reply(&format!("set_sleep_scene_listen failed: {e}")),
                }
            }
            // sleep.set_scene_volume / set_scene_volume
            "sleep.set_scene_volume" | "set_scene_volume" => {
                let volume = args.first().copied()
                    .or_else(|| req.args.get("kwargs").and_then(|v| v.get("volume")).and_then(|v| v.as_i64()))
                    .unwrap_or(0) as u8;
                match dev.send_command(0xa4, &[volume], true).await {
                    Ok(()) => json!({"success": true, "result": true}),
                    Err(e) => err_reply(&format!("set_scene_volume failed: {e}")),
                }
            }
            // sleep.set_sleep_color / set_sleep_color
            "sleep.set_sleep_color" | "set_sleep_color" => {
                let color_val = raw_args.first()
                    .or_else(|| req.args.get("kwargs").and_then(|v| v.get("color")));
                let [r, g, b] = if let Some(cv) = color_val {
                    if let Some(arr) = cv.as_array() {
                        let ns: Vec<u8> = arr.iter().filter_map(|x| x.as_u64().map(|n| n as u8)).collect();
                        if ns.len() >= 3 { [ns[0], ns[1], ns[2]] } else { [255, 255, 255] }
                    } else if let Some(s) = cv.as_str() {
                        parse_hex_color(s).unwrap_or([255, 255, 255])
                    } else {
                        [255, 255, 255]
                    }
                } else {
                    [255, 255, 255]
                };
                match dev.send_command(0xad, &[r, g, b], true).await {
                    Ok(()) => json!({"success": true, "result": true}),
                    Err(e) => err_reply(&format!("set_sleep_color failed: {e}")),
                }
            }
            // sleep.set_sleep_light / set_sleep_light
            "sleep.set_sleep_light" | "set_sleep_light" => {
                let light = args.first().copied()
                    .or_else(|| req.args.get("kwargs").and_then(|v| v.get("light")).and_then(|v| v.as_i64()))
                    .unwrap_or(0) as u8;
                match dev.send_command(0xae, &[light], true).await {
                    Ok(()) => json!({"success": true, "result": true}),
                    Err(e) => err_reply(&format!("set_sleep_light failed: {e}")),
                }
            }
            // sleep.set_sleep_scene / set_sleep_scene
            "sleep.set_sleep_scene" | "set_sleep_scene" => {
                let mode = args.first().copied()
                    .or_else(|| req.args.get("kwargs").and_then(|v| v.get("mode")).and_then(|v| v.as_i64()))
                    .unwrap_or(0) as u8;
                let on = args.get(1).copied()
                    .or_else(|| req.args.get("kwargs").and_then(|v| v.get("on")).and_then(|v| v.as_i64()))
                    .unwrap_or(0) as u8;
                let fm_freq: Vec<u8> = raw_args.get(2)
                    .and_then(|v| v.as_array())
                    .or_else(|| req.args.get("kwargs").and_then(|v| v.get("fm_freq")).and_then(|v| v.as_array()))
                    .map(|a| a.iter().filter_map(|x| x.as_u64().map(|n| n as u8)).collect())
                    .unwrap_or_else(|| vec![0, 0]);
                let fm_freq = if fm_freq.len() >= 2 { fm_freq } else { vec![0, 0] };
                let volume = args.get(3).copied()
                    .or_else(|| req.args.get("kwargs").and_then(|v| v.get("volume")).and_then(|v| v.as_i64()))
                    .unwrap_or(0) as u8;
                let color_val = raw_args.get(4)
                    .or_else(|| req.args.get("kwargs").and_then(|v| v.get("color")));
                let [r, g, b] = if let Some(cv) = color_val {
                    if let Some(arr) = cv.as_array() {
                        let ns: Vec<u8> = arr.iter().filter_map(|x| x.as_u64().map(|n| n as u8)).collect();
                        if ns.len() >= 3 { [ns[0], ns[1], ns[2]] } else { [255, 255, 255] }
                    } else if let Some(s) = cv.as_str() {
                        parse_hex_color(s).unwrap_or([255, 255, 255])
                    } else {
                        [255, 255, 255]
                    }
                } else {
                    [255, 255, 255]
                };
                let light = args.get(5).copied()
                    .or_else(|| req.args.get("kwargs").and_then(|v| v.get("light")).and_then(|v| v.as_i64()))
                    .unwrap_or(0) as u8;

                let mut payload = Vec::with_capacity(9);
                payload.push(mode);
                payload.push(on);
                payload.extend_from_slice(&fm_freq[0..2]);
                payload.push(volume);
                payload.push(r);
                payload.push(g);
                payload.push(b);
                payload.push(light);

                match dev.send_command(0x41, &payload, true).await {
                    Ok(()) => json!({"success": true, "result": true}),
                    Err(e) => err_reply(&format!("set_sleep_scene failed: {e}")),
                }
            }
            // timeplan.set_time_manage_info / set_time_manage_info
            "timeplan.set_time_manage_info" | "set_time_manage_info" => {
                let kw = req.args.get("kwargs");
                let status = kw.and_then(|v| v.get("status")).and_then(|v| v.as_i64())
                    .or_else(|| args.first().copied())
                    .unwrap_or(0) as u8;
                let hour = kw.and_then(|v| v.get("hour")).and_then(|v| v.as_i64())
                    .or_else(|| args.get(1).copied())
                    .unwrap_or(0) as u8;
                let minute = kw.and_then(|v| v.get("minute")).and_then(|v| v.as_i64())
                    .or_else(|| args.get(2).copied())
                    .unwrap_or(0) as u8;
                let week = kw.and_then(|v| v.get("week")).and_then(|v| v.as_i64())
                    .or_else(|| args.get(3).copied())
                    .unwrap_or(0) as u8;
                let mode = kw.and_then(|v| v.get("mode")).and_then(|v| v.as_i64())
                    .or_else(|| args.get(4).copied())
                    .unwrap_or(0) as u8;
                let trigger_mode = kw.and_then(|v| v.get("trigger_mode")).and_then(|v| v.as_i64())
                    .or_else(|| args.get(5).copied())
                    .unwrap_or(0) as u8;
                let fm_freq = kw.and_then(|v| v.get("fm_freq")).and_then(|v| v.as_i64())
                    .or_else(|| args.get(6).copied())
                    .unwrap_or(0) as u16;
                let volume = kw.and_then(|v| v.get("volume")).and_then(|v| v.as_i64())
                    .or_else(|| args.get(7).copied())
                    .unwrap_or(0) as u8;
                let tp_type = kw.and_then(|v| v.get("type")).and_then(|v| v.as_i64())
                    .or_else(|| args.get(8).copied())
                    .unwrap_or(0) as u8;

                let mut payload = Vec::with_capacity(10);
                payload.push(status);
                payload.push(hour);
                payload.push(minute);
                payload.push(week);
                payload.push(mode);
                payload.push(trigger_mode);
                payload.extend_from_slice(&fm_freq.to_le_bytes());
                payload.push(volume);
                payload.push(tp_type);

                if tp_type == 0 {
                    let animation_id = kw.and_then(|v| v.get("animation_id")).and_then(|v| v.as_i64())
                        .or_else(|| args.get(9).copied())
                        .unwrap_or(0) as u8;
                    let animation_speed = kw.and_then(|v| v.get("animation_speed")).and_then(|v| v.as_i64())
                        .or_else(|| args.get(10).copied())
                        .unwrap_or(0) as u8;
                    let animation_direction = kw.and_then(|v| v.get("animation_direction")).and_then(|v| v.as_i64())
                        .or_else(|| args.get(11).copied())
                        .unwrap_or(0) as u8;
                    let animation_frame_count = kw.and_then(|v| v.get("animation_frame_count")).and_then(|v| v.as_i64())
                        .or_else(|| args.get(12).copied())
                        .unwrap_or(0) as u8;
                    let animation_frame_delay = kw.and_then(|v| v.get("animation_frame_delay")).and_then(|v| v.as_i64())
                        .or_else(|| args.get(13).copied())
                        .unwrap_or(0) as u8;
                    let animation_frame_data: Vec<u8> = raw_args.get(14)
                        .and_then(|v| v.as_array())
                        .or_else(|| kw.and_then(|v| v.get("animation_frame_data")).and_then(|v| v.as_array()))
                        .map(|a| a.iter().filter_map(|x| x.as_u64().map(|n| n as u8)).collect())
                        .unwrap_or_default();

                    payload.push(animation_id);
                    payload.push(animation_speed);
                    payload.push(animation_direction);
                    payload.push(animation_frame_count);
                    payload.push(animation_frame_delay);
                    payload.extend_from_slice(&animation_frame_data);
                }

                match dev.send_command(0x56, &payload, true).await {
                    Ok(()) => json!({"success": true, "result": true}),
                    Err(e) => err_reply(&format!("set_time_manage_info failed: {e}")),
                }
            }
            // timeplan.set_time_manage_ctrl / set_time_manage_ctrl
            "timeplan.set_time_manage_ctrl" | "set_time_manage_ctrl" => {
                let status = args.first().copied()
                    .or_else(|| req.args.get("kwargs").and_then(|v| v.get("status")).and_then(|v| v.as_i64()))
                    .unwrap_or(0) as u8;
                let index = args.get(1).copied()
                    .or_else(|| req.args.get("kwargs").and_then(|v| v.get("index")).and_then(|v| v.as_i64()))
                    .unwrap_or(0) as u8;
                match dev.send_command(0x57, &[status, index], true).await {
                    Ok(()) => json!({"success": true, "result": true}),
                    Err(e) => err_reply(&format!("set_time_manage_ctrl failed: {e}")),
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
        let _ = self.tx.send(json!({
            "type": "status",
            "state": "idle",
            "counters": {}
        }));
        json!({"success": true})
    }
}

/// Parse a "#RRGGBB" or "RRGGBB" hex string to [R, G, B]. Returns None on malform.
fn parse_hex_color(s: &str) -> Option<[u8; 3]> {
    let s = s.trim_start_matches('#');
    if s.len() == 6 {
        let r = u8::from_str_radix(&s[0..2], 16).ok()?;
        let g = u8::from_str_radix(&s[2..4], 16).ok()?;
        let b = u8::from_str_radix(&s[4..6], 16).ok()?;
        Some([r, g, b])
    } else {
        None
    }
}

/// Extract [R, G, B] from the first positional arg (array [r,g,b] or hex string)
/// or the "color" kwarg. Returns None if absent or unparseable.
fn color_from_arg(raw_args: &[Value], req_args: &Value) -> Option<[u8; 3]> {
    let color_val = raw_args.first().or_else(|| req_args.get("kwargs").and_then(|v| v.get("color")))?;
    if let Some(arr) = color_val.as_array() {
        let ns: Vec<u8> = arr.iter().filter_map(|x| x.as_u64().map(|n| n as u8)).collect();
        if ns.len() >= 3 { return Some([ns[0], ns[1], ns[2]]); }
    }
    if let Some(s) = color_val.as_str() {
        return parse_hex_color(s);
    }
    None
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

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

use crate::command_queue::CommandQueue;
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
        }
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

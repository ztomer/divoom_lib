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
use crate::ble::{self, BleTransport};
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
        }
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
        match ble::scan(Duration::from_secs_f64(timeout)).await {
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
        match BleTransport::connect(&id).await {
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

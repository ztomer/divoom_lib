//! The daemon's request Handler — dispatches NDJSON commands to replies. This is
//! the seam the socket server calls. It owns the [`CommandQueue`] (so exclusive
//! mode / steal-reject are real), serves status + lifecycle commands, and honestly
//! reports device commands as not-yet-implemented until the BLE transport lands.
//!
//! Replies match the Python daemon's shapes so the existing Python clients (and the
//! conformance test suite) can drive this daemon unchanged.

use std::future::Future;
use std::pin::Pin;
use std::time::{Duration, Instant};

use serde_json::{json, Value};

use crate::command_queue::CommandQueue;
use crate::protocol::{err_reply, Request};
use crate::socket_server::Handler;

const EXCLUSIVE_TIMEOUT: Duration = Duration::from_secs(30);
const ITEM_TIMEOUT: Duration = Duration::from_secs(60);

pub struct Daemon {
    queue: CommandQueue,
    started: Instant,
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
        }
    }

    fn dispatch(&self, req: Request) -> Value {
        match req.command.as_str() {
            "ping" => json!({"success": true, "pong": true}),

            // status — no device held yet (BLE transport not wired)
            "device_status" => json!({
                "success": true,
                "connected": false,
                "connection_state": "disconnected",
                "mac": Value::Null,
                "lan_ip": Value::Null,
                "wall": false,
            }),
            "get_status" => json!({
                "success": true,
                "state": "idle",
                "uptime_s": self.started.elapsed().as_secs(),
                "counters": {},
            }),

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

            // Everything device-touching is honestly unimplemented until the BLE
            // transport + device owner land — never a silent fake success.
            other => err_reply(&format!(
                "command not implemented in the native daemon yet: {other}"
            )),
        }
    }
}

impl Handler for Daemon {
    fn handle<'a>(&'a self, req: Request) -> Pin<Box<dyn Future<Output = Value> + Send + 'a>> {
        Box::pin(async move { self.dispatch(req) })
    }
}

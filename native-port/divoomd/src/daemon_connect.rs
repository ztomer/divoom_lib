//! Connect / disconnect / scan command handlers for the native daemon.
//! Split from daemon.rs to keep that file under the 500-LOC ground rule.

use std::sync::Arc;
use std::time::Duration;
use serde_json::{json, Value};

use crate::daemon::{Daemon, DeviceTransport};
use crate::protocol::{err_reply, Request};
#[cfg(feature = "ble")]
use crate::ble::{self, BleTransport};

/// Handle `probe_lan` — check whether the connected device is reachable over its
/// LAN HTTP API (Python-daemon parity). BLE/SPP devices report "no LAN configured".
pub(crate) async fn probe_lan(daemon: &Daemon) -> Value {
    let dev = {
        let guard = daemon.device.lock().await;
        match &*guard {
            Some(d) => d.clone(),
            None => return json!({"success": true, "reachable": false, "detail": "no device connected"}),
        }
    };
    match dev.lan() {
        Some(lan) => {
            let reachable = lan.probe().await;
            json!({"success": true, "reachable": reachable, "device_ip": lan.device_ip})
        }
        None => json!({"success": true, "reachable": false, "detail": "no LAN configured"}),
    }
}

/// Handle `scan` command (BLE only).
#[cfg(feature = "ble")]
pub(crate) async fn cmd_scan(daemon: &Daemon, req: &Request) -> Value {
    let timeout = req.args.get("timeout").and_then(|v| v.as_f64()).unwrap_or(8.0);
    let central = match daemon.central().await {
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

/// Handle `connect_device` command (BLE or LAN).
pub(crate) async fn cmd_connect(daemon: &Daemon, req: &Request) -> Value {
    let mock = req.args.get("mock").and_then(|v| v.as_bool()).unwrap_or(false);
    if mock {
        let mock_transport = crate::mock_transport::MockTransport::new();
        *daemon.device.lock().await = Some(Arc::new(DeviceTransport::Mock(mock_transport)));
        *daemon.device_id.lock().await = Some("MOCK_MAC".to_string());
        let _ = daemon.tx.send(json!({"type":"status","state":"active","counters":{}}));
        return json!({"success":true,"connected":true,"connection_state":"connected","mac":"MOCK_MAC"});
    }

    let lan_ip = req.args.get("lan_ip").and_then(|v| v.as_str());
    if let Some(ip) = lan_ip {
        let token = req.args.get("lan_token").and_then(|v| v.as_i64()).unwrap_or(0);
        let lan = crate::lan::LanTransport::new(ip, token);
        if !lan.probe().await {
            return err_reply(&format!("LAN device at {ip} unreachable"));
        }
        *daemon.device.lock().await = Some(Arc::new(DeviceTransport::Lan(lan)));
        *daemon.device_id.lock().await = Some(format!("LAN:{ip}"));
        let _ = daemon.tx.send(json!({"type":"status","state":"active","counters":{}}));
        return json!({"success":true,"connected":true,"connection_state":"connected","lan_ip":ip});
    }
    #[cfg(feature = "ble")]
    {
        let id = req.args.get("mac").or_else(|| req.args.get("id")).and_then(|v| v.as_str());
        let id = match id {
            Some(i) => i.to_string(),
            None => return err_reply("connect_device requires 'mac' or 'lan_ip'"),
        };
        let use_ios_le = req.args.get("use_ios_le_protocol").and_then(|v| v.as_bool()).unwrap_or(true);
        if !use_ios_le {
            match crate::spp::SppTransport::connect(&id, None, None).await {
                Ok(t) => {
                    *daemon.device.lock().await = Some(Arc::new(DeviceTransport::Spp(t)));
                    *daemon.device_id.lock().await = Some(id.clone());
                    let _ = daemon.tx.send(json!({"type":"status","state":"active","counters":{}}));
                    return json!({"success":true,"connected":true,"connection_state":"connected","mac":id});
                }
                Err(e) => return err_reply(&format!("connect SPP failed: {e}")),
            }
        }

        let central = match daemon.central().await {
            Ok(c) => c,
            Err(e) => return err_reply(&format!("connect failed: {e}")),
        };
        match BleTransport::connect(&central, &id).await {
            Ok(t) => {
                *daemon.device.lock().await = Some(Arc::new(DeviceTransport::Ble(t)));
                *daemon.device_id.lock().await = Some(id.clone());
                let _ = daemon.tx.send(json!({"type":"status","state":"active","counters":{}}));
                json!({"success":true,"connected":true,"connection_state":"connected","mac":id})
            }
            Err(e) => err_reply(&format!("connect failed: {e}")),
        }
    }
    #[cfg(not(feature = "ble"))]
    err_reply("BLE support is disabled, requires 'lan_ip'")
}

/// Handle `disconnect` command.
pub(crate) async fn cmd_disconnect(daemon: &Daemon) -> Value {
    if let Some(t) = daemon.device.lock().await.take() {
        match &*t {
            #[cfg(feature = "ble")]
            DeviceTransport::Ble(b) => { let _ = b.disconnect().await; }
            DeviceTransport::Spp(s) => { let _ = s.disconnect().await; }
            DeviceTransport::Lan(_) => {}
            DeviceTransport::Mock(_) => {}
        }
    }
    *daemon.device_id.lock().await = None;
    let _ = daemon.tx.send(json!({"type":"status","state":"idle","counters":{}}));
    json!({"success": true})
}

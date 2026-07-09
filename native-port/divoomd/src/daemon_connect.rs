//! Connect / disconnect / scan command handlers for the native daemon.
//! Split from daemon.rs to keep that file under the 500-LOC ground rule.

use std::sync::Arc;
use std::time::{Duration, Instant};
use serde_json::{json, Value};

/// Minimum gap between BLE scans; a scan arriving sooner reuses the last result
/// instead of hitting the radio, so nothing (a retry, a script, a test) can
/// hammer the adapter into CoreBluetooth's scan-frequency throttle.
#[cfg(feature = "ble")]
const MIN_RESCAN_INTERVAL: Duration = Duration::from_secs(3);

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

/// Resets the daemon's `scanning` flag on drop, so a scan that returns via ANY
/// path (incl. an early error) can't wedge the guard.
#[cfg(feature = "ble")]
struct ScanGuard<'a>(&'a std::sync::atomic::AtomicBool);
#[cfg(feature = "ble")]
impl Drop for ScanGuard<'_> {
    fn drop(&mut self) {
        self.0.store(false, std::sync::atomic::Ordering::SeqCst);
    }
}

/// Handle `scan` command (BLE only).
#[cfg(feature = "ble")]
pub(crate) async fn cmd_scan(daemon: &Daemon, req: &Request) -> Value {
    use std::sync::atomic::Ordering;
    // Reject a concurrent scan: two scans share the one adapter and would corrupt
    // each other (one's stop_scan cuts the other short → a truncated device list,
    // which is exactly how an overlapping probe made the GUI miss a device).
    if daemon
        .scanning
        .compare_exchange(false, true, Ordering::SeqCst, Ordering::SeqCst)
        .is_err()
    {
        return err_reply("scan already in progress");
    }
    let _guard = ScanGuard(&daemon.scanning);

    // Rapid re-scan short-circuit: a scan within MIN_RESCAN_INTERVAL of the last
    // returns the cached result instead of hitting the radio. Back-to-back scans
    // trip CoreBluetooth's scan-frequency throttle (which then returns 0 devices
    // until Bluetooth is toggled) — the failure mode that dogged this feature.
    {
        let last = daemon.last_scan.lock().await;
        if let Some((at, devices)) = last.as_ref() {
            if at.elapsed() < MIN_RESCAN_INTERVAL {
                return json!({"success": true, "devices": devices.clone(), "cached": true});
            }
        }
    }

    let timeout = req.args.get("timeout").and_then(|v| v.as_f64()).unwrap_or(8.0);
    // `limit` is accepted but intentionally NOT used to truncate results: capping
    // could hide a real device (the "found 2 of 3" class of bug). ble::scan caps
    // an over-long timeout internally so a stray large value can't wedge things.
    let central = match daemon.central().await {
        Ok(c) => c,
        Err(e) => return err_reply(&format!("scan failed: {e}")),
    };
    match ble::scan(&central, Duration::from_secs_f64(timeout)).await {
        Ok(devs) => {
            let devices: Vec<Value> = devs
                .iter()
                .map(|d| json!({"name": d.name, "address": d.id}))
                .collect();
            *daemon.last_scan.lock().await = Some((Instant::now(), devices.clone()));
            json!({"success": true, "devices": devices})
        }
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

#[cfg(all(test, feature = "ble"))]
mod scan_guard_tests {
    use super::{cmd_scan, ScanGuard};
    use crate::daemon::Daemon;
    use crate::protocol::make_request;
    use serde_json::json;
    use std::sync::atomic::{AtomicBool, Ordering};
    use std::time::Instant;

    // A scan arriving within MIN_RESCAN_INTERVAL of the last returns the cached
    // result WITHOUT touching the radio (the check short-circuits before
    // daemon.central()), so this is unit-testable with no BLE device. Guards the
    // anti-throttle behavior that stops rapid re-scans wedging CoreBluetooth.
    #[tokio::test]
    async fn rapid_rescan_returns_cached_without_touching_radio() {
        let daemon = Daemon::new();
        let cached = vec![json!({"name": "Pixoo-1", "address": "AA:BB"})];
        *daemon.last_scan.lock().await = Some((Instant::now(), cached.clone()));

        let resp = cmd_scan(&daemon, &make_request("scan", None, None)).await;
        assert_eq!(resp["cached"], json!(true));
        assert_eq!(resp["devices"], json!(cached));
        // The guard must be released again after a cached return.
        assert!(!daemon.scanning.load(Ordering::SeqCst));
    }

    // The scan guard is what stops two overlapping scans from clobbering the one
    // adapter (the corruption that truncated the GUI's device list). Pin its
    // claim / reject-while-held / reset-on-drop behavior without needing BLE.
    #[test]
    fn rejects_concurrent_then_resets_on_drop() {
        let flag = AtomicBool::new(false);
        // First scan claims the guard.
        assert!(flag
            .compare_exchange(false, true, Ordering::SeqCst, Ordering::SeqCst)
            .is_ok());
        {
            let _g = ScanGuard(&flag);
            // A concurrent scan is rejected while the first holds it.
            assert!(flag
                .compare_exchange(false, true, Ordering::SeqCst, Ordering::SeqCst)
                .is_err());
        }
        // Guard dropped (scan finished) → flag cleared → a new scan can claim it.
        assert!(!flag.load(Ordering::SeqCst));
        assert!(flag
            .compare_exchange(false, true, Ordering::SeqCst, Ordering::SeqCst)
            .is_ok());
    }
}

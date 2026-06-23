//! BLE transport (btleplug) — connect / notify / write against a real Divoom, on
//! the foundation the TCC spike proved. Wires the hardware-free ported modules
//! (`framing`, `response`, `autoprobe`) to a `Peripheral`.
//!
//! Feature-gated (`ble`) so the protocol core + its tests stay btleplug-free. This
//! module can't be unit-tested (it needs a device); its verification is over the
//! socket against a real Pixoo/Ditoo once the daemon `.app` holds the BT grant.

use std::time::Duration;

use btleplug::api::{
    Central, CharPropFlags, Characteristic, Manager as _, Peripheral as _, ScanFilter, WriteType,
};
use btleplug::platform::{Manager, Peripheral};

/// The platform BLE adapter. On macOS the CoreBluetooth central manager it wraps
/// MUST stay alive for the duration of a connection — dropping it silently stops
/// notification delivery — so callers hold it (the daemon caches one; each
/// `BleTransport` keeps a clone).
pub use btleplug::platform::Adapter;
use futures::StreamExt;
use tokio::sync::{mpsc, Mutex};
use uuid::Uuid;

use crate::autoprobe::Protocol;
use crate::framing;
use crate::models::IOS_LE_HEADER;
use crate::response::{self, Frame};

// Divoom GATT (ISSC transparent-UART service), from divoom_lib/divoom.py.
const WRITE_UUID: Uuid = Uuid::from_u128(0x49535343_8841_43f4_a8d4_ecbe34729bb3);
const NOTIFY_UUID: Uuid = Uuid::from_u128(0x49535343_1e4d_4bd9_ba61_23c647249616);

const DEVICE_NAME_HINTS: &[&str] = &["Pixoo", "Divoom", "Tivoo", "Timoo", "Ditoo", "Timebox"];

pub type BleResult<T> = Result<T, Box<dyn std::error::Error + Send + Sync>>;

/// A device discovered during a scan.
#[derive(Debug, Clone)]
pub struct Discovered {
    pub name: String,
    pub id: String,
}

/// Create the platform adapter. The caller must keep it alive (see [`Adapter`]).
pub async fn make_central() -> BleResult<Adapter> {
    let manager = Manager::new().await?;
    manager.adapters().await?.into_iter().next().ok_or_else(|| "no BLE adapter".into())
}

/// Scan for Divoom devices for `timeout`, returning name + id pairs.
pub async fn scan(central: &Adapter, timeout: Duration) -> BleResult<Vec<Discovered>> {
    central.start_scan(ScanFilter::default()).await?;
    tokio::time::sleep(timeout).await;
    central.stop_scan().await?;
    let mut out = Vec::new();
    for p in central.peripherals().await? {
        let name = p.properties().await?.and_then(|pr| pr.local_name).unwrap_or_default();
        if DEVICE_NAME_HINTS.iter().any(|h| name.contains(h)) {
            out.push(Discovered { name, id: p.id().to_string() });
        }
    }
    Ok(out)
}

/// An owned connection to one device: serialized writes + a parsed-frame channel.
pub struct BleTransport {
    // keep the central alive for the connection's lifetime (notifications need it)
    _central: Adapter,
    peripheral: Peripheral,
    write_char: Characteristic,
    protocol: Protocol,
    rx: Mutex<mpsc::Receiver<Frame>>,
}

impl BleTransport {
    /// Connect to the device whose `id` matches a prior `scan()` result. Discovers
    /// services, subscribes to notifications, spawns the frame-parsing task, and
    /// runs the autoprobe to pick the framing.
    pub async fn connect(central: &Adapter, id: &str) -> BleResult<Self> {
        // ensure the peripheral is known to the adapter
        central.start_scan(ScanFilter::default()).await?;
        tokio::time::sleep(Duration::from_secs(3)).await;
        central.stop_scan().await?;
        let peripheral = central
            .peripherals()
            .await?
            .into_iter()
            .find(|p| p.id().to_string() == id)
            .ok_or("device not found in scan")?;

        peripheral.connect().await?;
        peripheral.discover_services().await?;
        let chars = peripheral.characteristics();
        let write_char = chars.iter().find(|c| c.uuid == WRITE_UUID).ok_or("no write characteristic")?.clone();
        let notify_char = chars.iter().find(|c| c.uuid == NOTIFY_UUID).ok_or("no notify characteristic")?.clone();

        peripheral.subscribe(&notify_char).await?;
        let mut notifications = peripheral.notifications().await?;
        let (tx, rx) = mpsc::channel::<Frame>(256);

        // Parse inbound bytes into Frames using the ported framing: iOS-LE frames
        // are self-delimited (header-prefixed); Basic frames need a stateful buffer.
        tokio::spawn(async move {
            let mut basic_buf: Vec<u8> = Vec::new();
            while let Some(n) = notifications.next().await {
                let data = n.value;
                if std::env::var("DIVOOMD_BLE_DEBUG").is_ok() {
                    let hx: String = data.iter().map(|b| format!("{b:02x}")).collect();
                    eprintln!("[ble] rx {} bytes: {hx}", data.len());
                }
                if data.len() >= 4 && data[0..4] == IOS_LE_HEADER {
                    if let Some(p) = framing::parse_ios_le_notification(&data) {
                        if tx.send(Frame { command_id: p.command_id, payload: p.payload }).await.is_err() {
                            break;
                        }
                    }
                } else {
                    basic_buf.extend_from_slice(&data);
                    for m in framing::parse_basic_protocol_frames(&mut basic_buf) {
                        if std::env::var("DIVOOMD_BLE_DEBUG").is_ok() {
                            eprintln!("[ble] basic frame cmd=0x{:02x} ({} payload bytes)", m.command_id, m.payload.len());
                        }
                        if tx.send(Frame { command_id: m.command_id, payload: m.payload }).await.is_err() {
                            return;
                        }
                    }
                }
            }
        });

        let mut transport = Self {
            _central: central.clone(),
            peripheral,
            write_char,
            protocol: Protocol::Basic,
            rx: Mutex::new(rx),
        };
        transport.autoprobe().await;
        Ok(transport)
    }

    /// Detect the framing by probing 0x46 in iOS-LE then Basic (default Basic).
    /// Mirrors `autoprobe_protocol`. Sets `self.protocol`.
    async fn autoprobe(&mut self) {
        let probe = Duration::from_millis(1500);
        self.protocol = Protocol::IosLe;
        if self.send_command_and_wait(0x46, &[], probe).await.is_some() {
            return; // iOS-LE answered
        }
        self.protocol = Protocol::Basic;
        let _ = self.send_command_and_wait(0x46, &[], probe).await; // warm/confirm; Basic is the default
        self.protocol = Protocol::Basic;
    }

    pub fn protocol(&self) -> Protocol {
        self.protocol
    }

    pub fn set_protocol(&mut self, protocol: Protocol) {
        self.protocol = protocol;
    }

    /// Encode `[command_id, args...]` in the active framing and write it.
    pub async fn send_command(&self, command_id: u8, args: &[u8], write_with_response: bool) -> BleResult<()> {
        let mut payload = Vec::with_capacity(1 + args.len());
        payload.push(command_id);
        payload.extend_from_slice(args);
        let frame = match self.protocol {
            Protocol::Basic => framing::encode_basic_payload(&payload, false),
            Protocol::IosLe => framing::encode_ios_le_payload(&payload, 0)?,
        };
        let wtype = if write_with_response {
            WriteType::WithResponse
        } else {
            WriteType::WithoutResponse
        };
        // prefer write-with-response only if the characteristic supports it
        let wtype = if matches!(wtype, WriteType::WithResponse)
            && !self.write_char.properties.contains(CharPropFlags::WRITE)
        {
            WriteType::WithoutResponse
        } else {
            wtype
        };
        self.peripheral.write(&self.write_char, &frame, wtype).await?;
        Ok(())
    }

    /// Wait for the response to `command_id` (resolves on the exact id, skips the
    /// 0x33 generic-ACK), or `None` on timeout. Uses the ported correlation.
    pub async fn wait_for_response(&self, command_id: u8, timeout: Duration) -> Option<Vec<u8>> {
        let mut rx = self.rx.lock().await;
        response::wait_for_response(&mut rx, command_id, timeout).await
    }

    /// Drain → send → wait, mirroring `send_command_and_wait_for_response`. The
    /// device emits UNSOLICITED frames (e.g. a proactive 0x46 on a brightness
    /// change), so stale frames are dropped before the query to avoid reading a
    /// value one step behind (HW-confirmed in the Python impl).
    pub async fn send_command_and_wait(
        &self,
        command_id: u8,
        args: &[u8],
        timeout: Duration,
    ) -> Option<Vec<u8>> {
        {
            let mut rx = self.rx.lock().await;
            while rx.try_recv().is_ok() {}
        }
        self.send_command(command_id, args, true).await.ok()?;
        self.wait_for_response(command_id, timeout).await
    }

    pub async fn disconnect(&self) -> BleResult<()> {
        self.peripheral.disconnect().await?;
        Ok(())
    }
}

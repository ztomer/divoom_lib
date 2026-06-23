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

async fn central() -> BleResult<btleplug::platform::Adapter> {
    let manager = Manager::new().await?;
    let adapter = manager.adapters().await?.into_iter().next().ok_or("no BLE adapter")?;
    Ok(adapter)
}

/// Scan for Divoom devices for `timeout`, returning name + id pairs.
pub async fn scan(timeout: Duration) -> BleResult<Vec<Discovered>> {
    let central = central().await?;
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
    peripheral: Peripheral,
    write_char: Characteristic,
    protocol: Protocol,
    rx: Mutex<mpsc::Receiver<Frame>>,
}

impl BleTransport {
    /// Connect to the device whose `id` matches a prior `scan()` result. Discovers
    /// services, subscribes to notifications, and spawns the frame-parsing task.
    pub async fn connect(id: &str) -> BleResult<Self> {
        let central = central().await?;
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
                if data.len() >= 4 && data[0..4] == IOS_LE_HEADER {
                    if let Some(p) = framing::parse_ios_le_notification(&data) {
                        if tx.send(Frame { command_id: p.command_id, payload: p.payload }).await.is_err() {
                            break;
                        }
                    }
                } else {
                    basic_buf.extend_from_slice(&data);
                    for m in framing::parse_basic_protocol_frames(&mut basic_buf) {
                        if tx.send(Frame { command_id: m.command_id, payload: m.payload }).await.is_err() {
                            return;
                        }
                    }
                }
            }
        });

        Ok(Self { peripheral, write_char, protocol: Protocol::Basic, rx: Mutex::new(rx) })
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

    pub async fn disconnect(&self) -> BleResult<()> {
        self.peripheral.disconnect().await?;
        Ok(())
    }
}

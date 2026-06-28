//! Phase-1 spike for the native daemon port (see docs/ROADMAP.md).
//!
//! Goal: prove the single riskiest unknown before committing to the full port —
//! that `btleplug` + `tokio` can own a Divoom device over BLE on macOS, and that
//! a *native* binary obtains the CoreBluetooth TCC grant (the thing the Python
//! daemon needs a signed `.app` for). This is NOT the daemon; it is a throwaway
//! proof that does one round trip:
//!
//!   scan -> connect -> discover -> subscribe(notify) -> write(0x46 query) -> read reply
//!
//! The 0x46 ("get light mode / brightness") query is sent in the Basic framing,
//! pre-computed from the Python encoder so the bytes are known-correct:
//!   divoom_lib.framing.encode_basic_payload([0x46]) == 01 03 00 46 49 00 02
//!
//! A Basic-protocol device answers with a 0x46 frame; an iOS-LE-only device will
//! not (it needs the iOS-LE framing + the autoprobe). Either way, getting a
//! connection + a subscribed notify stream is the win this spike is after.

use std::error::Error;
use std::time::Duration;

use btleplug::api::{
    Central, CharPropFlags, Manager as _, Peripheral as _, ScanFilter, WriteType,
};
use btleplug::platform::Manager;
use futures::stream::StreamExt;
use tokio::time;
use uuid::Uuid;

// Divoom GATT (ISSC transparent-UART service), from divoom_lib/divoom.py.
const WRITE_UUID: Uuid = Uuid::from_u128(0x49535343_8841_43f4_a8d4_ecbe34729bb3);
const NOTIFY_UUID: Uuid = Uuid::from_u128(0x49535343_1e4d_4bd9_ba61_23c647249616);

// Basic-framed 0x46 query: [start 0x01][len LE 0x0003][cmd 0x46][cksum LE 0x0049][end 0x02]
const QUERY_0X46: [u8; 7] = [0x01, 0x03, 0x00, 0x46, 0x49, 0x00, 0x02];

const DEVICE_NAME_HINTS: &[&str] = &["Pixoo", "Divoom", "Tivoo", "Timoo", "Ditoo", "Timebox"];

#[tokio::main]
async fn main() -> Result<(), Box<dyn Error>> {
    let manager = Manager::new().await?;
    let central = manager
        .adapters()
        .await?
        .into_iter()
        .next()
        .ok_or("no BLE adapter (is Bluetooth on?)")?;

    println!("[spike] scanning 5s for a Divoom device...");
    central.start_scan(ScanFilter::default()).await?;
    time::sleep(Duration::from_secs(5)).await;
    central.stop_scan().await?;

    let mut target = None;
    for p in central.peripherals().await? {
        let name = p
            .properties()
            .await?
            .and_then(|pr| pr.local_name)
            .unwrap_or_default();
        if DEVICE_NAME_HINTS.iter().any(|h| name.contains(h)) {
            println!("[spike] found: {name:?} [{}]", p.id());
            target = Some(p);
            break;
        }
    }
    let peripheral = target.ok_or("no Divoom device found in scan")?;

    println!("[spike] connecting...");
    peripheral.connect().await?;
    peripheral.discover_services().await?;

    let chars = peripheral.characteristics();
    let write_char = chars
        .iter()
        .find(|c| c.uuid == WRITE_UUID)
        .ok_or("write characteristic not found")?
        .clone();
    let notify_char = chars
        .iter()
        .find(|c| c.uuid == NOTIFY_UUID)
        .ok_or("notify characteristic not found")?
        .clone();

    println!("[spike] subscribing to notifications...");
    peripheral.subscribe(&notify_char).await?;
    let mut notifications = peripheral.notifications().await?;

    let wtype = if write_char.properties.contains(CharPropFlags::WRITE) {
        WriteType::WithResponse
    } else {
        WriteType::WithoutResponse
    };
    println!("[spike] writing 0x46 query ({}) as {:?}", hex(&QUERY_0X46), wtype);
    peripheral.write(&write_char, &QUERY_0X46, wtype).await?;

    println!("[spike] awaiting a reply (3s)...");
    match time::timeout(Duration::from_secs(3), notifications.next()).await {
        Ok(Some(n)) => println!("[spike] OK  NOTIFY {} -> {}", n.uuid, hex(&n.value)),
        Ok(None) => println!("[spike] notification stream ended unexpectedly"),
        Err(_) => println!(
            "[spike] no reply in 3s (expected for an iOS-LE-only device; the \
             connect + subscribe still proves the BLE+TCC path)"
        ),
    }

    peripheral.disconnect().await?;
    println!("[spike] done.");
    Ok(())
}

fn hex(bytes: &[u8]) -> String {
    bytes.iter().map(|b| format!("{b:02x}")).collect()
}

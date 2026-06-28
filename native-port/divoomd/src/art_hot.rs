//! Hot-channel update session: manifest fetch, file download, BLE streaming.
//! Split from art.rs to keep both files under the 500-LOC ground rule.

use std::sync::Arc;
use serde_json::{json, Value};

use crate::daemon::Daemon;
use crate::art::{HotProgress, device_type_for_size};

const HOT_API: &str = "https://appin.divoom-gz.com/Hot/GetHotFiles32";
const HOT_FILE_BASE: &str = "https://fin.divoom-gz.com/";
const CHUNK_SIZE: usize = 256;
const IDLE_DONE_TIMEOUT_SECS: f64 = 5.0;
const HTTP_TIMEOUT_SECS: u64 = 15;

struct HotFile { vendor_id: u32, file_id: String, version: u32, sha1: String, body: Vec<u8> }

impl HotFile {
    fn checksum(&self) -> u32 { self.body.iter().map(|&b| b as u32).sum::<u32>() }
    fn packet(&self, idx: usize) -> Vec<u8> {
        let start = idx * CHUNK_SIZE;
        let chunk = if start < self.body.len() {
            &self.body[start..(start + CHUNK_SIZE).min(self.body.len())]
        } else { &[] };
        let mut p = chunk.to_vec();
        p.resize(CHUNK_SIZE, 0);
        p
    }
    fn packet_count(&self) -> usize { (self.body.len() + CHUNK_SIZE - 1) / CHUNK_SIZE }
}

async fn fetch_hot_manifest(client: &reqwest::Client, device_type: u32) -> Result<Vec<HotFile>, String> {
    let body = serde_json::json!({"DeviceType": device_type, "IsTest": false});
    let resp = client.post(HOT_API).json(&body).send().await
        .map_err(|e| e.to_string())?;
    let data: Value = resp.json().await.map_err(|e| e.to_string())?;
    let mut files = Vec::new();
    for vendor in data.get("VendorList").and_then(|v| v.as_array()).unwrap_or(&vec![]) {
        let vid = vendor.get("VendorId").and_then(|v| v.as_u64()).unwrap_or(0) as u32;
        for f in vendor.get("FileList").and_then(|v| v.as_array()).unwrap_or(&vec![]) {
            let file_id = f.get("FileId").and_then(|v| v.as_str()).unwrap_or("").to_string();
            let version = f.get("Version").and_then(|v| v.as_u64()).unwrap_or(0) as u32;
            let sha1 = f.get("Sha1").and_then(|v| v.as_str()).unwrap_or("").to_string();
            files.push(HotFile { vendor_id: vid, file_id, version, sha1, body: Vec::new() });
        }
    }
    Ok(files)
}

async fn download_hot_file(client: &reqwest::Client, f: &mut HotFile) -> bool {
    let url = format!("{HOT_FILE_BASE}{}", f.file_id);
    let resp = match client.get(&url).send().await { Ok(r) => r, Err(_) => return false };
    let body = match resp.bytes().await { Ok(b) => b.to_vec(), Err(_) => return false };
    if !f.sha1.is_empty() {
        // verify SHA-1
        let digest = sha1_digest(&body);
        if digest != f.sha1.to_lowercase() { return false; }
    }
    f.body = body;
    true
}

fn sha1_digest(data: &[u8]) -> String {
    // Minimal SHA-1 (RFC 3174) — avoids a dep for a 20-byte output.
    let mut h: [u32; 5] = [0x67452301, 0xEFCDAB89, 0x98BADCFE, 0x10325476, 0xC3D2E1F0];
    let bit_len = (data.len() as u64) * 8;
    let mut padded = data.to_vec();
    padded.push(0x80);
    while padded.len() % 64 != 56 { padded.push(0); }
    padded.extend_from_slice(&bit_len.to_be_bytes());
    for chunk in padded.chunks_exact(64) {
        let mut w = [0u32; 80];
        for i in 0..16 { w[i] = u32::from_be_bytes(chunk[4*i..4*i+4].try_into().unwrap()); }
        for i in 16..80 { w[i] = (w[i-3]^w[i-8]^w[i-14]^w[i-16]).rotate_left(1); }
        let (mut a,mut b,mut c,mut d,mut e) = (h[0],h[1],h[2],h[3],h[4]);
        for i in 0..80 {
            let (f_val, k) = match i {
                0..=19  => ((b&c)|(!b&d), 0x5A827999u32),
                20..=39 => (b^c^d, 0x6ED9EBA1),
                40..=59 => ((b&c)|(b&d)|(c&d), 0x8F1BBCDC),
                _       => (b^c^d, 0xCA62C1D6),
            };
            let temp = a.rotate_left(5).wrapping_add(f_val).wrapping_add(e).wrapping_add(k).wrapping_add(w[i]);
            e=d; d=c; c=b.rotate_left(30); b=a; a=temp;
        }
        h[0]=h[0].wrapping_add(a); h[1]=h[1].wrapping_add(b);
        h[2]=h[2].wrapping_add(c); h[3]=h[3].wrapping_add(d);
        h[4]=h[4].wrapping_add(e);
    }
    format!("{:08x}{:08x}{:08x}{:08x}{:08x}", h[0],h[1],h[2],h[3],h[4])
}

fn pick_file<'a>(files: &'a [HotFile], vendor_id: u32, version: u32) -> Option<&'a HotFile> {
    let candidates: Vec<_> = files.iter()
        .filter(|f| f.vendor_id == vendor_id && !f.body.is_empty()).collect();
    if let Some(exact) = candidates.iter().find(|f| f.version == version) { return Some(exact); }
    candidates.iter().filter(|f| f.version >= version).min_by_key(|f| f.version).copied()
}

pub(crate) async fn run_hot_update(
    daemon: Arc<Daemon>,
    device_size: u32,
    _show_after: bool,
    progress: Arc<HotProgress>,
) -> Result<Value, String> {
    let client = reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(HTTP_TIMEOUT_SECS))
        .user_agent("okhttp/4.12.0")
        .build().map_err(|e| e.to_string())?;

    // 1. Fetch manifest
    progress.set(json!({"phase": "fetching_manifest"}));
    let device_type = device_type_for_size(device_size);
    let mut files = fetch_hot_manifest(&client, device_type).await?;
    if files.is_empty() { return Err("empty hot manifest".into()); }

    // 2. Download files
    let total_files = files.len();
    progress.set(json!({"phase": "downloading", "current": 0, "total": total_files}));
    let mut ok_dl = 0usize;
    for (i, f) in files.iter_mut().enumerate() {
        if download_hot_file(&client, f).await { ok_dl += 1; }
        progress.set(json!({"phase":"downloading","current":i+1,"total":total_files,"file_id":&f.file_id}));
    }
    if ok_dl == 0 { return Err("no hot files downloadable".into()); }

    // 3. BLE session
    #[cfg(feature = "ble")]
    {
        let guard = daemon.device.lock().await;
        let dev = match guard.as_ref() { Some(d) => d.clone(), None => return Err("no device connected".into()) };
        drop(guard);
        if matches!(&*dev, crate::daemon::DeviceTransport::Ble(_) | crate::daemon::DeviceTransport::Spp(_)) {
            return run_hot_session(&*dev, &files, ok_dl, progress).await;
        }
    }
    Err("hot_update requires BLE/SPP transport".into())
}

#[cfg(feature = "ble")]
async fn run_hot_session(
    ble: &crate::daemon::DeviceTransport,
    files: &[HotFile],
    ok_dl: usize,
    progress: Arc<HotProgress>,
) -> Result<Value, String> {
    use tokio::time::Duration;

    // Build 0x9B manifest payload: [count] + {vendorId:4 LE, newestVersion:4 LE}*
    let mut vendors: std::collections::HashMap<u32, u32> = std::collections::HashMap::new();
    for f in files.iter().filter(|f| !f.body.is_empty()) {
        let e = vendors.entry(f.vendor_id).or_insert(0);
        if f.version > *e { *e = f.version; }
    }
    let mut manifest_payload = vec![vendors.len() as u8];
    for (vid, newest) in &vendors {
        manifest_payload.extend_from_slice(&vid.to_le_bytes());
        manifest_payload.extend_from_slice(&newest.to_le_bytes());
    }
    if ble.send_command(0x9B, &manifest_payload, true).await.is_err() {
        return Err("manifest (0x9B) write failed".into());
    }

    let cmd_f7: u8 = 0xF7; let cmd_9d: u8 = 0x9D; let cmd_9e: u8 = 0x9E; let cmd_9f: u8 = 0x9F;
    let idle_to = Duration::from_secs_f64(IDLE_DONE_TIMEOUT_SECS);
    let mut served: Vec<Value> = Vec::new();
    let mut pending_request: Option<Vec<u8>> = None;

    loop {
        let (cmd, payload) = if let Some(p) = pending_request.take() {
            (cmd_f7, p)
        } else {
            match ble.wait_for_any_response(&[cmd_f7, cmd_9f], idle_to).await {
                Some((c, p)) => (c, p),
                None => break, // device quiet — up to date
            }
        };
        if cmd == cmd_9f { break; }
        if payload.len() < 8 { continue; }
        let vendor_id = u32::from_le_bytes(payload[0..4].try_into().unwrap_or([0;4]));
        let version = u32::from_le_bytes(payload[4..8].try_into().unwrap_or([0;4]));
        let f = match pick_file(files, vendor_id, version) {
            Some(f) => f,
            None => break,
        };
        // Send 0x9D file info
        let mut info = Vec::new();
        info.extend_from_slice(&f.vendor_id.to_le_bytes());
        info.extend_from_slice(&(f.body.len() as u32).to_le_bytes());
        info.extend_from_slice(&f.checksum().to_le_bytes());
        info.extend_from_slice(&f.version.to_le_bytes());
        if ble.send_command(cmd_9d, &info, true).await.is_err() {
            return Err("file info (0x9D) write failed".into());
        }
        // Wait for 0x9D ack
        let ack = match ble.wait_for_any_response(&[cmd_9d, cmd_f7], idle_to).await {
            Some(a) => a,
            None => break,
        };
        if ack.0 == cmd_f7 { pending_request = Some(ack.1); continue; }
        let p2 = &ack.1;
        if p2.is_empty() || p2[0] != 0 { continue; }
        let start_pkt = if p2.len() >= 3 { u16::from_le_bytes([p2[1], p2[2]]) as usize } else { 0 };

        // Stream file packets
        let total = f.packet_count();
        let mut confirmed = false;
        for idx in start_pkt..total {
            let mut pkt_payload = Vec::new();
            pkt_payload.extend_from_slice(&(idx as u16).to_le_bytes());
            pkt_payload.extend_from_slice(&f.packet(idx));
            if ble.send_command(cmd_9e, &pkt_payload, true).await.is_err() { break; }
            tokio::time::sleep(Duration::from_millis(20)).await;
        }
        // Post-stream: serve resends until device declares done
        loop {
            match ble.wait_for_any_response(&[cmd_9e, cmd_f7], idle_to).await {
                None => break, // IDLE_DONE_TIMEOUT — unconfirmed
                Some((c, p)) if c == cmd_f7 => {
                    pending_request = Some(p);
                    confirmed = true;
                    break;
                }
                Some((_, p)) if !p.is_empty() && (p[0] == 1 || p[0] == 2) => {
                    confirmed = true;
                    break;
                }
                Some((_, p)) if p.len() >= 3 && p[0] == 0 => {
                    let ridx = u16::from_le_bytes([p[1], p[2]]) as usize;
                    let mut rp = Vec::new();
                    rp.extend_from_slice(&(ridx as u16).to_le_bytes());
                    rp.extend_from_slice(&f.packet(ridx));
                    let _ = ble.send_command(cmd_9e, &rp, true).await;
                }
                _ => {}
            }
        }
        served.push(json!({"file_id": &f.file_id, "version": f.version, "confirmed": confirmed}));
        let n_served = served.len();
        progress.set(json!({"phase":"uploading","current":n_served,"total":ok_dl,"file_id":&f.file_id}));
    }

    let confirmed_count = served.iter().filter(|s| s.get("confirmed").and_then(|v| v.as_bool()).unwrap_or(false)).count();
    Ok(json!({
        "success": true,
        "served": served,
        "manifest": files.len(),
        "downloaded": ok_dl,
        "confirmed": confirmed_count,
    }))
}

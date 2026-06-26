use std::collections::HashMap;
use std::sync::{Arc, Weak};
use std::time::{Duration, SystemTime, UNIX_EPOCH};
use tokio::sync::Mutex;
use tokio::task::JoinHandle;
use serde_json::{json, Value};

use crate::daemon::{Daemon, DeviceTransport};

// --- Bitmap Font ---

const FIRST_CP: u32 = 0x20;
const LAST_CP: u32 = 0x7E;
const GLYPH_BYTES: usize = 32;
const CELL: usize = 16;
const FALLBACK_CP: u32 = 0x3F; // '?'

const FONT_BYTES: &[u8] = include_bytes!("../../../divoom_lib/fonts/divoom_fond16_default_half.bin");

struct BitmapFont {
    blob: &'static [u8],
    space_width: i32,
}

impl BitmapFont {
    fn new(blob: &'static [u8]) -> Self {
        Self { blob, space_width: 3 }
    }

    fn find_glyph_offset(&self, cp: u32) -> Option<usize> {
        if cp >= FIRST_CP && cp <= LAST_CP {
            Some(((cp - FIRST_CP) as usize) * GLYPH_BYTES)
        } else {
            None
        }
    }

    fn rows(&self, ch: char) -> [u16; 16] {
        let cp = ch as u32;
        let mut off = self.find_glyph_offset(cp);
        if off.is_none() {
            off = self.find_glyph_offset(FALLBACK_CP);
        }
        let off = match off {
            Some(o) => o,
            None => return [0; 16],
        };
        let g = &self.blob[off..off + GLYPH_BYTES];
        let mut r = [0u16; 16];
        for i in 0..16 {
            r[i] = ((g[i * 2] as u16) << 8) | (g[i * 2 + 1] as u16);
        }
        r
    }

    fn col_bbox(&self, rows: &[u16; 16]) -> Option<(usize, usize)> {
        let mut min_col = None;
        let mut max_col = None;
        for x in 0..CELL {
            let mask = 1 << (15 - x);
            let mut occupied = false;
            for &row in rows {
                if (row & mask) != 0 {
                    occupied = true;
                    break;
                }
            }
            if occupied {
                if min_col.is_none() {
                    min_col = Some(x);
                }
                max_col = Some(x);
            }
        }
        match (min_col, max_col) {
            (Some(min), Some(max)) => Some((min, max)),
            _ => None,
        }
    }

    fn _char_width(&self, ch: char) -> i32 {
        if ch == ' ' {
            return self.space_width;
        }
        let rows = self.rows(ch);
        if let Some((c0, c1)) = self.col_bbox(&rows) {
            (c1 - c0 + 1) as i32
        } else {
            self.space_width
        }
    }

    fn draw_text(
        &self,
        buf: &mut [u8],
        size: i32,
        x0: i32,
        y0: i32,
        text: &str,
        color: (u8, u8, u8),
        gap: i32,
        max_width: Option<i32>,
    ) -> i32 {
        let mut x = x0;
        let chars: Vec<char> = text.chars().collect();
        for (i, &ch) in chars.iter().enumerate() {
            let advance = if i > 0 { gap } else { 0 };
            if ch == ' ' {
                if let Some(mw) = max_width {
                    if (x + advance + self.space_width - x0) > mw {
                        break;
                    }
                }
                x += advance + self.space_width;
                continue;
            }
            let rows = self.rows(ch);
            let bb = self.col_bbox(&rows);
            if bb.is_none() {
                x += advance + self.space_width;
                continue;
            }
            let (c0, c1) = bb.unwrap();
            let gw = (c1 - c0 + 1) as i32;
            if let Some(mw) = max_width {
                if (x + advance + gw - x0) > mw {
                    break;
                }
            }
            x += advance;
            for r in 0..CELL {
                let v = rows[r];
                if v == 0 {
                    continue;
                }
                let yy = y0 + r as i32;
                if yy < 0 || yy >= size {
                    continue;
                }
                for c in c0..=c1 {
                    if ((v >> (15 - c)) & 1) != 0 {
                        let xx = x + (c as i32 - c0 as i32);
                        if xx >= 0 && xx < size {
                            let idx = ((yy * size + xx) * 3) as usize;
                            buf[idx] = color.0;
                            buf[idx + 1] = color.1;
                            buf[idx + 2] = color.2;
                        }
                    }
                }
            }
            x += gw;
        }
        x - x0
    }
}

// --- Renderers ---

fn render_sysmon(cpu: u8, mem: u8, battery: u8, size: u32) -> Vec<u8> {
    let mut buf = vec![0u8; (size * size * 3) as usize];
    for i in 0..(size * size) as usize {
        buf[i * 3] = 5;
        buf[i * 3 + 1] = 6;
        buf[i * 3 + 2] = 12;
    }

    let cpu_color = (255, 200, 0);
    let mem_color = (90, 170, 255);
    let bat_color = (255, 60, 60);

    let draw_gauge = |buf: &mut [u8], x: i32, y: i32, w_max: i32, h: i32, val: u8, color: (u8, u8, u8)| {
        let frac = val as f32 / 100.0;
        let w_fill = ((w_max as f32 * frac).round() as i32).clamp(1, w_max);
        for yy in y..y + h {
            if yy >= 0 && yy < size as i32 {
                for xx in x..x + w_fill {
                    if xx >= 0 && xx < size as i32 {
                        let idx = ((yy * size as i32 + xx) * 3) as usize;
                        buf[idx] = color.0;
                        buf[idx + 1] = color.1;
                        buf[idx + 2] = color.2;
                    }
                }
            }
        }
    };

    if size <= 16 {
        draw_gauge(&mut buf, 1, 1, 14, 3, cpu, cpu_color);
        draw_gauge(&mut buf, 1, 6, 14, 3, mem, mem_color);
        draw_gauge(&mut buf, 1, 11, 14, 3, battery, bat_color);
    } else {
        let scale = size as f32 / 32.0;
        let y_cpu_bar = (6.0 * scale).round() as i32;
        let y_mem_bar = (16.0 * scale).round() as i32;
        let y_bat_bar = (26.0 * scale).round() as i32;
        let bar_w = (28.0 * scale).round() as i32;
        let mut bar_h = (3.0 * scale).round() as i32;
        if bar_h < 3 {
            bar_h = 3;
        }
        draw_gauge(&mut buf, 2, y_cpu_bar, bar_w, bar_h, cpu, cpu_color);
        draw_gauge(&mut buf, 2, y_mem_bar, bar_w, bar_h, mem, mem_color);
        draw_gauge(&mut buf, 2, y_bat_bar, bar_w, bar_h, battery, bat_color);
    }

    buf
}

fn draw_triangle(buf: &mut [u8], size: i32, is_up: bool, color: (u8, u8, u8)) {
    if is_up {
        let rows = [(8, 8), (7, 9), (6, 10), (5, 11), (5, 11)];
        for (y, &(x0, x1)) in rows.iter().enumerate() {
            for x in x0..=x1 {
                let idx = ((y as i32 * size + x) * 3) as usize;
                buf[idx] = color.0;
                buf[idx + 1] = color.1;
                buf[idx + 2] = color.2;
            }
        }
    } else {
        let rows = [(5, 11), (5, 11), (6, 10), (7, 9), (8, 8)];
        for (y, &(x0, x1)) in rows.iter().enumerate() {
            for x in x0..=x1 {
                let idx = ((y as i32 * size + x) * 3) as usize;
                buf[idx] = color.0;
                buf[idx + 1] = color.1;
                buf[idx + 2] = color.2;
            }
        }
    }
}

fn draw_triangle_32(buf: &mut [u8], size: i32, is_up: bool, color: (u8, u8, u8)) {
    let y_range = if is_up {
        vec![(4, 25, 25), (5, 24, 26), (6, 23, 27), (7, 22, 28), (8, 21, 29), (9, 21, 29), (10, 21, 29)]
    } else {
        vec![(10, 25, 25), (9, 24, 26), (8, 23, 27), (7, 22, 28), (6, 21, 29), (5, 21, 29), (4, 21, 29)]
    };
    for (y, x0, x1) in y_range {
        for x in x0..=x1 {
            let idx = ((y * size + x) * 3) as usize;
            buf[idx] = color.0;
            buf[idx + 1] = color.1;
            buf[idx + 2] = color.2;
        }
    }
}

fn render_stock(symbol: &str, price: f64, change: f64, size: u32) -> Vec<u8> {
    let mut buf = vec![0u8; (size * size * 3) as usize];
    for i in 0..(size * size) as usize {
        buf[i * 3] = 5;
        buf[i * 3 + 1] = 6;
        buf[i * 3 + 2] = 12;
    }

    let is_up = change >= 0.0;
    let text_color = if is_up { (0, 255, 180) } else { (255, 60, 60) };
    let font = BitmapFont::new(FONT_BYTES);

    if size == 16 {
        draw_triangle(&mut buf, size as i32, is_up, text_color);
        font.draw_text(&mut buf, size as i32, 0, 6, &symbol.to_uppercase(), (255, 255, 255), 1, Some(size as i32));
    } else {
        font.draw_text(&mut buf, size as i32, 2, 2, &symbol.to_uppercase(), (255, 255, 255), 1, Some(size as i32 - 2));
        draw_triangle_32(&mut buf, size as i32, is_up, text_color);
        font.draw_text(&mut buf, size as i32, 2, 16, &format!("${:.2}", price), text_color, 1, Some(size as i32 - 2));
    }

    buf
}

// --- macOS Battery stats ---

fn get_battery_percent() -> Option<u8> {
    let output = std::process::Command::new("pmset")
        .args(&["-g", "batt"])
        .output()
        .ok()?;
    let text = String::from_utf8_lossy(&output.stdout);
    for line in text.lines() {
        if line.contains("InternalBattery") || line.contains("Drawing from") {
            if let Some(idx) = line.find('%') {
                let text_before = &line[..idx];
                if let Some(start) = text_before.rfind(|c: char| !c.is_numeric()) {
                    if let Ok(pct) = text_before[start + 1..].parse::<u8>() {
                        return Some(pct);
                    }
                }
            }
        }
    }
    None
}

// --- macOS Media AppleScripts ---

struct TrackInfo {
    track: String,
    artist: String,
    _source: String,
    artwork_url: Option<String>,
}

fn get_feishin_running() -> bool {
    std::process::Command::new("pgrep")
        .arg("-q")
        .arg("Feishin")
        .status()
        .ok()
        .map(|s| s.success())
        .unwrap_or(false)
}

fn find_feishin_creds() -> Option<(String, String)> {
    let home = std::env::var("HOME").ok()?;
    let path = std::path::PathBuf::from(home)
        .join("Library/Application Support/Feishin/Local Storage/leveldb");
    if !path.is_dir() {
        return None;
    }
    let mut server_url = None;
    let mut auth_qs = None;
    
    if let Ok(entries) = std::fs::read_dir(path) {
        for entry in entries.flatten() {
            let fpath = entry.path();
            let ext = fpath.extension().and_then(|s| s.to_str()).unwrap_or("");
            if ext == "ldb" || ext == "log" {
                if let Ok(data) = std::fs::read(&fpath) {
                    if auth_qs.is_none() {
                        if let Some(idx) = find_subsequence(&data, b"\"credential\":\"") {
                            let start = idx + 14;
                            if let Some(end) = data[start..].iter().position(|&b| b == b'"') {
                                if let Ok(s) = std::str::from_utf8(&data[start..start + end]) {
                                    if s.starts_with("u=") {
                                        auth_qs = Some(s.to_string());
                                    }
                                }
                            }
                        }
                    }
                    if server_url.is_none() {
                        if let Some(idx) = find_subsequence(&data, b"\"url\":\"http") {
                            let start = idx + 7;
                            if let Some(end) = data[start..].iter().position(|&b| b == b'"') {
                                if let Ok(s) = std::str::from_utf8(&data[start..start + end]) {
                                    server_url = Some(s.to_string());
                                }
                            }
                        }
                    }
                    if auth_qs.is_some() && server_url.is_some() {
                        break;
                    }
                }
            }
        }
    }
    
    match (server_url, auth_qs) {
        (Some(url), Some(qs)) => Some((url, qs)),
        _ => None,
    }
}

fn find_subsequence(haystack: &[u8], needle: &[u8]) -> Option<usize> {
    haystack.windows(needle.len()).position(|window| window == needle)
}

async fn get_feishin_playing_track(client: &reqwest::Client) -> Option<TrackInfo> {
    if !get_feishin_running() {
        return None;
    }
    let (server_url, auth_qs) = find_feishin_creds()?;
    let api_url = format!("{}/rest/getNowPlaying.view?f=json&c=divoom&v=1.16.0&{}", server_url, auth_qs);
    
    let res = client.get(&api_url)
        .timeout(Duration::from_secs(5))
        .send()
        .await
        .ok()?;
    let body: serde_json::Value = res.json().await.ok()?;
    let sr = body.get("subsonic-response")?;
    if sr.get("status")?.as_str()? != "ok" {
        return None;
    }
    let np = sr.get("nowPlaying")?;
    let entries = np.get("entry")?;
    let entry = if entries.is_array() {
        entries.as_array()?.first()?
    } else {
        entries
    };
    let title = entry.get("title")?.as_str()?.to_string();
    let artist = entry.get("artist").and_then(|v| v.as_str()).unwrap_or("").to_string();
    let cover_art = entry.get("coverArt").and_then(|v| v.as_str());
    let artwork_url = cover_art.map(|id| {
        format!("{}/rest/getCoverArt.view?f=json&c=divoom&v=1.16.0&id={}&{}", server_url, id, auth_qs)
    });
    Some(TrackInfo {
        track: title,
        artist,
        _source: "Feishin".to_string(),
        artwork_url,
    })
}

async fn get_kaset_playing_track() -> Option<TrackInfo> {
    let script = r#"
    if application "Kaset" is running then
        tell application "Kaset"
            set infoJson to get player info
            if infoJson is not "" then
                return infoJson
            end if
        end tell
    end if
    return ""
    "#;
    let output = std::process::Command::new("osascript")
        .arg("-e")
        .arg(script)
        .output()
        .ok()?;
    let raw = String::from_utf8_lossy(&output.stdout).trim().to_string();
    if raw.is_empty() {
        return None;
    }
    let info: serde_json::Value = serde_json::from_str(&raw).ok()?;
    if info.get("isPlaying")?.as_bool()? {
        let ct = info.get("currentTrack")?;
        let name = ct.get("name")?.as_str()?;
        let artist = ct.get("artist").and_then(|v| v.as_str()).unwrap_or("");
        let artwork_url = ct.get("artworkURL").and_then(|v| v.as_str()).map(|s| s.to_string());
        return Some(TrackInfo {
            track: name.to_string(),
            artist: artist.to_string(),
            _source: "Kaset".to_string(),
            artwork_url,
        });
    }
    None
}

async fn get_spotify_playing_track() -> Option<TrackInfo> {
    let script = r#"
    if application "Spotify" is running then
        tell application "Spotify"
            if player state is playing then
                return name of current track & " -|- " & artist of current track
            end if
        end tell
    end if
    return ""
    "#;
    let output = std::process::Command::new("osascript")
        .arg("-e")
        .arg(script)
        .output()
        .ok()?;
    let raw = String::from_utf8_lossy(&output.stdout).trim().to_string();
    if raw.contains(" -|- ") {
        let parts: Vec<&str> = raw.split(" -|- ").collect();
        return Some(TrackInfo {
            track: parts[0].to_string(),
            artist: parts[1].to_string(),
            _source: "Spotify".to_string(),
            artwork_url: None,
        });
    }
    None
}

async fn get_music_playing_track() -> Option<TrackInfo> {
    let script = r#"
    if application "Music" is running then
        tell application "Music"
            if player state is playing then
                return name of current track & " -|- " & artist of current track
            end if
        end tell
    end if
    return ""
    "#;
    let output = std::process::Command::new("osascript")
        .arg("-e")
        .arg(script)
        .output()
        .ok()?;
    let raw = String::from_utf8_lossy(&output.stdout).trim().to_string();
    if raw.contains(" -|- ") {
        let parts: Vec<&str> = raw.split(" -|- ").collect();
        return Some(TrackInfo {
            track: parts[0].to_string(),
            artist: parts[1].to_string(),
            _source: "Apple Music".to_string(),
            artwork_url: None,
        });
    }
    None
}

async fn get_current_playing_track(client: &reqwest::Client) -> Option<TrackInfo> {
    if cfg!(target_os = "macos") {
        if let Some(t) = get_feishin_playing_track(client).await {
            return Some(t);
        }
        if let Some(t) = get_kaset_playing_track().await {
            return Some(t);
        }
        if let Some(t) = get_spotify_playing_track().await {
            return Some(t);
        }
        if let Some(t) = get_music_playing_track().await {
            return Some(t);
        }
    }
    None
}

async fn fetch_album_art_url(client: &reqwest::Client, track: &str, artist: &str) -> Option<String> {
    let term = format!("{} {}", artist, track);
    let res = client.get("https://itunes.apple.com/search")
        .query(&[("term", term.as_str()), ("limit", "1"), ("entity", "song")])
        .timeout(Duration::from_secs(5))
        .send()
        .await
        .ok()?;
    let body: serde_json::Value = res.json().await.ok()?;
    let results = body.get("results")?.as_array()?;
    if !results.is_empty() {
        let artwork_url = results[0].get("artworkUrl100")?.as_str()?;
        return Some(artwork_url.replace("100x100bb", "500x500bb"));
    }
    None
}

// --- Device Helpers ---

async fn push_rgb_to_device(
    daemon: &Daemon,
    dev: &DeviceTransport,
    rgb: &[u8],
    w: i32,
    h: i32,
    time_ms: u16,
) -> Result<(), String> {
    if let DeviceTransport::Lan(_) = dev {
        return Err("LAN image push not supported".into());
    }

    #[cfg(feature = "ble")]
    {
        if let DeviceTransport::Ble(_) = dev {
            let enc = daemon.encoder().ok_or("encoder not available")?;
            let frame_body = if w == 32 && h == 32 {
                enc.encode_animation_frame_32(rgb, w, h, time_ms)
            } else {
                enc.encode_animation_frame(rgb, w, h, time_ms)
            };
            let blob = frame_body.ok_or("encode failed")?;
            
            dev.send_command(0x45, &[0x05, 0, 0, 0, 0, 0, 0, 0, 0, 0], false)
                .await
                .map_err(|e| format!("show_design failed: {e}"))?;

            dev.stream_animation_8b(&blob)
                .await
                .map(|_| ())
                .map_err(|e| format!("stream_8b failed: {e}"))
        } else {
            Err("BLE not connected".into())
        }
    }
    #[cfg(not(feature = "ble"))]
    {
        let _ = (daemon, w, h, time_ms, rgb);
        Err("BLE support disabled".into())
    }
}

async fn get_device_transport(daemon: &Daemon, mac: &str) -> Option<Arc<DeviceTransport>> {
    let guard = daemon.device.lock().await;
    if guard.is_some() {
        let cur_id = daemon.device_id.lock().await.clone().unwrap_or_default();
        if cur_id == mac {
            return (*guard).clone();
        }
    }
    None
}

// --- Live Widgets Loops ---

async fn run_sysmon(daemon_weak: Weak<Daemon>, mac: String, params: Value) {
    let size = params.get("size").and_then(|v| v.as_u64()).unwrap_or(16) as u32;
    let mut sys = sysinfo::System::new_all();
    
    loop {
        let daemon = match daemon_weak.upgrade() {
            Some(d) => d,
            None => break,
        };

        sys.refresh_cpu();
        sys.refresh_memory();
        
        let cpu = sys.global_cpu_info().cpu_usage() as u8;
        let total_mem = sys.total_memory();
        let used_mem = sys.used_memory();
        let mem = if total_mem > 0 {
            ((used_mem as f64 / total_mem as f64) * 100.0) as u8
        } else {
            0
        };
        let battery = get_battery_percent().unwrap_or(100);

        let rgb = render_sysmon(cpu, mem, battery, size);

        if get_device_transport(&daemon, &mac).await.is_some() {
            let d_weak = daemon_weak.clone();
            let mac_clone = mac.clone();
            let _ = daemon.queue.run(None, async move {
                if let Some(d) = d_weak.upgrade() {
                    if let Some(dev_t) = get_device_transport(&d, &mac_clone).await {
                        let _ = push_rgb_to_device(&d, &dev_t, &rgb, size as i32, size as i32, 100).await;
                    }
                }
            }).await;
        }

        tokio::time::sleep(Duration::from_secs(5)).await;
    }
}

async fn run_stocks(daemon_weak: Weak<Daemon>, mac: String, params: Value) {
    let symbol = params.get("symbol").and_then(|v| v.as_str()).unwrap_or("").to_string();
    if symbol.is_empty() {
        return;
    }
    let size = params.get("size").and_then(|v| v.as_u64()).unwrap_or(16) as u32;
    let client = reqwest::Client::builder()
        .user_agent("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36")
        .build()
        .unwrap_or_default();

    loop {
        let daemon = match daemon_weak.upgrade() {
            Some(d) => d,
            None => break,
        };

        let api_url = format!("https://query1.finance.yahoo.com/v8/finance/chart/{}", symbol);
        let res = client.get(&api_url)
            .timeout(Duration::from_secs(5))
            .send()
            .await;

        if let Ok(resp) = res {
            if let Ok(body) = resp.json::<serde_json::Value>().await {
                if let Some(result) = body.get("chart").and_then(|c| c.get("result")).and_then(|r| r.as_array()) {
                    if let Some(meta) = result.first().and_then(|r| r.get("meta")) {
                        let price = meta.get("regularMarketPrice").and_then(|v| v.as_f64()).unwrap_or(0.0);
                        let prev_close = meta.get("chartPreviousClose").and_then(|v| v.as_f64()).unwrap_or(0.0);
                        let change = price - prev_close;

                        let rgb = render_stock(&symbol, price, change, size);

                        if get_device_transport(&daemon, &mac).await.is_some() {
                            let d_weak = daemon_weak.clone();
                            let mac_clone = mac.clone();
                            let _ = daemon.queue.run(None, async move {
                                if let Some(d) = d_weak.upgrade() {
                                    if let Some(dev_t) = get_device_transport(&d, &mac_clone).await {
                                        let _ = push_rgb_to_device(&d, &dev_t, &rgb, size as i32, size as i32, 100).await;
                                    }
                                }
                            }).await;
                        }
                    }
                }
            }
        }

        tokio::time::sleep(Duration::from_secs(15)).await;
    }
}

async fn run_weather(daemon_weak: Weak<Daemon>, mac: String, params: Value) {
    let location = params.get("location").and_then(|v| v.as_str()).unwrap_or("").to_string();
    let client = reqwest::Client::new();

    loop {
        let daemon = match daemon_weak.upgrade() {
            Some(d) => d,
            None => break,
        };

        let mut url = "https://wttr.in/".to_string();
        if !location.is_empty() {
            url.push_str(&location);
        }
        
        let res = client.get(&url)
            .query(&[("format", "j1")])
            .timeout(Duration::from_secs(8))
            .send()
            .await;

        if let Ok(resp) = res {
            if resp.status() == 200 {
                if let Ok(body) = resp.json::<serde_json::Value>().await {
                    if let Some(current) = body.get("current_condition").and_then(|c| c.as_array()).and_then(|a| a.first()) {
                        let temp_str = current.get("temp_C").and_then(|v| v.as_str()).unwrap_or("0");
                        let code_str = current.get("weatherCode").and_then(|v| v.as_str()).unwrap_or("113");
                        
                        let temp_c = temp_str.parse::<i8>().unwrap_or(0);
                        let weather_code = code_str.parse::<i32>().unwrap_or(113);
                        
                        let weather_type = match weather_code {
                            113 => 1, // Clear
                            116 | 119 | 122 => 3, // CloudySky
                            143 | 185 | 248 | 260 => 9, // Fog
                            176 | 263 | 266 | 281 | 284 | 293 | 296 | 299 | 302 | 305 | 308 | 311 | 314 | 353 | 356 | 359 => 6, // Rain
                            179 | 182 | 227 | 230 | 317 | 320 | 323 | 326 | 329 | 332 | 335 | 338 | 350 | 362 | 365 | 368 | 371 | 374 | 377 => 8, // Snow
                            200 | 386 | 389 | 392 | 395 => 5, // Thunderstorm
                            _ => 1, // Default to Clear
                        };

                        if get_device_transport(&daemon, &mac).await.is_some() {
                            let d_weak = daemon_weak.clone();
                            let mac_clone = mac.clone();
                            let _ = daemon.queue.run(None, async move {
                                if let Some(d) = d_weak.upgrade() {
                                    if let Some(dev_t) = get_device_transport(&d, &mac_clone).await {
                                        let _ = dev_t.send_command(0x32, &[0x01, 0x00, 0xFF, 0xFF, 0xFF, 0x00], false).await;
                                        let _ = dev_t.send_command(0x5f, &[temp_c as u8, weather_type], true).await;
                                    }
                                }
                            }).await;
                        }
                    }
                }
            }
        }

        tokio::time::sleep(Duration::from_secs(15 * 60)).await;
    }
}

async fn run_music(daemon_weak: Weak<Daemon>, mac: String, params: Value) {
    let size = params.get("size").and_then(|v| v.as_u64()).unwrap_or(16) as u32;
    let client = reqwest::Client::new();
    
    let mut last_track = String::new();
    let mut last_artist = String::new();

    loop {
        let daemon = match daemon_weak.upgrade() {
            Some(d) => d,
            None => break,
        };

        if let Some(track_info) = get_current_playing_track(&client).await {
            if track_info.track != last_track || track_info.artist != last_artist {
                let mut art_url = track_info.artwork_url;
                if art_url.is_none() {
                    art_url = fetch_album_art_url(&client, &track_info.track, &track_info.artist).await;
                }
                
                if let Some(url) = art_url {
                    if let Ok(resp) = client.get(&url).send().await {
                        if let Ok(bytes) = resp.bytes().await {
                            if let Ok(frames) = crate::image_proc::process_image_bytes(bytes.to_vec(), size, 100) {
                                if let Some((rgb, w, h, t)) = frames.first() {
                                    if get_device_transport(&daemon, &mac).await.is_some() {
                                        let d_weak = daemon_weak.clone();
                                        let mac_clone = mac.clone();
                                        let rgb_vec = rgb.clone();
                                        let w_val = *w;
                                        let h_val = *h;
                                        let t_val = *t;
                                        let success = daemon.queue.run(None, async move {
                                            if let Some(d) = d_weak.upgrade() {
                                                if let Some(dev_t) = get_device_transport(&d, &mac_clone).await {
                                                    push_rgb_to_device(&d, &dev_t, &rgb_vec, w_val, h_val, t_val).await.is_ok()
                                                } else {
                                                    false
                                                }
                                            } else {
                                                false
                                            }
                                        }).await.unwrap_or(false);
                                        
                                        if success {
                                            last_track = track_info.track.clone();
                                            last_artist = track_info.artist.clone();
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }

        tokio::time::sleep(Duration::from_millis(1500)).await;
    }
}

// --- Job Coordinator ---

#[derive(serde::Serialize, Clone)]
struct ActivityEntry {
    name: String,
    kind: String,
    preview: Option<String>,
    at: u64,
    state: String,
}

pub struct LiveJobCoordinator {
    tasks: Arc<Mutex<HashMap<(String, String), JoinHandle<()>>>>,
    activity: Arc<Mutex<HashMap<String, ActivityEntry>>>,
    params: Arc<Mutex<HashMap<(String, String), Value>>>,
}

impl Default for LiveJobCoordinator {
    fn default() -> Self {
        Self::new()
    }
}

impl LiveJobCoordinator {
    pub fn new() -> Self {
        Self {
            tasks: Arc::new(Mutex::new(HashMap::new())),
            activity: Arc::new(Mutex::new(HashMap::new())),
            params: Arc::new(Mutex::new(HashMap::new())),
        }
    }

    fn now_secs() -> u64 {
        SystemTime::now().duration_since(UNIX_EPOCH).unwrap_or_default().as_secs()
    }

    pub async fn start(&self, daemon: Arc<Daemon>, mac: String, kind: String, params: Value) -> Result<(), String> {
        self.stop(&daemon, &mac, &kind).await;

        let daemon_weak = Arc::downgrade(&daemon);
        let mac_clone = mac.clone();
        let params_clone = params.clone();
        
        let handle = match kind.as_str() {
            "sysmon" => tokio::spawn(run_sysmon(daemon_weak, mac_clone, params_clone)),
            "stocks" => tokio::spawn(run_stocks(daemon_weak, mac_clone, params_clone)),
            "weather" => tokio::spawn(run_weather(daemon_weak, mac_clone, params_clone)),
            "music" => tokio::spawn(run_music(daemon_weak, mac_clone, params_clone)),
            _ => return Err(format!("unknown live job kind: {}", kind)),
        };

        self.tasks.lock().await.insert((mac.clone(), kind.clone()), handle);
        self.params.lock().await.insert((mac.clone(), kind.clone()), params.clone());

        let dev_name = params.get("device_name").and_then(|v| v.as_str()).unwrap_or("Divoom").to_string();
        self.activity.lock().await.insert(mac, ActivityEntry {
            name: dev_name,
            kind,
            preview: None,
            at: Self::now_secs(),
            state: "active".to_string(),
        });

        Ok(())
    }

    pub async fn stop(&self, _daemon: &Daemon, mac: &str, kind: &str) -> bool {
        let key = (mac.to_string(), kind.to_string());
        let handle = self.tasks.lock().await.remove(&key);
        if let Some(h) = handle {
            h.abort();
            self.params.lock().await.remove(&key);
            
            let has_other = self.tasks.lock().await.keys().any(|(m, _)| m == mac);
            if !has_other {
                if let Some(entry) = self.activity.lock().await.get_mut(mac) {
                    entry.kind = "idle".to_string();
                    entry.at = Self::now_secs();
                }
            }
            true
        } else {
            false
        }
    }

    pub async fn stop_all(&self, _daemon: &Daemon) {
        let mut tasks = self.tasks.lock().await;
        for (_, handle) in tasks.drain() {
            handle.abort();
        }
        self.params.lock().await.clear();
        self.activity.lock().await.clear();
    }

    pub async fn stop_all_for_device(&self, daemon: &Daemon, mac: &str) -> usize {
        let keys: Vec<(String, String)> = self.tasks.lock().await.keys()
            .filter(|(m, _)| m == mac)
            .cloned()
            .collect();
        let count = keys.len();
        for (m, k) in keys {
            self.stop(daemon, &m, &k).await;
        }
        count
    }

    pub async fn list(&self, mac: Option<&str>) -> Vec<Value> {
        let tasks = self.tasks.lock().await;
        let mut list = Vec::new();
        for ((m, k), _) in tasks.iter() {
            if mac.is_none() || mac == Some(m) {
                list.push(json!({
                    "mac": m,
                    "kind": k,
                    "done": false,
                    "cancelled": false,
                }));
            }
        }
        list
    }

    pub async fn get_device_activity(&self) -> Value {
        let activity = self.activity.lock().await;
        let snap: HashMap<String, ActivityEntry> = activity.clone();
        json!({
            "success": true,
            "activity": snap,
        })
    }

    pub async fn set_device_activity(&self, mac: String, kind: String, name: Option<String>, preview: Option<String>) {
        let mut act = self.activity.lock().await;
        let entry = act.entry(mac).or_insert(ActivityEntry {
            name: name.clone().unwrap_or_else(|| "Divoom".to_string()),
            kind: kind.clone(),
            preview: None,
            at: Self::now_secs(),
            state: "active".to_string(),
        });
        entry.kind = kind;
        if let Some(n) = name {
            entry.name = n;
        }
        if let Some(p) = preview {
            entry.preview = Some(p);
        }
        entry.at = Self::now_secs();
    }
}

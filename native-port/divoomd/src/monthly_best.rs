//! Monthly Best sync background service.
//! Ports `divoom_lib/monthly_best_daemon.py`.

use std::collections::HashMap;
use std::sync::Arc;
use std::time::Duration;
use tokio::time::sleep;
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};

use crate::daemon::Daemon;
use crate::protocol::Request;
use base64::Engine;

#[derive(Serialize, Deserialize, Clone, Debug)]
pub struct HotchannelConfig {
    #[serde(default)]
    pub enabled: bool,
    #[serde(default = "default_interval")]
    pub interval: u64,
    #[serde(default = "default_classify")]
    pub classify: i64,
    #[serde(default)]
    pub targets: Vec<String>,
    #[serde(default)]
    pub device_galleries: HashMap<String, Value>,
}

fn default_interval() -> u64 { 3600 }
fn default_classify() -> i64 { 18 }

pub fn load_hotchannel_config() -> HotchannelConfig {
    let mut path = match crate::cloud::config_dir() {
        Some(p) => p,
        None => return default_config(),
    };
    path.push("hotchannel.json");
    if !path.exists() {
        return default_config();
    }
    let content = match std::fs::read_to_string(&path) {
        Ok(c) => c,
        Err(_) => return default_config(),
    };
    let mut cfg: HotchannelConfig = match serde_json::from_str(&content) {
        Ok(c) => c,
        Err(_) => return default_config(),
    };
    
    // Normalize values
    cfg.interval = cfg.interval.clamp(60, 2592000); // 60s to 30 days
    if cfg.classify <= 0 {
        cfg.classify = 18;
    }
    cfg
}

fn default_config() -> HotchannelConfig {
    HotchannelConfig {
        enabled: false,
        interval: 3600,
        classify: 18,
        targets: Vec::new(),
        device_galleries: HashMap::new(),
    }
}

pub fn extract_gif_from_magic_43(data: &[u8]) -> Option<Vec<u8>> {
    if data.len() < 10 || data[0] != 43 { return None; }
    let text_len = u32::from_le_bytes(data[6..10].try_into().ok()?) as usize;
    let text_end = 10 + text_len;
    if data.len() < text_end + 4 { return None; }
    let gif_len = u32::from_le_bytes(data[text_end..text_end+4].try_into().ok()?) as usize;
    let gif_start = text_end + 4;
    let gif_end = gif_start + gif_len;
    if gif_end > data.len() { return None; }
    let gif_data = &data[gif_start..gif_end];
    if gif_data.starts_with(b"GIF89a") || gif_data.starts_with(b"GIF87a") {
        return Some(gif_data.to_vec());
    }
    None
}

pub async fn monthly_best_loop_task(daemon: Arc<Daemon>) {
    // Wait a brief moment after startup before starting
    sleep(Duration::from_secs(5)).await;

    loop {
        let config = load_hotchannel_config();
        if !config.enabled {
            sleep(Duration::from_secs(30)).await;
            continue;
        }

        let interval_secs = config.interval;
        println!("[ ==> ] Native Monthly Best Sync loop cycle started.");

        for target in &config.targets {
            let mut classify = config.classify;
            if let Some(c_val) = config.device_galleries.get(target) {
                if let Some(c) = c_val.as_i64() {
                    classify = c;
                }
            }

            println!("[ ==> ] Fetching gallery for target {} (classify={})...", target, classify);
            // Limit to 5 items to match python daemon default limit
            match crate::cloud::fetch_gallery(classify, 5, 1, 127).await {
                Ok(resp_val) => {
                    let file_list = resp_val.get("FileList").and_then(|v| v.as_array());
                    if let Some(files) = file_list {
                        if !files.is_empty() {
                            println!("[ Ok  ] Found {} files. Syncing to {}...", files.len(), target);
                            if let Err(e) = sync_files_to_device(&daemon, target, files).await {
                                eprintln!("[ Err ] Failed to sync to {}: {}", target, e);
                            }
                        }
                    }
                }
                Err(e) => {
                    eprintln!("[ Err ] Failed to fetch gallery for {}: {}", target, e);
                }
            }
        }

        println!("[ ==> ] Sleeping for {} seconds until next monthly best cycle...", interval_secs);
        sleep(Duration::from_secs(interval_secs)).await;
    }
}

async fn sync_files_to_device(
    daemon: &Daemon,
    target: &str,
    files: &[Value],
) -> Result<(), String> {
    // 1. Connect
    let mut connect_args = json!({});
    if target.starts_with("LAN:") {
        let ip = &target[4..];
        connect_args = json!({
            "lan_ip": ip
        });
    } else {
        connect_args = json!({
            "mac": target,
            "use_ios_le_protocol": true
        });
    }

    let req_connect = Request {
        command: "connect_device".to_string(),
        args: connect_args,
        token: None,
    };
    
    let res = daemon.dispatch(req_connect).await;
    if !res.get("success").and_then(|v| v.as_bool()).unwrap_or(false) {
        let err = res.get("error").and_then(|v| v.as_str()).unwrap_or("unknown connection error");
        return Err(format!("Connection to {} failed: {}", target, err));
    }

    // 2. Download and stream each file
    let client = reqwest::Client::builder()
        .timeout(Duration::from_secs(15))
        .user_agent("okhttp/4.12.0")
        .build()
        .map_err(|e| e.to_string())?;

    for (idx, item) in files.iter().enumerate() {
        let file_id = match item.get("FileId").and_then(|v| v.as_str()) {
            Some(f) => f,
            None => continue,
        };
        let file_name = item.get("FileName").and_then(|v| v.as_str()).unwrap_or("unnamed");

        println!("[ ==> ] Downloading item [{}/{}]: {} ({})...", idx + 1, files.len(), file_name, file_id);
        let dl_url = format!("https://fin.divoom-gz.com/{}", file_id);
        
        let resp = match client.get(&dl_url).send().await {
            Ok(r) => r,
            Err(e) => {
                eprintln!("[ Wrn ] Failed to download {}: {}", file_name, e);
                continue;
            }
        };

        if resp.status() != 200 {
            eprintln!("[ Wrn ] Download of {} failed with status {}", file_name, resp.status());
            continue;
        }

        let file_bytes = match resp.bytes().await {
            Ok(b) => b.to_vec(),
            Err(e) => {
                eprintln!("[ Wrn ] Failed to read bytes for {}: {}", file_name, e);
                continue;
            }
        };

        if file_bytes.len() < 4 {
            continue;
        }

        // Determine if file is a native binary payload or a GIF
        let has_gif_magic = file_bytes.starts_with(b"GIF");
        let has_m43_magic = file_bytes.starts_with(&[43]); // magic 43 container
        
        let is_gif = has_gif_magic || has_m43_magic;

        let success = if is_gif {
            // It is a GIF/image. Save to a temp file and send display.show_image.
            let gif_data = if has_m43_magic {
                match extract_gif_from_magic_43(&file_bytes) {
                    Some(g) => g,
                    None => {
                        eprintln!("[ Wrn ] Failed to extract GIF from magic 43 container");
                        continue;
                    }
                }
            } else {
                file_bytes
            };

            let temp_path = std::env::temp_dir().join(format!("mb_sync_temp_{}.gif", idx));
            if let Err(e) = std::fs::write(&temp_path, &gif_data) {
                eprintln!("[ Wrn ] Failed to write temp GIF file: {}", e);
                continue;
            }

            let req_show = Request {
                command: "device_call".to_string(),
                args: json!({
                    "method": "display.show_image",
                    // device_call reads positional args from "args" and named from
                    // "kwargs" (NOT "raw_args"/"kw") — using the wrong keys silently
                    // dropped the path + size, so show_image errored.
                    "args": [temp_path.to_str().unwrap_or("")],
                    "kwargs": {"size": 16}
                }),
                token: None,
            };

            let res_show = daemon.dispatch(req_show).await;
            res_show.get("success").and_then(|v| v.as_bool()).unwrap_or(false)
        } else {
            // Native binary payload. Stream it directly.
            // Insert the binary payload into blob_map at index 0
            // and dispatch animation.stream_animation_8b.
            let req_stream = Request {
                command: "device_call".to_string(),
                args: json!({
                    "method": "animation.stream_animation_8b",
                    "blobs": {
                        "0": base64::engine::general_purpose::STANDARD.encode(&file_bytes)
                    }
                }),
                token: None,
            };
            let res_stream = daemon.dispatch(req_stream).await;
            res_stream.get("success").and_then(|v| v.as_bool()).unwrap_or(false)
        };

        if success {
            println!("[ Ok  ] Successfully pushed {}", file_name);
        } else {
            eprintln!("[ Err ] Failed to push {}", file_name);
        }

        if idx < files.len() - 1 {
            sleep(Duration::from_secs(15)).await;
        }
    }

    // 3. Disconnect
    let req_disconnect = Request {
        command: "disconnect_device".to_string(),
        args: json!({}),
        token: None,
    };
    daemon.dispatch(req_disconnect).await;
    println!("[ ==> ] Sync completed for target {}", target);

    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    use tempfile::TempDir;

    #[test]
    fn test_extract_gif_from_magic_43() {
        // magic byte 43 (0x2b) + text_len (4 bytes LE) + text content + gif_len (4 bytes LE) + GIF89a
        let text_content = b"my metadata text content";
        let gif_content = b"GIF89a_my_awesome_gif_data_here";
        let mut data = vec![43u8, 0, 0, 0, 0, 0];
        data.extend_from_slice(&(text_content.len() as u32).to_le_bytes());
        data.extend_from_slice(text_content);
        data.extend_from_slice(&(gif_content.len() as u32).to_le_bytes());
        data.extend_from_slice(gif_content);

        let extracted = extract_gif_from_magic_43(&data).unwrap();
        assert_eq!(extracted, gif_content);
    }

    #[test]
    fn test_load_hotchannel_config() {
        let _lock = crate::cloud::TEST_MUTEX.get_or_init(|| std::sync::Mutex::new(())).lock().unwrap();
        let temp = TempDir::new().unwrap();
        std::env::set_var("HOME", temp.path());

        let conf_dir = temp.path().join(".config").join("divoom-control");
        fs::create_dir_all(&conf_dir).unwrap();

        let hc_json = r#"{"enabled": true, "interval": 120, "classify": 9, "targets": ["AA:BB:CC:DD:EE:FF"]}"#;
        fs::write(conf_dir.join("hotchannel.json"), hc_json).unwrap();

        let cfg = load_hotchannel_config();
        assert!(cfg.enabled);
        assert_eq!(cfg.interval, 120);
        assert_eq!(cfg.classify, 9);
        assert_eq!(cfg.targets, vec!["AA:BB:CC:DD:EE:FF"]);
    }
}

//! `sync_artwork` command — Python-daemon parity. Download a cloud artwork by
//! `file_id`, resolve it to a renderable payload, and show it on the currently
//! connected device. Mirrors `device_owner.sync_artwork`: GIF / magic-43 container
//! → `display.show_image`; anything else → raw `animation.stream_animation_8b`.
//!
//! Routes through `device_call` (so it targets the already-connected device and
//! reuses the exclusive gate + encoder), passing the payload as an in-memory blob
//! (no temp files, and the correct `blobs`/`kwargs` keys the dispatcher reads).

use base64::Engine;
use serde_json::{json, Value};

use crate::daemon::Daemon;
use crate::monthly_best::extract_gif_from_magic_43;
use crate::protocol::{err_reply, Request};

pub async fn sync_artwork(daemon: &Daemon, args: &Value) -> Value {
    let file_id = match args.get("file_id").and_then(|v| v.as_str()) {
        Some(f) if !f.is_empty() => f.to_string(),
        _ => return err_reply("sync_artwork requires 'file_id'"),
    };
    let size = args.get("default_size").and_then(|v| v.as_u64()).unwrap_or(16);

    let client = match reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(15))
        .user_agent("okhttp/4.12.0")
        .build()
    {
        Ok(c) => c,
        Err(e) => return err_reply(&format!("sync_artwork: client build failed: {e}")),
    };

    let url = format!("https://fin.divoom-gz.com/{file_id}");
    let file_bytes = match client.get(&url).send().await {
        Ok(r) if r.status() == 200 => match r.bytes().await {
            Ok(b) => b.to_vec(),
            Err(e) => return err_reply(&format!("sync_artwork: read body failed: {e}")),
        },
        Ok(r) => return err_reply(&format!("sync_artwork: download status {}", r.status())),
        Err(e) => return err_reply(&format!("sync_artwork: download failed: {e}")),
    };
    if file_bytes.len() < 4 {
        return err_reply("sync_artwork: downloaded file too small");
    }

    let has_gif = file_bytes.starts_with(b"GIF");
    let has_m43 = file_bytes.starts_with(&[43]); // magic-43 container

    let dispatch_args = if has_gif || has_m43 {
        // Resolve to a plain GIF and render via display.show_image (the APK path).
        let gif = if has_m43 {
            match extract_gif_from_magic_43(&file_bytes) {
                Some(g) => g,
                None => return err_reply("sync_artwork: magic-43 container decode failed"),
            }
        } else {
            file_bytes
        };
        json!({
            "method": "display.show_image",
            "kwargs": {"size": size},
            "blobs": {"0": base64::engine::general_purpose::STANDARD.encode(&gif)},
        })
    } else {
        // Unknown magic: last-resort raw 0x8B stream (matches the Python fallback).
        json!({
            "method": "animation.stream_animation_8b",
            "blobs": {"0": base64::engine::general_purpose::STANDARD.encode(&file_bytes)},
        })
    };

    // Box the recursive dispatch (sync_artwork is itself reached via dispatch) so
    // the async future has a finite size.
    let res = Box::pin(daemon.dispatch(Request {
        command: "device_call".to_string(),
        args: dispatch_args,
        token: None,
    }))
    .await;
    let ok = res.get("success").and_then(|v| v.as_bool()).unwrap_or(false);
    json!({"success": ok})
}

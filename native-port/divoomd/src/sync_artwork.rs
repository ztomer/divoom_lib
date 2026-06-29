//! `sync_artwork` command — Python-daemon parity (`device_owner.sync_artwork` +
//! `media_decoder.resolve_to_gif`). Download a cloud artwork by `file_id`, resolve
//! it to a renderable image, and show it on the connected device via
//! `display.show_image` (which resizes NEAREST to the device size and 0x8B-streams,
//! matching the Python resize-then-show path).
//!
//! PARITY NOTE: Python's `resolve_to_gif` also decodes AES cloud containers
//! (magic 9/18/26) and 0xAA hot files. The native daemon currently resolves
//! GIF/PNG/JPG and magic-43 (which covers files the device can render directly);
//! magic 9/18/26 (AES, +LZO for 18/26) and 0xAA decode to raw RGB frame lists and
//! are NOT yet ported. For those we return an HONEST error rather than raw-streaming
//! undecodable bytes — raw-streaming a container the device can't parse leaves it
//! stuck in its loading animation (observed on a Timoo with a magic-18 file).

use base64::Engine;
use serde_json::{json, Value};

use crate::daemon::Daemon;
use crate::media::resolve_to_gif;
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

    let img = match resolve_to_gif(&file_bytes) {
        Some(b) => b,
        None => {
            return err_reply(&format!(
                "sync_artwork: unrecognized container magic {} (could not resolve to an image; \
                 never raw-streamed to avoid sticking the device).",
                file_bytes[0]
            ));
        }
    };

    // display.show_image resizes (NEAREST) to `size` and 0x8B-streams. Box the
    // recursive dispatch (sync_artwork is itself reached via dispatch).
    let res = Box::pin(daemon.dispatch(Request {
        command: "device_call".to_string(),
        args: json!({
            "method": "display.show_image",
            "kwargs": {"size": size},
            "blobs": {"0": base64::engine::general_purpose::STANDARD.encode(&img)},
        }),
        token: None,
    }))
    .await;
    let ok = res.get("success").and_then(|v| v.as_bool()).unwrap_or(false);
    json!({"success": ok})
}

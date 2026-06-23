use serde_json::{json, Value};
use crate::protocol::err_reply;
use super::CallCtx;

#[cfg(feature = "ble")]
pub async fn handle(method: &str, ctx: CallCtx<'_>) -> Value {
    let dev = ctx.dev;
    let args = ctx.args;
    let raw_args = ctx.raw_args;
    let kw = ctx.kwargs;

    match method {
        "scoreboard.set_scoreboard" | "set_scoreboard" => {
            let on_off = args.first().copied()
                .or_else(|| kw.and_then(|v| v.get("on_off")).and_then(|v| v.as_i64()))
                .unwrap_or(0) as u8;
            let red_score = args.get(1).copied()
                .or_else(|| kw.and_then(|v| v.get("red_score")).and_then(|v| v.as_i64()))
                .unwrap_or(0).clamp(0, 999) as u16;
            let blue_score = args.get(2).copied()
                .or_else(|| kw.and_then(|v| v.get("blue_score")).and_then(|v| v.as_i64()))
                .unwrap_or(0).clamp(0, 999) as u16;
            let mut payload = Vec::with_capacity(6);
            payload.push(1u8); // TOOL_TYPE_SCORE
            payload.push(on_off);
            payload.extend_from_slice(&red_score.to_le_bytes());
            payload.extend_from_slice(&blue_score.to_le_bytes());
            match dev.send_command(0x72, &payload, true).await {
                Ok(()) => json!({"success": true, "result": true}),
                Err(e) => err_reply(&format!("set_scoreboard failed: {e}")),
            }
        }
        "scoreboard.get_scoreboard" | "get_scoreboard" => {
            match dev.send_command_and_wait(0x71, &[1], ctx.timeout).await {
                Some(p) if p.len() >= 5 => json!({
                    "success": true,
                    "result": {
                        "on_off": p[0] as i64,
                        "red_score": u16::from_le_bytes([p[1], p[2]]) as i64,
                        "blue_score": u16::from_le_bytes([p[3], p[4]]) as i64,
                    }
                }),
                _ => json!({"success": true, "result": Value::Null}),
            }
        }
        "timer.set_timer" | "set_timer" => {
            let ctrl_flag = args.first().copied()
                .or_else(|| kw.and_then(|v| v.get("ctrl_flag")).and_then(|v| v.as_i64()))
                .unwrap_or(0) as u8;
            let payload = [0u8, ctrl_flag]; // TOOL_TYPE_TIMER = 0
            match dev.send_command(0x72, &payload, true).await {
                Ok(()) => json!({"success": true, "result": true}),
                Err(e) => err_reply(&format!("set_timer failed: {e}")),
            }
        }
        "timer.get_timer" | "get_timer" => {
            match dev.send_command_and_wait(0x71, &[0], ctx.timeout).await {
                Some(p) if p.len() >= 1 => json!({
                    "success": true,
                    "result": {
                        "status": p[0] as i64,
                    }
                }),
                _ => json!({"success": true, "result": Value::Null}),
            }
        }
        "countdown.set_countdown" | "set_countdown" => {
            let ctrl_flag = args.first().copied()
                .or_else(|| kw.and_then(|v| v.get("ctrl_flag")).and_then(|v| v.as_i64()))
                .unwrap_or(0) as u8;
            let minutes = args.get(1).copied()
                .or_else(|| kw.and_then(|v| v.get("minutes")).and_then(|v| v.as_i64()))
                .unwrap_or(0) as u8;
            let seconds = args.get(2).copied()
                .or_else(|| kw.and_then(|v| v.get("seconds")).and_then(|v| v.as_i64()))
                .unwrap_or(0) as u8;
            let payload = [3u8, ctrl_flag, minutes, seconds]; // TOOL_TYPE_COUNTDOWN = 3
            match dev.send_command(0x72, &payload, true).await {
                Ok(()) => json!({"success": true, "result": true}),
                Err(e) => err_reply(&format!("set_countdown failed: {e}")),
            }
        }
        "countdown.get_countdown" | "get_countdown" => {
            match dev.send_command_and_wait(0x71, &[3], ctx.timeout).await {
                Some(p) if p.len() >= 3 => json!({
                    "success": true,
                    "result": {
                        "status": p[0] as i64,
                        "minutes": p[1] as i64,
                        "seconds": p[2] as i64,
                    }
                }),
                _ => json!({"success": true, "result": Value::Null}),
            }
        }
        "noise.set_noise" | "set_noise" => {
            let ctrl_flag = args.first().copied()
                .or_else(|| kw.and_then(|v| v.get("ctrl_flag")).and_then(|v| v.as_i64()))
                .unwrap_or(0) as u8;
            let payload = [2u8, ctrl_flag]; // TOOL_TYPE_NOISE = 2
            match dev.send_command(0x72, &payload, true).await {
                Ok(()) => json!({"success": true, "result": true}),
                Err(e) => err_reply(&format!("set_noise failed: {e}")),
            }
        }
        "noise.get_noise" | "get_noise" => {
            match dev.send_command_and_wait(0x71, &[2], ctx.timeout).await {
                Some(p) if p.len() >= 1 => json!({
                    "success": true,
                    "result": {
                        "status": p[0] as i64,
                    }
                }),
                _ => json!({"success": true, "result": Value::Null}),
            }
        }
        "device.show_notification" | "show_notification" | "notification.show_notification" => {
            let app_type = args.first().copied()
                .or_else(|| kw.and_then(|v| v.get("app_type")).and_then(|v| v.as_i64()))
                .unwrap_or(1) as u8;
            let wire = if app_type >= 8 { app_type + 1 } else { app_type };
            match dev.send_command(0x50, &[wire], true).await {
                Ok(()) => json!({"success": true, "result": true}),
                Err(e) => err_reply(&format!("show_notification failed: {e}")),
            }
        }
        "device.show_notification_text" | "show_notification_text" | "notification.show_notification_text" => {
            let app_type = args.first().copied()
                .or_else(|| kw.and_then(|v| v.get("app_type")).and_then(|v| v.as_i64()))
                .unwrap_or(1) as u8;
            let text = raw_args.get(1)
                .and_then(|v| v.as_str())
                .or_else(|| kw.and_then(|v| v.get("text")).and_then(|v| v.as_str()))
                .unwrap_or("");
            let mut text_bytes = text.as_bytes().to_vec();
            if text_bytes.len() > 128 {
                text_bytes.truncate(128);
            }
            let mut payload = Vec::with_capacity(2 + text_bytes.len());
            payload.push(app_type);
            payload.push(text_bytes.len() as u8);
            payload.extend_from_slice(&text_bytes);
            match dev.send_command(0x50, &payload, true).await {
                Ok(()) => json!({"success": true, "result": true}),
                Err(e) => err_reply(&format!("show_notification_text failed: {e}")),
            }
        }
        _ => err_reply("unimplemented tools command"),
    }
}

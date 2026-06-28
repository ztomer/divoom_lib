use serde_json::{json, Value};
use crate::protocol::err_reply;
use super::CallCtx;

pub async fn handle(method: &str, ctx: CallCtx<'_>) -> Value {
    let dev = ctx.dev;
    let args = ctx.args;
    let raw_args = ctx.raw_args;
    let kw = ctx.kwargs;
    let timeout = ctx.timeout;

    match method {
        "time.set_hour_type" | "set_hour_type" | "system.set_hour_type" => {
            let hour_type = args.first().copied()
                .or_else(|| kw.and_then(|v| v.get("hour_type")).and_then(|v| v.as_i64()))
                .unwrap_or(0) as u8;
            match dev.send_command(0x2c, &[hour_type], true).await {
                Ok(()) => json!({"success": true, "result": true}),
                Err(e) => err_reply(&format!("set_hour_type failed: {e}")),
            }
        }
        "bluetooth.set_bluetooth_password" | "set_bluetooth_password" | "system.set_bluetooth_password" => {
            let control = args.first().copied()
                .or_else(|| kw.and_then(|v| v.get("control")).and_then(|v| v.as_i64()))
                .unwrap_or(0) as u8;
            let password = raw_args.get(1)
                .and_then(|v| v.as_str())
                .or_else(|| kw.and_then(|v| v.get("password")).and_then(|v| v.as_str()))
                .unwrap_or("");
            
            let mut payload = Vec::new();
            payload.push(control);

            if control == 1 {
                if password.len() != 4 || !password.chars().all(|c| c.is_ascii_digit()) {
                    return err_reply("Password must be a 4-digit string");
                }
                for c in password.chars() {
                    payload.push(c.to_digit(10).unwrap() as u8);
                }
            }

            match dev.send_command(0x27, &payload, true).await {
                Ok(()) => json!({"success": true, "result": true}),
                Err(e) => err_reply(&format!("set_bluetooth_password failed: {e}")),
            }
        }
        "system.get_work_mode" | "get_work_mode" => {
            match dev.send_command_and_wait(0x13, &[], timeout).await {
                Some(p) if p.len() >= 1 => json!({"success": true, "result": p[0] as i64}),
                _ => json!({"success": true, "result": Value::Null}),
            }
        }
        "system.set_work_mode" | "set_work_mode" => {
            let mode = args.first().copied()
                .or_else(|| kw.and_then(|v| v.get("mode")).and_then(|v| v.as_i64()))
                .unwrap_or(0) as u8;
            match dev.send_command(0x05, &[mode], true).await {
                Ok(()) => json!({"success": true, "result": true}),
                Err(e) => err_reply(&format!("set_work_mode failed: {e}")),
            }
        }
        "system.set_channel" | "set_channel" | "device.set_channel" => {
            let channel_id = args.first().copied()
                .or_else(|| kw.and_then(|v| v.get("channel_id")).and_then(|v| v.as_i64()))
                .unwrap_or(0) as u8;
            match dev.send_command(0x45, &[channel_id], true).await {
                Ok(()) => json!({"success": true, "result": true}),
                Err(e) => err_reply(&format!("set_channel failed: {e}")),
            }
        }
        "system.send_sd_status" | "send_sd_status" | "device.send_sd_status" => {
            let status = args.first().copied()
                .or_else(|| kw.and_then(|v| v.get("status")).and_then(|v| v.as_i64()))
                .unwrap_or(0) as u8;
            match dev.send_command(0x15, &[status], true).await {
                Ok(()) => json!({"success": true, "result": true}),
                Err(e) => err_reply(&format!("send_sd_status failed: {e}")),
            }
        }
        "system.get_device_temp" | "get_device_temp" | "device.get_device_temp" => {
            match dev.send_command_and_wait(0x59, &[], timeout).await {
                Some(p) if p.len() >= 2 => json!({
                    "success": true,
                    "result": {
                        "format": p[0] as i64,
                        "value": p[1] as i8 as i64,
                    }
                }),
                _ => json!({"success": true, "result": Value::Null}),
            }
        }
        "system.send_net_temp" | "send_net_temp" | "device.send_net_temp" => {
            let year = args.first().copied()
                .or_else(|| kw.and_then(|v| v.get("year")).and_then(|v| v.as_i64()))
                .unwrap_or(2026) as u16;
            let month = args.get(1).copied()
                .or_else(|| kw.and_then(|v| v.get("month")).and_then(|v| v.as_i64()))
                .unwrap_or(1) as u8;
            let day = args.get(2).copied()
                .or_else(|| kw.and_then(|v| v.get("day")).and_then(|v| v.as_i64()))
                .unwrap_or(1) as u8;
            let hour = args.get(3).copied()
                .or_else(|| kw.and_then(|v| v.get("hour")).and_then(|v| v.as_i64()))
                .unwrap_or(0) as u8;
            let minute = args.get(4).copied()
                .or_else(|| kw.and_then(|v| v.get("minute")).and_then(|v| v.as_i64()))
                .unwrap_or(0) as u8;
            let num = args.get(5).copied()
                .or_else(|| kw.and_then(|v| v.get("num")).and_then(|v| v.as_i64()))
                .unwrap_or(0) as u8;
            
            let mut payload = Vec::new();
            payload.extend_from_slice(&year.to_le_bytes());
            payload.push(month);
            payload.push(day);
            payload.push(hour);
            payload.push(minute);
            payload.push(num);

            let temp_data = raw_args.get(6)
                .or_else(|| kw.and_then(|v| v.get("temp_data")))
                .and_then(|v| v.as_array());
            
            if let Some(arr) = temp_data {
                for item in arr {
                    if let Some(pair) = item.as_array() {
                        if pair.len() >= 2 {
                            let temp_val = pair[0].as_i64().unwrap_or(0) as i8;
                            let weather_type = pair[1].as_i64().unwrap_or(0) as u8;
                            payload.push(temp_val as u8);
                            payload.push(weather_type);
                        }
                    }
                }
            }

            match dev.send_command(0x5d, &payload, true).await {
                Ok(()) => json!({"success": true, "result": true}),
                Err(e) => err_reply(&format!("send_net_temp failed: {e}")),
            }
        }
        "system.send_net_temp_disp" | "send_net_temp_disp" | "device.send_net_temp_disp" => {
            let display_modes = raw_args.first()
                .or_else(|| kw.and_then(|v| v.get("display_modes")))
                .and_then(|v| v.as_array());
            let time_minutes = args.get(1).copied()
                .or_else(|| kw.and_then(|v| v.get("time_minutes")).and_then(|v| v.as_i64()))
                .unwrap_or(0) as u16;
            
            let mut payload = Vec::new();
            if let Some(arr) = display_modes {
                for mode_val in arr.iter().take(5) {
                    let mode_byte = match mode_val {
                        Value::Bool(b) => if *b { 1 } else { 0 },
                        Value::Number(n) => if n.as_i64().unwrap_or(0) != 0 { 1 } else { 0 },
                        _ => 0,
                    };
                    payload.push(mode_byte);
                }
            }
            while payload.len() < 5 {
                payload.push(0);
            }
            payload.extend_from_slice(&time_minutes.to_le_bytes());

            match dev.send_command(0x5e, &payload, true).await {
                Ok(()) => json!({"success": true, "result": true}),
                Err(e) => err_reply(&format!("send_net_temp_disp failed: {e}")),
            }
        }
        "system.get_net_temp_disp" | "get_net_temp_disp" | "device.get_net_temp_disp" => {
            match dev.send_command_and_wait(0x73, &[], timeout).await {
                Some(p) if p.len() >= 7 => json!({
                    "success": true,
                    "result": {
                        "display_modes": [p[0] as i64, p[1] as i64, p[2] as i64, p[3] as i64, p[4] as i64],
                        "time_minutes": u16::from_le_bytes([p[5], p[6]]) as i64,
                    }
                }),
                _ => json!({"success": true, "result": Value::Null}),
            }
        }
        "system.send_current_temp" | "send_current_temp" | "device.send_current_temp" => {
            let temp = args.first().copied()
                .or_else(|| kw.and_then(|v| v.get("temp")).and_then(|v| v.as_i64()))
                .unwrap_or(0) as i8;
            let weather = args.get(1).copied()
                .or_else(|| kw.and_then(|v| v.get("weather")).and_then(|v| v.as_i64()))
                .unwrap_or(0) as u8;
            match dev.send_command(0x5f, &[temp as u8, weather], true).await {
                Ok(()) => json!({"success": true, "result": true}),
                Err(e) => err_reply(&format!("send_current_temp failed: {e}")),
            }
        }
        "system.set_temp_type" | "set_temp_type" | "device.set_temp_type" => {
            let temp_type = args.first().copied()
                .or_else(|| kw.and_then(|v| v.get("temp_type")).and_then(|v| v.as_i64()))
                .unwrap_or(0) as u8;
            match dev.send_command(0x2b, &[temp_type], true).await {
                Ok(()) => json!({"success": true, "result": true}),
                Err(e) => err_reply(&format!("set_temp_type failed: {e}")),
            }
        }
        "system.set_song_display_control" | "set_song_display_control" | "device.set_song_display_control" => {
            let control = args.first().copied()
                .or_else(|| kw.and_then(|v| v.get("control")).and_then(|v| v.as_i64()))
                .unwrap_or(0) as u8;
            match dev.send_command(0x83, &[control], true).await {
                Ok(()) => json!({"success": true, "result": true}),
                Err(e) => err_reply(&format!("set_song_display_control failed: {e}")),
            }
        }
        "system.set_power_on_voice_volume" | "set_power_on_voice_volume" | "device.set_power_on_voice_volume" => {
            let control = args.first().copied()
                .or_else(|| kw.and_then(|v| v.get("control")).and_then(|v| v.as_i64()))
                .unwrap_or(0) as u8;
            let volume = args.get(1).copied()
                .or_else(|| kw.and_then(|v| v.get("volume")).and_then(|v| v.as_i64()))
                .unwrap_or(0) as u8;
            let payload = if control == 1 { vec![control, volume] } else { vec![control] };
            match dev.send_command(0xbb, &payload, true).await {
                Ok(()) => json!({"success": true, "result": true}),
                Err(e) => err_reply(&format!("set_power_on_voice_volume failed: {e}")),
            }
        }
        "system.set_power_on_channel" | "device.set_power_on_channel" => {
            let control = args.first().copied()
                .or_else(|| kw.and_then(|v| v.get("control")).and_then(|v| v.as_i64()))
                .unwrap_or(0) as u8;
            let channel_id = args.get(1).copied()
                .or_else(|| kw.and_then(|v| v.get("channel_id")).and_then(|v| v.as_i64()))
                .unwrap_or(0) as u8;
            let payload = if control == 1 { vec![control, channel_id] } else { vec![control] };
            match dev.send_command(0x8a, &payload, true).await {
                Ok(()) => json!({"success": true, "result": true}),
                Err(e) => err_reply(&format!("set_power_on_channel failed: {e}")),
            }
        }
        "system.set_boot_gif" | "device.set_boot_gif" => {
            let on_off = args.first().copied()
                .or_else(|| kw.and_then(|v| v.get("on_off")).and_then(|v| v.as_i64()))
                .unwrap_or(0) as u8;
            let total_length = args.get(1).copied()
                .or_else(|| kw.and_then(|v| v.get("total_length")).and_then(|v| v.as_i64()))
                .unwrap_or(0) as u16;
            let gif_id = args.get(2).copied()
                .or_else(|| kw.and_then(|v| v.get("gif_id")).and_then(|v| v.as_i64()))
                .unwrap_or(0) as u8;
            let data: Vec<u8> = raw_args.get(3)
                .and_then(|v| v.as_array())
                .or_else(|| kw.and_then(|v| v.get("data")).and_then(|v| v.as_array()))
                .map(|a| a.iter().filter_map(|x| x.as_u64().map(|n| n as u8)).collect())
                .unwrap_or_default();

            let mut payload = Vec::with_capacity(4 + data.len());
            payload.push(on_off);
            payload.extend_from_slice(&total_length.to_le_bytes());
            payload.push(gif_id);
            payload.extend_from_slice(&data);

            match dev.send_command(0x52, &payload, true).await {
                Ok(()) => json!({"success": true, "result": true}),
                Err(e) => err_reply(&format!("set_boot_gif failed: {e}")),
            }
        }
        "system.set_sound_control" | "set_sound_control" | "device.set_sound_control" => {
            let enable = args.first().copied()
                .or_else(|| kw.and_then(|v| v.get("enable")).and_then(|v| v.as_i64()))
                .unwrap_or(0) as u8;
            match dev.send_command(0xa7, &[enable], true).await {
                Ok(()) => json!({"success": true, "result": true}),
                Err(e) => err_reply(&format!("set_sound_control failed: {e}")),
            }
        }
        "system.get_sound_control" | "get_sound_control" | "device.get_sound_control" => {
            match dev.send_command_and_wait(0xa8, &[], timeout).await {
                Some(p) if p.len() >= 1 => json!({"success": true, "result": p[0] as i64}),
                _ => json!({"success": true, "result": Value::Null}),
            }
        }
        _ => err_reply("unimplemented system command"),
    }
}

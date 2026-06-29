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
        "device.get_device_name" | "get_device_name" => {
            if let Some(name) = dev.device_name() {
                if !name.trim().is_empty() {
                    return json!({"success": true, "result": name});
                }
            }
            match dev.send_command_and_wait(0x76, &[], timeout).await {
                Some(p) if p.len() >= 1 => {
                    let name_len = p[0] as usize;
                    if p.len() >= 1 + name_len {
                        let name_bytes = &p[1..1 + name_len];
                        match std::str::from_utf8(name_bytes) {
                            Ok(name) => {
                                dev.set_cached_device_name(name.to_string());
                                json!({"success": true, "result": name})
                            }
                            Err(_) => json!({"success": true, "result": Value::Null}),
                        }
                    } else {
                        json!({"success": true, "result": Value::Null})
                    }
                }
                _ => json!({"success": true, "result": Value::Null}),
            }
        }
        "device.set_device_name" | "set_device_name" => {
            let name = raw_args.first()
                .and_then(|v| v.as_str())
                .or_else(|| kw.and_then(|v| v.get("name")).and_then(|v| v.as_str()))
                .unwrap_or("");
            let mut name_bytes = name.as_bytes().to_vec();
            if name_bytes.len() > 16 {
                name_bytes.truncate(16);
            }
            let mut payload = Vec::with_capacity(1 + name_bytes.len());
            payload.push(name_bytes.len() as u8);
            payload.extend_from_slice(&name_bytes);
            match dev.send_command(0x75, &payload, true).await {
                Ok(()) => {
                    if let Ok(utf8_name) = std::str::from_utf8(&name_bytes) {
                        dev.set_cached_device_name(utf8_name.to_string());
                    }
                    json!({"success": true, "result": true})
                }
                Err(e) => err_reply(&format!("set_device_name failed: {e}")),
            }
        }
        "device.get_brightness" | "get_brightness" | "display.get_brightness" => {
            match dev.send_command_and_wait(0x46, &[], timeout).await {
                Some(p) if p.len() >= 7 => json!({"success": true, "result": p[6] as i64}),
                _ => json!({"success": true, "result": Value::Null}),
            }
        }
        "device.set_brightness" | "set_brightness" | "display.set_brightness" => {
            let val = args.first().copied()
                .or_else(|| kw.and_then(|v| v.get("brightness")).and_then(|v| v.as_i64()))
                .unwrap_or(0).clamp(0, 100) as u8;
            match dev.send_command(0x74, &[val], true).await {
                Ok(()) => json!({"success": true, "result": true}),
                Err(e) => err_reply(&format!("set_brightness failed: {e}")),
            }
        }
        "device.show_clock" | "show_clock" => {
            let clock = args.first().copied().unwrap_or(0).clamp(0, 15) as u8;
            let payload = [0u8, 1, clock, 1, 0, 0, 0, 0xFF, 0xFF, 0xFF];
            match dev.send_command(0x45, &payload, true).await {
                Ok(()) => json!({"success": true, "result": true}),
                Err(e) => err_reply(&format!("show_clock failed: {e}")),
            }
        }
        "device.show_image" | "show_image" => {
            let w = get_kwarg_i64(kw, "w", 16) as i32;
            let h = get_kwarg_i64(kw, "h", 16) as i32;
            let time_ms = get_kwarg_i64(kw, "time_ms", 100) as u16;
            let rgb: Vec<u8> = match kw.and_then(|m| m.get("rgb")).and_then(|v| v.as_array()) {
                Some(a) => a.iter().filter_map(|x| x.as_u64().map(|n| n as u8)).collect(),
                None => return err_reply("show_image requires 'rgb' (array of u8)"),
            };
            let expected = (w * h * 3) as usize;
            if rgb.len() != expected {
                return err_reply(&format!(
                    "show_image: rgb.len()={} expected w*h*3={expected}",
                    rgb.len()
                ));
            }
            let enc = match ctx.daemon.encoder() {
                Some(e) => e,
                None => return err_reply("encoder not available"),
            };
            let blob = match enc.encode_animation_frame(&rgb, w, h, time_ms) {
                Some(b) => b,
                None => return err_reply("encode_animation_frame failed"),
            };
            match dev.stream_animation_8b(&blob).await {
                Ok(true) => json!({"success": true, "result": true}),
                Ok(false) => err_reply("stream_animation_8b: empty blob"),
                Err(e) => err_reply(&format!("stream_animation_8b failed: {e}")),
            }
        }
        "display.show_image" | "display.display_image" => {
            let size = kw.and_then(|v| v.get("size")).and_then(|v| v.as_u64()).unwrap_or(16) as u32;
            let default_time_ms = raw_args.get(1).and_then(|v| v.as_u64()).unwrap_or(100) as u16;

            let img_data: Vec<u8> = if let Some(data) = ctx.blob_map.lock().unwrap().remove(&0) {
                data
            } else {
                let path = match raw_args.get(0).and_then(|v| v.as_str()) {
                    Some(p) => p,
                    None => return err_reply("display.show_image requires a path or blob[0]"),
                };
                match std::fs::read(path) {
                    Ok(d) => d,
                    Err(e) => return err_reply(&format!("display.show_image: read {path}: {e}")),
                }
            };

            if let Err(e) = dev.send_command(0x45, &[0x05, 0, 0, 0, 0, 0, 0, 0, 0, 0], false).await {
                return err_reply(&format!("show_design failed: {e}"));
            }

            let frames = match tokio::task::spawn_blocking(move || {
                crate::image_proc::process_image_bytes(img_data, size, default_time_ms)
            }).await {
                Ok(Ok(f)) => f,
                Ok(Err(e)) => return err_reply(&format!("image decode: {e}")),
                Err(e) => return err_reply(&format!("image decode task: {e}")),
            };

            let enc = match ctx.daemon.encoder() {
                Some(e) => e,
                None => return err_reply("encoder not available (DIVOOMD_ENCODER_LIB)"),
            };
            let mut blob = Vec::new();
            for (rgb, w, h, t) in &frames {
                let frame_body = if *w == 32 && *h == 32 {
                    enc.encode_animation_frame_32(rgb, *w, *h, *t)
                } else {
                    enc.encode_animation_frame(rgb, *w, *h, *t)
                };
                match frame_body {
                    Some(b) => blob.extend_from_slice(&b),
                    None => return err_reply(&format!("encode_animation_frame failed (frame {w}x{h})")),
                }
            }

            match dev.stream_animation_8b(&blob).await {
                Ok(true) => json!({"success": true, "result": true}),
                Ok(false) => err_reply("stream_animation_8b: empty blob"),
                Err(e) => err_reply(&format!("stream_animation_8b failed: {e}")),
            }
        }
        "display.show_clock" => {
            let clock = kw.and_then(|v| v.get("clock")).and_then(|v| v.as_i64())
                .or_else(|| args.first().copied())
                .unwrap_or(0).clamp(0, 15) as u8;
            let twentyfour = kw.and_then(|v| v.get("twentyfour")).and_then(|v| v.as_bool()).unwrap_or(true);
            let weather = kw.and_then(|v| v.get("weather")).and_then(|v| v.as_bool()).unwrap_or(false);
            let temp = kw.and_then(|v| v.get("temp")).and_then(|v| v.as_bool()).unwrap_or(false);
            let calendar = kw.and_then(|v| v.get("calendar")).and_then(|v| v.as_bool()).unwrap_or(false);
            let [r, g, b] = kw
                .and_then(|v| v.get("color")).and_then(|v| v.as_str())
                .and_then(parse_hex_color)
                .unwrap_or([0xFF, 0xFF, 0xFF]);
            let payload = [
                0u8, // env = 0 (clock channel)
                twentyfour as u8,
                clock,
                1u8, // clock_active
                weather as u8,
                temp as u8,
                calendar as u8,
                r, g, b,
            ];
            match dev.send_command(0x45, &payload, true).await {
                Ok(()) => json!({"success": true, "result": true}),
                Err(e) => err_reply(&format!("display.show_clock failed: {e}")),
            }
        }
        "display.set_clock_rich" => {
            let style = kw.and_then(|v| v.get("style")).and_then(|v| v.as_i64())
                .unwrap_or(0).clamp(0, 15) as u8;
            let twentyfour = kw.and_then(|v| v.get("twentyfour")).and_then(|v| v.as_bool()).unwrap_or(true);
            let humidity = kw.and_then(|v| v.get("humidity")).and_then(|v| v.as_bool()).unwrap_or(false);
            let weather = kw.and_then(|v| v.get("weather")).and_then(|v| v.as_bool()).unwrap_or(false);
            let date = kw.and_then(|v| v.get("date")).and_then(|v| v.as_bool()).unwrap_or(false);
            let [r, g, b] = kw
                .and_then(|v| v.get("color")).and_then(|v| v.as_str())
                .and_then(parse_hex_color)
                .unwrap_or([0xFF, 0xFF, 0xFF]);
            let payload = [
                0x00, // env = 0
                twentyfour as u8,
                style,
                1u8, // clock active
                humidity as u8,
                weather as u8,
                date as u8,
                r, g, b,
            ];
            match dev.send_command(0x45, &payload, true).await {
                Ok(()) => json!({"success": true, "result": true}),
                Err(e) => err_reply(&format!("display.set_clock_rich failed: {e}")),
            }
        }
        "display.show_design" => {
            match dev.send_command(0x45, &[0x05, 0, 0, 0, 0, 0, 0, 0, 0, 0], false).await {
                Ok(()) => json!({"success": true, "result": true}),
                Err(e) => err_reply(&format!("display.show_design failed: {e}")),
            }
        }
        "display.show_light" | "light.show_light" | "show_light" => {
            let [r, g, b] = color_from_arg(&raw_args, kw).unwrap_or([0xFF, 0xFF, 0xFF]);
            let brightness = args.get(1).copied()
                .or_else(|| kw.and_then(|v| v.get("brightness")).and_then(|v| v.as_i64()))
                .unwrap_or(100).clamp(0, 100) as u8;
            let power = kw.and_then(|v| v.get("power")).and_then(|v| v.as_bool()).unwrap_or(true);
            let payload = [0x01u8, r, g, b, brightness, 0x00, power as u8, 0x00, 0x00, 0x00];
            match dev.send_command(0x45, &payload, true).await {
                Ok(()) => json!({"success": true, "result": true}),
                Err(e) => err_reply(&format!("display.show_light failed: {e}")),
            }
        }
        // VJ effects (1-indexed on BLE): 0x45 [0x03, number+1, 0×8] (Python show_effects).
        "display.show_effects" | "show_effects" => {
            let number = args.first().copied()
                .or_else(|| kw.and_then(|v| v.get("number")).and_then(|v| v.as_i64()))
                .unwrap_or(0);
            let payload = [0x03u8, (number + 1) as u8, 0, 0, 0, 0, 0, 0, 0, 0];
            match dev.send_command(0x45, &payload, true).await {
                Ok(()) => json!({"success": true, "result": true}),
                Err(e) => err_reply(&format!("display.show_effects failed: {e}")),
            }
        }
        // Visualization channel: 0x45 [0x04, number, 0×8] (Python show_visualization).
        "display.show_visualization" | "show_visualization" => {
            let number = args.first().copied()
                .or_else(|| kw.and_then(|v| v.get("number")).and_then(|v| v.as_i64()))
                .unwrap_or(0);
            let payload = [0x04u8, number as u8, 0, 0, 0, 0, 0, 0, 0, 0];
            match dev.send_command(0x45, &payload, true).await {
                Ok(()) => json!({"success": true, "result": true}),
                Err(e) => err_reply(&format!("display.show_visualization failed: {e}")),
            }
        }
        // Scoreboard channel: 0x45 [0x06, 0×9] (Python show_scoreboard).
        "display.show_scoreboard" | "show_scoreboard" => {
            let payload = [0x06u8, 0, 0, 0, 0, 0, 0, 0, 0, 0];
            match dev.send_command(0x45, &payload, true).await {
                Ok(()) => json!({"success": true, "result": true}),
                Err(e) => err_reply(&format!("display.show_scoreboard failed: {e}")),
            }
        }
        // Temperature channel: 0x45 [0x01, temp_type, r, g, b, 0x00] (Python set_temperature_channel).
        "display.set_temperature_channel" | "set_temperature_channel" => {
            let celsius = kw.and_then(|v| v.get("celsius")).and_then(|v| v.as_bool()).unwrap_or(true);
            let [r, g, b] = kw.and_then(|v| v.get("color")).and_then(|v| v.as_str())
                .and_then(parse_hex_color)
                .or_else(|| color_from_arg(&raw_args, kw))
                .unwrap_or([0xFF, 0xFF, 0xFF]);
            let temp_type = if celsius { 0u8 } else { 1u8 };
            let payload = [0x01u8, temp_type, r, g, b, 0x00];
            match dev.send_command(0x45, &payload, true).await {
                Ok(()) => json!({"success": true, "result": true}),
                Err(e) => err_reply(&format!("display.set_temperature_channel failed: {e}")),
            }
        }
        // Channel switch by name → the matching 0x45 channel payload (Python switch_channel).
        "display.switch_channel" | "switch_channel" => {
            let channel = raw_args.first().and_then(|v| v.as_str())
                .or_else(|| kw.and_then(|v| v.get("channel")).and_then(|v| v.as_str()))
                .unwrap_or("").to_lowercase();
            let payload: [u8; 10] = match channel.as_str() {
                "clock" => [0x00, 1, 0, 1, 0, 0, 0, 0xFF, 0xFF, 0xFF],
                "visualizer" => [0x04, 0, 0, 0, 0, 0, 0, 0, 0, 0],
                "vj" => [0x03, 1, 0, 0, 0, 0, 0, 0, 0, 0],
                "design" => [0x05, 0, 0, 0, 0, 0, 0, 0, 0, 0],
                "scoreboard" => [0x06, 0, 0, 0, 0, 0, 0, 0, 0, 0],
                other => return err_reply(&format!("switch_channel: unknown channel '{other}'")),
            };
            match dev.send_command(0x45, &payload, true).await {
                Ok(()) => json!({"success": true, "result": true}),
                Err(e) => err_reply(&format!("display.switch_channel failed: {e}")),
            }
        }
        "music.set_volume" | "set_volume" => {
            let val = args.first().copied()
                .or_else(|| kw.and_then(|v| v.get("volume")).and_then(|v| v.as_i64()))
                .unwrap_or(0).clamp(0, 15) as u8;
            match dev.send_command(0x08, &[val], true).await {
                Ok(()) => json!({"success": true, "result": true}),
                Err(e) => err_reply(&format!("set_volume failed: {e}")),
            }
        }
        "music.get_volume" | "get_volume" => {
            match dev.send_command_and_wait(0x09, &[], timeout).await {
                Some(p) if p.len() >= 1 => json!({"success": true, "result": p[0] as i64}),
                _ => json!({"success": true, "result": Value::Null}),
            }
        }
        "radio.set_radio_frequency" | "set_radio_frequency" | "radio.set_radio" | "set_radio" => {
            let freq = args.first().copied()
                .or_else(|| kw.and_then(|v| v.get("frequency")).and_then(|v| v.as_i64()))
                .or_else(|| kw.and_then(|v| v.get("freq_x10")).and_then(|v| v.as_i64()))
                .unwrap_or(875) as u16;
            let payload = freq.to_le_bytes();
            match dev.send_command(0x61, &payload, true).await {
                Ok(()) => json!({"success": true, "result": true}),
                Err(e) => err_reply(&format!("set_radio_frequency failed: {e}")),
            }
        }
        "device.set_low_power_switch" | "set_low_power_switch" | "device.set_low_power" | "set_low_power" => {
            let on_off_val = raw_args.first()
                .or_else(|| kw.and_then(|v| v.get("on_off")))
                .or_else(|| kw.and_then(|v| v.get("enabled")));
            let on_off = match on_off_val {
                Some(Value::Bool(b)) => if *b { 1 } else { 0 },
                Some(Value::Number(n)) => n.as_i64().unwrap_or(0).clamp(0, 1) as u8,
                _ => args.first().copied().unwrap_or(0).clamp(0, 1) as u8,
            };
            match dev.send_command(0xb2, &[on_off], true).await {
                Ok(()) => json!({"success": true, "result": true}),
                Err(e) => err_reply(&format!("set_low_power_switch failed: {e}")),
            }
        }
        "device.get_low_power_switch" | "get_low_power_switch" | "device.get_low_power" | "get_low_power" => {
            match dev.send_command_and_wait(0xb3, &[], timeout).await {
                Some(p) if p.len() >= 1 => json!({"success": true, "result": p[0] as i64}),
                _ => json!({"success": true, "result": Value::Null}),
            }
        }
        "device.set_auto_power_off" | "set_auto_power_off" | "sound.set_auto_power_off" => {
            let minutes = args.first().copied()
                .or_else(|| kw.and_then(|v| v.get("minutes")).and_then(|v| v.as_i64()))
                .unwrap_or(0) as u16;
            let payload = minutes.to_le_bytes();
            match dev.send_command(0xab, &payload, true).await {
                Ok(()) => json!({"success": true, "result": true}),
                Err(e) => err_reply(&format!("set_auto_power_off failed: {e}")),
            }
        }
        "device.get_auto_power_off" | "get_auto_power_off" | "sound.get_auto_power_off" => {
            match dev.send_command_and_wait(0xac, &[], timeout).await {
                Some(p) if p.len() >= 2 => {
                    let minutes = u16::from_le_bytes([p[0], p[1]]) as i64;
                    json!({"success": true, "result": minutes})
                }
                _ => json!({"success": true, "result": Value::Null}),
            }
        }
        "animation.stream_animation_8b" => {
            let blob: Vec<u8> = if let Some(data) = ctx.blob_map.lock().unwrap().remove(&0) {
                data
            } else {
                match kw.and_then(|m| m.get("blob")).and_then(|v| v.as_array()) {
                    Some(a) => a.iter().filter_map(|x| x.as_u64().map(|n| n as u8)).collect(),
                    None => return err_reply("animation.stream_animation_8b requires 'blob'"),
                }
            };
            match dev.stream_animation_8b(&blob).await {
                Ok(true) => json!({"success": true, "result": true}),
                Ok(false) => err_reply("stream_animation_8b: empty blob"),
                Err(e) => err_reply(&format!("stream_animation_8b failed: {e}")),
            }
        }
        _ => err_reply("unimplemented basic command"),
    }
}

fn get_kwarg_i64(kw: Option<&serde_json::Map<String, Value>>, name: &str, default: i64) -> i64 {
    kw.and_then(|m| m.get(name)).and_then(|v| v.as_i64()).unwrap_or(default)
}

fn parse_hex_color(s: &str) -> Option<[u8; 3]> {
    let s = s.trim_start_matches('#');
    if s.len() == 6 {
        let r = u8::from_str_radix(&s[0..2], 16).ok()?;
        let g = u8::from_str_radix(&s[2..4], 16).ok()?;
        let b = u8::from_str_radix(&s[4..6], 16).ok()?;
        Some([r, g, b])
    } else {
        None
    }
}

fn color_from_arg(raw_args: &[Value], kw: Option<&serde_json::Map<String, Value>>) -> Option<[u8; 3]> {
    let color_val = raw_args.first().or_else(|| kw.and_then(|v| v.get("color")))?;
    if let Some(arr) = color_val.as_array() {
        let ns: Vec<u8> = arr.iter().filter_map(|x| x.as_u64().map(|n| n as u8)).collect();
        if ns.len() >= 3 { return Some([ns[0], ns[1], ns[2]]); }
    }
    if let Some(s) = color_val.as_str() {
        return parse_hex_color(s);
    }
    None
}

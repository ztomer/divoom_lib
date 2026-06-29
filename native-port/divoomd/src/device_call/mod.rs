use serde_json::{json, Value};
use std::time::Duration;
use crate::daemon::{Daemon, DeviceTransport};
use crate::protocol::Request;


pub struct CallCtx<'a> {
    pub daemon: &'a Daemon,
    pub dev: &'a DeviceTransport,
    pub args: &'a [i64],
    pub raw_args: &'a [Value],
    pub kwargs: Option<&'a serde_json::Map<String, Value>>,
    pub blob_map: &'a std::sync::Mutex<std::collections::HashMap<usize, Vec<u8>>>,
    pub timeout: Duration,
}

pub mod basic;
pub mod alarm;
pub mod sleep;
pub mod timeplan;
pub mod tools;
pub mod text;
pub mod game;
pub mod design;
pub mod system;

use base64::{engine::general_purpose::STANDARD as B64, Engine as _};

pub async fn handle_device_call(
    _daemon: &Daemon,
    dev: &DeviceTransport,
    req: &Request,
    _timeout: Duration,
) -> Value {
    let method = match req.args.get("method").and_then(|v| v.as_str()) {
        Some(m) => m,
        None => return crate::protocol::err_reply("device_call requires 'method'"),
    };

    // Numeric positional args (for brightness, clock, etc.)
    let args: Vec<i64> = req
        .args
        .get("args")
        .and_then(|v| v.as_array())
        .map(|a| a.iter().filter_map(|x| x.as_i64()).collect())
        .unwrap_or_default();

    // Raw positional args as Values (for string paths in display.show_image)
    let raw_args: Vec<Value> = req
        .args
        .get("args")
        .and_then(|v| v.as_array())
        .cloned()
        .unwrap_or_default();

    // Blob map: base64-encoded binary data keyed by positional arg index.
    let mut blob_map_raw: std::collections::HashMap<usize, Vec<u8>> = std::collections::HashMap::new();
    if let Some(blobs) = req.args.get("blobs").and_then(|v| v.as_object()) {
        for (idx_str, b64val) in blobs {
            let idx: usize = match idx_str.parse() {
                Ok(i) => i,
                Err(_) => return crate::protocol::err_reply(&format!("blobs: bad index key '{idx_str}'")),
            };
            let b64 = match b64val.as_str() {
                Some(s) => s,
                None => return crate::protocol::err_reply(&format!("blobs[{idx_str}]: not a string")),
            };
            match B64.decode(b64) {
                Ok(data) => { blob_map_raw.insert(idx, data); }
                Err(e) => return crate::protocol::err_reply(&format!("blobs[{idx_str}]: base64 error: {e}")),
            }
        }
    }
    let blob_map = std::sync::Mutex::new(blob_map_raw);

    if method.starts_with("lan.") {
        if let Some(lan_dev) = dev.lan() {
            let kwargs = req.args.get("kwargs").and_then(|v| v.as_object());
            return handle_lan_call(lan_dev, method, &args, kwargs).await;
        } else {
            return crate::protocol::err_reply("device is not connected via LAN");
        }
    }

    // LAN devices are handled above; everything else (BLE / SPP / Mock) routes
    // through the build-agnostic DeviceTransport method layer.
    {
        if !matches!(dev, DeviceTransport::Lan(_)) {
            let kwargs = req.args.get("kwargs").and_then(|v| v.as_object());
            let ctx = CallCtx {
                daemon: _daemon,
                dev,
                args: &args,
                raw_args: &raw_args,
                kwargs,
                blob_map: &blob_map,
                timeout: _timeout,
            };

            match method {
                // basic.rs commands:
                "device.get_device_name" | "get_device_name" |
                "device.set_device_name" | "set_device_name" |
                "device.get_brightness" | "get_brightness" |
                "device.set_brightness" | "set_brightness" |
                "device.show_clock" | "show_clock" |
                "device.show_image" | "show_image" |
                "display.show_image" | "display.display_image" |
                "display.set_clock_rich" |
                "animation.stream_animation_8b" |
                "display.show_clock" |
                "display.show_design" |
                "display.get_brightness" |
                "display.set_brightness" |
                "display.show_light" | "light.show_light" | "show_light" |
                "display.show_effects" | "show_effects" |
                "display.show_visualization" | "show_visualization" |
                "display.show_scoreboard" | "show_scoreboard" |
                "display.set_temperature_channel" | "set_temperature_channel" |
                "display.switch_channel" | "switch_channel" |
                "music.set_volume" | "set_volume" |
                "music.get_volume" | "get_volume" |
                "radio.set_radio_frequency" | "set_radio_frequency" | "radio.set_radio" | "set_radio" |
                "device.set_low_power_switch" | "set_low_power_switch" | "device.set_low_power" | "set_low_power" |
                "device.get_low_power_switch" | "get_low_power_switch" | "device.get_low_power" | "get_low_power" |
                "device.set_auto_power_off" | "set_auto_power_off" | "sound.set_auto_power_off" |
                "device.get_auto_power_off" | "get_auto_power_off" | "sound.get_auto_power_off" => {
                    basic::handle(method, ctx).await
                }

                // alarm.rs:
                "alarm.get_alarm_time" | "get_alarm_time" |
                "alarm.set_alarm" | "set_alarm" |
                "alarm.set_alarm_gif" | "set_alarm_gif" |
                "alarm.get_memorial_time" | "get_memorial_time" |
                "alarm.set_memorial_time" | "set_memorial_time" |
                "alarm.set_memorial_gif" | "set_memorial_gif" |
                "alarm.set_alarm_listen" | "set_alarm_listen" |
                "alarm.set_alarm_volume" | "set_alarm_volume" |
                "alarm.set_alarm_volume_control" | "set_alarm_volume_control" => {
                    alarm::handle(method, ctx).await
                }

                // sleep.rs:
                "sleep.show_sleep" | "show_sleep" |
                "sleep.get_sleep_scene" | "get_sleep_scene" |
                "sleep.set_sleep_scene_listen" | "set_sleep_scene_listen" |
                "sleep.set_scene_volume" | "set_scene_volume" |
                "sleep.set_sleep_color" | "set_sleep_color" |
                "sleep.set_sleep_light" | "set_sleep_light" |
                "sleep.set_sleep_scene" | "set_sleep_scene" => {
                    sleep::handle(method, ctx).await
                }

                // timeplan.rs:
                "timeplan.set_time_manage_info" | "set_time_manage_info" |
                "timeplan.set_time_manage_ctrl" | "set_time_manage_ctrl" => {
                    timeplan::handle(method, ctx).await
                }

                // tools.rs:
                "scoreboard.set_scoreboard" | "set_scoreboard" |
                "scoreboard.get_scoreboard" | "get_scoreboard" |
                "timer.set_timer" | "set_timer" |
                "timer.get_timer" | "get_timer" |
                "countdown.set_countdown" | "set_countdown" |
                "countdown.get_countdown" | "get_countdown" |
                "noise.set_noise" | "set_noise" |
                "noise.get_noise" | "get_noise" |
                "device.show_notification" | "show_notification" | "notification.show_notification" |
                "device.show_notification_text" | "show_notification_text" | "notification.show_notification_text" => {
                    tools::handle(method, ctx).await
                }

                // text.rs:
                "text.set_light_phone_word_attr" | "set_light_phone_word_attr" |
                "text.set_text_content" | "set_text_content" => {
                    text::handle(method, ctx).await
                }

                // game.rs:
                "game.show_game" | "show_game" |
                "game.hide_game" | "hide_game" |
                "game.exit_game" | "exit_game" |
                "game.set_key_down" | "set_key_down" |
                "game.set_key_up" | "set_key_up" |
                "game.set_magic_ball_answer" | "set_magic_ball_answer" |
                "game.send_gamecontrol" | "send_gamecontrol" => {
                    game::handle(method, ctx).await
                }

                // design.rs:
                "design.set_eq" | "set_eq" |
                "design.set_language" | "set_language" |
                "design.set_user_define_time" | "set_user_define_time" |
                "design.get_user_define_time" | "get_user_define_time" |
                "design.set_screen_dir" | "set_screen_dir" |
                "design.set_screen_mirror" | "set_screen_mirror" |
                "design.factory_reset" | "factory_reset" |
                "design.use_user_define_index" | "use_user_define_index" |
                "design.clear_user_define_index" | "clear_user_define_index" => {
                    design::handle(method, ctx).await
                }

                // system.rs:
                "time.set_hour_type" | "set_hour_type" | "system.set_hour_type" |
                "bluetooth.set_bluetooth_password" | "set_bluetooth_password" | "system.set_bluetooth_password" |
                "system.get_work_mode" | "get_work_mode" |
                "system.set_work_mode" | "set_work_mode" |
                "system.set_channel" | "set_channel" | "device.set_channel" |
                "system.send_sd_status" | "send_sd_status" | "device.send_sd_status" |
                "system.get_device_temp" | "get_device_temp" | "device.get_device_temp" |
                "system.send_net_temp" | "send_net_temp" | "device.send_net_temp" |
                "system.send_net_temp_disp" | "send_net_temp_disp" | "device.send_net_temp_disp" |
                "system.get_net_temp_disp" | "get_net_temp_disp" | "device.get_net_temp_disp" |
                "system.send_current_temp" | "send_current_temp" | "device.send_current_temp" |
                "system.set_temp_type" | "set_temp_type" | "device.set_temp_type" |
                "system.set_song_display_control" | "set_song_display_control" | "device.set_song_display_control" |
                "system.set_power_on_voice_volume" | "set_power_on_voice_volume" | "device.set_power_on_voice_volume" |
                "system.set_power_on_channel" | "device.set_power_on_channel" |
                "system.set_boot_gif" | "device.set_boot_gif" |
                "system.set_sound_control" | "set_sound_control" | "device.set_sound_control" |
                "system.get_sound_control" | "get_sound_control" | "device.get_sound_control" => {
                    system::handle(method, ctx).await
                }

                m => crate::protocol::err_reply(&format!("device_call method not ported yet: {m}")),
            }
        } else {
            crate::protocol::err_reply("method only supported on a BLE/SPP device")
        }
    }
}

fn get_arg_i64(
    args: &[i64],
    kw: Option<&serde_json::Map<String, Value>>,
    idx: usize,
    name: &str,
    default: i64,
) -> i64 {
    if idx < args.len() {
        return args[idx];
    }
    if let Some(map) = kw {
        if let Some(val) = map.get(name) {
            if let Some(n) = val.as_i64() {
                return n;
            }
        }
    }
    default
}

async fn handle_lan_call(
    lan: &crate::lan::LanTransport,
    method: &str,
    args: &[i64],
    kw: Option<&serde_json::Map<String, Value>>,
) -> Value {
    let res = match method {
        "lan.set_channel" => {
            let index = get_arg_i64(args, kw, 0, "SelectIndex", 0);
            lan.post("Channel/SetIndex", Some(json!({ "SelectIndex": index }))).await
        }
        "lan.get_channel" => {
            lan.post("Channel/GetIndex", None).await
        }
        "lan.set_brightness" => {
            let val = get_arg_i64(args, kw, 0, "Brightness", 100);
            lan.post("Channel/SetBrightness", Some(json!({ "Brightness": val }))).await
        }
        "lan.set_clock" => {
            let clock_id = get_arg_i64(args, kw, 0, "ClockId", 0);
            lan.post("Channel/SetClockSelectId", Some(json!({ "ClockId": clock_id }))).await
        }
        "lan.on_off_screen" => {
            let on_off = get_arg_i64(args, kw, 0, "OnOff", 1);
            lan.post("Channel/OnOffScreen", Some(json!({ "OnOff": on_off }))).await
        }
        "lan.set_ambient_light" => {
            let brightness = get_arg_i64(args, kw, 0, "Brightness", 100);
            let color = if let Some(c) = kw.and_then(|m| m.get("Color")).and_then(|v| v.as_str()) {
                c.to_string()
            } else {
                let r = get_arg_i64(args, kw, 1, "r", 0) as u8;
                let g = get_arg_i64(args, kw, 2, "g", 0) as u8;
                let b = get_arg_i64(args, kw, 3, "b", 0) as u8;
                format!("#{:02X}{:02X}{:02X}", r, g, b)
            };
            let power = get_arg_i64(args, kw, 4, "Power", 1);
            lan.post("Channel/SetAmbientLight", Some(json!({
                "Brightness": brightness,
                "Color": color,
                "Power": power,
            }))).await
        }
        "lan.set_rgb_info" => {
            let mode = get_arg_i64(args, kw, 0, "RgbMode", 1);
            let speed = get_arg_i64(args, kw, 1, "RgbSpeed", 50);
            let color = if let Some(c) = kw.and_then(|m| m.get("RgbColor")).and_then(|v| v.as_str()) {
                c.to_string()
            } else {
                let r = get_arg_i64(args, kw, 2, "r", 0) as u8;
                let g = get_arg_i64(args, kw, 3, "g", 0) as u8;
                let b = get_arg_i64(args, kw, 4, "b", 0) as u8;
                format!("#{:02X}{:02X}{:02X}", r, g, b)
            };
            lan.post("Channel/SetRGBInfo", Some(json!({
                "RgbMode": mode,
                "RgbSpeed": speed,
                "RgbColor": color,
            }))).await
        }
        "lan.set_timer" => {
            let minute = get_arg_i64(args, kw, 0, "Minute", 0);
            let second = get_arg_i64(args, kw, 1, "Second", 0);
            let status = get_arg_i64(args, kw, 2, "Status", 0);
            lan.post("Tools/SetTimer", Some(json!({
                "Minute": minute,
                "Second": second,
                "Status": status,
            }))).await
        }
        "lan.set_scoreboard" => {
            let blue = get_arg_i64(args, kw, 0, "BlueScore", 0);
            let red = get_arg_i64(args, kw, 1, "RedScore", 0);
            lan.post("Tools/SetScoreBoard", Some(json!({
                "BlueScore": blue,
                "RedScore": red,
            }))).await
        }
        "lan.set_stopwatch" => {
            let status = get_arg_i64(args, kw, 0, "Status", 0);
            lan.post("Tools/SetStopWatch", Some(json!({ "Status": status }))).await
        }
        "lan.set_noise_status" => {
            let status = get_arg_i64(args, kw, 0, "NoiseStatus", 0);
            lan.post("Tools/SetNoiseStatus", Some(json!({ "NoiseStatus": status }))).await
        }
        _ => return crate::protocol::err_reply(&format!("unknown LAN method: {method}")),
    };

    match res {
        Ok(val) => json!({ "success": true, "result": val }),
        Err(e) => crate::protocol::err_reply(&e.to_string()),
    }
}

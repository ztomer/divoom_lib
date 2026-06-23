#[cfg(feature = "ble")]
use serde_json::Value;
#[cfg(feature = "ble")]
use std::time::Duration;
#[cfg(feature = "ble")]
use crate::daemon::Daemon;
#[cfg(feature = "ble")]
use crate::protocol::Request;

#[cfg(feature = "ble")]
use crate::ble::BleTransport;

#[cfg(feature = "ble")]
pub struct CallCtx<'a> {
    pub daemon: &'a Daemon,
    pub dev: &'a BleTransport,
    pub args: &'a [i64],
    pub raw_args: &'a [Value],
    pub kwargs: Option<&'a serde_json::Map<String, Value>>,
    pub blob_map: &'a std::sync::Mutex<std::collections::HashMap<usize, Vec<u8>>>,
    pub timeout: Duration,
}

#[cfg(feature = "ble")]
pub mod basic;
#[cfg(feature = "ble")]
pub mod alarm;
#[cfg(feature = "ble")]
pub mod sleep;
#[cfg(feature = "ble")]
pub mod timeplan;
#[cfg(feature = "ble")]
pub mod tools;
#[cfg(feature = "ble")]
pub mod text;
#[cfg(feature = "ble")]
pub mod game;
#[cfg(feature = "ble")]
pub mod design;
#[cfg(feature = "ble")]
pub mod system;

#[cfg(feature = "ble")]
pub async fn handle_device_call(
    daemon: &Daemon,
    dev: &BleTransport,
    req: &Request,
    args: &[i64],
    raw_args: &[Value],
    blob_map: &std::sync::Mutex<std::collections::HashMap<usize, Vec<u8>>>,
    timeout: Duration,
) -> Value {
    let method = match req.args.get("method").and_then(|v| v.as_str()) {
        Some(m) => m,
        None => return crate::protocol::err_reply("device_call requires 'method'"),
    };
    let kwargs = req.args.get("kwargs").and_then(|v| v.as_object());
    let ctx = CallCtx {
        daemon,
        dev,
        args,
        raw_args,
        kwargs,
        blob_map,
        timeout,
    };

    match method {
        // basic.rs commands:
        "device.get_device_name" | "get_device_name" |
        "device.set_device_name" | "set_device_name" |
        "device.get_brightness" | "get_brightness" |
        "device.set_brightness" | "set_brightness" |
        "device.show_clock" | "show_clock" |
        "device.show_image" | "show_image" |
        "display.show_image" |
        "display.show_clock" |
        "display.show_design" |
        "display.get_brightness" |
        "display.set_brightness" |
        "display.show_light" | "light.show_light" | "show_light" |
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
}

//! Daemon Handler dispatch — status/lifecycle commands and the exclusive
//! steal-reject through the real command queue.

use divoomd::daemon::Daemon;
use divoomd::protocol::make_request;
use divoomd::socket_server::Handler;
use serde_json::json;

#[tokio::test]
async fn ping_and_status_shapes() {
    let d = Daemon::new();
    assert_eq!(
        d.handle(make_request("ping", None, None)).await,
        json!({"success": true, "pong": true})
    );
    let st = d.handle(make_request("device_status", None, None)).await;
    assert_eq!(st["success"], json!(true));
    assert_eq!(st["connected"], json!(false));
    assert_eq!(st["connection_state"], json!("disconnected"));
    assert_eq!(st["wall"], json!(false));

    let gs = d.handle(make_request("get_status", None, None)).await;
    assert_eq!(gs["state"], json!("idle"));
    assert!(gs["uptime_s"].is_u64());
}

#[tokio::test]
async fn exclusive_steal_reject_through_handler() {
    let d = Daemon::new();
    let a = d.handle(make_request("exclusive_start", Some(json!({"token": "A"})), None)).await;
    assert_eq!(a["success"], json!(true));
    assert_eq!(a["token"], json!("A"));

    // a competing session is rejected immediately (the R53.x steal-reject)
    let b = d.handle(make_request("exclusive_start", Some(json!({"token": "B"})), None)).await;
    assert_eq!(b["success"], json!(false));
    assert!(b["error"].as_str().unwrap().contains("exclusively held"));

    let end = d.handle(make_request("exclusive_end", Some(json!({"token": "A"})), None)).await;
    assert_eq!(end["success"], json!(true));

    // after release, B can acquire
    let b2 = d.handle(make_request("exclusive_start", Some(json!({"token": "B"})), None)).await;
    assert_eq!(b2["success"], json!(true));
}

#[tokio::test]
async fn exclusive_start_requires_token() {
    let d = Daemon::new();
    let r = d.handle(make_request("exclusive_start", None, None)).await;
    assert_eq!(r["success"], json!(false));
    assert!(r["error"].as_str().unwrap().contains("requires 'token'"));
}

#[tokio::test]
async fn device_commands_are_honestly_unimplemented() {
    let d = Daemon::new();
    let r = d.handle(make_request("device_call", Some(json!({"method": "device.unimplemented_method"})), None)).await;
    assert_eq!(r["success"], json!(false), "must NOT fake success");
    let err = r["error"].as_str().unwrap();
    assert!(err.contains("no device connected") || err.contains("not implemented") || err.contains("not ported"), "Unexpected error: {}", err);
}

#[tokio::test]
async fn device_name_commands_route_to_device_call() {
    let d = Daemon::new();
    // get_device_name returns "no device connected" when no device is connected,
    // which confirms it is routed to cmd_device_call (implemented)
    let r1 = d.handle(make_request("device_call", Some(json!({"method": "device.get_device_name"})), None)).await;
    assert_eq!(r1["success"], json!(false));
    let err1 = r1["error"].as_str().unwrap();
    assert!(err1.contains("no device connected") || err1.contains("not implemented"), "Unexpected error: {}", err1);

    // set_device_name returns "no device connected"
    let r2 = d.handle(make_request("device_call", Some(json!({"method": "device.set_device_name", "args": ["NewName"]})), None)).await;
    assert_eq!(r2["success"], json!(false));
    let err2 = r2["error"].as_str().unwrap();
    assert!(err2.contains("no device connected") || err2.contains("not implemented"), "Unexpected error: {}", err2);
}

#[tokio::test]
async fn ported_commands_route_to_device_call() {
    let d = Daemon::new();
    let methods = vec![
        ("music.get_volume", json!([])),
        ("music.set_volume", json!([10])),
        ("radio.set_radio_frequency", json!([875])),
        ("device.get_low_power_switch", json!([])),
        ("device.set_low_power_switch", json!([1])),
        ("device.get_auto_power_off", json!([])),
        ("device.set_auto_power_off", json!([15])),
        ("scoreboard.set_scoreboard", json!([1, 10, 20])),
        ("scoreboard.get_scoreboard", json!([])),
        ("set_scoreboard", json!([1, 10, 20])),
        ("get_scoreboard", json!([])),
        ("timer.set_timer", json!([1])),
        ("timer.get_timer", json!([])),
        ("set_timer", json!([1])),
        ("get_timer", json!([])),
        ("countdown.set_countdown", json!([1, 10, 0])),
        ("countdown.get_countdown", json!([])),
        ("set_countdown", json!([1, 10, 0])),
        ("get_countdown", json!([])),
        ("noise.set_noise", json!([1])),
        ("noise.get_noise", json!([])),
        ("set_noise", json!([1])),
        ("get_noise", json!([])),
        ("device.show_notification", json!([1])),
        ("show_notification", json!([1])),
        ("notification.show_notification", json!([1])),
        ("device.show_notification_text", json!([1, "hello"])),
        ("show_notification_text", json!([1, "hello"])),
        ("notification.show_notification_text", json!([1, "hello"])),
        ("alarm.get_alarm_time", json!([])),
        ("get_alarm_time", json!([])),
        ("alarm.set_alarm", json!([0, 1, 8, 30, 127, 0, 1, 0, 10])),
        ("set_alarm", json!([0, 1, 8, 30, 127, 0, 1, 0, 10])),
        ("alarm.set_alarm_gif", json!([0, 100, 1, [0, 1, 2]])),
        ("set_alarm_gif", json!([0, 100, 1, [0, 1, 2]])),
        ("alarm.get_memorial_time", json!([])),
        ("get_memorial_time", json!([])),
        ("alarm.set_memorial_time", json!([0, 1, 1, 1, 12, 0, 1, "Memorial"])),
        ("set_memorial_time", json!([0, 1, 1, 1, 12, 0, 1, "Memorial"])),
        ("alarm.set_memorial_gif", json!([0, 100, 1, [0, 1, 2]])),
        ("set_memorial_gif", json!([0, 100, 1, [0, 1, 2]])),
        ("alarm.set_alarm_listen", json!([1, 0, 15])),
        ("set_alarm_listen", json!([1, 0, 15])),
        ("alarm.set_alarm_volume", json!([15])),
        ("set_alarm_volume", json!([15])),
        ("alarm.set_alarm_volume_control", json!([1, 0])),
        ("set_alarm_volume_control", json!([1, 0])),
        ("sleep.show_sleep", json!([60, 0, 1, 875, 10, [255, 255, 255], 100])),
        ("show_sleep", json!([60, 0, 1, 875, 10, [255, 255, 255], 100])),
        ("sleep.get_sleep_scene", json!([])),
        ("get_sleep_scene", json!([])),
        ("sleep.set_sleep_scene_listen", json!([1, 0, 15])),
        ("set_sleep_scene_listen", json!([1, 0, 15])),
        ("sleep.set_scene_volume", json!([15])),
        ("set_scene_volume", json!([15])),
        ("sleep.set_sleep_color", json!([[0, 0, 255]])),
        ("set_sleep_color", json!([[0, 0, 255]])),
        ("sleep.set_sleep_light", json!([50])),
        ("set_sleep_light", json!([50])),
        ("sleep.set_sleep_scene", json!([0, 1, [0, 0], 10, [255, 255, 255], 50])),
        ("set_sleep_scene", json!([0, 1, [0, 0], 10, [255, 255, 255], 50])),
        ("timeplan.set_time_manage_info", json!([1, 8, 0, 127, 0, 1, 875, 15, 1])),
        ("set_time_manage_info", json!([1, 8, 0, 127, 0, 1, 875, 15, 1])),
        ("timeplan.set_time_manage_ctrl", json!([1, 0])),
        ("set_time_manage_ctrl", json!([1, 0])),
    ];

    for (method, args) in methods {
        let r = d.handle(make_request("device_call", Some(json!({"method": method, "args": args})), None)).await;
        assert_eq!(r["success"], json!(false), "method {} should fail", method);
        let err = r["error"].as_str().unwrap();
        assert!(
            err.contains("no device connected") || err.contains("not implemented") || err.contains("not ported"),
            "Method {} returned unexpected error: {}",
            method,
            err
        );
    }
}





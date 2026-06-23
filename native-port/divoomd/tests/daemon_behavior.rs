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
    let r = d.handle(make_request("device_call", Some(json!({"method": "device.set_brightness"})), None)).await;
    assert_eq!(r["success"], json!(false), "must NOT fake success");
    assert!(r["error"].as_str().unwrap().contains("not implemented"));
}

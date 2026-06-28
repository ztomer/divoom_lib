#[cfg(test)]
mod tests {
    use crate::daemon::{Daemon, DeviceTransport};
    use crate::protocol::make_request;
    use crate::socket_server::Handler;
    use serde_json::json;

    async fn setup_mock_daemon() -> Daemon {
        let d = Daemon::new();
        let conn_res = d.handle(make_request("connect", Some(json!({"mock": true})), None)).await;
        assert!(conn_res["success"].as_bool().unwrap_or(false));
        d
    }

    #[tokio::test]
    async fn test_mock_display_set_clock_rich() {
        let d = setup_mock_daemon().await;
        
        let call_res = d.handle(make_request("device_call", Some(json!({
            "method": "display.set_clock_rich",
            "kwargs": {
                "style": 3,
                "twentyfour": true,
                "humidity": true,
                "weather": false,
                "date": true,
                "color": "#ff00ff"
            }
        })), None)).await;
        
        assert!(call_res["success"].as_bool().unwrap_or(false));

        let device_lock = d.device.lock().await;
        if let Some(ref transport_arc) = &*device_lock {
            if let DeviceTransport::Mock(ref mock) = **transport_arc {
                let cmds = mock.sent_commands.lock().unwrap();
                assert_eq!(cmds.len(), 1);
                let (cmd_id, payload) = &cmds[0];
                assert_eq!(*cmd_id, 0x45);
                // Expected APK C2 bytes: [0x00, 0x01, 0x03, 0x01, 0x01, 0x00, 0x01, 0xFF, 0x00, 0xFF]
                assert_eq!(*payload, vec![0x00, 0x01, 0x03, 0x01, 0x01, 0x00, 0x01, 0xFF, 0x00, 0xFF]);
            } else {
                panic!("Expected Mock transport");
            }
        } else {
            panic!("Expected connected device");
        }
    }

    #[tokio::test]
    async fn test_mock_display_show_clock() {
        let d = setup_mock_daemon().await;
        
        let call_res = d.handle(make_request("device_call", Some(json!({
            "method": "display.show_clock",
            "kwargs": {
                "clock": 4,
                "twentyfour": false,
                "weather": true,
                "temp": true,
                "calendar": false,
                "color": "#00ff00"
            }
        })), None)).await;
        
        assert!(call_res["success"].as_bool().unwrap_or(false));

        let device_lock = d.device.lock().await;
        if let Some(ref transport_arc) = &*device_lock {
            if let DeviceTransport::Mock(ref mock) = **transport_arc {
                let cmds = mock.sent_commands.lock().unwrap();
                assert_eq!(cmds.len(), 1);
                let (cmd_id, payload) = &cmds[0];
                assert_eq!(*cmd_id, 0x45);
                // Expected hass-divoom show_clock bytes: [0x00, 0x00, 0x04, 0x01, 0x01, 0x01, 0x00, 0x00, 0xFF, 0x00]
                assert_eq!(*payload, vec![0x00, 0x00, 0x04, 0x01, 0x01, 0x01, 0x00, 0x00, 0xFF, 0x00]);
            } else {
                panic!("Expected Mock transport");
            }
        } else {
            panic!("Expected connected device");
        }
    }

    #[tokio::test]
    async fn test_mock_device_set_brightness() {
        let d = setup_mock_daemon().await;
        
        let call_res = d.handle(make_request("device_call", Some(json!({
            "method": "device.set_brightness",
            "args": [75]
        })), None)).await;
        
        assert!(call_res["success"].as_bool().unwrap_or(false));

        let device_lock = d.device.lock().await;
        if let Some(ref transport_arc) = &*device_lock {
            if let DeviceTransport::Mock(ref mock) = **transport_arc {
                let cmds = mock.sent_commands.lock().unwrap();
                assert_eq!(cmds.len(), 1);
                let (cmd_id, payload) = &cmds[0];
                assert_eq!(*cmd_id, 0x74);
                assert_eq!(*payload, vec![75]);
            } else {
                panic!("Expected Mock transport");
            }
        } else {
            panic!("Expected connected device");
        }
    }

    #[tokio::test]
    async fn test_mock_music_set_volume() {
        let d = setup_mock_daemon().await;
        
        let call_res = d.handle(make_request("device_call", Some(json!({
            "method": "music.set_volume",
            "args": [12]
        })), None)).await;
        
        assert!(call_res["success"].as_bool().unwrap_or(false));

        let device_lock = d.device.lock().await;
        if let Some(ref transport_arc) = &*device_lock {
            if let DeviceTransport::Mock(ref mock) = **transport_arc {
                let cmds = mock.sent_commands.lock().unwrap();
                assert_eq!(cmds.len(), 1);
                let (cmd_id, payload) = &cmds[0];
                assert_eq!(*cmd_id, 0x08);
                assert_eq!(*payload, vec![12]);
            } else {
                panic!("Expected Mock transport");
            }
        } else {
            panic!("Expected connected device");
        }
    }
}

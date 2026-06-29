//! Application state + frame orchestration. The visual reference is the current
//! pywebview dashboard (`divoom_gui/web_ui/`): integrated appbar (window controls
//! + brightness/volume + settings gear), a 168px sidebar (6 nav tabs + device
//! panel pinned to the bottom), and a tab content area.

use crate::daemon::{self, DaemonHandle, Device, Update};
use crate::shell;

pub use crate::model::{Alarm, Channel, PixelSub, Tab};

pub struct DivoomApp {
    pub daemon: DaemonHandle,
    pub tab: Tab,
    pub channel: Channel,
    pub brightness: u8,
    pub volume: u8,
    pub devices: Vec<Device>,
    pub selected_device: Option<usize>,
    pub daemon_connected: bool,
    pub status_detail: String,
    pub last_error: Option<String>,
    // --- Channels tab control state (mirrors web_ui channel panels) ---
    pub clock_face: i64,
    pub clock_color: [u8; 3],
    pub viz_sel: i64,
    pub vj_sel: i64,
    pub ambient_mode: i64,
    pub ambient_color: [u8; 3],
    pub score_blue: i64,
    pub score_red: i64,
    pub text_content: String,
    pub text_color: [u8; 3],
    pub text_speed: i64,
    pub text_effect: i64,
    // --- Sessions sub-tab ---
    pub sleep_minutes: i64,
    pub sleep_color: [u8; 3],
    pub sleep_volume: i64,
    pub countdown_min: i64,
    pub countdown_sec: i64,
    /// Debug self-screenshot: if `DIVOOM_UI_SCREENSHOT` is set, render a few
    /// frames, grab the framebuffer (no OS screen-recording permission needed),
    /// save it there, and exit. Used for headless visual verification.
    screenshot_path: Option<String>,
    frame_count: u32,
    tray: Option<crate::tray::Tray>,
    tray_inited: bool,
    tray_device_sig: String,
    notif_running: bool,
    last_active: bool,
    // --- Device Settings tab ---
    pub device_name: String,
    pub hour24: bool,
    pub temp_f: bool,
    pub low_power: bool,
    pub auto_off_min: i64,
    pub screen_dir: i64,
    pub screen_mirror: bool,
    pub fm_freq: f32,
    pub confirm_reset: bool,
    // --- Settings tab ---
    pub lan_ip: String,
    pub lan_token: String,
    pub keep_alive: bool,
    pub scan_timeout: f64,
    // --- Schedule tab (alarm slots) ---
    pub alarms: Vec<Alarm>,
    // --- Pixel Art tab (16x16 editor) ---
    pub pixels: Vec<[u8; 3]>,
    pub paint_color: [u8; 3],
    pub pixel_sub: PixelSub,
    // --- Live Widgets tab (live data feeds → live_job_start/stop) ---
    pub music_sync: bool,
    pub stocks_sync: bool,
    pub sysmon_sync: bool,
    pub weather_sync: bool,
    pub stocks_symbol: String,
    pub temp_celsius: bool,
    pub temp_color: [u8; 3],
    // --- Schedule: memorial slot + one-shot alarm fetch ---
    pub mem_enabled: bool,
    pub mem_month: i64,
    pub mem_day: i64,
    pub mem_hour: i64,
    pub mem_minute: i64,
    pub mem_title: String,
    pub alarms_fetched: bool,
    // --- Schedule: time plan (scheduled on/off) ---
    pub tp_enabled: bool,
    pub tp_hour: i64,
    pub tp_minute: i64,
    pub tp_week: u8,
    /// Replies to `Cmd::Raw`, keyed by tag (Settings/Schedule/gallery read these).
    pub replies: std::collections::HashMap<String, serde_json::Value>,
}

impl DivoomApp {
    pub fn new(cc: &eframe::CreationContext<'_>) -> Self {
        crate::theme::apply(&cc.egui_ctx);
        let daemon = daemon::start();
        daemon.send(daemon::Cmd::Scan(8.0));
        Self {
            daemon,
            tab: match std::env::var("DIVOOM_UI_TAB").as_deref() {
                Ok("widgets") => Tab::Widgets,
                Ok("pixelart") => Tab::PixelArt,
                Ok("wall") => Tab::Wall,
                Ok("schedule") => Tab::Schedule,
                Ok("device") => Tab::DeviceSettings,
                Ok("settings") => Tab::Settings,
                _ => Tab::Channels,
            },
            channel: match std::env::var("DIVOOM_UI_CHANNEL").as_deref() {
                Ok("visualizer") => Channel::Visualizer,
                Ok("vj") => Channel::Vj,
                Ok("ambient") => Channel::Ambient,
                Ok("scoreboard") => Channel::Scoreboard,
                Ok("text") => Channel::Text,
                Ok("sessions") => Channel::Sessions,
                _ => Channel::Clock,
            },
            brightness: 80,
            volume: 7,
            devices: Vec::new(),
            selected_device: None,
            daemon_connected: false,
            status_detail: "connecting…".into(),
            last_error: None,
            screenshot_path: std::env::var("DIVOOM_UI_SCREENSHOT").ok(),
            frame_count: 0,
            tray: None,
            tray_inited: false,
            tray_device_sig: String::new(),
            notif_running: false,
            last_active: false,
            clock_face: 0,
            clock_color: [255, 255, 255],
            viz_sel: 0,
            vj_sel: 0,
            ambient_mode: 0,
            ambient_color: [0, 255, 204],
            score_blue: 0,
            score_red: 0,
            text_content: std::env::var("DIVOOM_UI_TEXT").unwrap_or_default(),
            text_color: [0, 255, 204],
            text_speed: 50,
            text_effect: 1,
            sleep_minutes: 30,
            sleep_color: [0x20, 0x40, 0xff],
            sleep_volume: 10,
            countdown_min: 5,
            countdown_sec: 0,
            device_name: String::new(),
            hour24: true,
            temp_f: false,
            low_power: false,
            auto_off_min: 0,
            screen_dir: 0,
            screen_mirror: false,
            fm_freq: 87.5,
            confirm_reset: false,
            lan_ip: String::new(),
            lan_token: String::new(),
            keep_alive: true,
            scan_timeout: 8.0,
            alarms: vec![Alarm::default(); 5],
            pixels: vec![[0, 0, 0]; 16 * 16],
            paint_color: [255, 90, 31],
            pixel_sub: PixelSub::Paint,
            music_sync: false,
            stocks_sync: false,
            sysmon_sync: false,
            weather_sync: false,
            stocks_symbol: String::new(),
            temp_celsius: true,
            temp_color: [255, 255, 255],
            mem_enabled: false,
            mem_month: 1,
            mem_day: 1,
            mem_hour: 0,
            mem_minute: 0,
            mem_title: String::new(),
            alarms_fetched: false,
            tp_enabled: false,
            tp_hour: 8,
            tp_minute: 0,
            tp_week: 0,
            replies: std::collections::HashMap::new(),
        }
    }

    /// Fire a device_call with positional args (the convention the Rust daemon's
    /// channel methods parse). Returns immediately; errors surface via `pump`.
    pub fn call(&self, method: &str, args: serde_json::Value) {
        self.daemon.send(daemon::Cmd::DeviceCall { method: method.to_string(), args });
    }

    /// Fire a top-level daemon command (not a device_call) with a reply tag.
    pub fn raw(&self, command: &str, args: serde_json::Value, tag: &str) {
        self.daemon.send(daemon::Cmd::Raw {
            command: command.to_string(),
            args,
            tag: tag.to_string(),
        });
    }

    /// device_call with KEYWORD args (the convention for methods like
    /// `display.set_clock_rich` / `show_image` that read `kwargs`, not positional).
    pub fn call_kw(&self, method: &str, kwargs: serde_json::Value) {
        self.raw(
            "device_call",
            serde_json::json!({ "method": method, "args": [], "kwargs": kwargs }),
            "_kw",
        );
    }

    /// Read current device state into the UI (so controls reflect the device, not
    /// hardcoded defaults). Only meaningful once a device is connected.
    fn fetch_device_state(&self) {
        for (method, tag) in [
            ("get_brightness", "rb_brightness"),
            ("get_volume", "rb_volume"),
            ("get_device_name", "rb_name"),
            ("get_scoreboard", "rb_score"),
        ] {
            self.raw("device_call", serde_json::json!({ "method": method, "args": [] }), tag);
        }
    }

    /// Hex `#rrggbb` for an `[r,g,b]` (device_call color args parse a hex string).
    pub fn hex(rgb: [u8; 3]) -> String {
        format!("#{:02x}{:02x}{:02x}", rgb[0], rgb[1], rgb[2])
    }

    /// MAC/address of the currently-selected device, if any (live jobs need it).
    pub fn active_mac(&self) -> Option<String> {
        self.selected_device
            .and_then(|i| self.devices.get(i))
            .map(|d| d.address.clone())
            .filter(|a| !a.is_empty())
    }

    /// Start/stop a server-side live-push job (music/stocks/sysmon/weather).
    pub fn toggle_live_job(&self, kind: &str, enable: bool, params: serde_json::Value) {
        let Some(mac) = self.active_mac() else { return };
        if enable {
            self.raw(
                "live_job_start",
                serde_json::json!({ "mac": mac, "kind": kind, "params": params }),
                "live_job",
            );
        } else {
            self.raw("live_job_stop", serde_json::json!({ "mac": mac, "kind": kind }), "live_job");
        }
    }

    /// Headless visual check: request a framebuffer grab after the UI settles,
    /// save it, then close. No-op unless `DIVOOM_UI_SCREENSHOT` is set.
    fn maybe_screenshot(&mut self, ctx: &egui::Context) {
        let Some(path) = self.screenshot_path.clone() else { return };
        self.frame_count += 1;
        if self.frame_count == 4 {
            ctx.send_viewport_cmd(egui::ViewportCommand::Screenshot);
        }
        let shot = ctx.input(|i| {
            i.events.iter().find_map(|e| match e {
                egui::Event::Screenshot { image, .. } => Some(image.clone()),
                _ => None,
            })
        });
        if let Some(img) = shot {
            let [w, h] = img.size;
            let mut buf = Vec::with_capacity(w * h * 4);
            for px in &img.pixels {
                buf.extend_from_slice(&[px.r(), px.g(), px.b(), px.a()]);
            }
            if let Some(rgba) = image::RgbaImage::from_raw(w as u32, h as u32, buf) {
                let _ = rgba.save(&path);
            }
            ctx.send_viewport_cmd(egui::ViewportCommand::Close);
        }
    }

    /// Drain worker updates into UI state.
    fn pump(&mut self) {
        let mut became_active = false;
        while let Ok(upd) = self.daemon.rx.try_recv() {
            match upd {
                Update::Status { connected, detail, .. } => {
                    self.daemon_connected = connected;
                    let active = detail == "active";
                    if active && !self.last_active {
                        became_active = true; // device just connected → read its state
                    }
                    self.last_active = active;
                    self.status_detail = detail;
                }
                Update::Devices(d) => {
                    if self.selected_device.is_none() && !d.is_empty() {
                        self.selected_device = Some(0);
                    }
                    self.devices = d;
                }
                Update::Error(e) => self.last_error = Some(e),
                Update::Info(_) => {}
                Update::Reply { tag, value } => {
                    match tag.as_str() {
                        "notif_status" => {
                            self.notif_running = value
                                .get("running")
                                .and_then(|r| r.as_bool())
                                .or_else(|| value.get("state").and_then(|s| s.as_str()).map(|s| s == "running"))
                                .unwrap_or(false);
                            // tray notif label is synced in handle_tray.
                        }
                        "rb_brightness" => {
                            if let Some(n) = value.get("result").and_then(|v| v.as_i64()) {
                                self.brightness = n.clamp(0, 100) as u8;
                            }
                        }
                        "rb_volume" => {
                            if let Some(n) = value.get("result").and_then(|v| v.as_i64()) {
                                self.volume = n.clamp(0, 15) as u8;
                            }
                        }
                        "rb_name" => {
                            if let Some(s) = value.get("result").and_then(|v| v.as_str()) {
                                if !s.is_empty() {
                                    self.device_name = s.to_string();
                                }
                            }
                        }
                        "rb_score" => {
                            if let Some(r) = value.get("result") {
                                if let Some(n) = r.get("red_score").and_then(|v| v.as_i64()) {
                                    self.score_red = n;
                                }
                                if let Some(n) = r.get("blue_score").and_then(|v| v.as_i64()) {
                                    self.score_blue = n;
                                }
                            }
                        }
                        "rb_alarms" => {
                            if let Some(arr) = value.get("result").and_then(|v| v.as_array()) {
                                for (i, a) in arr.iter().enumerate() {
                                    if let Some(slot) = self.alarms.get_mut(i) {
                                        slot.enabled = a.get("status").and_then(|v| v.as_i64()).unwrap_or(0) != 0;
                                        slot.hour = a.get("hour").and_then(|v| v.as_i64()).unwrap_or(slot.hour);
                                        slot.minute = a.get("minute").and_then(|v| v.as_i64()).unwrap_or(slot.minute);
                                        slot.week = a.get("week").and_then(|v| v.as_i64()).unwrap_or(0) as u8;
                                    }
                                }
                            }
                        }
                        _ => {}
                    }
                    self.replies.insert(tag, value);
                }
            }
        }
        if became_active {
            self.fetch_device_state();
            self.alarms_fetched = false; // re-read alarms when the Schedule tab opens
        }
    }
}

impl eframe::App for DivoomApp {
    fn clear_color(&self, _visuals: &egui::Visuals) -> [f32; 4] {
        crate::theme::BG_BASE.to_normalized_gamma_f32()
    }

    fn update(&mut self, ctx: &egui::Context, _frame: &mut eframe::Frame) {
        self.pump();
        self.handle_tray(ctx);
        shell::appbar(self, ctx);
        shell::sidebar(self, ctx);
        shell::content(self, ctx);
        self.maybe_screenshot(ctx);
        // Keep the live-status poll flowing even when idle.
        ctx.request_repaint_after(std::time::Duration::from_millis(200));
    }
}

impl DivoomApp {
    /// Lazily build the tray on the first frame (main thread, event loop up), then
    /// poll its menu each frame. Skipped in screenshot mode / when DIVOOM_UI_NO_TRAY
    /// is set (headless runs).
    fn handle_tray(&mut self, ctx: &egui::Context) {
        if !self.tray_inited {
            self.tray_inited = true;
            if self.screenshot_path.is_none() && std::env::var("DIVOOM_UI_NO_TRAY").is_err() {
                self.tray = crate::tray::Tray::build();
                if self.tray.is_some() {
                    // Fetch notification state to label the menu correctly.
                    self.raw("notification_status", serde_json::json!({}), "notif_status");
                }
            }
        }
        // Sync the dynamic device section + notif label to current state.
        let devices: Vec<(String, String)> =
            self.devices.iter().map(|d| (d.name.clone(), d.address.clone())).collect();
        let sig = devices.iter().map(|(_, a)| a.as_str()).collect::<Vec<_>>().join(",");
        let sig_changed = sig != self.tray_device_sig;
        let notif = self.notif_running;
        if let Some(t) = self.tray.as_mut() {
            if sig_changed {
                t.set_devices(&devices);
            }
            t.set_notifications_running(notif, &devices);
        }
        self.tray_device_sig = sig;

        let Some(action) = self.tray.as_ref().and_then(|t| t.poll()) else { return };
        match action {
            crate::tray::TrayAction::ShowDashboard => {
                ctx.send_viewport_cmd(egui::ViewportCommand::Visible(true));
                ctx.send_viewport_cmd(egui::ViewportCommand::Focus);
            }
            crate::tray::TrayAction::ToggleNotifications => {
                let cmd = if self.notif_running { "stop_notifications" } else { "start_notifications" };
                self.raw(cmd, serde_json::json!({}), "notif_status");
            }
            crate::tray::TrayAction::SelectDevice(addr) => {
                if let Some(i) = self.devices.iter().position(|d| d.address == addr) {
                    self.selected_device = Some(i);
                }
                self.daemon.send(daemon::Cmd::Connect(addr));
            }
            crate::tray::TrayAction::Quit => {
                ctx.send_viewport_cmd(egui::ViewportCommand::Close);
            }
        }
    }
}

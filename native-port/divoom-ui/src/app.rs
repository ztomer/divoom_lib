//! Application state + frame orchestration. The visual reference is the current
//! pywebview dashboard (`divoom_gui/web_ui/`): integrated appbar (window controls
//! + brightness/volume + settings gear), a 168px sidebar (6 nav tabs + device
//! panel pinned to the bottom), and a tab content area.

use crate::daemon::{self, DaemonHandle, Device, Update};
use crate::shell;

#[derive(PartialEq, Eq, Clone, Copy)]
pub enum Tab {
    Channels,
    Widgets,
    PixelArt,
    Wall,
    Schedule,
    DeviceSettings,
    Settings,
}

impl Tab {
    /// Sidebar nav entries, in order (Settings is reached via the appbar gear).
    pub const NAV: [(Tab, &'static str); 6] = [
        (Tab::Channels, "Channels"),
        (Tab::Widgets, "Live Widgets"),
        (Tab::PixelArt, "Pixel Art"),
        (Tab::Wall, "Virtual Wall"),
        (Tab::Schedule, "Schedule"),
        (Tab::DeviceSettings, "Device Settings"),
    ];

    pub fn title(self) -> &'static str {
        match self {
            Tab::Channels => "Channels",
            Tab::Widgets => "Live Widgets",
            Tab::PixelArt => "Pixel Art",
            Tab::Wall => "Virtual Wall",
            Tab::Schedule => "Schedule",
            Tab::DeviceSettings => "Device Settings",
            Tab::Settings => "Settings",
        }
    }
}

/// Channel sub-tabs inside the Channels tab (the control-panel row).
#[derive(PartialEq, Eq, Clone, Copy)]
pub enum Channel {
    Clock,
    Visualizer,
    Vj,
    Ambient,
    Scoreboard,
    Text,
    Sessions,
}

impl Channel {
    pub const ALL: [(Channel, &'static str); 7] = [
        (Channel::Clock, "Clock"),
        (Channel::Visualizer, "Visualizer"),
        (Channel::Vj, "VJ FX"),
        (Channel::Ambient, "Ambient"),
        (Channel::Scoreboard, "Scoreboard"),
        (Channel::Text, "Text"),
        (Channel::Sessions, "Sessions"),
    ];
}

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
    /// Debug self-screenshot: if `DIVOOM_UI_SCREENSHOT` is set, render a few
    /// frames, grab the framebuffer (no OS screen-recording permission needed),
    /// save it there, and exit. Used for headless visual verification.
    screenshot_path: Option<String>,
    frame_count: u32,
    // --- Device Settings tab ---
    pub device_name: String,
    pub hour24: bool,
    pub temp_f: bool,
    pub low_power: bool,
    pub auto_off_min: i64,
    pub screen_dir: i64,
    pub screen_mirror: bool,
    pub confirm_reset: bool,
    // --- Settings tab ---
    pub lan_ip: String,
    pub lan_token: String,
    pub keep_alive: bool,
    // --- Schedule tab (alarm slots) ---
    pub alarms: Vec<Alarm>,
    /// Replies to `Cmd::Raw`, keyed by tag (Settings/Schedule/gallery read these).
    pub replies: std::collections::HashMap<String, serde_json::Value>,
}

/// One alarm slot, mirroring `tools.set_alarm(index, enabled, hour, minute, week,
/// mode, trigger_mode)`. `week` is a 7-bit day mask (bit0=Mon … bit6=Sun).
#[derive(Clone)]
pub struct Alarm {
    pub enabled: bool,
    pub hour: i64,
    pub minute: i64,
    pub week: u8,
}

impl Default for Alarm {
    fn default() -> Self {
        Alarm { enabled: false, hour: 8, minute: 0, week: 0 }
    }
}

impl DivoomApp {
    pub fn new(cc: &eframe::CreationContext<'_>) -> Self {
        crate::theme::apply(&cc.egui_ctx);
        let daemon = daemon::start();
        daemon.send(daemon::Cmd::Scan);
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
            clock_face: 0,
            clock_color: [255, 255, 255],
            viz_sel: 0,
            vj_sel: 0,
            ambient_mode: 0,
            ambient_color: [0, 255, 204],
            score_blue: 0,
            score_red: 0,
            text_content: String::new(),
            text_color: [0, 255, 204],
            text_speed: 50,
            text_effect: 1,
            device_name: String::new(),
            hour24: true,
            temp_f: false,
            low_power: false,
            auto_off_min: 0,
            screen_dir: 0,
            screen_mirror: false,
            confirm_reset: false,
            lan_ip: String::new(),
            lan_token: String::new(),
            keep_alive: true,
            alarms: vec![Alarm::default(); 5],
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

    /// Hex `#rrggbb` for an `[r,g,b]` (device_call color args parse a hex string).
    pub fn hex(rgb: [u8; 3]) -> String {
        format!("#{:02x}{:02x}{:02x}", rgb[0], rgb[1], rgb[2])
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
        while let Ok(upd) = self.daemon.rx.try_recv() {
            match upd {
                Update::Status { connected, detail, .. } => {
                    self.daemon_connected = connected;
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
                    self.replies.insert(tag, value);
                }
            }
        }
    }
}

impl eframe::App for DivoomApp {
    fn clear_color(&self, _visuals: &egui::Visuals) -> [f32; 4] {
        crate::theme::BG_BASE.to_normalized_gamma_f32()
    }

    fn update(&mut self, ctx: &egui::Context, _frame: &mut eframe::Frame) {
        self.pump();
        shell::appbar(self, ctx);
        shell::sidebar(self, ctx);
        shell::content(self, ctx);
        self.maybe_screenshot(ctx);
        // Keep the live-status poll flowing even when idle.
        ctx.request_repaint_after(std::time::Duration::from_millis(200));
    }
}

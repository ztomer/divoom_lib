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
    /// Debug self-screenshot: if `DIVOOM_UI_SCREENSHOT` is set, render a few
    /// frames, grab the framebuffer (no OS screen-recording permission needed),
    /// save it there, and exit. Used for headless visual verification.
    screenshot_path: Option<String>,
    frame_count: u32,
}

impl DivoomApp {
    pub fn new(cc: &eframe::CreationContext<'_>) -> Self {
        crate::theme::apply(&cc.egui_ctx);
        let daemon = daemon::start();
        daemon.send(daemon::Cmd::Scan);
        Self {
            daemon,
            tab: Tab::Channels,
            channel: Channel::Clock,
            brightness: 80,
            volume: 7,
            devices: Vec::new(),
            selected_device: None,
            daemon_connected: false,
            status_detail: "connecting…".into(),
            last_error: None,
            screenshot_path: std::env::var("DIVOOM_UI_SCREENSHOT").ok(),
            frame_count: 0,
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

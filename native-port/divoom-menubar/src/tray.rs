//! The tray/menubar itself: a status-coloured glyph + a menu that mirrors the
//! pyobjc menubar (Launch Dashboard / Open Notifications / Start+Stop
//! Notifications / Quit) plus a read-only active-device section. State is refreshed
//! by polling the daemon (`poll_daemon`); menu clicks are dispatched in `on_menu`.

use tray_icon::menu::{Menu, MenuEvent, MenuId, MenuItem, PredefinedMenuItem};
use tray_icon::{TrayIcon, TrayIconBuilder};

use crate::{daemon, launch};

// Status glyph colours (match the app theme / pyobjc status states).
const GREEN: [u8; 3] = [0x00, 0xcc, 0x66]; // a device is active
const ORANGE: [u8; 3] = [0xff, 0x5a, 0x1f]; // daemon up / idle
const RED: [u8; 3] = [0xff, 0x44, 0x44]; // daemon offline

pub enum TrayAction {
    Quit,
}

pub struct Tray {
    icon: TrayIcon,
    launch_id: MenuId,
    notif_open_id: MenuId,
    notif_start_id: MenuId,
    notif_stop_id: MenuId,
    quit_id: MenuId,
    last_sig: String,
    last_color: [u8; 3],
}

impl Tray {
    pub fn build() -> Option<Tray> {
        let icon = TrayIconBuilder::new()
            .with_tooltip("Divoom Control")
            .with_icon(make_icon(ORANGE))
            .build()
            .ok()?;
        let mut tray = Tray {
            icon,
            launch_id: MenuId::new("launch"),
            notif_open_id: MenuId::new("notif_open"),
            notif_start_id: MenuId::new("notif_start"),
            notif_stop_id: MenuId::new("notif_stop"),
            quit_id: MenuId::new("quit"),
            last_sig: String::new(),
            last_color: ORANGE,
        };
        tray.rebuild(&[], false);
        Some(tray)
    }

    /// Build + install the whole menu: active-device rows (disabled, informational)
    /// then the fixed actions.
    fn rebuild(&mut self, devices: &[(String, String)], notif_running: bool) {
        let menu = Menu::new();
        if devices.is_empty() {
            let _ = menu.append(&MenuItem::new("No active devices", false, None));
        } else {
            for (name, kind) in devices {
                let label = if kind.is_empty() || kind == "idle" {
                    name.clone()
                } else {
                    format!("{name} — {kind}")
                };
                let _ = menu.append(&MenuItem::new(label, false, None));
            }
        }
        let _ = menu.append(&PredefinedMenuItem::separator());
        let _ = menu.append(&MenuItem::with_id(self.launch_id.clone(), "Launch Dashboard", true, None));
        let _ = menu.append(&MenuItem::with_id(self.notif_open_id.clone(), "Open Notifications…", true, None));
        let _ = menu.append(&PredefinedMenuItem::separator());
        // Start is enabled when stopped; Stop when running (parity with pyobjc,
        // which shows both — we just disable the inapplicable one).
        let _ = menu.append(&MenuItem::with_id(self.notif_start_id.clone(), "Start Notifications", !notif_running, None));
        let _ = menu.append(&MenuItem::with_id(self.notif_stop_id.clone(), "Stop Notifications", notif_running, None));
        let _ = menu.append(&PredefinedMenuItem::separator());
        let _ = menu.append(&MenuItem::with_id(self.quit_id.clone(), "Quit Divoom (stop daemon)", true, None));
        self.icon.set_menu(Some(Box::new(menu)));
    }

    /// Poll the daemon and refresh the glyph colour + menu (only when changed, to
    /// avoid rebuilding the menu while the user has it open).
    pub fn poll_daemon(&mut self) {
        let status = daemon::status();
        let color = match status {
            daemon::Status::Offline => RED,
            daemon::Status::Active => GREEN,
            daemon::Status::Idle => ORANGE,
        };
        if color != self.last_color {
            let _ = self.icon.set_icon(Some(make_icon(color)));
            self.last_color = color;
        }

        let offline = matches!(status, daemon::Status::Offline);
        let devices = if offline { Vec::new() } else { daemon::device_activity() };
        let notif_running = !offline && daemon::notifications_running();

        let sig = format!(
            "{}|{}|{}",
            if offline { "off" } else { "on" },
            notif_running,
            devices.iter().map(|(n, k)| format!("{n}:{k}")).collect::<Vec<_>>().join(",")
        );
        if sig != self.last_sig {
            self.rebuild(&devices, notif_running);
            self.last_sig = sig;
        }
    }

    /// Dispatch a menu click. Returns `Some(Quit)` when the app should exit.
    pub fn on_menu(&mut self, ev: &MenuEvent) -> Option<TrayAction> {
        if ev.id == self.launch_id {
            launch::open_dashboard();
        } else if ev.id == self.notif_open_id {
            launch::open_notifications();
        } else if ev.id == self.notif_start_id {
            daemon::start_notifications();
            self.last_sig.clear(); // force a menu refresh on next poll
        } else if ev.id == self.notif_stop_id {
            daemon::stop_notifications();
            self.last_sig.clear();
        } else if ev.id == self.quit_id {
            launch::quit();
            return Some(TrayAction::Quit);
        }
        None
    }
}

/// A 16x16 filled rounded square in `rgb` — the menubar glyph (status-coloured).
fn make_icon(rgb: [u8; 3]) -> tray_icon::Icon {
    const N: usize = 16;
    let mut rgba = vec![0u8; N * N * 4];
    for y in 0..N {
        for x in 0..N {
            let edge = x == 0 || y == 0 || x == N - 1 || y == N - 1;
            if !edge {
                let i = (y * N + x) * 4;
                rgba[i] = rgb[0];
                rgba[i + 1] = rgb[1];
                rgba[i + 2] = rgb[2];
                rgba[i + 3] = 0xff;
            }
        }
    }
    tray_icon::Icon::from_rgba(rgba, N as u32, N as u32).expect("valid tray icon")
}

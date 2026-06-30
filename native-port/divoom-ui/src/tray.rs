//! Native tray/menubar — cross-platform replacement for `divoom_menubar/` (pyobjc
//! NSStatusItem). Built with `tray-icon`; menu/click events arrive on global
//! channels polled from the eframe loop (`poll`). The menu has a dynamic device
//! section (rebuilt via `set_devices` when the scan list changes), plus Show
//! Dashboard / Notifications / Quit. Same-process: "Show Dashboard" focuses our
//! window rather than spawning a subprocess.

use tray_icon::menu::{Menu, MenuId, MenuItem, PredefinedMenuItem};
use tray_icon::{TrayIcon, TrayIconBuilder};

pub struct Tray {
    icon: TrayIcon,
    show_id: MenuId,
    notif_id: MenuId,
    quit_id: MenuId,
    /// (menu id, device address) for the current device section.
    device_ids: Vec<(MenuId, String)>,
    notif_running: bool,
}

pub enum TrayAction {
    ShowDashboard,
    ToggleNotifications,
    SelectDevice(String),
    Quit,
}

impl Tray {
    pub fn build() -> Option<Tray> {
        let icon = TrayIconBuilder::new()
            .with_tooltip("Divoom Control")
            .with_icon(make_icon([0xff, 0x5a, 0x1f]))
            .build()
            .ok()?;
        let mut tray = Tray {
            icon,
            show_id: MenuId::new("show"),
            notif_id: MenuId::new("notif"),
            quit_id: MenuId::new("quit"),
            device_ids: Vec::new(),
            notif_running: false,
        };
        tray.rebuild(&[]);
        Some(tray)
    }

    /// Rebuild the whole menu (device section + fixed items) and install it.
    fn rebuild(&mut self, devices: &[(String, String)]) {
        let menu = Menu::new();
        self.device_ids.clear();
        if devices.is_empty() {
            let _ = menu.append(&MenuItem::new("No screens found", false, None));
        } else {
            for (name, addr) in devices {
                let label = if name.is_empty() { addr.clone() } else { name.clone() };
                let item = MenuItem::new(label, true, None);
                self.device_ids.push((item.id().clone(), addr.clone()));
                let _ = menu.append(&item);
            }
        }
        let _ = menu.append(&PredefinedMenuItem::separator());
        let show = MenuItem::with_id(self.show_id.clone(), "Show Dashboard", true, None);
        let notif_label = if self.notif_running { "Stop Notifications" } else { "Start Notifications" };
        let notif = MenuItem::with_id(self.notif_id.clone(), notif_label, true, None);
        let quit = MenuItem::with_id(self.quit_id.clone(), "Quit Divoom", true, None);
        let _ = menu.append_items(&[&show, &PredefinedMenuItem::separator(), &notif, &PredefinedMenuItem::separator(), &quit]);
        self.icon.set_menu(Some(Box::new(menu)));
    }

    /// Update the device section (called when the scan list changes).
    pub fn set_devices(&mut self, devices: &[(String, String)]) {
        self.rebuild(devices);
    }

    pub fn set_notifications_running(&mut self, running: bool, devices: &[(String, String)]) {
        if running != self.notif_running {
            self.notif_running = running;
            self.rebuild(devices);
        }
    }

    /// Color-code the menubar glyph by status (parity with the pyobjc menubar).
    pub fn set_status_color(&self, rgb: [u8; 3]) {
        let _ = self.icon.set_icon(Some(make_icon(rgb)));
    }

    /// Drain pending menu events; return the action if one of ours was clicked.
    pub fn poll(&self) -> Option<TrayAction> {
        let mut action = None;
        while let Ok(ev) = tray_icon::menu::MenuEvent::receiver().try_recv() {
            if ev.id == self.show_id {
                action = Some(TrayAction::ShowDashboard);
            } else if ev.id == self.notif_id {
                action = Some(TrayAction::ToggleNotifications);
            } else if ev.id == self.quit_id {
                action = Some(TrayAction::Quit);
            } else if let Some((_, addr)) = self.device_ids.iter().find(|(id, _)| *id == ev.id) {
                action = Some(TrayAction::SelectDevice(addr.clone()));
            }
        }
        action
    }
}

/// A 16x16 filled rounded square in `rgb` — the menubar glyph (status-colored).
fn make_icon(rgb: [u8; 3]) -> tray_icon::Icon {
    const N: usize = 16;
    let mut rgba = vec![0u8; N * N * 4];
    for y in 0..N {
        for x in 0..N {
            let edge = x == 0 || y == 0 || x == N - 1 || y == N - 1;
            let i = (y * N + x) * 4;
            if !edge {
                rgba[i] = rgb[0];
                rgba[i + 1] = rgb[1];
                rgba[i + 2] = rgb[2];
                rgba[i + 3] = 0xff;
            }
        }
    }
    tray_icon::Icon::from_rgba(rgba, N as u32, N as u32).expect("valid tray icon")
}

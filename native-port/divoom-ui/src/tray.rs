//! Native tray/menubar — the cross-platform replacement for `divoom_menubar/`
//! (pyobjc NSStatusItem). Built with `tray-icon`; its menu/click events arrive on
//! global channels that we poll from the eframe frame loop (`poll`). The tray
//! lives in the same process as the window (the Python menubar was a separate
//! process that spawned the GUI; here "Show Dashboard" just focuses our window).

use tray_icon::menu::{Menu, MenuEvent, MenuId, MenuItem, PredefinedMenuItem};
use tray_icon::{TrayIcon, TrayIconBuilder};

pub struct Tray {
    _icon: TrayIcon,
    show_id: MenuId,
    notif_id: MenuId,
    quit_id: MenuId,
    notif_item: MenuItem,
}

/// What the user picked from the tray menu this frame.
pub enum TrayAction {
    ShowDashboard,
    ToggleNotifications,
    Quit,
}

impl Tray {
    /// Build the tray icon + menu. Must run on the main thread with the event loop
    /// already up (call lazily from the first `update`). Returns None if the
    /// platform refuses (e.g. headless) — the app then runs window-only.
    pub fn build() -> Option<Tray> {
        let menu = Menu::new();
        let show = MenuItem::new("Show Dashboard", true, None);
        let notif = MenuItem::new("Start Notifications", true, None);
        let quit = MenuItem::new("Quit Divoom", true, None);
        menu.append_items(&[
            &show,
            &PredefinedMenuItem::separator(),
            &notif,
            &PredefinedMenuItem::separator(),
            &quit,
        ])
        .ok()?;
        let icon = make_icon();
        let tray = TrayIconBuilder::new()
            .with_menu(Box::new(menu))
            .with_tooltip("Divoom Control")
            .with_icon(icon)
            .build()
            .ok()?;
        Some(Tray {
            show_id: show.id().clone(),
            notif_id: notif.id().clone(),
            quit_id: quit.id().clone(),
            notif_item: notif,
            _icon: tray,
        })
    }

    /// Drain pending menu events; return the action if one of ours was clicked.
    pub fn poll(&self) -> Option<TrayAction> {
        let mut action = None;
        while let Ok(ev) = MenuEvent::receiver().try_recv() {
            if ev.id == self.show_id {
                action = Some(TrayAction::ShowDashboard);
            } else if ev.id == self.notif_id {
                action = Some(TrayAction::ToggleNotifications);
            } else if ev.id == self.quit_id {
                action = Some(TrayAction::Quit);
            }
        }
        action
    }

    /// Reflect notification-listener state in the menu label.
    pub fn set_notifications_running(&self, running: bool) {
        self.notif_item
            .set_text(if running { "Stop Notifications" } else { "Start Notifications" });
    }
}

/// A 16x16 orange rounded square — the Braun accent, good enough as a tray glyph
/// until a real icon asset is bundled.
fn make_icon() -> tray_icon::Icon {
    const N: usize = 16;
    let mut rgba = vec![0u8; N * N * 4];
    for y in 0..N {
        for x in 0..N {
            let edge = x == 0 || y == 0 || x == N - 1 || y == N - 1;
            let i = (y * N + x) * 4;
            if !edge {
                rgba[i] = 0xff;
                rgba[i + 1] = 0x5a;
                rgba[i + 2] = 0x1f;
                rgba[i + 3] = 0xff;
            }
        }
    }
    tray_icon::Icon::from_rgba(rgba, N as u32, N as u32).expect("valid tray icon")
}

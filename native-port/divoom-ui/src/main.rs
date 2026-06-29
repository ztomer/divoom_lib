//! divoom-ui — native (Rust/egui) cross-platform UI for divoom-control.
//!
//! Replaces the Python presentation layer (pywebview GUI + pyobjc menubar). The
//! current web UI (`divoom_gui/web_ui/`) is the visual reference. The daemon
//! (`divoomd`) stays the single device owner; this is a pure socket client.

#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod app;
mod channels;
mod daemon;
mod device_settings;
mod pixel_art;
mod schedule;
mod settings;
mod shell;
mod theme;
mod wall;
mod widgets;

use app::DivoomApp;

fn main() -> eframe::Result<()> {
    let options = eframe::NativeOptions {
        viewport: egui::ViewportBuilder::default()
            .with_inner_size([1080.0, 768.0])
            .with_min_inner_size([1050.0, 400.0])
            .with_decorations(false) // integrated custom appbar, like the web UI
            .with_title("Divoom Control Center"),
        ..Default::default()
    };
    eframe::run_native(
        "Divoom Control Center",
        options,
        Box::new(|cc| Ok(Box::new(DivoomApp::new(cc)))),
    )
}

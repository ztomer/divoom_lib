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
mod gallery;
mod model;
mod pixel_art;
mod schedule;
mod settings;
mod shell;
mod text_font;
mod theme;
mod tray;
mod ui_widgets;
mod wall;
mod widgets;

use app::DivoomApp;

fn main() -> eframe::Result<()> {
    let mut viewport = egui::ViewportBuilder::default()
        .with_inner_size([1080.0, 768.0])
        .with_min_inner_size([1050.0, 400.0])
        .with_title("Divoom Control Center");
    // macOS: keep the native traffic-light buttons but extend our content under the
    // title bar (the "unified" look) — instead of a frameless window with painted
    // pseudo-buttons. Other platforms keep normal decorations.
    #[cfg(target_os = "macos")]
    {
        viewport = viewport
            .with_fullsize_content_view(true)
            .with_title_shown(false)
            .with_titlebar_shown(false);
    }
    let options = eframe::NativeOptions { viewport, ..Default::default() };
    eframe::run_native(
        "Divoom Control Center",
        options,
        Box::new(|cc| {
            // Enable ui.image() loaders (file:// channel previews/icons, https gallery).
            egui_extras::install_image_loaders(&cc.egui_ctx);
            Ok(Box::new(DivoomApp::new(cc)))
        }),
    )
}

//! Small reusable custom widgets. `toggle` is the canonical egui toggle-switch
//! (painted pill + animated knob), themed to the Braun palette — replaces the
//! plain checkboxes so the UI matches the web_ui's switch controls.

use eframe::egui::{self, Color32, CornerRadius, Sense, Stroke, Vec2};

use crate::theme;

/// An iOS-style toggle switch bound to `on`. Returns the Response (`.changed()`
/// fires on toggle), so call sites can react exactly like a checkbox.
pub fn toggle(ui: &mut egui::Ui, on: &mut bool) -> egui::Response {
    let size = Vec2::new(38.0, 21.0);
    let (rect, mut resp) = ui.allocate_exact_size(size, Sense::click());
    if resp.clicked() {
        *on = !*on;
        resp.mark_changed();
    }
    let how_on = ui.ctx().animate_bool(resp.id, *on);
    let radius = 0.5 * rect.height();
    let bg = if *on {
        theme::PRIMARY
    } else {
        theme::INPUT_BG
    };
    let stroke = Stroke::new(1.0, if *on { theme::PRIMARY } else { theme::BORDER });
    ui.painter().rect(rect, CornerRadius::same(radius as u8), bg, stroke, egui::StrokeKind::Inside);
    let knob_x = egui::lerp((rect.left() + radius)..=(rect.right() - radius), how_on);
    ui.painter()
        .circle_filled(egui::pos2(knob_x, rect.center().y), radius - 3.0, Color32::WHITE);
    resp
}

/// Resolve the directory of reusable preview assets (the web_ui `assets/` webp
/// icons). Order: `DIVOOM_UI_ASSETS` env → `assets/` next to the executable
/// (bundle) → the dev path under the repo. Returns None if none exist.
pub fn assets_dir() -> Option<std::path::PathBuf> {
    use std::path::PathBuf;
    if let Ok(p) = std::env::var("DIVOOM_UI_ASSETS") {
        let pb = PathBuf::from(p);
        if pb.is_dir() {
            return Some(pb);
        }
    }
    if let Some(sib) = std::env::current_exe()
        .ok()
        .and_then(|e| e.parent().map(|d| d.join("assets")))
        .filter(|p| p.is_dir())
    {
        return Some(sib);
    }
    let dev = PathBuf::from("divoom_gui/web_ui/assets");
    if dev.is_dir() {
        return Some(dev);
    }
    None
}

/// `file://` URI for an asset file name, for `ui.image(...)`. None if no assets dir
/// or the file is missing.
pub fn asset_uri(name: &str) -> Option<String> {
    let p = assets_dir()?.join(name);
    if p.is_file() {
        Some(format!("file://{}", p.display()))
    } else {
        None
    }
}

/// Toggle with a trailing label (common layout). Returns the toggle Response.
pub fn toggle_with_label(ui: &mut egui::Ui, on: &mut bool, label: &str) -> egui::Response {
    ui.horizontal(|ui| {
        let r = toggle(ui, on);
        ui.label(egui::RichText::new(label).size(12.0).color(theme::TEXT_MAIN));
        r
    })
    .inner
}

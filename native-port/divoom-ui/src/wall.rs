//! Virtual Wall tab — compose several screens into one logical display. Mirrors
//! the web wall: assign discovered devices to grid slots, then `wall_configure`
//! with a `slots` object {index: mac}. Most useful with 2+ devices; with one it's
//! a passthrough.

use eframe::egui::{self, RichText};
use serde_json::json;

use crate::app::DivoomApp;
use crate::theme;

pub fn panel(app: &mut DivoomApp, ui: &mut egui::Ui) {
    card(ui, |ui| {
        ui.label(
            RichText::new("Combine multiple Divoom screens into one wall. Discovered devices:")
                .size(12.0)
                .color(theme::TEXT_MUTED),
        );
        ui.add_space(10.0);
        if app.devices.is_empty() {
            ui.label(RichText::new("No devices found — run a scan first.").size(12.0).color(theme::WARN));
            if ui.button("Scan").clicked() {
                app.daemon.send(crate::daemon::Cmd::Scan(app.scan_timeout));
            }
            return;
        }
        // Visual wall canvas: a row of device "screens" (bezels) forming the wall.
        wall_canvas(app, ui);
        ui.add_space(12.0);
        if ui.button("Apply wall layout").clicked() {
            let slots: serde_json::Map<String, serde_json::Value> = app
                .devices
                .iter()
                .enumerate()
                .map(|(i, d)| (i.to_string(), json!(d.address)))
                .collect();
            app.raw("wall_configure", json!({ "slots": slots }), "wall");
        }
        if let Some(v) = app.replies.get("wall") {
            let on = v.get("wall").and_then(|w| w.as_bool()).unwrap_or(false);
            ui.add_space(6.0);
            ui.colored_label(
                if on { theme::ACCENT } else { theme::TEXT_MUTED },
                if on { "Wall configured" } else { "Wall cleared / single device" },
            );
        }
    });
}

/// Paint the discovered devices as a row of screen tiles (neutral bezel + label),
/// the composite "wall" preview.
fn wall_canvas(app: &DivoomApp, ui: &mut egui::Ui) {
    let n = app.devices.len().max(1);
    let tile = egui::Vec2::new(84.0, 84.0);
    let gap = 12.0;
    let total_w = n as f32 * tile.x + (n as f32 - 1.0) * gap;
    let (rect, _) = ui.allocate_exact_size(egui::Vec2::new(ui.available_width(), tile.y + 28.0), egui::Sense::hover());
    let p = ui.painter_at(rect);
    let x0 = rect.left() + ((rect.width() - total_w) / 2.0).max(0.0);
    for (i, d) in app.devices.iter().enumerate() {
        let min = egui::pos2(x0 + i as f32 * (tile.x + gap), rect.top());
        let tr = egui::Rect::from_min_size(min, tile);
        // bezel + screen
        p.rect(tr, egui::CornerRadius::same(8), theme::CARD_BG, egui::Stroke::new(1.0, theme::BORDER), egui::StrokeKind::Inside);
        let screen = tr.shrink(8.0);
        p.rect_filled(screen, egui::CornerRadius::same(3), theme::BG_BASE);
        let sel = app.selected_device == Some(i);
        if sel {
            p.rect_stroke(screen, egui::CornerRadius::same(3), egui::Stroke::new(1.5, theme::PRIMARY), egui::StrokeKind::Inside);
        }
        let name = if d.name.is_empty() { d.address.clone() } else { d.name.clone() };
        let short = name.split('-').next().unwrap_or(&name).to_string();
        p.text(screen.center(), egui::Align2::CENTER_CENTER, short, egui::FontId::proportional(10.0), theme::TEXT_MUTED);
        p.text(egui::pos2(tr.center().x, tr.bottom() + 12.0), egui::Align2::CENTER_CENTER, format!("Slot {i}"), egui::FontId::proportional(10.0), theme::TEXT_MUTED);
    }
}

fn card(ui: &mut egui::Ui, add: impl FnOnce(&mut egui::Ui)) {
    egui::Frame::NONE
        .fill(theme::CARD_BG)
        .corner_radius(egui::CornerRadius::same(theme::RADIUS as u8))
        .stroke(egui::Stroke::new(1.0, theme::BORDER))
        .inner_margin(egui::Margin::same(14))
        .show(ui, |ui| {
            ui.set_width(ui.available_width());
            add(ui);
        });
}

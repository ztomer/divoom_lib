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
                app.daemon.send(crate::daemon::Cmd::Scan);
            }
            return;
        }
        // Slot list: each discovered device gets a slot index (its position).
        for (i, d) in app.devices.iter().enumerate() {
            ui.horizontal(|ui| {
                ui.label(RichText::new(format!("Slot {i}")).size(12.0).color(theme::TEXT_MUTED));
                let name = if d.name.is_empty() { d.address.clone() } else { d.name.clone() };
                ui.label(RichText::new(name).size(12.5).color(theme::TEXT_MAIN));
            });
        }
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

fn card(ui: &mut egui::Ui, add: impl FnOnce(&mut egui::Ui)) {
    egui::Frame::none()
        .fill(theme::CARD_BG)
        .rounding(egui::Rounding::same(theme::RADIUS))
        .stroke(egui::Stroke::new(1.0, theme::BORDER))
        .inner_margin(egui::Margin::same(14.0))
        .show(ui, |ui| {
            ui.set_width(ui.available_width());
            add(ui);
        });
}

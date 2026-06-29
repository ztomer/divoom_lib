//! Device Settings tab — reproduced from `web_ui/templates_device_settings.js`.
//! Each control maps to the device_call leaf the Python `ToolsApi` uses (verified
//! against the Rust daemon dispatch + positional-arg convention):
//!   device name   → device.set_device_name [name]
//!   clock format  → system.set_hour_type   [0|1]   (12h=0, 24h=1)
//!   temperature   → device.set_temp_type   [0|1]   (C=0, F=1)
//!   power mode    → device.set_low_power_switch [0|1]
//!   auto power-off→ device.set_auto_power_off [minutes]
//!   orientation   → design.set_screen_dir  [0..3]
//!   mirror/flip   → design.set_screen_mirror [bool]
//!   factory reset → design.factory_reset
//! `sync_time` (Update device time) is a daemon gap (Python uses DateTimeCommand
//! directly, not a device_call leaf) → the button is disabled with a note.

use eframe::egui::{self, RichText};
use serde_json::json;

use crate::app::DivoomApp;
use crate::theme;

pub fn panel(app: &mut DivoomApp, ui: &mut egui::Ui) {
    egui::ScrollArea::vertical().show(ui, |ui| {
        card(ui, |ui| {
            // Device name.
            row(ui, "Device name", |ui| {
                ui.add(
                    egui::TextEdit::singleline(&mut app.device_name)
                        .hint_text("Read from device…")
                        .desired_width(150.0),
                );
                if ui.button("Save").clicked() && !app.device_name.is_empty() {
                    app.call("device.set_device_name", json!([app.device_name]));
                }
            });
            sep(ui);

            // Clock format.
            row(ui, "Clock format", |ui| {
                if seg(ui, app.hour24, "12-hour", "24-hour") != app.hour24 {
                    app.hour24 = !app.hour24;
                    app.call("system.set_hour_type", json!([app.hour24 as i64]));
                }
            });
            sep(ui);

            // Temperature unit.
            row(ui, "Temperature", |ui| {
                if seg(ui, app.temp_f, "Celsius", "Fahrenheit") != app.temp_f {
                    app.temp_f = !app.temp_f;
                    app.call("device.set_temp_type", json!([app.temp_f as i64]));
                }
            });
            sep(ui);

            // Power mode.
            row(ui, "Power mode", |ui| {
                if seg(ui, app.low_power, "Normal", "Low power") != app.low_power {
                    app.low_power = !app.low_power;
                    app.call("device.set_low_power_switch", json!([app.low_power as i64]));
                }
            });
            sep(ui);

            // Auto power-off.
            row(ui, "Auto power-off (min, 0=off)", |ui| {
                let r = ui.add(egui::DragValue::new(&mut app.auto_off_min).range(0..=240));
                if (r.drag_stopped() || r.lost_focus()) && r.changed() {
                    app.call("device.set_auto_power_off", json!([app.auto_off_min]));
                }
                if ui.button("Save").clicked() {
                    app.call("device.set_auto_power_off", json!([app.auto_off_min]));
                }
            });
            sep(ui);

            // Orientation.
            row(ui, "Orientation", |ui| {
                // right_to_left layout → iterate reversed so it reads 0°→270°.
                for (val, label) in [(3, "270°"), (2, "180°"), (1, "90°"), (0, "0°")] {
                    if ui.selectable_label(app.screen_dir == val, label).clicked() {
                        app.screen_dir = val;
                        app.call("design.set_screen_dir", json!([val]));
                    }
                }
            });
            sep(ui);

            // Mirror / flip.
            row(ui, "Mirror / flip display", |ui| {
                if ui.checkbox(&mut app.screen_mirror, "").changed() {
                    app.call("design.set_screen_mirror", json!([app.screen_mirror]));
                }
            });
            sep(ui);

            // FM radio frequency → radio.set_radio_frequency [freq_x10].
            row(ui, "FM radio (MHz)", |ui| {
                if ui.button("Tune").clicked() {
                    let x10 = (app.fm_freq * 10.0).round() as i64;
                    app.call("radio.set_radio_frequency", json!([x10]));
                }
                ui.add(egui::DragValue::new(&mut app.fm_freq).range(76.0..=108.0).speed(0.1).fixed_decimals(1));
            });
            sep(ui);

            // Sync the device clock to this machine's local time → set_date_time
            // (ported DateTimeCommand: cmd 0x18). Daemon gap closed.
            if ui.button("Update device time").clicked() {
                use chrono::{Datelike, Timelike};
                let now = chrono::Local::now();
                app.call(
                    "set_date_time",
                    json!([now.year(), now.month(), now.day(), now.hour(), now.minute(), now.second()]),
                );
            }
        });

        ui.add_space(12.0);

        // Danger zone.
        danger_card(ui, |ui| {
            ui.label(RichText::new("Danger zone").size(15.0).color(theme::ERROR).strong());
            ui.add_space(6.0);
            ui.label(
                RichText::new("Factory reset wipes the device's stored configuration. This cannot be undone.")
                    .size(12.0)
                    .color(theme::TEXT_MUTED),
            );
            ui.add_space(8.0);
            ui.checkbox(&mut app.confirm_reset, "I understand — confirm factory reset");
            ui.add_space(6.0);
            if ui
                .add_enabled(app.confirm_reset, egui::Button::new(RichText::new("Factory reset device").color(theme::ERROR)))
                .clicked()
            {
                app.call("design.factory_reset", json!([]));
                app.confirm_reset = false;
            }
        });
    });
}

// --- layout helpers ----------------------------------------------------------

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

fn danger_card(ui: &mut egui::Ui, add: impl FnOnce(&mut egui::Ui)) {
    egui::Frame::none()
        .fill(theme::CARD_BG)
        .rounding(egui::Rounding::same(theme::RADIUS))
        .stroke(egui::Stroke::new(1.0, theme::ERROR.linear_multiply(0.6)))
        .inner_margin(egui::Margin::same(14.0))
        .show(ui, |ui| {
            ui.set_width(ui.available_width());
            add(ui);
        });
}

/// A label on the left, controls pushed to the right (the web `.ds-row` shape).
fn row(ui: &mut egui::Ui, label: &str, controls: impl FnOnce(&mut egui::Ui)) {
    ui.horizontal(|ui| {
        ui.label(RichText::new(label).size(12.5).color(theme::TEXT_MAIN));
        ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), controls);
    });
}

fn sep(ui: &mut egui::Ui) {
    ui.add_space(6.0);
    ui.separator();
    ui.add_space(6.0);
}

/// Two-segment pill; returns which side is selected (`false`=left, `true`=right).
fn seg(ui: &mut egui::Ui, right_selected: bool, left: &str, right: &str) -> bool {
    // Rendered right-to-left (inside a right_to_left layout): draw right first.
    let mut sel = right_selected;
    if ui.selectable_label(right_selected, right).clicked() {
        sel = true;
    }
    if ui.selectable_label(!right_selected, left).clicked() {
        sel = false;
    }
    sel
}

//! Schedule tab — alarm slots. Mirrors `tools.set_alarm(index, enabled, hour,
//! minute, week, mode, trigger_mode)` → device_call leaf `alarm.set_alarm`
//! (positional args, verified vs the Rust dispatch). `week` is a 7-bit day mask
//! (bit0=Mon … bit6=Sun). Reading current alarms (`alarm.get_alarm_time`) is a
//! later refinement; this is the editor + push.

use eframe::egui::{self, RichText};
use serde_json::json;

use crate::app::DivoomApp;
use crate::theme;

const DAYS: [&str; 7] = ["M", "T", "W", "T", "F", "S", "S"];

pub fn panel(app: &mut DivoomApp, ui: &mut egui::Ui) {
    // Read the device's current alarms once (status idle->active also resets this).
    if !app.alarms_fetched && app.active_mac().is_some() {
        app.alarms_fetched = true;
        app.raw("device_call", json!({ "method": "alarm.get_alarm_time", "args": [] }), "rb_alarms");
    }
    egui::ScrollArea::vertical().show(ui, |ui| {
        ui.label(
            RichText::new("Set up to 5 device alarms. Each pushes immediately on Save.")
                .size(12.0)
                .color(theme::TEXT_MUTED),
        );
        ui.add_space(10.0);
        for i in 0..app.alarms.len() {
            alarm_row(app, ui, i);
            ui.add_space(8.0);
        }
        ui.add_space(8.0);
        memorial(app, ui);
    });
}

/// Memorial countdown → alarm.set_memorial_time [dialy_id, on_off, month, day, hour, minute, title].
fn memorial(app: &mut DivoomApp, ui: &mut egui::Ui) {
    egui::Frame::none()
        .fill(theme::CARD_BG)
        .rounding(egui::Rounding::same(theme::RADIUS))
        .stroke(egui::Stroke::new(1.0, theme::BORDER))
        .inner_margin(egui::Margin::same(12.0))
        .show(ui, |ui| {
            ui.set_width(ui.available_width());
            ui.label(RichText::new("Memorial Countdown").size(13.5).color(theme::TEXT_MAIN).strong());
            ui.add_space(6.0);
            ui.horizontal(|ui| {
                ui.checkbox(&mut app.mem_enabled, "On");
                ui.add(egui::DragValue::new(&mut app.mem_month).range(1..=12).prefix("M "));
                ui.add(egui::DragValue::new(&mut app.mem_day).range(1..=31).prefix("D "));
                ui.add(egui::DragValue::new(&mut app.mem_hour).range(0..=23).prefix("h "));
                ui.add(egui::DragValue::new(&mut app.mem_minute).range(0..=59).prefix("m "));
            });
            ui.add_space(6.0);
            ui.horizontal(|ui| {
                ui.add(egui::TextEdit::singleline(&mut app.mem_title).hint_text("Title").desired_width(180.0));
                if ui.button("Save").clicked() {
                    app.call(
                        "alarm.set_memorial_time",
                        json!([0, app.mem_enabled as i64, app.mem_month, app.mem_day, app.mem_hour, app.mem_minute, app.mem_title]),
                    );
                }
            });
        });
}

fn alarm_row(app: &mut DivoomApp, ui: &mut egui::Ui, idx: usize) {
    egui::Frame::none()
        .fill(theme::CARD_BG)
        .rounding(egui::Rounding::same(theme::RADIUS))
        .stroke(egui::Stroke::new(1.0, theme::BORDER))
        .inner_margin(egui::Margin::same(12.0))
        .show(ui, |ui| {
            ui.set_width(ui.available_width());
            ui.horizontal(|ui| {
                ui.label(RichText::new(format!("Alarm {}", idx + 1)).size(12.5).color(theme::TEXT_MAIN));
                ui.checkbox(&mut app.alarms[idx].enabled, "On");
                ui.add_space(8.0);
                ui.add(egui::DragValue::new(&mut app.alarms[idx].hour).range(0..=23).custom_formatter(|n, _| format!("{:02}", n as i64)));
                ui.label(":");
                ui.add(egui::DragValue::new(&mut app.alarms[idx].minute).range(0..=59).custom_formatter(|n, _| format!("{:02}", n as i64)));
                ui.add_space(12.0);
                // Weekday mask toggles (bit0=Mon).
                for (d, label) in DAYS.iter().enumerate() {
                    let bit = 1u8 << d;
                    let mut on = app.alarms[idx].week & bit != 0;
                    if ui.selectable_label(on, *label).clicked() {
                        on = !on;
                        if on {
                            app.alarms[idx].week |= bit;
                        } else {
                            app.alarms[idx].week &= !bit;
                        }
                    }
                }
                ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                    if ui.button("Save").clicked() {
                        let a = app.alarms[idx].clone();
                        // alarm.set_alarm(index, status, hour, minute, week, mode=0, trigger_mode=0)
                        app.call(
                            "alarm.set_alarm",
                            json!([idx, a.enabled as i64, a.hour, a.minute, a.week as i64, 0, 0]),
                        );
                    }
                });
            });
        });
}

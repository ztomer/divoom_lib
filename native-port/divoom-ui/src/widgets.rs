//! Live Widgets tab (web `data-sources`) — LIVE DATA FEEDS, not the gallery.
//! Mirrors `MediaSyncMixin`: each toggle starts/stops a server-side push job via
//! the daemon's `live_job_start(mac, kind, params)` / `live_job_stop(mac, kind)`
//! (kinds music/stocks/sysmon/weather — verified in divoomd/src/live_jobs). The
//! daemon owns the recurring render+push; the UI just toggles.

use eframe::egui::{self, RichText};
use serde_json::json;

use crate::app::DivoomApp;
use crate::theme;

pub fn panel(app: &mut DivoomApp, ui: &mut egui::Ui) {
    // Lazily read which jobs the daemon reports running (status, read-only — does
    // not drive the toggles, to avoid fighting user input).
    if let Some(mac) = app.active_mac() {
        if !app.replies.contains_key("live_jobs") {
            app.raw("live_job_list", json!({ "mac": mac }), "live_jobs");
        }
    }
    egui::ScrollArea::vertical().show(ui, |ui| {
        if app.active_mac().is_none() {
            ui.colored_label(theme::WARN, "Connect a device to start live widgets.");
            ui.add_space(10.0);
        }
        running_status(app, ui);
        feed(app, ui, "Now Playing", "Album art from Music / Spotify.", "music", |a| a.music_sync, |a, v| a.music_sync = v, json!({}));
        feed(app, ui, "System Stats", "CPU / RAM gauges on the device.", "sysmon", |a| a.sysmon_sync, |a, v| a.sysmon_sync = v, json!({}));
        feed(app, ui, "Weather", "Live local weather.", "weather", |a| a.weather_sync, |a, v| a.weather_sync = v, json!({}));
        stocks(app, ui);
        temperature(app, ui);
    });
}

/// One-shot: show the temperature channel on the device (color + unit).
fn temperature(app: &mut DivoomApp, ui: &mut egui::Ui) {
    card(ui, |ui| {
        ui.label(RichText::new("Temperature Channel").size(14.0).color(theme::TEXT_MAIN).strong());
        ui.label(RichText::new("Switch the device to its temperature display.").size(11.0).color(theme::TEXT_MUTED));
        ui.add_space(6.0);
        ui.horizontal(|ui| {
            if ui.selectable_label(app.temp_celsius, "°C").clicked() { app.temp_celsius = true; }
            if ui.selectable_label(!app.temp_celsius, "°F").clicked() { app.temp_celsius = false; }
            ui.label(RichText::new("Color").size(11.0).color(theme::TEXT_MUTED));
            ui.color_edit_button_srgb(&mut app.temp_color);
            if ui.button("Show on device").clicked() {
                app.call_kw("display.set_temperature_channel", json!({
                    "celsius": app.temp_celsius,
                    "color": DivoomApp::hex(app.temp_color),
                }));
            }
        });
    });
    ui.add_space(8.0);
}

#[allow(clippy::too_many_arguments)]
fn feed(
    app: &mut DivoomApp,
    ui: &mut egui::Ui,
    title: &str,
    desc: &str,
    kind: &str,
    get: fn(&DivoomApp) -> bool,
    set: fn(&mut DivoomApp, bool),
    params: serde_json::Value,
) {
    card(ui, |ui| {
        ui.horizontal(|ui| {
            ui.vertical(|ui| {
                ui.label(RichText::new(title).size(14.0).color(theme::TEXT_MAIN).strong());
                ui.label(RichText::new(desc).size(11.0).color(theme::TEXT_MUTED));
            });
            ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                let mut on = get(app);
                let enabled = app.active_mac().is_some();
                let r = ui.add_enabled_ui(enabled, |ui| crate::ui_widgets::toggle(ui, &mut on)).inner;
                if r.changed() {
                    set(app, on);
                    app.toggle_live_job(kind, on, params.clone());
                }
            });
        });
    });
    ui.add_space(8.0);
}

fn stocks(app: &mut DivoomApp, ui: &mut egui::Ui) {
    card(ui, |ui| {
        ui.label(RichText::new("Stocks Ticker").size(14.0).color(theme::TEXT_MAIN).strong());
        ui.label(RichText::new("Scrolling price for a symbol.").size(11.0).color(theme::TEXT_MUTED));
        ui.add_space(6.0);
        ui.horizontal(|ui| {
            ui.label(RichText::new("Symbol").size(11.0).color(theme::TEXT_MUTED));
            ui.add(egui::TextEdit::singleline(&mut app.stocks_symbol).hint_text("AAPL").desired_width(90.0));
            let mut on = app.stocks_sync;
            let can = app.active_mac().is_some() && !app.stocks_symbol.trim().is_empty();
            let r = ui.add_enabled_ui(can || app.stocks_sync, |ui| crate::ui_widgets::toggle(ui, &mut on)).inner;
            ui.label(RichText::new("Sync").size(11.0).color(theme::TEXT_MUTED));
            if r.changed() {
                app.stocks_sync = on;
                let sym = app.stocks_symbol.trim().to_uppercase();
                app.toggle_live_job("stocks", on, json!({ "symbol": sym }));
            }
        });
    });
    ui.add_space(8.0);
}

/// Read-only "what's running" line from live_job_list, with a refresh.
fn running_status(app: &mut DivoomApp, ui: &mut egui::Ui) {
    let running: Vec<String> = app
        .replies
        .get("live_jobs")
        .and_then(|v| v.get("jobs"))
        .and_then(|j| j.as_array())
        .map(|a| {
            a.iter()
                .filter_map(|j| j.get("kind").and_then(|k| k.as_str()))
                .filter(|k| *k != "idle")
                .map(String::from)
                .collect()
        })
        .unwrap_or_default();
    ui.horizontal(|ui| {
        let txt = if running.is_empty() {
            "Running: none".to_string()
        } else {
            format!("Running: {}", running.join(", "))
        };
        ui.label(RichText::new(txt).size(11.0).color(theme::TEXT_MUTED));
        if ui.small_button("Refresh").clicked() {
            if let Some(mac) = app.active_mac() {
                app.raw("live_job_list", json!({ "mac": mac }), "live_jobs");
            }
        }
    });
    ui.add_space(8.0);
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

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
    egui::ScrollArea::vertical().show(ui, |ui| {
        if app.active_mac().is_none() {
            ui.colored_label(theme::WARN, "Connect a device to start live widgets.");
            ui.add_space(10.0);
        }
        feed(app, ui, "Now Playing", "Album art from Music / Spotify.", "music", |a| a.music_sync, |a, v| a.music_sync = v, json!({}));
        feed(app, ui, "System Stats", "CPU / RAM gauges on the device.", "sysmon", |a| a.sysmon_sync, |a, v| a.sysmon_sync = v, json!({}));
        feed(app, ui, "Weather", "Live local weather.", "weather", |a| a.weather_sync, |a, v| a.weather_sync = v, json!({}));
        stocks(app, ui);
    });
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
                if ui.add_enabled(app.active_mac().is_some(), egui::Checkbox::new(&mut on, "")).changed() {
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
            if ui.add_enabled(can || app.stocks_sync, egui::Checkbox::new(&mut on, "Sync")).changed() {
                app.stocks_sync = on;
                let sym = app.stocks_symbol.trim().to_uppercase();
                app.toggle_live_job("stocks", on, json!({ "symbol": sym }));
            }
        });
    });
    ui.add_space(8.0);
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

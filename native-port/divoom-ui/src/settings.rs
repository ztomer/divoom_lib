//! Settings tab — app/daemon-level controls (reached via the appbar gear).
//! These are top-level daemon RPCs (not device_call), routed through `Cmd::Raw`:
//!   notifications → start_notifications / stop_notifications / notification_status
//!   LAN          → probe_lan (+ connect with lan_ip)
//! keep-daemon-alive is app-local (Python uses divoom_lib.lifecycle_config; a
//! persisted config is a later polish). MCP server is a subprocess (GUI-local in
//! Python) → deferred with a note.

use eframe::egui::{self, RichText};
use serde_json::json;

use crate::app::DivoomApp;
use crate::theme;

pub fn panel(app: &mut DivoomApp, ui: &mut egui::Ui) {
    // Lazy-fetch notification status on first visit.
    if !app.replies.contains_key("notif_status") {
        app.raw("notification_status", json!({}), "notif_status");
    }
    egui::ScrollArea::vertical().show(ui, |ui| {
        notifications_card(app, ui);
        ui.add_space(12.0);
        lan_card(app, ui);
        ui.add_space(12.0);
        app_card(app, ui);
    });
}

fn notifications_card(app: &mut DivoomApp, ui: &mut egui::Ui) {
    card(ui, "Notification mirroring", |ui| {
        let running = app
            .replies
            .get("notif_status")
            .and_then(|v| v.get("running").and_then(|r| r.as_bool()).or_else(|| {
                v.get("state").and_then(|s| s.as_str()).map(|s| s == "running")
            }))
            .unwrap_or(false);
        ui.horizontal(|ui| {
            dot(ui, if running { theme::ACCENT } else { theme::TEXT_MUTED });
            ui.label(
                RichText::new(if running { "Listener running" } else { "Listener stopped" })
                    .size(12.0)
                    .color(theme::TEXT_MUTED),
            );
        });
        ui.add_space(8.0);
        ui.horizontal(|ui| {
            if ui.add_enabled(!running, egui::Button::new("Start")).clicked() {
                app.raw("start_notifications", json!({}), "notif_status");
            }
            if ui.add_enabled(running, egui::Button::new("Stop")).clicked() {
                app.raw("stop_notifications", json!({}), "notif_status");
            }
            if ui.button("Refresh").clicked() {
                app.raw("notification_status", json!({}), "notif_status");
            }
        });
    });
}

fn lan_card(app: &mut DivoomApp, ui: &mut egui::Ui) {
    card(ui, "LAN device (Wi-Fi)", |ui| {
        ui.horizontal(|ui| {
            ui.label(RichText::new("IP").size(12.0).color(theme::TEXT_MUTED));
            ui.add(egui::TextEdit::singleline(&mut app.lan_ip).hint_text("192.168.x.x").desired_width(140.0));
            ui.label(RichText::new("Token").size(12.0).color(theme::TEXT_MUTED));
            ui.add(egui::TextEdit::singleline(&mut app.lan_token).hint_text("0").desired_width(80.0));
        });
        ui.add_space(8.0);
        ui.horizontal(|ui| {
            if ui.button("Probe").clicked() {
                app.raw("probe_lan", json!({}), "lan_probe");
            }
            if ui.add_enabled(!app.lan_ip.is_empty(), egui::Button::new("Connect")).clicked() {
                let token: i64 = app.lan_token.trim().parse().unwrap_or(0);
                app.raw("connect", json!({ "lan_ip": app.lan_ip, "token": token }), "lan_connect");
            }
        });
        if let Some(v) = app.replies.get("lan_probe") {
            let reachable = v.get("reachable").and_then(|r| r.as_bool()).unwrap_or(false);
            let detail = v.get("detail").and_then(|d| d.as_str()).unwrap_or("");
            ui.add_space(6.0);
            ui.colored_label(
                if reachable { theme::ACCENT } else { theme::WARN },
                if reachable { "Reachable".to_string() } else { format!("Not reachable {detail}") },
            );
        }
    });
}

fn app_card(app: &mut DivoomApp, ui: &mut egui::Ui) {
    card(ui, "Application", |ui| {
        ui.checkbox(&mut app.keep_alive, "Keep the daemon running after closing this window");
        ui.add_space(6.0);
        ui.add_enabled(false, egui::Button::new("MCP server (subprocess — Phase 4)"))
            .on_disabled_hover_text("The MCP stdio server runs as a separate process; wiring it is Phase 4.");
        ui.add_space(8.0);
        ui.label(
            RichText::new("divoom-ui (native) — talks to divoomd over the local socket.")
                .size(11.0)
                .color(theme::TEXT_MUTED),
        );
    });
}

// --- helpers -----------------------------------------------------------------

fn card(ui: &mut egui::Ui, title: &str, add: impl FnOnce(&mut egui::Ui)) {
    egui::Frame::none()
        .fill(theme::CARD_BG)
        .rounding(egui::Rounding::same(theme::RADIUS))
        .stroke(egui::Stroke::new(1.0, theme::BORDER))
        .inner_margin(egui::Margin::same(14.0))
        .show(ui, |ui| {
            ui.set_width(ui.available_width());
            ui.label(RichText::new(title).size(14.0).color(theme::TEXT_MAIN).strong());
            ui.add_space(8.0);
            add(ui);
        });
}

fn dot(ui: &mut egui::Ui, color: egui::Color32) {
    let (r, _) = ui.allocate_exact_size(egui::Vec2::splat(8.0), egui::Sense::hover());
    ui.painter().circle_filled(r.center(), 4.0, color);
}

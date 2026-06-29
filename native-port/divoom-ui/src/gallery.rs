//! Cloud gallery — lives UNDER the Pixel Art tab (web TAB 4 = "Custom Art +
//! Gallery + Hot Channel"), not as its own tab. `fetch_gallery{classify,limit,
//! file_sort}` returns the cloud API's file list. Thumbnails are remote URLs that
//! need the user's Divoom account (cloud auth) + an HTTP image fetch; rendering +
//! apply is a later refinement (depends on cloud credentials).

use eframe::egui::{self, RichText};
use serde_json::json;

use crate::app::DivoomApp;
use crate::theme;

const CATEGORIES: [(i64, &str); 3] = [(0, "Monthly Best"), (12, "Featured"), (16, "Recommend")];

pub fn panel(app: &mut DivoomApp, ui: &mut egui::Ui) {
    ui.horizontal(|ui| {
        ui.label(RichText::new("Category").size(12.0).color(theme::TEXT_MUTED));
        for (classify, name) in CATEGORIES {
            if ui.button(name).clicked() {
                app.raw(
                    "fetch_gallery",
                    json!({ "classify": classify, "limit": 30, "file_sort": 1 }),
                    "gallery",
                );
            }
        }
    });
    ui.add_space(10.0);
    match app.replies.get("gallery") {
        None => {
            ui.label(RichText::new("Pick a category to load the cloud gallery.").size(12.0).color(theme::TEXT_MUTED));
        }
        Some(v) if v.get("success").and_then(|s| s.as_bool()) == Some(true) => {
            let count = v
                .get("result")
                .and_then(|r| r.get("FileList").or_else(|| r.as_array().map(|_| r)))
                .and_then(|f| f.as_array())
                .map(|a| a.len())
                .unwrap_or(0);
            ui.colored_label(theme::ACCENT, format!("Loaded {count} gallery items."));
            ui.add_space(4.0);
            ui.label(
                RichText::new("Thumbnail render + tap-to-push need cloud auth + a remote image fetch — follow-up.")
                    .size(11.0)
                    .color(theme::TEXT_MUTED),
            );
        }
        Some(v) => {
            let err = v.get("error").and_then(|e| e.as_str()).unwrap_or("unknown error");
            ui.colored_label(theme::WARN, format!("Gallery unavailable: {err}"));
            ui.add_space(4.0);
            ui.label(
                RichText::new("Usually means Divoom cloud credentials aren't configured yet.")
                    .size(11.0)
                    .color(theme::TEXT_MUTED),
            );
        }
    }
}

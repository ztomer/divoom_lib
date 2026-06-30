//! Cloud gallery — lives UNDER the Pixel Art tab (web TAB 4 = "Custom Art +
//! Gallery + Hot Channel"). `fetch_gallery{classify,limit,file_sort}` returns the
//! cloud file list; each item's thumbnail is lazily decoded by the daemon
//! (`get_animated_preview{file_id}` → base64 data-url, reusing the cloud decoder)
//! and rendered here. Clicking a tile pushes it to the device via `sync_artwork`.
//! Needs the user's Divoom cloud login (Settings) for a non-empty list.

use eframe::egui::{self, Color32, RichText, Sense, Stroke, Vec2};
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

    let reply = app.replies.get("gallery").cloned();
    match reply {
        None => {
            hint(ui, "Pick a category to load the cloud gallery.");
        }
        Some(v) if v.get("success").and_then(|s| s.as_bool()) == Some(true) => {
            // FileList may be nested under `result` or be the result array itself.
            let items: Vec<serde_json::Value> = v
                .get("result")
                .and_then(|r| r.get("FileList").or(Some(r)))
                .and_then(|f| f.as_array())
                .cloned()
                .unwrap_or_default();
            if items.is_empty() {
                hint(ui, "No gallery items returned for this category.");
            } else {
                ui.label(
                    RichText::new(format!("{} items — click a tile to push to the device.", items.len()))
                        .size(11.0)
                        .color(theme::TEXT_MUTED),
                );
                ui.add_space(6.0);
                egui::ScrollArea::vertical().show(ui, |ui| grid(app, ui, &items));
            }
        }
        Some(v) => {
            let err = v.get("error").and_then(|e| e.as_str()).unwrap_or("unknown error");
            ui.colored_label(theme::WARN, format!("Gallery unavailable: {err}"));
            ui.add_space(4.0);
            hint(ui, "Usually means Divoom cloud credentials aren't configured yet (see Settings).");
        }
    }
}

fn grid(app: &mut DivoomApp, ui: &mut egui::Ui, items: &[serde_json::Value]) {
    let ctx = ui.ctx().clone();
    let cell = Vec2::new(96.0, 116.0);
    let per_row = ((ui.available_width() + 8.0) / (cell.x + 8.0)).floor().max(1.0) as usize;
    egui::Grid::new("gallerygrid").spacing(Vec2::new(8.0, 8.0)).show(ui, |ui| {
        for (i, it) in items.iter().enumerate() {
            let Some(file_id) = it.get("FileId").and_then(|v| v.as_str()) else { continue };
            let name = it.get("FileName").and_then(|v| v.as_str()).unwrap_or("");
            let likes = it.get("LikeCnt").and_then(|v| v.as_i64()).unwrap_or(0);
            tile(app, &ctx, ui, cell, file_id, name, likes);
            if (i + 1) % per_row == 0 {
                ui.end_row();
            }
        }
    });
}

fn tile(
    app: &mut DivoomApp,
    ctx: &egui::Context,
    ui: &mut egui::Ui,
    cell: Vec2,
    file_id: &str,
    name: &str,
    likes: i64,
) {
    let (rect, resp) = ui.allocate_exact_size(cell, Sense::click());
    let stroke = if resp.hovered() {
        Stroke::new(1.5, theme::PRIMARY)
    } else {
        Stroke::new(1.0, theme::BORDER)
    };
    ui.painter().rect(rect, egui::CornerRadius::same(theme::RADIUS as u8), theme::CARD_BG, stroke, egui::StrokeKind::Inside);

    // Thumbnail box (top), lazily filled by the daemon's decoded preview.
    let img = egui::Rect::from_min_size(rect.left_top() + Vec2::new((cell.x - 76.0) / 2.0, 8.0), Vec2::splat(76.0));
    ui.painter().rect_filled(img, egui::CornerRadius::same(4), theme::BG_BASE);
    let tag = format!("gp:{file_id}");
    let data_url = app
        .replies
        .get(&tag)
        .and_then(|r| r.get("preview"))
        .and_then(|p| p.as_str())
        .map(|s| s.to_string());
    if let Some(url) = data_url {
        if let Some(tex) = app.gallery_texture(ctx, file_id, &url) {
            let uv = egui::Rect::from_min_max(egui::pos2(0.0, 0.0), egui::pos2(1.0, 1.0));
            ui.painter().image(tex.id(), img, uv, Color32::WHITE);
        }
    } else if app.gallery_requested.insert(file_id.to_string()) {
        // First sighting → fire the one-shot decode request.
        app.raw("get_animated_preview", json!({ "file_id": file_id }), &tag);
    }

    // Name (truncated) + like count.
    ui.painter().text(
        egui::pos2(rect.center().x, rect.top() + 92.0),
        egui::Align2::CENTER_CENTER,
        truncate(name, 14),
        egui::FontId::proportional(10.0),
        theme::TEXT_MAIN,
    );
    ui.painter().text(
        egui::pos2(rect.center().x, rect.top() + 104.0),
        egui::Align2::CENTER_CENTER,
        format!("{likes} likes"),
        egui::FontId::proportional(9.5),
        theme::TEXT_MUTED,
    );

    if resp.clicked() {
        app.raw(
            "sync_artwork",
            json!({ "file_id": file_id, "default_size": 16, "target": "device" }),
            "gallery_apply",
        );
    }
    resp.on_hover_text(name);
}

fn truncate(s: &str, max: usize) -> String {
    if s.chars().count() <= max {
        s.to_string()
    } else {
        format!("{}…", s.chars().take(max - 1).collect::<String>())
    }
}

fn hint(ui: &mut egui::Ui, text: &str) {
    ui.label(RichText::new(text).size(12.0).color(theme::TEXT_MUTED));
}

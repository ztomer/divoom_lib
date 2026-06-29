//! Pixel Art tab — a 16x16 paintable editor. Mirrors `web_ui` custom-art: paint
//! cells, then push the frame to the device. Push routes through `show_image`
//! with `rgb` kwargs (w·h·3 bytes), the same leaf the daemon encodes + streams.

use eframe::egui::{self, Color32, RichText, Sense, Stroke, Vec2};
use serde_json::json;

use crate::app::DivoomApp;
use crate::theme;

const GRID: usize = 16;

pub fn panel(app: &mut DivoomApp, ui: &mut egui::Ui) {
    ui.horizontal(|ui| {
        ui.label(RichText::new("Color").size(12.0).color(theme::TEXT_MUTED));
        ui.color_edit_button_srgb(&mut app.paint_color);
        ui.add_space(12.0);
        if ui.button("Clear").clicked() {
            for p in app.pixels.iter_mut() {
                *p = [0, 0, 0];
            }
        }
        if ui.button("Fill").clicked() {
            for p in app.pixels.iter_mut() {
                *p = app.paint_color;
            }
        }
        ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
            if ui.button("Push to Device").clicked() {
                push(app);
            }
        });
    });
    ui.add_space(10.0);
    canvas(app, ui);
    ui.add_space(8.0);
    ui.label(
        RichText::new("Click or drag to paint. 16x16 — pushed via show_image.")
            .size(11.0)
            .color(theme::TEXT_MUTED),
    );
}

fn canvas(app: &mut DivoomApp, ui: &mut egui::Ui) {
    let cell = 24.0;
    let size = Vec2::splat(cell * GRID as f32);
    let (rect, resp) = ui.allocate_exact_size(size, Sense::click_and_drag());
    let painter = ui.painter_at(rect);

    // Paint on press/drag: map pointer → cell.
    if resp.is_pointer_button_down_on() || resp.dragged() {
        if let Some(pos) = resp.interact_pointer_pos() {
            let col = ((pos.x - rect.left()) / cell).floor() as i64;
            let row = ((pos.y - rect.top()) / cell).floor() as i64;
            if (0..GRID as i64).contains(&col) && (0..GRID as i64).contains(&row) {
                app.pixels[row as usize * GRID + col as usize] = app.paint_color;
            }
        }
    }

    for r in 0..GRID {
        for c in 0..GRID {
            let p = app.pixels[r * GRID + c];
            let min = rect.left_top() + Vec2::new(c as f32 * cell, r as f32 * cell);
            let cr = egui::Rect::from_min_size(min, Vec2::splat(cell));
            painter.rect(
                cr,
                egui::Rounding::ZERO,
                Color32::from_rgb(p[0], p[1], p[2]),
                Stroke::new(0.5, theme::BORDER),
            );
        }
    }
    painter.rect_stroke(rect, egui::Rounding::ZERO, Stroke::new(1.0, theme::BORDER));
}

fn push(app: &DivoomApp) {
    let rgb: Vec<u8> = app.pixels.iter().flat_map(|p| [p[0], p[1], p[2]]).collect();
    app.raw(
        "device_call",
        json!({
            "method": "show_image",
            "args": [],
            "kwargs": { "w": GRID, "h": GRID, "time_ms": 100, "rgb": rgb }
        }),
        "pixel_push",
    );
}

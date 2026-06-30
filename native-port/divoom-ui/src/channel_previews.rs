//! Painted/image preview grids for the Channels tab (clock faces, ambient modes,
//! VJ/EQ thumbnails) + the color swatch. Split out of `channels.rs` to keep it
//! under the 500-line house limit.

use eframe::egui::{self, Color32, Margin, RichText, CornerRadius, Stroke, Vec2};

use crate::theme;

/// Ambient mode grid: each cell paints the mode's representative look (web
/// AMBIENT_PREVIEWS); Plain Color shows the chosen color.
pub fn ambient_grid(ui: &mut egui::Ui, labels: &[&str], selected: i64, plain: [u8; 3]) -> Option<i64> {
    let mut clicked = None;
    let cell = Vec2::new(100.0, 80.0);
    let per_row = ((ui.available_width() + 8.0) / (cell.x + 8.0)).floor().max(1.0) as usize;
    egui::Grid::new("ambgrid").spacing(Vec2::new(8.0, 8.0)).show(ui, |ui| {
        for (i, label) in labels.iter().enumerate() {
            let sel = selected == i as i64;
            let (rect, resp) = ui.allocate_exact_size(cell, egui::Sense::click());
            let stroke = sel_stroke(sel, resp.hovered());
            ui.painter().rect(rect, CornerRadius::same(theme::RADIUS as u8), theme::CARD_BG, stroke, egui::StrokeKind::Inside);
            let pv = egui::Rect::from_min_size(rect.left_top() + Vec2::new(8.0, 8.0), Vec2::new(cell.x - 16.0, 46.0));
            paint_ambient_preview(ui.painter(), pv, i as i64, plain);
            cell_label(ui, rect, label, sel);
            if resp.clicked() {
                clicked = Some(i as i64);
            }
            if (i + 1) % per_row == 0 {
                ui.end_row();
            }
        }
    });
    clicked
}

fn paint_ambient_preview(p: &egui::Painter, r: egui::Rect, mode: i64, plain: [u8; 3]) {
    let rnd = CornerRadius::same(4);
    match mode {
        0 => { p.rect_filled(r, rnd, Color32::from_rgb(plain[0], plain[1], plain[2])); }
        1 => { p.rect_filled(r, rnd, Color32::from_rgb(0xff, 0x3d, 0x9a)); }
        2 => {
            p.rect_filled(r, rnd, Color32::from_rgb(0xd0, 0x20, 0x20));
            for k in 0..4 {
                let x = r.left() + (k as f32 + 0.5) * (r.width() / 4.0);
                p.line_segment([egui::pos2(x, r.top()), egui::pos2(x, r.bottom())], Stroke::new(2.0, Color32::from_rgb(0x30, 0x50, 0xff)));
            }
        }
        3 => { p.rect_filled(r, rnd, Color32::from_rgb(0x33, 0xcc, 0x33)); }
        _ => { p.rect_filled(r, rnd, Color32::from_rgb(0xff, 0xa5, 0x00).linear_multiply(0.5)); }
    }
}

/// Clock-face grid: each cell paints a mini preview (digital "12:00" or analog).
pub fn clock_grid(ui: &mut egui::Ui, labels: &[&str], selected: i64) -> Option<i64> {
    let mut clicked = None;
    let cell = Vec2::new(100.0, 88.0);
    let per_row = ((ui.available_width() + 8.0) / (cell.x + 8.0)).floor().max(1.0) as usize;
    egui::Grid::new("clockgrid").spacing(Vec2::new(8.0, 8.0)).show(ui, |ui| {
        for (i, label) in labels.iter().enumerate() {
            let sel = selected == i as i64;
            let (rect, resp) = ui.allocate_exact_size(cell, egui::Sense::click());
            ui.painter().rect(rect, CornerRadius::same(theme::RADIUS as u8), cell_bg(sel), sel_stroke(sel, resp.hovered()), egui::StrokeKind::Inside);
            let pv = egui::Rect::from_min_size(rect.left_top() + Vec2::new((cell.x - 64.0) / 2.0, 8.0), Vec2::new(64.0, 56.0));
            ui.painter().rect_filled(pv, CornerRadius::same(4), theme::BG_BASE);
            paint_clock_preview(ui.painter(), pv, i as i64);
            cell_label(ui, rect, label, sel);
            if resp.clicked() {
                clicked = Some(i as i64);
            }
            if (i + 1) % per_row == 0 {
                ui.end_row();
            }
        }
    });
    clicked
}

fn paint_clock_preview(p: &egui::Painter, r: egui::Rect, face: i64) {
    let c = r.center();
    match face {
        3 | 5 => {
            let radius = 18.0;
            if face == 5 {
                p.circle_stroke(c, radius, Stroke::new(1.5, theme::TEXT_MAIN));
            } else {
                p.rect_stroke(egui::Rect::from_center_size(c, Vec2::splat(radius * 2.0)), CornerRadius::same(2), Stroke::new(1.5, theme::TEXT_MAIN), egui::StrokeKind::Inside);
            }
            p.line_segment([c, c + Vec2::new(0.0, -radius * 0.7)], Stroke::new(2.0, theme::TEXT_MAIN));
            p.line_segment([c, c + Vec2::new(radius * 0.55, 0.0)], Stroke::new(1.5, theme::TEXT_MUTED));
        }
        _ => {
            if face == 4 {
                p.rect_filled(r.shrink(6.0), CornerRadius::same(2), theme::TEXT_MAIN);
            }
            if face == 2 {
                p.rect_stroke(r.shrink(6.0), CornerRadius::same(2), Stroke::new(1.0, theme::TEXT_MUTED), egui::StrokeKind::Inside);
            }
            let col = match face {
                1 => theme::PRIMARY,
                4 => Color32::BLACK,
                _ => theme::TEXT_MAIN,
            };
            p.text(c, egui::Align2::CENTER_CENTER, "12:00", egui::FontId::proportional(15.0), col);
        }
    }
}

/// Grid where each cell shows a webp preview thumbnail above the label.
/// `asset_fn(index, selected) -> candidate file names` (first that exists wins).
pub fn image_grid(
    ui: &mut egui::Ui,
    labels: &[&str],
    selected: i64,
    asset_fn: impl Fn(i64, bool) -> Vec<String>,
) -> Option<i64> {
    let mut clicked = None;
    let cell = Vec2::new(96.0, 92.0);
    let per_row = ((ui.available_width() + 8.0) / (cell.x + 8.0)).floor().max(1.0) as usize;
    egui::Grid::new("imggrid").spacing(Vec2::new(8.0, 8.0)).show(ui, |ui| {
        for (i, label) in labels.iter().enumerate() {
            let sel = selected == i as i64;
            let uri = asset_fn(i as i64, sel).into_iter().find_map(|n| crate::ui_widgets::asset_uri(&n));
            let (rect, resp) = ui.allocate_exact_size(cell, egui::Sense::click());
            ui.painter().rect(rect, CornerRadius::same(theme::RADIUS as u8), cell_bg(sel), sel_stroke(sel, resp.hovered()), egui::StrokeKind::Inside);
            let img = egui::Rect::from_min_size(rect.left_top() + Vec2::new((cell.x - 60.0) / 2.0, 8.0), Vec2::splat(60.0));
            if let Some(u) = uri {
                egui::Image::new(u).corner_radius(CornerRadius::same(4)).paint_at(ui, img);
            } else {
                ui.painter().rect_filled(img, CornerRadius::same(4), theme::BG_BASE);
            }
            cell_label(ui, rect, label, sel);
            if resp.clicked() {
                clicked = Some(i as i64);
            }
            if (i + 1) % per_row == 0 {
                ui.end_row();
            }
        }
    });
    clicked
}

/// A clickable color swatch (ambient quick colors).
pub fn swatch(ui: &mut egui::Ui, rgb: [u8; 3]) -> egui::Response {
    let (rect, resp) = ui.allocate_exact_size(Vec2::splat(22.0), egui::Sense::click());
    ui.painter().rect(rect, CornerRadius::same(4), Color32::from_rgb(rgb[0], rgb[1], rgb[2]), Stroke::new(1.0, theme::BORDER), egui::StrokeKind::Inside);
    resp
}

fn sel_stroke(selected: bool, hovered: bool) -> Stroke {
    if selected {
        Stroke::new(1.5, theme::PRIMARY)
    } else if hovered {
        Stroke::new(1.0, theme::PRIMARY)
    } else {
        Stroke::new(1.0, theme::BORDER)
    }
}

fn cell_bg(selected: bool) -> Color32 {
    if selected { theme::PRIMARY.linear_multiply(0.18) } else { theme::CARD_BG }
}

fn cell_label(ui: &egui::Ui, rect: egui::Rect, label: &str, selected: bool) {
    ui.painter().text(
        egui::pos2(rect.center().x, rect.bottom() - 10.0),
        egui::Align2::CENTER_CENTER,
        label,
        egui::FontId::proportional(10.5),
        if selected { theme::TEXT_MAIN } else { theme::TEXT_MUTED },
    );
}

pub fn hint(ui: &mut egui::Ui, text: &str) {
    ui.label(RichText::new(text).size(12.0).color(theme::TEXT_MUTED));
    ui.add_space(10.0);
}

pub fn card_margin() -> Margin {
    Margin::same(14)
}

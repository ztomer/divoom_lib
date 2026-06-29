//! Channels tab panels — the per-channel controls, reproduced from
//! `divoom_gui/web_ui/index.html` (#channel-panels) + `channels_grids.js`. Each
//! control maps to the same device_call leaf the Python `LightingApi`/`ToolsApi`
//! facades use (verified against the Rust daemon's `device_call` dispatch):
//!   clock face   → display.show_clock      [style]
//!   visualizer   → display.show_visualization [number]
//!   vj effect    → display.show_effects    [number]
//!   ambient      → display.show_light      [colorHex, brightness] (+switch_channel)
//!   scoreboard   → set_scoreboard          [on_off, red, blue]
//!   text         → push_text (bitmap render) — deferred to Phase 3 (needs font)

use eframe::egui::{self, Color32, Margin, RichText, Rounding, Stroke, Vec2};

use crate::app::{Channel, DivoomApp};
use crate::theme;

// Data tables — values + labels straight from channels_grids.js.
const CLOCK_FACES: [&str; 6] = [
    "Full Screen", "Rainbow", "With Box", "Analog Square", "Full Screen Neg", "Analog Round",
];
const VJ_EFFECTS: [&str; 16] = [
    "Sparkles", "Lava", "Vertical Rainbow", "Drops", "Rainbow Swirl", "CMY Fade", "Rainbow Lava",
    "Pastel Patterns", "CMY Wave", "Fire", "Countdown", "Pink/Blue Fade", "Rainbow Polygons",
    "Pink/Blue Wave", "Rainbow Cross", "Rainbow Shapes",
];
const AMBIENT_MODES: [&str; 5] = [
    "Plain Color", "Love (Pulse)", "Plants (Breathe)", "Sleeping (Fade)", "No Mosquitto",
];

/// Render the active channel's panel inside the content card.
pub fn panel(app: &mut DivoomApp, ui: &mut egui::Ui) {
    match app.channel {
        Channel::Clock => clock(app, ui),
        Channel::Visualizer => visualizer(app, ui),
        Channel::Vj => vj(app, ui),
        Channel::Ambient => ambient(app, ui),
        Channel::Scoreboard => scoreboard(app, ui),
        Channel::Text => text(app, ui),
        Channel::Sessions => sessions(app, ui),
    }
}

fn clock(app: &mut DivoomApp, ui: &mut egui::Ui) {
    hint(ui, "Pick a built-in clock face. It switches the device to the clock channel.");
    if let Some(v) = selector_grid(ui, &CLOCK_FACES, app.clock_face) {
        app.clock_face = v;
        app.call("display.show_clock", serde_json::json!([v]));
    }
    ui.add_space(12.0);
    ui.horizontal(|ui| {
        ui.label(RichText::new("Clock color").size(12.0).color(theme::TEXT_MUTED));
        if ui.color_edit_button_srgb(&mut app.clock_color).changed() {
            // The plain show_clock face is white-only on the device; color is
            // applied via the richer overlay path.
            app.call(
                "display.set_clock_rich",
                serde_json::json!([app.clock_face]),
            );
        }
    });
}

fn visualizer(app: &mut DivoomApp, ui: &mut egui::Ui) {
    hint(ui, "Music EQ / visualizer patterns.");
    let labels: Vec<String> = (1..=12).map(|i| format!("EQ {i:02}")).collect();
    let refs: Vec<&str> = labels.iter().map(|s| s.as_str()).collect();
    if let Some(v) = selector_grid(ui, &refs, app.viz_sel) {
        app.viz_sel = v;
        app.call("display.show_visualization", serde_json::json!([v]));
    }
}

fn vj(app: &mut DivoomApp, ui: &mut egui::Ui) {
    hint(ui, "VJ light effects.");
    if let Some(v) = selector_grid(ui, &VJ_EFFECTS, app.vj_sel) {
        app.vj_sel = v;
        app.call("display.show_effects", serde_json::json!([v]));
    }
}

fn ambient(app: &mut DivoomApp, ui: &mut egui::Ui) {
    hint(ui, "Ambient light effect + color.");
    if let Some(v) = selector_grid(ui, &AMBIENT_MODES, app.ambient_mode) {
        app.ambient_mode = v;
        apply_ambient(app);
    }
    ui.add_space(12.0);
    ui.horizontal(|ui| {
        ui.label(RichText::new("Color").size(12.0).color(theme::TEXT_MUTED));
        if ui.color_edit_button_srgb(&mut app.ambient_color).changed() {
            apply_ambient(app);
        }
        for sw in [
            [0xff, 0, 0], [0, 0xff, 0], [0, 0, 0xff], [0xff, 0xff, 0],
            [0xff, 0x77, 0], [0, 0xff, 0xcc], [0xff, 0, 0xff], [0xff, 0xff, 0xff],
        ] {
            if swatch(ui, sw).clicked() {
                app.ambient_color = sw;
                apply_ambient(app);
            }
        }
    });
}

fn apply_ambient(app: &DivoomApp) {
    app.call(
        "display.show_light",
        serde_json::json!([DivoomApp::hex(app.ambient_color), app.brightness, true, app.ambient_mode]),
    );
}

fn scoreboard(app: &mut DivoomApp, ui: &mut egui::Ui) {
    hint(ui, "Two-team score counter on the device's scoreboard tool.");
    let mut changed = false;
    ui.horizontal(|ui| {
        ui.colored_label(Color32::from_rgb(0x4a, 0x90, 0xff), "BLUE");
        changed |= ui.add(egui::DragValue::new(&mut app.score_blue).range(0..=999)).changed();
        ui.add_space(20.0);
        ui.colored_label(theme::ERROR, "RED");
        changed |= ui.add(egui::DragValue::new(&mut app.score_red).range(0..=999)).changed();
    });
    ui.add_space(10.0);
    if ui.button("Reset to 0 - 0").clicked() {
        app.score_blue = 0;
        app.score_red = 0;
        changed = true;
    }
    if changed {
        // set_scoreboard(on_off=1, red, blue)
        app.call("set_scoreboard", serde_json::json!([1, app.score_red, app.score_blue]));
    }
}

fn text(app: &mut DivoomApp, ui: &mut egui::Ui) {
    hint(ui, "Type a message and push it to the device as text.");
    ui.add(egui::TextEdit::singleline(&mut app.text_content).hint_text("Enter text…").desired_width(f32::INFINITY));
    ui.add_space(8.0);
    ui.horizontal(|ui| {
        ui.label(RichText::new("Color").size(11.0).color(theme::TEXT_MUTED));
        ui.color_edit_button_srgb(&mut app.text_color);
        ui.add_space(12.0);
        ui.label(RichText::new("Effect").size(11.0).color(theme::TEXT_MUTED));
        egui::ComboBox::from_id_salt("text_effect")
            .selected_text(text_effect_name(app.text_effect))
            .show_ui(ui, |ui| {
                for (val, name) in [(1, "Scroll left"), (0, "Static"), (2, "Scroll up"), (3, "Hold"), (4, "Marquee")] {
                    ui.selectable_value(&mut app.text_effect, val, name);
                }
            });
    });
    ui.add_space(8.0);
    ui.horizontal(|ui| {
        ui.label(RichText::new(format!("Speed {}", app.text_speed)).size(11.0).color(theme::TEXT_MUTED));
        ui.add(egui::Slider::new(&mut app.text_speed, 1..=100).show_value(false));
    });
    ui.add_space(12.0);
    // push_text renders a bitmap font to an image on the GUI side (LightingApi
    // ._render_text_png) then show_image — that font port is Phase 3.
    ui.add_enabled(false, egui::Button::new("Push to Device (Phase 3)"));
}

fn text_effect_name(v: i64) -> &'static str {
    match v {
        0 => "Static",
        2 => "Scroll up",
        3 => "Hold",
        4 => "Marquee",
        _ => "Scroll left",
    }
}

fn sessions(_app: &mut DivoomApp, ui: &mut egui::Ui) {
    hint(ui, "Sleep Aid + session tools — ported in Phase 3.");
}

// --- shared widgets ----------------------------------------------------------

/// A responsive grid of selectable cells (the web `.selector-grid`). Returns the
/// newly-clicked value, if any.
fn selector_grid(ui: &mut egui::Ui, labels: &[&str], selected: i64) -> Option<i64> {
    let mut clicked = None;
    let cell = Vec2::new(118.0, 40.0);
    let per_row = ((ui.available_width() + 8.0) / (cell.x + 8.0)).floor().max(1.0) as usize;
    egui::Grid::new("selgrid")
        .spacing(Vec2::new(8.0, 8.0))
        .show(ui, |ui| {
            for (i, label) in labels.iter().enumerate() {
                if cell_button(ui, label, selected == i as i64, cell).clicked() {
                    clicked = Some(i as i64);
                }
                if (i + 1) % per_row == 0 {
                    ui.end_row();
                }
            }
        });
    clicked
}

fn cell_button(ui: &mut egui::Ui, label: &str, selected: bool, size: Vec2) -> egui::Response {
    let (rect, resp) = ui.allocate_exact_size(size, egui::Sense::click());
    let p = ui.painter();
    let (bg, stroke) = if selected {
        (theme::PRIMARY.linear_multiply(0.18), Stroke::new(1.5, theme::PRIMARY))
    } else if resp.hovered() {
        (theme::CARD_BG, Stroke::new(1.0, theme::PRIMARY))
    } else {
        (theme::CARD_BG, Stroke::new(1.0, theme::BORDER))
    };
    p.rect(rect, Rounding::same(theme::RADIUS), bg, stroke);
    p.text(
        rect.center(),
        egui::Align2::CENTER_CENTER,
        label,
        egui::FontId::proportional(12.5),
        if selected { theme::TEXT_MAIN } else { theme::TEXT_MUTED },
    );
    resp
}

fn swatch(ui: &mut egui::Ui, rgb: [u8; 3]) -> egui::Response {
    let (rect, resp) = ui.allocate_exact_size(Vec2::splat(22.0), egui::Sense::click());
    ui.painter().rect(
        rect,
        Rounding::same(4.0),
        Color32::from_rgb(rgb[0], rgb[1], rgb[2]),
        Stroke::new(1.0, theme::BORDER),
    );
    resp
}

fn hint(ui: &mut egui::Ui, text: &str) {
    ui.label(RichText::new(text).size(12.0).color(theme::TEXT_MUTED));
    ui.add_space(10.0);
}

/// Margin helper kept here so shell.rs's content card stays generic.
pub fn card_margin() -> Margin {
    Margin::same(14.0)
}

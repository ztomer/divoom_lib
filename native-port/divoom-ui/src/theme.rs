//! Design tokens + egui visuals, mirroring `divoom_gui/web_ui/style.css` `:root`
//! (the Braun-style dark dashboard). The current web UI is the visual reference;
//! these are the same hex values so the native port reads identically.

use egui::{Color32, Rounding, Stroke, Visuals};

// Palette — byte-for-byte from web_ui/style.css :root.
pub const BG_BASE: Color32 = Color32::from_rgb(0x12, 0x13, 0x16);
pub const CARD_BG: Color32 = Color32::from_rgb(0x1e, 0x1f, 0x24);
pub const SIDEBAR_BG: Color32 = Color32::from_rgb(0x18, 0x19, 0x1d);
pub const INPUT_BG: Color32 = Color32::from_rgb(0x18, 0x19, 0x1d);
pub const APPBAR_BG: Color32 = Color32::from_rgb(0x0a, 0x0c, 0x16); // win-appbar-bg ~rgba(10,12,22,.95)
pub const BORDER: Color32 = Color32::from_rgb(0x2b, 0x2c, 0x32);
pub const PRIMARY: Color32 = Color32::from_rgb(0xff, 0x5a, 0x1f); // Braun tuner orange
pub const ACCENT: Color32 = Color32::from_rgb(0x00, 0xcc, 0x66); // indicator green
pub const WARN: Color32 = Color32::from_rgb(0xff, 0xcc, 0x00);
pub const ERROR: Color32 = Color32::from_rgb(0xff, 0x44, 0x44);
pub const TEXT_MAIN: Color32 = Color32::from_rgb(0xe8, 0xe9, 0xeb);
pub const TEXT_MUTED: Color32 = Color32::from_rgb(0x82, 0x83, 0x8a);

pub const SIDEBAR_WIDTH: f32 = 168.0;
pub const APPBAR_HEIGHT: f32 = 52.0;
pub const RADIUS: f32 = 6.0;

/// Install the dark Braun theme onto the egui context.
pub fn apply(ctx: &egui::Context) {
    let mut v = Visuals::dark();
    v.panel_fill = BG_BASE;
    v.window_fill = CARD_BG;
    v.extreme_bg_color = INPUT_BG;
    v.faint_bg_color = SIDEBAR_BG;
    v.override_text_color = Some(TEXT_MAIN);
    v.hyperlink_color = PRIMARY;
    v.window_rounding = Rounding::same(RADIUS);
    v.window_stroke = Stroke::new(1.0, BORDER);
    v.selection.bg_fill = PRIMARY.linear_multiply(0.35);
    v.selection.stroke = Stroke::new(1.0, PRIMARY);

    let r = Rounding::same(RADIUS);
    // Resting widgets sit on the card colour with a hairline border.
    v.widgets.noninteractive.bg_fill = CARD_BG;
    v.widgets.noninteractive.bg_stroke = Stroke::new(1.0, BORDER);
    v.widgets.noninteractive.rounding = r;
    v.widgets.noninteractive.fg_stroke = Stroke::new(1.0, TEXT_MUTED);

    v.widgets.inactive.bg_fill = CARD_BG;
    v.widgets.inactive.weak_bg_fill = CARD_BG;
    v.widgets.inactive.bg_stroke = Stroke::new(1.0, BORDER);
    v.widgets.inactive.rounding = r;
    v.widgets.inactive.fg_stroke = Stroke::new(1.0, TEXT_MAIN);

    // Hover: orange border (matches --border-hover).
    v.widgets.hovered.bg_fill = CARD_BG;
    v.widgets.hovered.weak_bg_fill = CARD_BG;
    v.widgets.hovered.bg_stroke = Stroke::new(1.0, PRIMARY);
    v.widgets.hovered.rounding = r;
    v.widgets.hovered.fg_stroke = Stroke::new(1.0, TEXT_MAIN);

    // Active/pressed: filled orange.
    v.widgets.active.bg_fill = PRIMARY;
    v.widgets.active.weak_bg_fill = PRIMARY;
    v.widgets.active.bg_stroke = Stroke::new(1.0, PRIMARY);
    v.widgets.active.rounding = r;
    v.widgets.active.fg_stroke = Stroke::new(1.0, Color32::BLACK);

    ctx.set_visuals(v);

    // A touch more breathing room than egui's defaults (closer to the web spacing).
    let mut style = (*ctx.style()).clone();
    style.spacing.item_spacing = egui::vec2(8.0, 8.0);
    style.spacing.button_padding = egui::vec2(10.0, 6.0);
    style.spacing.slider_width = 120.0;
    ctx.set_style(style);
}

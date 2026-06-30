//! Sidebar nav glyphs — the Kare icons from `web_ui/index.html`, embedded as SVG
//! (white fill/stroke so `Image::tint` can color them per nav state). Rendered via
//! the egui_extras svg loader. `viewBox` + shapes are copied verbatim from the web.

use eframe::egui::{self, Color32, Rect, Vec2};

use crate::app::Tab;

const CHANNELS: &str = r#"<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16' fill='#ffffff'><rect x='1' y='4' width='14' height='8' rx='2'/><rect x='4' y='7' width='3' height='1'/><rect x='5' y='6' width='1' height='3'/><circle cx='10' cy='8' r='1'/><circle cx='12' cy='8' r='1'/></svg>"#;
const WIDGETS: &str = r#"<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16' fill='none' stroke='#ffffff' stroke-width='2'><line x1='1' y1='15' x2='15' y2='15'/><line x1='1' y1='1' x2='1' y2='15'/><path d='M2,12 L6,8 L10,10 L14,3'/></svg>"#;
const PIXEL_ART: &str = r#"<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16' fill='#ffffff'><rect x='1' y='1' width='6' height='6' rx='1'/><rect x='9' y='1' width='6' height='6' rx='1'/><rect x='1' y='9' width='6' height='6' rx='1'/><rect x='9' y='9' width='6' height='6' rx='1'/></svg>"#;
const WALL: &str = r#"<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16' fill='#ffffff'><rect x='1' y='1' width='14' height='11' rx='1'/><rect x='3' y='3' width='10' height='7' fill='none' stroke='#ffffff' stroke-width='1'/><rect x='6' y='12' width='4' height='2'/><rect x='4' y='14' width='8' height='1'/></svg>"#;
const SCHEDULE: &str = r#"<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16' fill='none' stroke='#ffffff' stroke-width='2'><rect x='2' y='2' width='12' height='12' rx='2'/><path d='M5,8 L8,11 L12,5'/></svg>"#;
const DEVICE: &str = r#"<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16' fill='none' stroke='#ffffff' stroke-width='2'><circle cx='8' cy='8' r='2.5'/><path d='M8,1 L8,3 M8,13 L8,15 M1,8 L3,8 M13,8 L15,8 M3.2,3.2 L4.6,4.6 M11.4,11.4 L12.8,12.8 M3.2,12.8 L4.6,11.4 M11.4,4.6 L12.8,3.2'/></svg>"#;
const SETTINGS: &str = r#"<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16' fill='#ffffff'><path d='M8,6 C6.9,6 6,6.9 6,8 C6,9.1 6.9,10 8,10 C9.1,10 10,9.1 10,8 C10,6.9 9.1,6 8,6 Z M8,0 L6,3 L10,3 Z M8,16 L10,13 L6,13 Z M0,8 L3,6 L3,10 Z M16,8 L13,10 L13,6 Z'/></svg>"#;

fn svg(tab: Tab) -> (&'static str, &'static str) {
    match tab {
        Tab::Channels => ("bytes://nav_channels.svg", CHANNELS),
        Tab::Widgets => ("bytes://nav_widgets.svg", WIDGETS),
        Tab::PixelArt => ("bytes://nav_pixelart.svg", PIXEL_ART),
        Tab::Wall => ("bytes://nav_wall.svg", WALL),
        Tab::Schedule => ("bytes://nav_schedule.svg", SCHEDULE),
        Tab::DeviceSettings => ("bytes://nav_device.svg", DEVICE),
        Tab::Settings => ("bytes://nav_settings.svg", SETTINGS),
    }
}

/// Paint a nav glyph (tinted) into `rect` (svg loader rasterizes at that size).
pub fn paint_nav(ui: &egui::Ui, tab: Tab, rect: Rect, tint: Color32) {
    let (uri, markup) = svg(tab);
    egui::Image::new(egui::ImageSource::Bytes {
        uri: uri.into(),
        bytes: markup.as_bytes().into(),
    })
    .tint(tint)
    .paint_at(ui, rect);
}

/// The settings gear glyph for the appbar pill.
pub fn paint_settings(ui: &egui::Ui, rect: Rect, tint: Color32) {
    paint_nav(ui, Tab::Settings, rect, tint);
}

pub const ICON: Vec2 = Vec2::splat(16.0);

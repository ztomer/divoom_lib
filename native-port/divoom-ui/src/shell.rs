//! App shell rendering: the integrated appbar, the sidebar, and the tab content
//! host. Mirrors `divoom_gui/web_ui/index.html` (appbar + .sidebar + .main-content).

use eframe::egui::{
    self, Align, Color32, Frame, Layout, Margin, RichText, Rounding, Sense, Stroke, Vec2,
};

use crate::app::{Channel, DivoomApp, Tab};
use crate::daemon::Cmd;
use crate::theme;

// --- appbar ------------------------------------------------------------------

pub fn appbar(app: &mut DivoomApp, ctx: &egui::Context) {
    let frame = Frame::none()
        .fill(theme::APPBAR_BG)
        .inner_margin(Margin::symmetric(10.0, 6.0));
    egui::TopBottomPanel::top("appbar")
        .exact_height(theme::APPBAR_HEIGHT)
        .frame(frame)
        .show(ctx, |ui| {
            ui.horizontal_centered(|ui| {
                // Reserve room for the native macOS traffic-light buttons (top-left).
                #[cfg(target_os = "macos")]
                ui.add_space(72.0);
                ui.with_layout(Layout::right_to_left(Align::Center), |ui| {
                    settings_gear(app, ui);
                    ui.add_space(10.0);
                    volume_control(app, ui);
                    ui.add_space(14.0);
                    brightness_control(app, ui);
                    ui.add_space(14.0);
                    // Everything to the left of the controls is the window drag region.
                    let drag = ui.allocate_response(ui.available_size(), Sense::click_and_drag());
                    if drag.dragged() {
                        ctx.send_viewport_cmd(egui::ViewportCommand::StartDrag);
                    }
                    if drag.double_clicked() {
                        let max = ctx.input(|i| i.viewport().maximized.unwrap_or(false));
                        ctx.send_viewport_cmd(egui::ViewportCommand::Maximized(!max));
                    }
                });
            });
        });
}

fn brightness_control(app: &mut DivoomApp, ui: &mut egui::Ui) {
    ui.label(RichText::new("Brightness").size(11.0).color(theme::TEXT_MUTED));
    let r = ui.add(
        egui::Slider::new(&mut app.brightness, 0..=100)
            .show_value(false)
            .trailing_fill(true),
    );
    ui.label(RichText::new(format!("{}%", app.brightness)).size(11.0).monospace());
    if r.drag_stopped() || r.lost_focus() {
        app.daemon.send(Cmd::SetBrightness(app.brightness));
    }
}

fn volume_control(app: &mut DivoomApp, ui: &mut egui::Ui) {
    ui.label(RichText::new("Volume").size(11.0).color(theme::TEXT_MUTED));
    let r = ui.add(
        egui::Slider::new(&mut app.volume, 0..=15)
            .show_value(false)
            .trailing_fill(true),
    );
    ui.label(RichText::new(format!("{}/15", app.volume)).size(11.0).monospace());
    if r.drag_stopped() || r.lost_focus() {
        app.daemon.send(Cmd::SetVolume(app.volume));
    }
}

fn settings_gear(app: &mut DivoomApp, ui: &mut egui::Ui) {
    let selected = app.tab == Tab::Settings;
    let txt = RichText::new("Settings").size(12.0).color(if selected {
        theme::PRIMARY
    } else {
        theme::TEXT_MAIN
    });
    if ui.add(egui::Button::new(txt).rounding(Rounding::same(12.0))).clicked() {
        app.tab = Tab::Settings;
    }
}

// --- sidebar -----------------------------------------------------------------

pub fn sidebar(app: &mut DivoomApp, ctx: &egui::Context) {
    let frame = Frame::none()
        .fill(theme::SIDEBAR_BG)
        .inner_margin(Margin::same(10.0))
        .stroke(Stroke::new(1.0, theme::BORDER));
    egui::SidePanel::left("sidebar")
        .exact_width(theme::SIDEBAR_WIDTH)
        .resizable(false)
        .frame(frame)
        .show(ctx, |ui| {
            // Device panel pinned to the bottom; nav fills the rest.
            egui::TopBottomPanel::bottom("device_panel")
                .frame(Frame::none())
                .show_inside(ui, |ui| device_panel(app, ui));
            egui::CentralPanel::default()
                .frame(Frame::none())
                .show_inside(ui, |ui| nav_menu(app, ui));
        });
}

fn nav_menu(app: &mut DivoomApp, ui: &mut egui::Ui) {
    ui.add_space(2.0);
    for (tab, label) in Tab::NAV {
        if nav_button(ui, app.tab == tab, label).clicked() {
            app.tab = tab;
        }
        ui.add_space(4.0);
    }
}

fn nav_button(ui: &mut egui::Ui, selected: bool, label: &str) -> egui::Response {
    let desired = Vec2::new(ui.available_width(), 34.0);
    let (rect, resp) = ui.allocate_exact_size(desired, Sense::click());
    let painter = ui.painter();
    let bg = if selected {
        theme::PRIMARY.linear_multiply(0.18)
    } else if resp.hovered() {
        theme::CARD_BG
    } else {
        Color32::TRANSPARENT
    };
    painter.rect_filled(rect, Rounding::same(theme::RADIUS), bg);
    if selected {
        // Orange left accent bar (the active-nav cue from the web UI).
        let bar = egui::Rect::from_min_size(rect.left_top(), Vec2::new(3.0, rect.height()));
        painter.rect_filled(bar, Rounding::same(2.0), theme::PRIMARY);
    }
    let text_color = if selected { theme::TEXT_MAIN } else { theme::TEXT_MUTED };
    painter.text(
        rect.left_center() + Vec2::new(12.0, 0.0),
        egui::Align2::LEFT_CENTER,
        label,
        egui::FontId::proportional(13.5),
        text_color,
    );
    resp
}

fn device_panel(app: &mut DivoomApp, ui: &mut egui::Ui) {
    ui.add_space(8.0);
    Frame::none()
        .fill(theme::CARD_BG)
        .stroke(Stroke::new(1.0, theme::BORDER))
        .rounding(Rounding::same(theme::RADIUS))
        .inner_margin(Margin::same(8.0))
        .show(ui, |ui| {
            ui.vertical_centered(|ui| {
                // Flat face-on screen preview (neutral bezel placeholder for now).
                let (rect, _) =
                    ui.allocate_exact_size(Vec2::new(96.0, 96.0), Sense::hover());
                ui.painter().rect_filled(rect, Rounding::same(4.0), theme::BG_BASE);
                ui.painter().rect_stroke(
                    rect,
                    Rounding::same(4.0),
                    Stroke::new(1.0, theme::BORDER),
                );
                ui.add_space(6.0);
                let name = app
                    .selected_device
                    .and_then(|i| app.devices.get(i))
                    .map(|d| d.name.clone())
                    .unwrap_or_else(|| "No screen connected".into());
                ui.label(RichText::new(name).size(12.0).color(theme::TEXT_MAIN));
            });
        });

    // Device chips (switch device).
    ui.add_space(6.0);
    let devices = app.devices.clone();
    ui.horizontal_wrapped(|ui| {
        for (i, d) in devices.iter().enumerate() {
            let selected = app.selected_device == Some(i);
            let label = if d.name.is_empty() { d.address.clone() } else { d.name.clone() };
            if ui.selectable_label(selected, RichText::new(label).size(11.0)).clicked() {
                app.selected_device = Some(i);
                app.daemon.send(Cmd::Connect(d.address.clone()));
            }
        }
    });

    // Daemon / scan status row, height always reserved (no reflow).
    ui.add_space(6.0);
    ui.horizontal(|ui| {
        let (dot, txt) = if app.daemon_connected {
            (theme::ACCENT, "daemon ready")
        } else {
            (theme::ERROR, "daemon offline")
        };
        let (r, _) = ui.allocate_exact_size(Vec2::new(8.0, 8.0), Sense::hover());
        ui.painter().circle_filled(r.center(), 4.0, dot);
        ui.label(RichText::new(txt).size(10.5).color(theme::TEXT_MUTED));
        if ui.small_button("Scan").clicked() {
            app.daemon.send(Cmd::Scan(app.scan_timeout));
        }
    });
}

// --- content -----------------------------------------------------------------

pub fn content(app: &mut DivoomApp, ctx: &egui::Context) {
    let frame = Frame::none().inner_margin(Margin::same(14.0));
    egui::CentralPanel::default().frame(frame).show(ctx, |ui| {
        ui.heading(RichText::new(app.tab.title()).color(theme::TEXT_MAIN));
        ui.add_space(8.0);
        match app.tab {
            Tab::Channels => channels_tab(app, ui),
            Tab::DeviceSettings => crate::device_settings::panel(app, ui),
            Tab::Settings => crate::settings::panel(app, ui),
            Tab::Schedule => crate::schedule::panel(app, ui),
            Tab::PixelArt => crate::pixel_art::panel(app, ui),
            Tab::Wall => crate::wall::panel(app, ui),
            Tab::Widgets => crate::widgets::panel(app, ui),
        }
        if let Some(err) = &app.last_error {
            ui.add_space(8.0);
            ui.colored_label(theme::ERROR, format!("! {err}"));
        }
    });
}

fn channels_tab(app: &mut DivoomApp, ui: &mut egui::Ui) {
    // Channel sub-tab row, sitting on its own glass pane (.tabs-section).
    Frame::none()
        .fill(theme::SIDEBAR_BG)
        .rounding(Rounding::same(theme::RADIUS))
        .stroke(Stroke::new(1.0, theme::BORDER))
        .inner_margin(Margin::symmetric(8.0, 4.0))
        .show(ui, |ui| {
            ui.horizontal_wrapped(|ui| {
                for (ch, label) in Channel::ALL {
                    if ui.selectable_label(app.channel == ch, label).clicked() {
                        app.channel = ch;
                    }
                }
            });
        });
    ui.add_space(theme::RADIUS);

    Frame::none()
        .fill(theme::CARD_BG)
        .rounding(Rounding::same(theme::RADIUS))
        .stroke(Stroke::new(1.0, theme::BORDER))
        .inner_margin(crate::channels::card_margin())
        .show(ui, |ui| {
            ui.set_width(ui.available_width());
            crate::channels::panel(app, ui);
        });
}

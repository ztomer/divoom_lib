//! Bundled typography — Inter (body) + Inter Display (headings), matching the web
//! UI's Inter/Outfit stack (no Outfit locally; Inter Display fills the display
//! role). Inter is SIL OFL-1.1 (see fonts/ATTRIBUTION.txt). egui loads OTF/CFF via
//! ttf-parser, so the .otf files work directly.

use eframe::egui::{self, FontData, FontDefinitions, FontFamily, TextStyle};

pub fn install(ctx: &egui::Context) {
    let mut fonts = FontDefinitions::default();
    fonts.font_data.insert(
        "inter".to_owned(),
        FontData::from_static(include_bytes!("../fonts/Inter-Regular.otf")),
    );
    fonts.font_data.insert(
        "inter_display".to_owned(),
        FontData::from_static(include_bytes!("../fonts/InterDisplay-SemiBold.otf")),
    );
    // Inter is the primary proportional face (keep egui's fallbacks after it).
    fonts.families.entry(FontFamily::Proportional).or_default().insert(0, "inter".to_owned());
    // A named "display" family for headings.
    fonts.families.insert(
        FontFamily::Name("display".into()),
        vec!["inter_display".to_owned(), "inter".to_owned()],
    );
    ctx.set_fonts(fonts);

    // Point the Heading text style at the display family.
    let mut style = (*ctx.style()).clone();
    if let Some(h) = style.text_styles.get_mut(&TextStyle::Heading) {
        h.family = FontFamily::Name("display".into());
    }
    ctx.set_style(style);
}

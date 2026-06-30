//! Device-screen preview frames. Mirrors the web UI's "last pushed image" sidebar
//! preview (`divoom_gui/web_ui/app_globals.js` + `media_sync._frame_to_data_url`):
//! the daemon's `get_device_activity` returns `activity[mac].preview` as a
//! `data:image/png;base64,...` URL, and the GUI also computes that data-url
//! client-side for frames IT pushes so the preview updates instantly. This module
//! is the encode (rgb -> data-url) + decode (data-url -> egui texture) plumbing.

use base64::Engine;
use serde_json::json;

use crate::app::DivoomApp;

const PNG_DATA_URL_PREFIX: &str = "data:image/png;base64,";

impl DivoomApp {
    /// Debug harness: auto-select the first fake device, and (optionally) seed a
    /// synthetic last-pushed frame so the sidebar preview render path is testable
    /// headlessly (no daemon). Mirrors a real connect + push. No-op in production.
    pub fn apply_debug_seed(&mut self) {
        if self.devices.is_empty() || std::env::var("DIVOOM_UI_FAKE_DEVICES").is_err() {
            return;
        }
        self.selected_device = Some(0);
        if std::env::var("DIVOOM_UI_FAKE_PREVIEW").is_err() {
            return;
        }
        if let Some(mac) = self.active_mac() {
            let px: Vec<[u8; 3]> = (0..16 * 16)
                .map(|i| {
                    let (x, y) = (i % 16, i / 16);
                    [(x * 16) as u8, (y * 16) as u8, ((x + y) * 8) as u8]
                })
                .collect();
            if let Some(url) = rgb_to_data_url(16, 16, &px) {
                self.local_previews.insert(mac, url);
            }
        }
    }

    /// Poll the daemon for per-device activity (the sidebar preview frame) ~every
    /// 1.5s while a device is selected. Read-only; populates `replies`.
    pub fn poll_device_activity(&mut self) {
        if self.active_mac().is_none() {
            return;
        }
        let due = self
            .last_activity_poll
            .map_or(true, |t| t.elapsed().as_secs_f32() > 1.5);
        if due {
            self.last_activity_poll = Some(std::time::Instant::now());
            self.raw("get_device_activity", json!({}), "device_activity");
        }
    }

    /// Record a preview (data-url PNG) for a just-pushed frame: show it instantly
    /// in the sidebar and persist it in the daemon so other clients see it too
    /// (mirrors the web UI's localStorage + `set_device_activity`).
    pub fn record_local_preview(&mut self, kind: &str, data_url: String) {
        let Some(mac) = self.active_mac() else { return };
        let name = self
            .selected_device
            .and_then(|i| self.devices.get(i))
            .map(|d| d.name.clone())
            .unwrap_or_else(|| "Divoom".into());
        self.raw(
            "set_device_activity",
            json!({ "mac": mac, "kind": kind, "name": name, "preview": data_url }),
            "set_activity",
        );
        self.local_previews.insert(mac, data_url);
    }

    /// Resolve the active device's current preview data-url: a frame WE just pushed
    /// (local cache) wins; otherwise the daemon's recorded `get_device_activity`.
    fn current_preview_url(&self) -> Option<String> {
        let mac = self.active_mac()?;
        if let Some(u) = self.local_previews.get(&mac) {
            return Some(u.clone());
        }
        self.replies
            .get("device_activity")?
            .get("activity")?
            .get(&mac)?
            .get("preview")?
            .as_str()
            .filter(|s| s.starts_with("data:"))
            .map(|s| s.to_string())
    }

    /// Texture for the active device's preview, decoding (and caching) on change.
    /// `None` when there's nothing to show (fresh connect) → bezel placeholder.
    pub fn device_preview_texture(&mut self, ctx: &egui::Context) -> Option<egui::TextureHandle> {
        let url = self.current_preview_url()?;
        if let Some((k, t)) = &self.preview_tex {
            if *k == url {
                return Some(t.clone());
            }
        }
        let img = data_url_to_color_image(&url)?;
        // NEAREST: device screens are low-res pixel grids — crisp upscaling, no blur.
        let tex = ctx.load_texture("device_preview", img, egui::TextureOptions::NEAREST);
        self.preview_tex = Some((url, tex.clone()));
        Some(tex)
    }
}

/// Encode a `w*h` RGB pixel buffer (one `[r,g,b]` per pixel, row-major) as a
/// `data:image/png;base64,` URL — the exact form the web UI stores/sends.
pub fn rgb_to_data_url(w: u32, h: u32, pixels: &[[u8; 3]]) -> Option<String> {
    if pixels.len() != (w * h) as usize {
        return None;
    }
    let mut rgba = Vec::with_capacity(pixels.len() * 4);
    for p in pixels {
        rgba.extend_from_slice(&[p[0], p[1], p[2], 0xff]);
    }
    let img = image::RgbaImage::from_raw(w, h, rgba)?;
    let mut png: Vec<u8> = Vec::new();
    img.write_to(&mut std::io::Cursor::new(&mut png), image::ImageFormat::Png)
        .ok()?;
    let b64 = base64::engine::general_purpose::STANDARD.encode(&png);
    Some(format!("{PNG_DATA_URL_PREFIX}{b64}"))
}

/// Decode a `data:image/...;base64,` URL into an egui `ColorImage` ready for
/// `ctx.load_texture`. Tolerant of any image MIME the `image` crate decodes.
pub fn data_url_to_color_image(data_url: &str) -> Option<egui::ColorImage> {
    let b64 = data_url
        .strip_prefix(PNG_DATA_URL_PREFIX)
        .or_else(|| data_url.split_once(',').map(|(_, b)| b))?;
    let bytes = base64::engine::general_purpose::STANDARD
        .decode(b64.trim())
        .ok()?;
    let img = image::load_from_memory(&bytes).ok()?.to_rgba8();
    let (w, h) = img.dimensions();
    Some(egui::ColorImage::from_rgba_unmultiplied(
        [w as usize, h as usize],
        img.as_raw(),
    ))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn rgb_round_trips_through_data_url() {
        let px = vec![[10, 20, 30], [40, 50, 60], [70, 80, 90], [100, 110, 120]];
        let url = rgb_to_data_url(2, 2, &px).expect("encode");
        assert!(url.starts_with(PNG_DATA_URL_PREFIX));
        let img = data_url_to_color_image(&url).expect("decode");
        assert_eq!(img.size, [2, 2]);
        // Pixel (0,0) survives the PNG round-trip exactly (RGB, opaque alpha).
        let p0 = img.pixels[0];
        assert_eq!((p0.r(), p0.g(), p0.b(), p0.a()), (10, 20, 30, 255));
    }

    #[test]
    fn rejects_wrong_buffer_length() {
        assert!(rgb_to_data_url(2, 2, &[[0, 0, 0]]).is_none());
    }

    #[test]
    fn decodes_bare_and_prefixed_data_urls() {
        let url = rgb_to_data_url(1, 1, &[[1, 2, 3]]).unwrap();
        // Strip the mime prefix → a bare "...,base64" form is still accepted.
        let comma = url.find(',').unwrap();
        let bare = format!("data:,{}", &url[comma + 1..]);
        assert!(data_url_to_color_image(&bare).is_some());
        assert!(data_url_to_color_image("not a data url").is_none());
    }
}

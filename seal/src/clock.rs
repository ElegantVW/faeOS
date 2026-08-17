use rusttype::{Font, Scale};

pub struct ClockRenderer {
    font: Font<'static>,
    pub font_path: String,
}

impl ClockRenderer {
    pub fn new() -> Option<Self> {
        // Prefer mono so fae_termart box-drawing (╭─│╰) lines up.
        let font_paths = [
            "/usr/share/fonts/TTF/DejaVuSansMono.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
            "/usr/share/fonts/noto/NotoSansMono-Regular.ttf",
            "/usr/share/fonts/TTF/NotoSansMono-Regular.ttf",
            "/usr/share/fonts/liberation/LiberationMono-Regular.ttf",
            "/usr/share/fonts/TTF/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        ];
        for path in &font_paths {
            if let Ok(data) = std::fs::read(path) {
                if let Some(font) = Font::try_from_vec(data) {
                    return Some(Self {
                        font,
                        font_path: path.to_string(),
                    });
                }
            }
        }
        None
    }

    pub fn draw_text(
        &self,
        buf: &mut [u8],
        stride: u32,
        w: u32,
        h: u32,
        text: &str,
        x: i32,
        y: i32,
        scale: f32,
        r: u8,
        g: u8,
        b: u8,
    ) {
        let scale = Scale::uniform(scale);
        let v_metrics = self.font.v_metrics(scale);
        let offset = rusttype::point(0.0, v_metrics.ascent);

        for glyph in self.font.layout(text, scale, offset) {
            if let Some(bb) = glyph.pixel_bounding_box() {
                // rusttype coverage `v` is already 0.0..=1.0 (NOT 0..255).
                glyph.draw(|gx, gy, v| {
                    let a = v.clamp(0.0, 1.0);
                    if a < 0.01 {
                        return;
                    }
                    let px = x + gx as i32 + bb.min.x;
                    let py = y + gy as i32 + bb.min.y;
                    if px >= 0 && py >= 0 && (px as u32) < w && (py as u32) < h {
                        let idx = (py as u32 * stride + px as u32 * 3) as usize;
                        if idx + 2 < buf.len() {
                            buf[idx] = blend(buf[idx], r, a);
                            buf[idx + 1] = blend(buf[idx + 1], g, a);
                            buf[idx + 2] = blend(buf[idx + 2], b, a);
                        }
                    }
                });
            }
        }
    }

    pub fn text_width(&self, text: &str, scale: f32) -> u32 {
        let scale = Scale::uniform(scale);
        let mut adv = 0.0f32;
        for ch in text.chars() {
            let g = self.font.glyph(ch).scaled(scale);
            adv += g.h_metrics().advance_width;
        }
        adv.ceil().max(1.0) as u32
    }
}

fn blend(existing: u8, new: u8, alpha: f32) -> u8 {
    (new as f32 * alpha + existing as f32 * (1.0 - alpha)).round() as u8
}

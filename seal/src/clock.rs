use rusttype::{Font, Scale};

pub struct ClockRenderer {
    font: Font<'static>,
}

impl ClockRenderer {
    pub fn new() -> Option<Self> {
        let font_paths = [
            "/usr/share/fonts/TTF/DejaVuSansMono.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
            "/usr/share/fonts/TTF/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        ];
        for path in &font_paths {
            if let Ok(data) = std::fs::read(path) {
                if let Some(font) = Font::try_from_vec(data) {
                    return Some(Self { font });
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
                glyph.draw(|gx, gy, v| {
                    let px = x + gx as i32 + bb.min.x;
                    let py = y + gy as i32 + bb.min.y;
                    if px >= 0 && py >= 0 && (px as u32) < w && (py as u32) < h {
                        let a = v as f32 / 255.0;
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
        let mut width: f32 = 0.0;
        for glyph in self.font.layout(text, scale, rusttype::point(0.0, 0.0)) {
            if let Some(bb) = glyph.pixel_bounding_box() {
                width = width.max((bb.max.x + 1) as f32);
            }
        }
        width.ceil() as u32
    }
}

fn blend(existing: u8, new: u8, alpha: f32) -> u8 {
    (new as f32 * alpha + existing as f32 * (1.0 - alpha)) as u8
}

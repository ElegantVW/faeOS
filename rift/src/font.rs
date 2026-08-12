use rusttype::{Font as RusttypeFont, Scale};
use std::collections::HashMap;

pub struct Font {
    font: RusttypeFont<'static>,
    cache: HashMap<char, Option<Glyph>>,
    pub cell_w: u32,
    pub cell_h: u32,
    scale: Scale,
    ascent: i32,
}

pub struct Glyph {
    pub bitmap: Vec<u8>,
    pub w: u32,
    pub h: u32,
    pub x_off: i32,
    pub y_off: i32,
}

impl Font {
    pub fn new(size: f32) -> Option<Self> {
        let paths = [
            "/usr/share/fonts/TTF/DejaVuSansMono.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
            "/usr/share/fonts/TTF/DejaVuSans.ttf",
        ];

        let font = paths.iter().find_map(|p| {
            std::fs::read(p).ok().and_then(|d| RusttypeFont::try_from_vec(d))
        })?;

        let scale = Scale::uniform(size);
        let v = font.v_metrics(scale);
        let h = font.glyph('M').scaled(scale).h_metrics();
        let cw = h.advance_width.round() as u32;
        let ascent = v.ascent.round() as i32;
        let descent = (-v.descent).round() as u32;
        let ch = ascent as u32 + descent + 2;

        Some(Self {
            font, cache: HashMap::new(), cell_w: cw, cell_h: ch,
            scale, ascent,
        })
    }

    pub fn get_glyph(&mut self, ch: char) -> &Option<Glyph> {
        if !self.cache.contains_key(&ch) {
            let g = self.render(ch);
            self.cache.insert(ch, g);
        }
        self.cache.get(&ch).unwrap()
    }

    fn render(&self, ch: char) -> Option<Glyph> {
        let glyph = self.font.glyph(ch).scaled(self.scale);
        let pos = glyph.positioned(rusttype::point(0.0, 0.0));
        let bb = pos.pixel_bounding_box()?;

        let w = (bb.max.x - bb.min.x) as u32;
        let h = (bb.max.y - bb.min.y) as u32;
        let mut bitmap = vec![0u8; (w * h) as usize];

        pos.draw(|x, y, v| {
            let idx = (y as u32 * w + x as u32) as usize;
            if idx < bitmap.len() {
                bitmap[idx] = (v * 255.0) as u8;
            }
        });

        Some(Glyph { bitmap, w, h, x_off: bb.min.x, y_off: bb.min.y })
    }
}

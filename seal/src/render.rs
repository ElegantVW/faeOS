//! Minimal seal face: black screen + rounded crystal + hand termart.
//!
//! Imagine → chafa is a valid *bake* path for terminal apps; for this X11
//! lock face we hand-author mono art so it stays sharp (no chafa at runtime).

use crate::battery::BatteryInfo;
use crate::clock::ClockRenderer;
use crate::input::PasswordInput;
use crate::users::User;

/// Face phase.
#[derive(Clone, Copy, Debug)]
pub enum AnimPhase {
    Idle,
    /// After correct password: recolor then fade out. `t` is 0..1 over 1s.
    Unlock(f32),
}

const PINK: (u8, u8, u8) = (0xe8, 0x79, 0xa0);
const SILVER: (u8, u8, u8) = (0xc0, 0xc0, 0xc8);
const WHITE: (u8, u8, u8) = (0xff, 0xff, 0xff);
const DIM: (u8, u8, u8) = (0x9d, 0x5c, 0x75);

/// Symmetric crystal (fixed 15-column mono grid — each line same length).
/// Centering is per-line by measured advance; equal width keeps the shape true.
const FAE_SIGIL: &[&str] = &[
    "       *       ", // 15
    "      / \\      ",
    "     /   \\     ",
    "    /  +  \\    ",
    "   /       \\   ",
    "   \\       /   ",
    "    \\  |  /    ",
    "     \\ | /     ",
    "      \\|/      ",
    "       V       ",
];

pub struct FrameRenderer {
    pub width: u32,
    pub height: u32,
    pub stride: u32,
    pub buffer: Vec<u8>,
    clock: ClockRenderer,
    greeter: bool,
}

impl FrameRenderer {
    pub fn new(w: u32, h: u32) -> anyhow::Result<Self> {
        Self::new_with_mode(w, h, false)
    }

    pub fn new_with_mode(w: u32, h: u32, greeter: bool) -> anyhow::Result<Self> {
        let clock = ClockRenderer::new()
            .ok_or_else(|| anyhow::anyhow!("no font found for lock screen"))?;
        let stride = w * 3;
        Ok(Self {
            width: w,
            height: h,
            stride,
            buffer: vec![0u8; (stride * h) as usize],
            clock,
            greeter,
        })
    }

    pub fn burst_sparkles(&mut self) {}

    pub fn render_frame(
        &mut self,
        _message: &str,
        _battery: &BatteryInfo,
        input: &PasswordInput,
        _guest_enabled: bool,
        user_list: &[User],
        user_sel: usize,
        anim: AnimPhase,
    ) {
        let w = self.width;
        let h = self.height;
        self.buffer.fill(0);

        let (accent, body, mute, fade) = match anim {
            AnimPhase::Idle => (PINK, SILVER, DIM, 1.0_f32),
            AnimPhase::Unlock(t) => {
                let t = t.clamp(0.0, 1.0);
                let recolor = (t / 0.2).min(1.0);
                let fade = if t <= 0.2 {
                    1.0
                } else {
                    1.0 - ((t - 0.2) / 0.8).clamp(0.0, 1.0)
                };
                (
                    lerp(PINK, WHITE, recolor),
                    lerp(SILVER, WHITE, recolor),
                    lerp(DIM, WHITE, recolor),
                    fade,
                )
            }
        };

        if fade < 0.01 {
            return;
        }

        draw_face(
            &mut self.buffer,
            self.stride,
            &self.clock,
            w,
            h,
            dim(accent, fade),
            dim(body, fade),
            dim(mute, fade),
            self.greeter,
            input,
            user_list,
            user_sel,
        );
    }

    pub fn raw_pixels(&self) -> &[u8] {
        &self.buffer
    }
}

fn draw_face(
    buf: &mut [u8],
    stride: u32,
    cr: &ClockRenderer,
    w: u32,
    h: u32,
    accent: (u8, u8, u8),
    body: (u8, u8, u8),
    mute: (u8, u8, u8),
    greeter: bool,
    input: &PasswordInput,
    user_list: &[User],
    user_sel: usize,
) {
    // Outer rounded frame — large, centered on screen
    let box_w = ((w as f32) * 0.58).clamp(300.0, (w as f32 - 48.0).max(300.0)) as u32;
    let box_h = ((h as f32) * 0.72).clamp(340.0, (h as f32 - 40.0).max(340.0)) as u32;
    let bx = w.saturating_sub(box_w) / 2;
    let by = h.saturating_sub(box_h) / 2;
    let radius = ((box_h.min(box_w) as f32) * 0.09).clamp(20.0, 52.0) as u32;
    let thickness = ((box_h as f32) * 0.012).clamp(2.0, 4.0) as u32;

    stroke_rounded_rect(
        buf, stride, w, h, bx, by, box_w, box_h, radius, thickness, accent,
    );

    // Art: crystal + wordmark + user / password
    let word = if greeter { "welcome" } else { "faeOS" };
    let mut owned: Vec<String> = FAE_SIGIL.iter().map(|s| (*s).to_string()).collect();
    owned.push(String::new());
    owned.push(format!("* {word} *"));
    owned.push(String::new());

    let selected = user_list.get(user_sel);
    let uname = selected
        .map(|u| {
            if u.display.is_empty() {
                u.name.clone()
            } else {
                u.display.clone()
            }
        })
        .unwrap_or_else(|| "user".into());
    let user_line = if greeter && user_list.len() > 1 {
        format!("< {uname} >")
    } else {
        uname
    };
    owned.push(user_line);

    let pw_line = if input.is_empty() {
        if greeter {
            "password".to_string()
        } else {
            "••••".to_string()
        }
    } else {
        input.pretty_dots()
    };
    owned.push(pw_line);

    if input.caps_lock_on() {
        owned.push("caps".to_string());
    } else if greeter && user_list.len() > 1 {
        owned.push("tab users".to_string());
    }

    let lines: Vec<&str> = owned.iter().map(|s| s.as_str()).collect();

    // Fit inside rounded box with generous padding so corners don't clip
    let inner_w = box_w.saturating_sub(radius * 2 + 32);
    let inner_h = box_h.saturating_sub(radius * 2 + 48);
    let (scale, line_h, _art_w, art_h) = fit_art(cr, &lines, inner_w, inner_h);

    // Vertical center of the block inside the frame
    let ay = by as i32 + (box_h as i32 - art_h as i32) / 2;
    // Horizontal: center each line on the *frame* midpoint (not max-line-width box)
    // so uneven advances cannot shift the whole sigil.
    let mid_x = (bx + box_w / 2) as i32;

    let sigil_end = FAE_SIGIL.len(); // exclusive index of last sigil line
    let word_idx = sigil_end + 1;

    for (i, line) in lines.iter().enumerate() {
        if line.is_empty() {
            continue;
        }
        let y = ay + (i as f32 * line_h) as i32;
        let col = if i < sigil_end {
            if line.contains('*') || line.contains('+') || line.contains('V') {
                accent
            } else {
                mute
            }
        } else if i == word_idx {
            body
        } else if *line == "password" || *line == "••••" || *line == "caps" || *line == "tab users"
        {
            mute
        } else {
            // username or dots
            accent
        };
        let lw = cr.text_width(line, scale) as i32;
        let x = mid_x - lw / 2;
        cr.draw_text(buf, stride, w, h, line, x, y, scale, col.0, col.1, col.2);
    }
}

fn fit_art(
    cr: &ClockRenderer,
    lines: &[&str],
    max_w: u32,
    max_h: u32,
) -> (f32, f32, u32, u32) {
    let n = lines.iter().filter(|l| !l.is_empty()).count().max(1) + lines.iter().filter(|l| l.is_empty()).count();
    let n = n.max(lines.len()).max(1);
    // Prefer larger glyphs — crystal is the hero
    let mut scale = (max_h as f32 / (n as f32 * 1.22)).clamp(14.0, 48.0);
    for _ in 0..20 {
        let mut max_line_w = 1u32;
        for line in lines {
            if line.is_empty() {
                continue;
            }
            max_line_w = max_line_w.max(cr.text_width(line, scale));
        }
        let line_h = scale * 1.22;
        let art_h = (line_h * lines.len() as f32) as u32;
        if max_line_w <= max_w && art_h <= max_h {
            return (scale, line_h, max_line_w, art_h);
        }
        scale *= 0.92;
        if scale < 11.0 {
            let line_h = scale * 1.22;
            return (
                scale,
                line_h,
                max_line_w.min(max_w),
                (line_h * lines.len() as f32) as u32,
            );
        }
    }
    let line_h = scale * 1.22;
    (scale, line_h, max_w, max_h)
}

// ── rounded geometry ──────────────────────────────────────────────────

fn stroke_rounded_rect(
    buf: &mut [u8],
    stride: u32,
    sw: u32,
    sh: u32,
    x: u32,
    y: u32,
    bw: u32,
    bh: u32,
    radius: u32,
    thickness: u32,
    col: (u8, u8, u8),
) {
    let t = thickness.max(1);
    let r = radius.min(bw / 2).min(bh / 2).max(t + 1);

    // Straight edges (inset by r)
    // top
    fill_rect(buf, stride, sw, sh, x + r, y, bw.saturating_sub(r * 2), t, col);
    // bottom
    fill_rect(
        buf,
        stride,
        sw,
        sh,
        x + r,
        y + bh.saturating_sub(t),
        bw.saturating_sub(r * 2),
        t,
        col,
    );
    // left
    fill_rect(buf, stride, sw, sh, x, y + r, t, bh.saturating_sub(r * 2), col);
    // right
    fill_rect(
        buf,
        stride,
        sw,
        sh,
        x + bw.saturating_sub(t),
        y + r,
        t,
        bh.saturating_sub(r * 2),
        col,
    );

    // Corner centers
    let tl = (x + r, y + r);
    let tr = (x + bw.saturating_sub(r + 1), y + r);
    let bl = (x + r, y + bh.saturating_sub(r + 1));
    let br = (x + bw.saturating_sub(r + 1), y + bh.saturating_sub(r + 1));

    stroke_arc(buf, stride, sw, sh, tl.0, tl.1, r, t, true, true, col); // TL
    stroke_arc(buf, stride, sw, sh, tr.0, tr.1, r, t, false, true, col); // TR
    stroke_arc(buf, stride, sw, sh, bl.0, bl.1, r, t, true, false, col); // BL
    stroke_arc(buf, stride, sw, sh, br.0, br.1, r, t, false, false, col); // BR
}

/// Thick arc in one quadrant of a circle centered at (cx, cy).
fn stroke_arc(
    buf: &mut [u8],
    stride: u32,
    sw: u32,
    sh: u32,
    cx: u32,
    cy: u32,
    r: u32,
    t: u32,
    left: bool,
    top: bool,
    col: (u8, u8, u8),
) {
    let r = r as i32;
    let t = t as i32;
    let cx = cx as i32;
    let cy = cy as i32;
    let outer = r as f32;
    let inner = (r - t).max(0) as f32;

    let x0 = if left { cx - r - 1 } else { cx };
    let x1 = if left { cx + 1 } else { cx + r + 1 };
    let y0 = if top { cy - r - 1 } else { cy };
    let y1 = if top { cy + 1 } else { cy + r + 1 };

    for py in y0..y1 {
        for px in x0..x1 {
            if px < 0 || py < 0 {
                continue;
            }
            let dx = (px - cx) as f32;
            let dy = (py - cy) as f32;
            // quadrant check
            if left && dx > 0.5 {
                continue;
            }
            if !left && dx < -0.5 {
                continue;
            }
            if top && dy > 0.5 {
                continue;
            }
            if !top && dy < -0.5 {
                continue;
            }
            let d = (dx * dx + dy * dy).sqrt();
            if d <= outer + 0.6 && d >= inner - 0.4 {
                put(buf, stride, sw, sh, px, py, col);
            }
        }
    }
}

fn hline(
    buf: &mut [u8],
    stride: u32,
    w: u32,
    h: u32,
    x: u32,
    y: u32,
    len: u32,
    t: u32,
    col: (u8, u8, u8),
) {
    fill_rect(buf, stride, w, h, x, y, len, t.max(1), col);
}

fn fill_rect(
    buf: &mut [u8],
    stride: u32,
    w: u32,
    h: u32,
    x: u32,
    y: u32,
    bw: u32,
    bh: u32,
    col: (u8, u8, u8),
) {
    let x1 = x.saturating_add(bw).min(w);
    let y1 = y.saturating_add(bh).min(h);
    for py in y..y1 {
        for px in x..x1 {
            let idx = (py * stride + px * 3) as usize;
            if idx + 2 < buf.len() {
                buf[idx] = col.0;
                buf[idx + 1] = col.1;
                buf[idx + 2] = col.2;
            }
        }
    }
}

fn put(buf: &mut [u8], stride: u32, w: u32, h: u32, x: i32, y: i32, col: (u8, u8, u8)) {
    if x < 0 || y < 0 || x as u32 >= w || y as u32 >= h {
        return;
    }
    let idx = (y as u32 * stride + x as u32 * 3) as usize;
    if idx + 2 < buf.len() {
        buf[idx] = col.0;
        buf[idx + 1] = col.1;
        buf[idx + 2] = col.2;
    }
}

fn lerp(a: (u8, u8, u8), b: (u8, u8, u8), t: f32) -> (u8, u8, u8) {
    let t = t.clamp(0.0, 1.0);
    (
        (a.0 as f32 + (b.0 as f32 - a.0 as f32) * t) as u8,
        (a.1 as f32 + (b.1 as f32 - a.1 as f32) * t) as u8,
        (a.2 as f32 + (b.2 as f32 - a.2 as f32) * t) as u8,
    )
}

fn dim(c: (u8, u8, u8), fade: f32) -> (u8, u8, u8) {
    let f = fade.clamp(0.0, 1.0);
    (
        (c.0 as f32 * f) as u8,
        (c.1 as f32 * f) as u8,
        (c.2 as f32 * f) as u8,
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::battery::BatteryInfo;
    use crate::input::PasswordInput;

    #[test]
    fn idle_frame_is_not_blank() {
        let mut fr = FrameRenderer::new_with_mode(800, 600, false).expect("font");
        let bat = BatteryInfo {
            present: false,
            capacity: 0,
            on_ac: true,
        };
        let pw = PasswordInput::new();
        fr.render_frame("", &bat, &pw, false, &[], 0, AnimPhase::Idle);
        let lit = fr
            .buffer
            .chunks_exact(3)
            .filter(|c| c[0] | c[1] | c[2] != 0)
            .count();
        assert!(
            lit > 800,
            "expected visible rounded frame + termart, got {lit} lit pixels"
        );
    }
}

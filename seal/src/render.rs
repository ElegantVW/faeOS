use crate::battery::BatteryInfo;
use crate::clock::ClockRenderer;
use crate::input::PasswordInput;
use crate::users::User;
use chrono::Local;
use rand::Rng;

static BG: (u8, u8, u8) = (0x1a, 0x0a, 0x12);
static PINK: (u8, u8, u8) = (0xe8, 0x79, 0xa0);
static HOT_PINK: (u8, u8, u8) = (0xff, 0x2d, 0x55);
static DARK_PINK: (u8, u8, u8) = (0xc4, 0x4d, 0x7a);
static DIM_PINK: (u8, u8, u8) = (0x9d, 0x5c, 0x75);
static SILVER: (u8, u8, u8) = (0xc0, 0xc0, 0xc8);
static GREEN: (u8, u8, u8) = (0x3d, 0xd6, 0x8c);

pub struct FrameRenderer {
    pub width: u32,
    pub height: u32,
    pub stride: u32,
    pub buffer: Vec<u8>,
    clock: ClockRenderer,
    particles: Vec<Particle>,
    tick: u64,
}

struct Particle {
    x: f32,
    y: f32,
    vx: f32,
    vy: f32,
    life: u8,
    brightness: u8,
}

impl FrameRenderer {
    pub fn new(w: u32, h: u32) -> anyhow::Result<Self> {
        let clock = ClockRenderer::new()
            .ok_or_else(|| anyhow::anyhow!("no font found for lock screen"))?;

        let stride = w * 3;
        let buffer = vec![0u8; (stride * h) as usize];

        let mut rng = rand::thread_rng();
        let mut particles = Vec::with_capacity(30);
        for _ in 0..30 {
            particles.push(Particle {
                x: rng.gen_range(0.0..w as f32),
                y: rng.gen_range(0.0..h as f32),
                vx: rng.gen_range(-0.3..0.3),
                vy: rng.gen_range(-0.6..-0.1),
                life: rng.gen_range(0..120),
                brightness: rng.gen_range(60..180),
            });
        }

        Ok(Self {
            width: w,
            height: h,
            stride,
            buffer,
            clock,
            particles,
            tick: 0,
        })
    }

    pub fn render_frame(
        &mut self,
        message: &str,
        battery: &BatteryInfo,
        input: &PasswordInput,
        guest_enabled: bool,
        user_list: &[User],
        user_sel: usize,
    ) {
        self.tick += 1;
        let w = self.width;
        let h = self.height;

        draw_background(&mut self.buffer, self.stride, w, h);

        scanlines(&mut self.buffer, self.stride, w, h);

        update_particles(&mut self.particles, w, h);
        draw_particles(&mut self.buffer, self.stride, &self.particles, w);

        let sigil_opacity = 0.4 + 0.15 * (self.tick as f32 * 0.03).sin();
        draw_sigil(
            &mut self.buffer,
            self.stride,
            &self.clock,
            w,
            h,
            sigil_opacity,
        );

        draw_clock(&mut self.buffer, self.stride, &self.clock, w, h);
        draw_date(&mut self.buffer, self.stride, &self.clock, w, h);

        if user_list.len() > 1 {
            draw_user_panel(&mut self.buffer, self.stride, &self.clock, w, h, user_list, user_sel);
        }

        let msg = if message.is_empty() {
            "away gathering moonlight..."
        } else {
            message
        };
        draw_message(&mut self.buffer, self.stride, &self.clock, w, h, msg);

        if input.has_error() {
            draw_password_box(
                &mut self.buffer,
                self.stride,
                &self.clock,
                w,
                h,
                input,
                HOT_PINK,
            );
        } else {
            draw_password_box(
                &mut self.buffer,
                self.stride,
                &self.clock,
                w,
                h,
                input,
                PINK,
            );
        }

        if input.caps_lock_on() {
            draw_caps_warning(&mut self.buffer, self.stride, &self.clock, w, h);
        }

        draw_status_bar(&mut self.buffer, self.stride, &self.clock, w, h, battery);

        if guest_enabled {
            draw_guest_hint(&mut self.buffer, self.stride, &self.clock, w, h);
        }
    }

    pub fn raw_pixels(&self) -> &[u8] {
        &self.buffer
    }
}

fn draw_background(buf: &mut [u8], stride: u32, w: u32, h: u32) {
    let mut rng = rand::thread_rng();
    for y in 0..h {
        for x in 0..w {
            let noise: u8 = rng.gen_range(0..6);
            let idx = (y * stride + x * 3) as usize;
            buf[idx] = BG.0.saturating_add(noise);
            buf[idx + 1] = BG.1.saturating_add(noise);
            buf[idx + 2] = BG.2.saturating_add(noise);
        }
    }
}

fn scanlines(buf: &mut [u8], stride: u32, w: u32, h: u32) {
    for y in (0..h).step_by(3) {
        for x in 0..w {
            let idx = (y * stride + x * 3) as usize;
            buf[idx] = (buf[idx] as f32 * 0.85) as u8;
            buf[idx + 1] = (buf[idx + 1] as f32 * 0.85) as u8;
            buf[idx + 2] = (buf[idx + 2] as f32 * 0.85) as u8;
        }
    }
}

fn update_particles(particles: &mut Vec<Particle>, w: u32, h: u32) {
    let mut rng = rand::thread_rng();
    for p in particles.iter_mut() {
        p.x += p.vx;
        p.y += p.vy;
        if p.life > 0 {
            p.life -= 1;
        }
        if p.y < -10.0 || p.life == 0 {
            p.x = rng.gen_range(0.0..w as f32);
            p.y = h as f32 + 10.0;
            p.vx = rng.gen_range(-0.3..0.3);
            p.vy = rng.gen_range(-0.8..-0.2);
            p.life = rng.gen_range(60..200);
            p.brightness = rng.gen_range(40..160);
        }
    }
}

fn draw_particles(buf: &mut [u8], stride: u32, particles: &[Particle], w: u32) {
    for p in particles {
        let px = p.x as i32;
        let py = p.y as i32;
        if px < 0 || py < 0 || px as u32 >= w {
            continue;
        }
        let idx = (py as u32 * stride + px as u32 * 3) as usize;
        if idx + 2 < buf.len() {
            let a = p.brightness as f32 / 255.0;
            buf[idx] = blend(buf[idx], PINK.0, a);
            buf[idx + 1] = blend(buf[idx + 1], PINK.1, a);
            buf[idx + 2] = blend(buf[idx + 2], PINK.2, a);
        }
    }
}

fn draw_sigil(
    buf: &mut [u8],
    stride: u32,
    cr: &ClockRenderer,
    w: u32,
    h: u32,
    opacity: f32,
) {
    let sigil = "\u{2726}  faeOS  \u{2726}";
    let scale = (w as f32 * 0.05).clamp(28.0, 72.0);
    let tw = cr.text_width(sigil, scale);
    let x = (w as i32 - tw as i32) / 2;
    let y = (h as f32 * 0.08) as i32;

    let r = (DIM_PINK.0 as f32 * opacity) as u8;
    let g = (DIM_PINK.1 as f32 * opacity) as u8;
    let b = (DIM_PINK.2 as f32 * opacity) as u8;

    cr.draw_text(buf, stride, w, h, sigil, x, y, scale, r, g, b);
}

fn draw_clock(buf: &mut [u8], stride: u32, cr: &ClockRenderer, w: u32, h: u32) {
    let now = Local::now();
    let time = now.format("%H:%M").to_string();
    let scale = (w as f32 * 0.14).clamp(80.0, 220.0);
    let tw = cr.text_width(&time, scale);
    let x = (w as i32 - tw as i32) / 2;
    let y = (h as f32 * 0.22) as i32;
    cr.draw_text(buf, stride, w, h, &time, x, y, scale, PINK.0, PINK.1, PINK.2);
}

fn draw_date(buf: &mut [u8], stride: u32, cr: &ClockRenderer, w: u32, h: u32) {
    let now = Local::now();
    let date = now.format("%A, %B %d").to_string();
    let scale = (w as f32 * 0.025).clamp(18.0, 36.0);
    let tw = cr.text_width(&date, scale);
    let x = (w as i32 - tw as i32) / 2;
    let y = (h as f32 * 0.38) as i32;
    cr.draw_text(
        buf, stride, w, h, &date, x, y, scale,
        DARK_PINK.0, DARK_PINK.1, DARK_PINK.2,
    );
}

fn draw_message(
    buf: &mut [u8],
    stride: u32,
    cr: &ClockRenderer,
    w: u32,
    h: u32,
    msg: &str,
) {
    let scale = (w as f32 * 0.018).clamp(16.0, 28.0);
    let tw = cr.text_width(msg, scale);
    let x = (w as i32 - tw as i32) / 2;
    let y = (h as f32 * 0.47) as i32;
    cr.draw_text(
        buf, stride, w, h, msg, x, y, scale,
        SILVER.0, SILVER.1, SILVER.2,
    );
}

fn draw_user_panel(
    buf: &mut [u8],
    stride: u32,
    cr: &ClockRenderer,
    w: u32,
    h: u32,
    user_list: &[User],
    user_sel: usize,
) {
    let py = (h as f32 * 0.46) as i32;
    let scale = (w as f32 * 0.018).clamp(16.0, 26.0);
    let line_h = (scale * 1.6) as i32;

    for (i, user) in user_list.iter().enumerate() {
        let y: i32 = py + (i as i32 * line_h) + 8;
        let init = user.name.chars().next().unwrap_or('?').to_uppercase().collect::<String>();
        let label = format!("{}  {}", init, user.display);
        let tw = cr.text_width(&label, scale);
        let x = (w as i32 - tw as i32) / 2;

        let color = if i == user_sel {
            (PINK.0, PINK.1, PINK.2)
        } else {
            (DIM_PINK.0, DIM_PINK.1, DIM_PINK.2)
        };

        cr.draw_text(buf, stride, w, h, &label, x, y, scale, color.0, color.1, color.2);
    }
}

fn draw_password_box(
    buf: &mut [u8],
    stride: u32,
    cr: &ClockRenderer,
    w: u32,
    h: u32,
    input: &PasswordInput,
    border_color: (u8, u8, u8),
) {
    let box_w = (w as f32 * 0.4).clamp(260.0, 500.0) as u32;
    let box_h: u32 = 44;
    let bx = (w - box_w) / 2;
    let by = (h as f32 * 0.57) as u32;

    let r = border_color.0;
    let g = border_color.1;
    let b = border_color.2;
    let dim = (DIM_PINK.0, DIM_PINK.1, DIM_PINK.2);

    for py in by..by + box_h {
        for px in bx..bx + box_w {
            let idx = (py * stride + px * 3) as usize;
            if idx + 2 >= buf.len() {
                continue;
            }

            let mut rr = BG.0;
            let mut gg = BG.1;
            let mut bb = BG.2;

            let border = 2u32;
            if py < by + border
                || py >= by + box_h - border
                || px < bx + border
                || px >= bx + box_w - border
            {
                rr = r;
                gg = g;
                bb = b;
            }

            if px >= bx + 8 && px < bx + box_w - 4 && py > by + border && py < by + box_h - border
            {
                rr = 0x2a;
                gg = 0x15;
                bb = 0x20;
            }

            buf[idx] = rr;
            buf[idx + 1] = gg;
            buf[idx + 2] = bb;
        }
    }

    let dots = if input.is_empty() {
        "type password".to_string()
    } else {
        input.dots()
    };

    let dot_color = if input.has_error() {
        HOT_PINK
    } else {
        PINK
    };
    let scale = (box_h as f32 * 0.45).clamp(14.0, 22.0);

    if input.is_empty() {
        let tw = cr.text_width(&dots, scale);
        let dx = (w as i32 - tw as i32) / 2;
        cr.draw_text(
            buf, stride, w, h, &dots, dx, (by + 12) as i32, scale,
            dim.0, dim.1, dim.2,
        );
    } else {
        let tw = cr.text_width(&dots, scale);
        let dx = (w as i32 - tw as i32) / 2;
        cr.draw_text(
            buf, stride, w, h, &dots, dx, (by + 12) as i32, scale,
            dot_color.0, dot_color.1, dot_color.2,
        );
    }
}

fn draw_caps_warning(
    buf: &mut [u8],
    stride: u32,
    cr: &ClockRenderer,
    w: u32,
    h: u32,
) {
    let text = "CAPS LOCK ON";
    let scale = (w as f32 * 0.016).clamp(12.0, 20.0);
    let tw = cr.text_width(text, scale);
    let x = (w as i32 - tw as i32) / 2;
    let y = (h as f32 * 0.67) as i32;
    cr.draw_text(
        buf, stride, w, h, text, x, y, scale,
        HOT_PINK.0, HOT_PINK.1, HOT_PINK.2,
    );
}

fn draw_guest_hint(
    buf: &mut [u8],
    stride: u32,
    cr: &ClockRenderer,
    w: u32,
    h: u32,
) {
    let text = "\u{25c7}  guest session available  \u{25c7}";
    let scale = (w as f32 * 0.015).clamp(14.0, 22.0);
    let tw = cr.text_width(text, scale);
    let x = (w as i32 - tw as i32) / 2;
    let y = (h as f32 * 0.73) as i32;
    cr.draw_text(
        buf, stride, w, h, text, x, y, scale,
        GREEN.0, GREEN.1, GREEN.2,
    );
}

fn draw_status_bar(
    buf: &mut [u8],
    stride: u32,
    cr: &ClockRenderer,
    w: u32,
    h: u32,
    battery: &BatteryInfo,
) {
    let bar_h: u32 = (h as f32 * 0.05) as u32;
    let bar_y = h - bar_h;

    for py in bar_y..h {
        for px in 0..w {
            let idx = (py * stride + px * 3) as usize;
            if idx + 2 < buf.len() {
                buf[idx] = (buf[idx] as f32 * 0.6) as u8;
                buf[idx + 1] = (buf[idx + 1] as f32 * 0.6) as u8;
                buf[idx + 2] = (buf[idx + 2] as f32 * 0.6) as u8;
            }
        }
    }

    let scale = (bar_h as f32 * 0.55).clamp(12.0, 20.0);
    let mut x: i32 = 16;

    if battery.present {
        let power = if battery.on_ac {
            "\u{26a1} AC"
        } else {
            "\u{25a2}"
        };
        let text = format!("{} {:3}%", power, battery.capacity);
        cr.draw_text(
            buf, stride, w, h, &text, x, (bar_y + 4) as i32, scale,
            PINK.0, PINK.1, PINK.2,
        );
        x += cr.text_width(&text, scale) as i32 + 20;
    }

    let hint = "\u{2726} esc clear  \u{2726} enter unlock";
    cr.draw_text(
        buf, stride, w, h, hint, x, (bar_y + 4) as i32, scale,
        DIM_PINK.0, DIM_PINK.1, DIM_PINK.2,
    );
}

fn blend(existing: u8, new: u8, alpha: f32) -> u8 {
    (new as f32 * alpha + existing as f32 * (1.0 - alpha)) as u8
}

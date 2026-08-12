use crate::battery::BatteryInfo;
use crate::clock::ClockRenderer;
use chrono::Local;
use image::{Rgb, RgbImage};
use rand::Rng;

const BG: Rgb<u8> = Rgb([0x1a, 0x0a, 0x12]);
const PINK: Rgb<u8> = Rgb([0xe8, 0x79, 0xa0]);
const HOT_PINK: Rgb<u8> = Rgb([0xff, 0x2d, 0x55]);
const DARK_PINK: Rgb<u8> = Rgb([0xc4, 0x4d, 0x7a]);
const DIM_PINK: Rgb<u8> = Rgb([0x9d, 0x5c, 0x75]);
const CREAM: Rgb<u8> = Rgb([0xff, 0xe3, 0xee]);
const SILVER: Rgb<u8> = Rgb([0xc0, 0xc0, 0xc8]);
const GREEN: Rgb<u8> = Rgb([0x3d, 0xd6, 0x8c]);

pub fn get_screen_size() -> (u32, u32) {
    std::process::Command::new("xrandr")
        .output()
        .ok()
        .and_then(|out| {
            let s = String::from_utf8_lossy(&out.stdout);
            for line in s.lines() {
                if line.contains(" connected") {
                    if let Some(res) = line.split_whitespace().find(|w| w.contains('x') && w.chars().next().map_or(false, |c| c.is_ascii_digit())) {
                        let parts: Vec<&str> = res.split('x').collect();
                        if parts.len() == 2 {
                            let w: u32 = parts[0].parse().ok()?;
                            let h: u32 = parts[1].split('+').next()?.parse().ok()?;
                            return Some((w, h));
                        }
                    }
                }
            }
            None
        })
        .unwrap_or((1920, 1080))
}

pub fn generate(
    message: &str,
    battery: &BatteryInfo,
    guest_enabled: bool,
) -> anyhow::Result<Vec<u8>> {
    let renderer = ClockRenderer::new()
        .ok_or_else(|| anyhow::anyhow!("no font found"))?;

    let (w, h) = get_screen_size();
    let mut img = RgbImage::new(w, h);

    draw_background(&mut img, w, h);
    draw_scanlines(&mut img, w, h);
    draw_sigil(&mut img, &renderer, w, h);
    draw_clock(&mut img, &renderer, w, h);
    draw_date(&mut img, &renderer, w, h);
    draw_message(&mut img, &renderer, w, h, message);
    draw_guest_hint(&mut img, &renderer, w, h, guest_enabled);
    draw_status_bar(&mut img, &renderer, w, h, battery);

    let mut buf = Vec::new();
    img.write_to(
        &mut std::io::Cursor::new(&mut buf),
        image::ImageFormat::Png,
    )?;
    Ok(buf)
}

fn draw_background(img: &mut RgbImage, w: u32, h: u32) {
    let mut rng = rand::thread_rng();
    for y in 0..h {
        for x in 0..w {
            let noise: u8 = rng.gen_range(0..6);
            let r = BG[0].saturating_add(noise);
            let g = BG[1].saturating_add(noise);
            let b = BG[2].saturating_add(noise);
            img.put_pixel(x, y, Rgb([r, g, b]));
        }
    }
}

fn draw_scanlines(img: &mut RgbImage, w: u32, h: u32) {
    for y in (0..h).step_by(3) {
        for x in 0..w {
            let px = img.get_pixel(x, y);
            let r = (px[0] as f32 * 0.85) as u8;
            let g = (px[1] as f32 * 0.85) as u8;
            let b = (px[2] as f32 * 0.85) as u8;
            img.put_pixel(x, y, Rgb([r, g, b]));
        }
    }
}

fn draw_sigil(img: &mut RgbImage, renderer: &ClockRenderer, w: u32, h: u32) {
    let sigil = "\u{2726}  faeOS  \u{2726}";
    let scale = (w as f32 * 0.05).clamp(28.0, 72.0);
    let tw = renderer.text_width(sigil, scale);
    let x = (w as i32 - tw as i32) / 2;
    let y = (h as f32 * 0.12) as i32;
    renderer.draw_text(img, sigil, x, y, scale, DIM_PINK);
}

fn draw_clock(img: &mut RgbImage, renderer: &ClockRenderer, w: u32, _h: u32) {
    let now = Local::now();
    let time = now.format("%H:%M").to_string();
    let scale = (w as f32 * 0.12).clamp(80.0, 200.0);
    let tw = renderer.text_width(&time, scale);
    let x = (w as i32 - tw as i32) / 2;
    let y = (_h as f32 * 0.30) as i32;
    renderer.draw_text(img, &time, x, y, scale, PINK);
}

fn draw_date(img: &mut RgbImage, renderer: &ClockRenderer, w: u32, _h: u32) {
    let now = Local::now();
    let date = now.format("%A, %B %d").to_string();
    let scale = (w as f32 * 0.025).clamp(18.0, 36.0);
    let tw = renderer.text_width(&date, scale);
    let x = (w as i32 - tw as i32) / 2;
    let y = (_h as f32 * 0.42) as i32;
    renderer.draw_text(img, &date, x, y, scale, DARK_PINK);
}

fn draw_message(img: &mut RgbImage, renderer: &ClockRenderer, w: u32, _h: u32, msg: &str) {
    let text = if msg.is_empty() {
        "away gathering moonlight..."
    } else {
        msg
    };
    let scale = (w as f32 * 0.018).clamp(16.0, 28.0);
    let tw = renderer.text_width(text, scale);
    let x = (w as i32 - tw as i32) / 2;
    let y = (_h as f32 * 0.55) as i32;
    renderer.draw_text(img, text, x, y, scale, SILVER);
}

fn draw_guest_hint(img: &mut RgbImage, renderer: &ClockRenderer, w: u32, _h: u32, guest: bool) {
    if !guest {
        return;
    }
    let text = "\u{25c7}  Guest session available  \u{25c7}";
    let scale = (w as f32 * 0.015).clamp(14.0, 22.0);
    let tw = renderer.text_width(text, scale);
    let x = (w as i32 - tw as i32) / 2;
    let y = (_h as f32 * 0.65) as i32;
    renderer.draw_text(img, text, x, y, scale, GREEN);
}

fn draw_status_bar(img: &mut RgbImage, renderer: &ClockRenderer, w: u32, h: u32, battery: &BatteryInfo) {
    let bar_h = (h as f32 * 0.06) as u32;
    let bar_y = h - bar_h;

    for y in bar_y..h {
        for x in 0..w {
            let px = img.get_pixel(x, y);
            let r = (px[0] as f32 * 0.6) as u8;
            let g = (px[1] as f32 * 0.6) as u8;
            let b = (px[2] as f32 * 0.6) as u8;
            img.put_pixel(x, y, Rgb([r, g, b]));
        }
    }

    let mut left_texts: Vec<(String, Rgb<u8>)> = Vec::new();

    if battery.present {
        let power = if battery.on_ac { "\u{26a1} AC" } else { "\u{25a2}" };
        left_texts.push((format!("{} {:3}%", power, battery.capacity), PINK));
    }

    let scale = (bar_h as f32 * 0.55).clamp(14.0, 22.0);
    let mut x = 20i32;

    for (text, color) in &left_texts {
        renderer.draw_text(img, text, x, (bar_y + 4) as i32, scale, *color);
        x += renderer.text_width(text, scale) as i32 + 20;
    }

    let unlock_hint = "\u{2726} type password to unlock \u{2726}";
    let tw = renderer.text_width(unlock_hint, scale);
    let xc = (w as i32 - tw as i32) / 2;
    renderer.draw_text(img, unlock_hint, xc, (bar_y + 4) as i32, scale, DIM_PINK);
}

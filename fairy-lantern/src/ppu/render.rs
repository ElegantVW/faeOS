//! Scanline renderers.

use super::{HEIGHT, WIDTH};
use crate::bus::Bus;

pub fn render_scanline(bus: &Bus, y: usize, frame: &mut [u16]) {
    if y >= HEIGHT {
        return;
    }
    let dispcnt = bus.dispcnt();
    let mode = dispcnt & 7;
    // Forced blank
    if dispcnt & 0x80 != 0 {
        let row = &mut frame[y * WIDTH..(y + 1) * WIDTH];
        row.fill(0);
        return;
    }
    match mode {
        3 => mode3(bus, y, frame),
        4 => mode4(bus, y, frame, dispcnt),
        _ => {
            // Unimplemented modes: dark magenta so we see *something*
            let row = &mut frame[y * WIDTH..(y + 1) * WIDTH];
            row.fill(0x8010);
        }
    }
}

fn mode3(bus: &Bus, y: usize, frame: &mut [u16]) {
    let base = y * WIDTH * 2;
    for x in 0..WIDTH {
        let off = base + x * 2;
        let lo = bus.vram.get(off).copied().unwrap_or(0) as u16;
        let hi = bus.vram.get(off + 1).copied().unwrap_or(0) as u16;
        frame[y * WIDTH + x] = lo | (hi << 8);
    }
}

fn mode4(bus: &Bus, y: usize, frame: &mut [u16], dispcnt: u16) {
    let page = if dispcnt & 0x10 != 0 { 0xA000 } else { 0 };
    let base = page + y * WIDTH;
    for x in 0..WIDTH {
        let idx = bus.vram.get(base + x).copied().unwrap_or(0) as usize;
        let pal_off = idx * 2;
        let lo = bus.pal.get(pal_off).copied().unwrap_or(0) as u16;
        let hi = bus.pal.get(pal_off + 1).copied().unwrap_or(0) as u16;
        frame[y * WIDTH + x] = lo | (hi << 8);
    }
}

/// Convert BGR555 frame to RGB888 bytes.
pub fn frame_to_rgb(frame: &[u16]) -> Vec<u8> {
    let mut out = Vec::with_capacity(WIDTH * HEIGHT * 3);
    for &p in frame.iter().take(WIDTH * HEIGHT) {
        let r = ((p & 0x1F) as u8) << 3;
        let g = (((p >> 5) & 0x1F) as u8) << 3;
        let b = (((p >> 10) & 0x1F) as u8) << 3;
        out.push(r);
        out.push(g);
        out.push(b);
    }
    out
}

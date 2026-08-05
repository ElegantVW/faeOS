//! Scanline renderers — Mode 0–2 (tiles), 3–5 (bitmap), + OBJ sprites.

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
        fill_row(frame, y, 0);
        return;
    }
    // Backdrop = palette 0
    let backdrop = pal_color(bus, 0);
    fill_row(frame, y, backdrop);

    match mode {
        0 => {
            // Text BGs 0–3 by priority
            for prio in (0..4).rev() {
                for bg in 0..4u16 {
                    if dispcnt & (1 << (8 + bg)) == 0 {
                        continue;
                    }
                    let cnt = bg_cnt(bus, bg);
                    if (cnt & 3) as u8 != prio {
                        continue;
                    }
                    render_text_bg(bus, bg, y, frame, cnt);
                }
            }
        }
        1 => {
            // BG0/1 text, BG2 affine
            for prio in (0..4).rev() {
                for bg in 0..2u16 {
                    if dispcnt & (1 << (8 + bg)) == 0 {
                        continue;
                    }
                    let cnt = bg_cnt(bus, bg);
                    if (cnt & 3) as u8 != prio {
                        continue;
                    }
                    render_text_bg(bus, bg, y, frame, cnt);
                }
            }
            if dispcnt & (1 << 10) != 0 {
                render_affine_bg(bus, 2, y, frame);
            }
        }
        2 => {
            if dispcnt & (1 << 10) != 0 {
                render_affine_bg(bus, 2, y, frame);
            }
            if dispcnt & (1 << 11) != 0 {
                render_affine_bg(bus, 3, y, frame);
            }
        }
        3 => mode3(bus, y, frame),
        4 => mode4(bus, y, frame, dispcnt),
        5 => mode5(bus, y, frame, dispcnt),
        _ => {}
    }

    // OBJ layer if enabled
    if dispcnt & (1 << 12) != 0 {
        render_sprites(bus, y, frame, dispcnt);
    }
}

fn fill_row(frame: &mut [u16], y: usize, color: u16) {
    let row = &mut frame[y * WIDTH..(y + 1) * WIDTH];
    row.fill(color);
}

fn bg_cnt(bus: &Bus, bg: u16) -> u16 {
    bus.read16(0x0400_0008 + bg as u32 * 2)
}

fn bg_offsets(bus: &Bus, bg: u16) -> (u16, u16) {
    let base = 0x0400_0010 + bg as u32 * 4;
    (bus.read16(base) & 0x1FF, bus.read16(base + 2) & 0x1FF)
}

fn pal_color(bus: &Bus, index: usize) -> u16 {
    let off = index * 2;
    let lo = bus.pal.get(off).copied().unwrap_or(0) as u16;
    let hi = bus.pal.get(off + 1).copied().unwrap_or(0) as u16;
    lo | (hi << 8)
}

fn vram_u8(bus: &Bus, off: usize) -> u8 {
    bus.vram.get(off).copied().unwrap_or(0)
}

fn vram_u16(bus: &Bus, off: usize) -> u16 {
    let lo = vram_u8(bus, off) as u16;
    let hi = vram_u8(bus, off + 1) as u16;
    lo | (hi << 8)
}

/// Mode 0/1 text background scanline.
fn render_text_bg(bus: &Bus, bg: u16, y: usize, frame: &mut [u16], cnt: u16) {
    let char_base = ((cnt >> 2) & 3) as usize * 0x4000;
    let screen_base = ((cnt >> 8) & 0x1F) as usize * 0x800;
    let color256 = cnt & (1 << 7) != 0;
    let size = (cnt >> 14) & 3;
    let (map_w, map_h) = match size {
        0 => (32usize, 32usize),
        1 => (64, 32),
        2 => (32, 64),
        _ => (64, 64),
    };

    let (hofs, vofs) = bg_offsets(bus, bg);
    let fy = (y + vofs as usize) & (map_h * 8 - 1);
    let ty = fy / 8;
    let y_in_tile = fy % 8;

    for x in 0..WIDTH {
        let fx = (x + hofs as usize) & (map_w * 8 - 1);
        let tx = fx / 8;
        let x_in_tile = fx % 8;

        // screenblock layout for 512-wide: 2 blocks side by side
        let (sb_x, sb_y, local_tx, local_ty) = if map_w == 64 {
            let sx = tx / 32;
            let lx = tx % 32;
            if map_h == 64 {
                let sy = ty / 32;
                let ly = ty % 32;
                (sx, sy, lx, ly)
            } else {
                (sx, 0, lx, ty)
            }
        } else if map_h == 64 {
            let sy = ty / 32;
            let ly = ty % 32;
            (0, sy, tx, ly)
        } else {
            (0, 0, tx, ty)
        };

        let map_index = screen_base
            + (sb_y * 2 + sb_x) * 0x800
            + (local_ty * 32 + local_tx) * 2;
        let entry = vram_u16(bus, map_index);
        let tile_id = (entry & 0x3FF) as usize;
        let hflip = entry & (1 << 10) != 0;
        let vflip = entry & (1 << 11) != 0;
        let pal_bank = ((entry >> 12) & 0xF) as usize;

        let px = if hflip { 7 - x_in_tile } else { x_in_tile };
        let py = if vflip { 7 - y_in_tile } else { y_in_tile };

        let color = if color256 {
            let tile_off = char_base + tile_id * 64 + py * 8 + px;
            let idx = vram_u8(bus, tile_off) as usize;
            if idx == 0 {
                continue; // transparent
            }
            pal_color(bus, idx)
        } else {
            let tile_off = char_base + tile_id * 32 + py * 4 + px / 2;
            let byte = vram_u8(bus, tile_off);
            let idx = if px & 1 == 0 {
                byte & 0xF
            } else {
                byte >> 4
            } as usize;
            if idx == 0 {
                continue;
            }
            pal_color(bus, pal_bank * 16 + idx)
        };
        frame[y * WIDTH + x] = color;
    }
}

/// Affine BG2/BG3 (Mode 1/2) — simplified integer transform.
fn render_affine_bg(bus: &Bus, bg: u16, y: usize, frame: &mut [u16]) {
    let cnt = bg_cnt(bus, bg);
    let char_base = ((cnt >> 2) & 3) as usize * 0x4000;
    let screen_base = ((cnt >> 8) & 0x1F) as usize * 0x800;
    let size = (cnt >> 14) & 3;
    let dim = 16usize << size; // tiles across: 16/32/64/128

    // PA,PB,PC,PD and x/y ref — 8.8 fixed
    let base = if bg == 2 {
        0x0400_0020u32
    } else {
        0x0400_0030
    };
    let pa = bus.read16(base) as i16 as i32;
    let pb = bus.read16(base + 2) as i16 as i32;
    let pc = bus.read16(base + 4) as i16 as i32;
    let pd = bus.read16(base + 6) as i16 as i32;
    // reference point 24.8 — we store simplified from IO
    let x_raw = bus.read32(base + 8) as i32;
    let y_raw = bus.read32(base + 0xC) as i32;
    // GBA uses internal ref that increments; approximate per-scanline
    let mut rx = x_raw + pb * y as i32;
    let mut ry = y_raw + pd * y as i32;

    let map_pix = dim * 8;
    let wrap = cnt & (1 << 13) != 0;

    for x in 0..WIDTH {
        let mut sx = rx >> 8;
        let mut sy = ry >> 8;
        if wrap {
            sx = sx.rem_euclid(map_pix as i32);
            sy = sy.rem_euclid(map_pix as i32);
        } else if sx < 0 || sy < 0 || sx >= map_pix as i32 || sy >= map_pix as i32 {
            rx += pa;
            ry += pc;
            continue;
        }
        let tx = sx as usize / 8;
        let ty = sy as usize / 8;
        let px = sx as usize % 8;
        let py = sy as usize % 8;
        let map_off = screen_base + ty * dim + tx;
        let tile_id = vram_u8(bus, map_off) as usize;
        let tile_off = char_base + tile_id * 64 + py * 8 + px;
        let idx = vram_u8(bus, tile_off) as usize;
        if idx != 0 {
            frame[y * WIDTH + x] = pal_color(bus, idx);
        }
        rx += pa;
        ry += pc;
    }
}

fn mode3(bus: &Bus, y: usize, frame: &mut [u16]) {
    let base = y * WIDTH * 2;
    for x in 0..WIDTH {
        let off = base + x * 2;
        frame[y * WIDTH + x] = vram_u16(bus, off);
    }
}

fn mode4(bus: &Bus, y: usize, frame: &mut [u16], dispcnt: u16) {
    let page = if dispcnt & 0x10 != 0 { 0xA000 } else { 0 };
    let base = page + y * WIDTH;
    for x in 0..WIDTH {
        let idx = vram_u8(bus, base + x) as usize;
        frame[y * WIDTH + x] = pal_color(bus, idx);
    }
}

fn mode5(bus: &Bus, y: usize, frame: &mut [u16], dispcnt: u16) {
    if y >= 128 {
        return;
    }
    let page = if dispcnt & 0x10 != 0 { 0xA000 } else { 0 };
    let base = page + y * 160 * 2;
    for x in 0..WIDTH.min(160) {
        frame[y * WIDTH + x] = vram_u16(bus, base + x * 2);
    }
}

/// Regular (non-affine) 4bpp/8bpp sprites for one scanline.
fn render_sprites(bus: &Bus, y: usize, frame: &mut [u16], dispcnt: u16) {
    let one_d = dispcnt & (1 << 6) != 0;
    let map_2d = !one_d;

    // OAM: 128 entries × 8 bytes; draw low priority first so high paints over
    for prio in (0..4).rev() {
        for i in (0..128).rev() {
            let o = i * 8;
            let attr0 = oam_u16(bus, o);
            let attr1 = oam_u16(bus, o + 2);
            let attr2 = oam_u16(bus, o + 4);

            let obj_mode = (attr0 >> 8) & 3;
            if obj_mode == 2 {
                continue; // disabled
            }
            let affine = obj_mode == 1 || obj_mode == 3;
            if affine {
                continue; // skip affine for now
            }

            let shape = (attr0 >> 14) & 3;
            let size = (attr1 >> 14) & 3;
            let (ow, oh) = obj_dims(shape, size);
            let mut oy = attr0 & 0xFF;
            if oy >= 160 {
                // y is signed 8-bit for y>=160... actually 0-255, values >160 mean y-256
            }
            let y_signed = if oy > 160 { (oy as i32) - 256 } else { oy as i32 };
            let y0 = y_signed;
            let y1 = y0 + oh as i32;
            if (y as i32) < y0 || (y as i32) >= y1 {
                continue;
            }

            let pr = ((attr2 >> 10) & 3) as u8;
            if pr != prio as u8 {
                continue;
            }

            let mut ox = attr1 & 0x1FF;
            let x_signed = if ox >= 240 { (ox as i32) - 512 } else { ox as i32 };
            let color256 = attr0 & (1 << 13) != 0;
            let hflip = attr1 & (1 << 12) != 0;
            let vflip = attr1 & (1 << 13) != 0;
            let tile = (attr2 & 0x3FF) as usize;
            let pal_bank = ((attr2 >> 12) & 0xF) as usize;
            let row = (y as i32 - y0) as usize;
            let row_f = if vflip { oh - 1 - row } else { row };

            for xi in 0..ow {
                let sx = x_signed + xi as i32;
                if sx < 0 || sx >= WIDTH as i32 {
                    continue;
                }
                let col = if hflip { ow - 1 - xi } else { xi };
                let color = sample_obj_pixel(
                    bus, tile, col, row_f, ow, color256, pal_bank, map_2d,
                );
                if let Some(c) = color {
                    frame[y * WIDTH + sx as usize] = c;
                }
            }
        }
    }
}

fn oam_u16(bus: &Bus, off: usize) -> u16 {
    let lo = bus.oam.get(off).copied().unwrap_or(0) as u16;
    let hi = bus.oam.get(off + 1).copied().unwrap_or(0) as u16;
    lo | (hi << 8)
}

fn obj_dims(shape: u16, size: u16) -> (usize, usize) {
    match (shape, size) {
        (0, 0) => (8, 8),
        (0, 1) => (16, 16),
        (0, 2) => (32, 32),
        (0, 3) => (64, 64),
        (1, 0) => (16, 8),
        (1, 1) => (32, 8),
        (1, 2) => (32, 16),
        (1, 3) => (64, 32),
        (2, 0) => (8, 16),
        (2, 1) => (8, 32),
        (2, 2) => (16, 32),
        (2, 3) => (32, 64),
        _ => (8, 8),
    }
}

fn sample_obj_pixel(
    bus: &Bus,
    base_tile: usize,
    x: usize,
    y: usize,
    obj_w: usize,
    color256: bool,
    pal_bank: usize,
    map_2d: bool,
) -> Option<u16> {
    let tx = x / 8;
    let ty = y / 8;
    let px = x % 8;
    let py = y % 8;
    // OBJ character data starts at VRAM 0x10000
    let obj_vram = 0x10000usize;

    if color256 {
        let tile_index = if map_2d {
            base_tile + ty * 32 + tx * 2
        } else {
            base_tile + (ty * (obj_w / 8) + tx) * 2
        };
        let off = obj_vram + tile_index * 32 + py * 8 + px;
        let idx = vram_u8(bus, off) as usize;
        if idx == 0 {
            return None;
        }
        let lo = bus.pal.get(0x200 + idx * 2).copied().unwrap_or(0) as u16;
        let hi = bus.pal.get(0x200 + idx * 2 + 1).copied().unwrap_or(0) as u16;
        Some(lo | (hi << 8))
    } else {
        let tile_index = if map_2d {
            base_tile + ty * 32 + tx
        } else {
            base_tile + ty * (obj_w / 8) + tx
        };
        let off = obj_vram + tile_index * 32 + py * 4 + px / 2;
        let byte = vram_u8(bus, off);
        let idx = if px & 1 == 0 { byte & 0xF } else { byte >> 4 } as usize;
        if idx == 0 {
            return None;
        }
        let pal_off = 0x200 + (pal_bank * 16 + idx) * 2;
        let lo = bus.pal.get(pal_off).copied().unwrap_or(0) as u16;
        let hi = bus.pal.get(pal_off + 1).copied().unwrap_or(0) as u16;
        Some(lo | (hi << 8))
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

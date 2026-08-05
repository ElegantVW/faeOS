//! Interactive window — light the lantern and play.

use crate::emu::Emu;
use crate::ppu::{self, render};
use anyhow::{bail, Result};
use minifb::{Key, KeyRepeat, Scale, Window, WindowOptions};
use std::time::{Duration, Instant};

/// GBA KEYINPUT bits
const KEY_A: u16 = 1 << 0;
const KEY_B: u16 = 1 << 1;
const KEY_SELECT: u16 = 1 << 2;
const KEY_START: u16 = 1 << 3;
const KEY_RIGHT: u16 = 1 << 4;
const KEY_LEFT: u16 = 1 << 5;
const KEY_UP: u16 = 1 << 6;
const KEY_DOWN: u16 = 1 << 7;
const KEY_R: u16 = 1 << 8;
const KEY_L: u16 = 1 << 9;

pub fn run_window(emu: &mut Emu, title: &str) -> Result<()> {
    let mut window = Window::new(
        &format!("Fairy Lantern — {title}"),
        ppu::WIDTH,
        ppu::HEIGHT,
        WindowOptions {
            resize: true,
            scale: Scale::X4,
            ..WindowOptions::default()
        },
    )
    .map_err(|e| anyhow::anyhow!("window: {e}"))?;

    window.set_target_fps(60);

    let mut fb = vec![0u32; ppu::WIDTH * ppu::HEIGHT];
    let frame_budget = Duration::from_nanos(1_000_000_000 / 60);
    let mut paused = false;

    println!("✦ Fairy Lantern lit — {title}");
    println!("  arrows/WASD move · Z/X = A/B · Enter Start · P pause · Esc snuff");

    while window.is_open() && !window.is_key_down(Key::Escape) {
        let t0 = Instant::now();

        if window.is_key_pressed(Key::P, KeyRepeat::No) {
            paused = !paused;
        }

        let keys = poll_keys(&window);
        emu.bus.set_keys_pressed(keys);

        if !paused {
            // run one frame worth of cycles
            let mut guard = 0u32;
            while !emu.step_cycles(1) {
                guard += 1;
                if guard > 500_000 {
                    bail!("frame watchdog — CPU stuck (pc=0x{:08X})", emu.cpu.pc());
                }
            }
        }

        // convert BGR555 → 0xRRGGBB for minifb
        for (i, &p) in emu.ppu.frame.iter().enumerate().take(fb.len()) {
            let r = ((p & 0x1F) as u32) << 3;
            let g = (((p >> 5) & 0x1F) as u32) << 3;
            let b = (((p >> 10) & 0x1F) as u32) << 3;
            fb[i] = (r << 16) | (g << 8) | b;
        }

        window
            .update_with_buffer(&fb, ppu::WIDTH, ppu::HEIGHT)
            .map_err(|e| anyhow::anyhow!("present: {e}"))?;

        let spent = t0.elapsed();
        if spent < frame_budget {
            std::thread::sleep(frame_budget - spent);
        }
    }

    println!("  lantern snuffed.");
    let _ = render::frame_to_rgb; // keep import used if needed
    Ok(())
}

fn poll_keys(window: &Window) -> u16 {
    let mut m = 0u16;
    if window.is_key_down(Key::Z) || window.is_key_down(Key::J) {
        m |= KEY_A;
    }
    if window.is_key_down(Key::X) || window.is_key_down(Key::K) {
        m |= KEY_B;
    }
    if window.is_key_down(Key::RightShift) || window.is_key_down(Key::Backspace) {
        m |= KEY_SELECT;
    }
    if window.is_key_down(Key::Enter) {
        m |= KEY_START;
    }
    if window.is_key_down(Key::Right) || window.is_key_down(Key::D) {
        m |= KEY_RIGHT;
    }
    if window.is_key_down(Key::Left) || window.is_key_down(Key::A) {
        m |= KEY_LEFT;
    }
    if window.is_key_down(Key::Up) || window.is_key_down(Key::W) {
        m |= KEY_UP;
    }
    if window.is_key_down(Key::Down) || window.is_key_down(Key::S) {
        m |= KEY_DOWN;
    }
    if window.is_key_down(Key::Q) {
        m |= KEY_L;
    }
    if window.is_key_down(Key::E) {
        m |= KEY_R;
    }
    m
}

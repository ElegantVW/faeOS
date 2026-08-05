//! Fairy Lantern core — CPU + bus + PPU + timers + IRQ + battery.

use crate::battery;
use crate::bus::Bus;
use crate::cart::Cart;
use crate::cpu::Cpu;
use crate::irq;
use crate::ppu::Ppu;
use crate::timers::{self, Timers};
use anyhow::Result;
use std::path::{Path, PathBuf};

pub struct Emu {
    pub cpu: Cpu,
    pub bus: Bus,
    pub ppu: Ppu,
    pub timers: Timers,
    pub cart_title: String,
    pub rom_path: Option<PathBuf>,
    frames_since_flush: u32,
}

impl Emu {
    pub fn new(cart: &Cart, bios: Option<Vec<u8>>) -> Self {
        let mut cpu = Cpu::new();
        let bus = Bus::new(cart, bios);
        cpu.cpsr.thumb = false;
        cpu.cpsr.mode = 0x1F;
        cpu.cpsr.irq_disable = false;
        cpu.r[13] = 0x0300_7F00;
        cpu.r[14] = 0;
        cpu.set_pc(0x0800_0000);
        Self {
            cpu,
            bus,
            ppu: Ppu::new(),
            timers: Timers::new(),
            cart_title: cart.title.clone(),
            rom_path: None,
            frames_since_flush: 0,
        }
    }

    pub fn from_path(path: &Path, bios_path: Option<&Path>) -> Result<Self> {
        let cart = Cart::load(path)?;
        let mut emu = Self::new(&cart, load_bios(bios_path));
        emu.attach_rom_path(path);
        Ok(emu)
    }

    pub fn from_cart(cart: Cart, bios_path: Option<&Path>) -> Self {
        Self::new(&cart, load_bios(bios_path))
    }

    /// Wire battery .sav next to the ROM (or under data dir).
    pub fn attach_rom_path(&mut self, path: &Path) {
        self.rom_path = Some(path.to_path_buf());
        let sav = battery::sav_path_for_rom(path);
        self.bus.load_battery(sav);
        eprintln!(
            "  battery: {} → {}",
            self.bus.save_type.label(),
            self.bus
                .save_path
                .as_ref()
                .map(|p| p.display().to_string())
                .unwrap_or_else(|| "(none)".into())
        );
    }

    pub fn flush_battery(&mut self) {
        if let Err(e) = self.bus.flush_battery() {
            eprintln!("fairy-lantern: battery save failed: {e:#}");
        }
    }

    pub fn state_path(&self) -> Option<PathBuf> {
        self.rom_path.as_ref().map(|p| battery::state_path_for_rom(p))
    }

    /// Step a few CPU cycles; returns true if a video frame completed.
    pub fn step_cycles(&mut self, min_cycles: u32) -> bool {
        let mut left = min_cycles.max(1);
        let mut frame = false;
        while left > 0 {
            let c = self.cpu.step(&mut self.bus);
            // sync reloads from bus IO side-effects
            self.timers.reload = self.bus.timer_reload;
            timers::step(&mut self.timers, &mut self.bus, c);
            self.bus.timer_reload = self.timers.reload;
            if self.ppu.step(&mut self.bus, c) {
                frame = true;
                self.frames_since_flush += 1;
                // autosave battery every ~2s of game time
                if self.frames_since_flush >= 120 && self.bus.save_dirty {
                    self.flush_battery();
                    self.frames_since_flush = 0;
                }
            }
            irq::check(&mut self.cpu, &mut self.bus);
            left = left.saturating_sub(c);
        }
        frame
    }

    pub fn run_frames(&mut self, n: u32) -> u32 {
        let mut frames = 0u32;
        let mut guard = 0u64;
        while frames < n {
            if self.step_cycles(64) {
                frames += 1;
            }
            guard += 1;
            if guard > 80_000_000 {
                break;
            }
        }
        self.flush_battery();
        frames
    }
}

fn load_bios(bios_path: Option<&Path>) -> Option<Vec<u8>> {
    if let Some(p) = bios_path {
        return std::fs::read(p).ok();
    }
    if let Ok(p) = std::env::var("FAIRY_LANTERN_BIOS") {
        let p = Path::new(&p);
        if p.is_file() {
            return std::fs::read(p).ok();
        }
    }
    None
}

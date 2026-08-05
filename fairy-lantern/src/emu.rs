//! Fairy Lantern core — CPU + bus + PPU + timers + IRQ.

use crate::bus::Bus;
use crate::cart::Cart;
use crate::cpu::Cpu;
use crate::irq;
use crate::ppu::Ppu;
use crate::timers::{self, Timers};
use anyhow::Result;
use std::path::Path;

pub struct Emu {
    pub cpu: Cpu,
    pub bus: Bus,
    pub ppu: Ppu,
    pub timers: Timers,
    pub cart_title: String,
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
        }
    }

    pub fn from_path(path: &Path, bios_path: Option<&Path>) -> Result<Self> {
        let cart = Cart::load(path)?;
        Ok(Self::new(&cart, load_bios(bios_path)))
    }

    pub fn from_cart(cart: Cart, bios_path: Option<&Path>) -> Self {
        Self::new(&cart, load_bios(bios_path))
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

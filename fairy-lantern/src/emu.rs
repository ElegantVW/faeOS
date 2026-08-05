//! Fairy Lantern core — CPU + bus + PPU wired together.

use crate::bus::Bus;
use crate::cart::Cart;
use crate::cpu::Cpu;
use crate::ppu::Ppu;
use anyhow::Result;
use std::path::Path;

pub struct Emu {
    pub cpu: Cpu,
    pub bus: Bus,
    pub ppu: Ppu,
    pub cart_title: String,
}

impl Emu {
    pub fn new(cart: &Cart, bios: Option<Vec<u8>>) -> Self {
        let mut cpu = Cpu::new();
        let bus = Bus::new(cart, bios);
        // Homebrew-friendly boot: PC at ROM, ARM mode, stack in IWRAM
        cpu.cpsr.thumb = false;
        cpu.cpsr.mode = 0x1F; // SYS
        cpu.r[13] = 0x0300_7F00;
        cpu.r[14] = 0;
        // GBA ROMs are mapped at 0x0800_0000; entry from cart header branch
        let entry = cart.entry_pc();
        // entry_pc may return offset from 0 if branch at start of file —
        // homebrew often has B at file+0 meaning ROM+0 → 0x08000000+target
        let pc = if entry < 0x0800_0000 {
            0x0800_0000u32.wrapping_add(entry)
        } else {
            entry
        };
        // Simpler: always start at 0x08000000 (execute the header branch in place)
        cpu.set_pc(0x0800_0000);
        let _ = pc;
        Self {
            cpu,
            bus,
            ppu: Ppu::new(),
            cart_title: cart.title.clone(),
        }
    }

    pub fn from_path(path: &Path, bios_path: Option<&Path>) -> Result<Self> {
        let cart = Cart::load(path)?;
        let bios = if let Some(p) = bios_path {
            Some(std::fs::read(p)?)
        } else if let Ok(p) = std::env::var("FAIRY_LANTERN_BIOS") {
            let p = Path::new(&p);
            if p.is_file() {
                Some(std::fs::read(p)?)
            } else {
                None
            }
        } else {
            None
        };
        Ok(Self::new(&cart, bios))
    }

    /// Run until `max_cycles` or `max_frames` frames completed.
    pub fn run(&mut self, max_cycles: u64, max_frames: u32) -> u32 {
        let start = self.cpu.cycles;
        let mut frames = 0u32;
        while self.cpu.cycles.wrapping_sub(start) < max_cycles && frames < max_frames {
            let c = self.cpu.step(&mut self.bus);
            if self.ppu.step(&mut self.bus, c) {
                frames += 1;
            }
        }
        frames
    }

    /// Run a fixed number of frames.
    pub fn run_frames(&mut self, n: u32) -> u32 {
        self.run(u64::MAX / 4, n)
    }
}

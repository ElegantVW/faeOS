//! Picture processing unit — Mode 3/4 first.

pub mod render;

use crate::bus::Bus;

pub const WIDTH: usize = 240;
pub const HEIGHT: usize = 160;
/// Approx cycles per scanline (GBA ~1232); simplified.
pub const CYCLES_PER_LINE: u32 = 1232;
pub const LINES_PER_FRAME: u32 = 228; // 160 vis + 68 vblank

pub struct Ppu {
    pub line: u16,
    pub line_cycles: u32,
    pub frame: [u16; WIDTH * HEIGHT], // BGR555
    pub frame_ready: bool,
}

impl Default for Ppu {
    fn default() -> Self {
        Self::new()
    }
}

impl Ppu {
    pub fn new() -> Self {
        Self {
            line: 0,
            line_cycles: 0,
            frame: [0; WIDTH * HEIGHT],
            frame_ready: false,
        }
    }

    /// Advance PPU by cpu cycles; returns true if a full frame was completed.
    pub fn step(&mut self, bus: &mut Bus, cycles: u32) -> bool {
        self.frame_ready = false;
        self.line_cycles += cycles;
        while self.line_cycles >= CYCLES_PER_LINE {
            self.line_cycles -= CYCLES_PER_LINE;
            let entering_vblank = self.line == HEIGHT as u16;
            if self.line < HEIGHT as u16 {
                render::render_scanline(bus, self.line as usize, &mut self.frame);
            }
            self.line += 1;
            if self.line >= LINES_PER_FRAME as u16 {
                self.line = 0;
                self.frame_ready = true;
            }
            bus.set_vcount(self.line);

            let mut ds = bus.dispstat() & !1;
            if self.line >= HEIGHT as u16 {
                ds |= 1; // VBlank flag while lines 160..227
            }
            bus.set_dispstat(ds);

            if entering_vblank {
                crate::irq::raise(bus, crate::irq::IRQ_VBLANK);
            }
        }
        self.frame_ready
    }
}

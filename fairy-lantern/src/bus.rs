//! GBA memory map (simplified waitstates).

use crate::cart::Cart;

pub const EWRAM_SIZE: usize = 256 * 1024;
pub const IWRAM_SIZE: usize = 32 * 1024;
pub const VRAM_SIZE: usize = 96 * 1024;
pub const PAL_SIZE: usize = 1024;
pub const OAM_SIZE: usize = 1024;
pub const BIOS_SIZE: usize = 16 * 1024;
pub const IO_SIZE: usize = 0x400;

pub struct Bus {
    pub bios: Vec<u8>,
    pub ewram: Vec<u8>,
    pub iwram: Vec<u8>,
    pub io: Vec<u8>,
    pub pal: Vec<u8>,
    pub vram: Vec<u8>,
    pub oam: Vec<u8>,
    pub rom: Vec<u8>,
    pub sram: Vec<u8>,
    /// KEYINPUT active-low bits (0 = pressed)
    pub keyinput: u16,
}

impl Bus {
    pub fn new(cart: &Cart, bios: Option<Vec<u8>>) -> Self {
        let mut b = Self {
            bios: bios.unwrap_or_else(|| vec![0; BIOS_SIZE]),
            ewram: vec![0; EWRAM_SIZE],
            iwram: vec![0; IWRAM_SIZE],
            io: vec![0; IO_SIZE],
            pal: vec![0; PAL_SIZE],
            vram: vec![0; VRAM_SIZE],
            oam: vec![0; OAM_SIZE],
            rom: cart.data.clone(),
            sram: vec![0xFF; 64 * 1024],
            keyinput: 0x03FF, // all released
        };
        // Sensible power-on IO defaults
        b.write16(0x0400_0130, 0x03FF); // KEYINPUT
        b.write16(0x0400_0000, 0x0080); // DISPCNT forced blank until game sets it
        b
    }

    pub fn read8(&self, addr: u32) -> u8 {
        let a = addr;
        match a >> 24 {
            0x00 => self.bios.get((a & 0x3FFF) as usize).copied().unwrap_or(0),
            0x02 => self.ewram[(a as usize) & (EWRAM_SIZE - 1)],
            0x03 => self.iwram[(a as usize) & (IWRAM_SIZE - 1)],
            0x04 => {
                if a == 0x0400_0130 || a == 0x0400_0131 {
                    let v = self.keyinput;
                    if a & 1 == 0 {
                        (v & 0xFF) as u8
                    } else {
                        (v >> 8) as u8
                    }
                } else {
                    self.io.get((a as usize) & (IO_SIZE - 1)).copied().unwrap_or(0)
                }
            }
            0x05 => self.pal[(a as usize) & (PAL_SIZE - 1)],
            0x06 => self.vram[vram_index(a)],
            0x07 => self.oam[(a as usize) & (OAM_SIZE - 1)],
            0x08 | 0x09 | 0x0A | 0x0B | 0x0C | 0x0D => {
                let off = (a as usize) & 0x01FF_FFFF;
                self.rom.get(off).copied().unwrap_or(0)
            }
            0x0E | 0x0F => self.sram[(a as usize) & 0xFFFF],
            _ => 0,
        }
    }

    pub fn write8(&mut self, addr: u32, val: u8) {
        let a = addr;
        match a >> 24 {
            0x02 => self.ewram[(a as usize) & (EWRAM_SIZE - 1)] = val,
            0x03 => self.iwram[(a as usize) & (IWRAM_SIZE - 1)] = val,
            0x04 => {
                let i = (a as usize) & (IO_SIZE - 1);
                if i < self.io.len() {
                    self.io[i] = val;
                }
            }
            0x05 => self.pal[(a as usize) & (PAL_SIZE - 1)] = val,
            0x06 => self.vram[vram_index(a)] = val,
            0x07 => self.oam[(a as usize) & (OAM_SIZE - 1)] = val,
            0x0E | 0x0F => self.sram[(a as usize) & 0xFFFF] = val,
            _ => {}
        }
    }

    pub fn read16(&self, addr: u32) -> u16 {
        let a = addr & !1;
        u16::from_le_bytes([self.read8(a), self.read8(a.wrapping_add(1))])
    }

    pub fn write16(&mut self, addr: u32, val: u16) {
        let a = addr & !1;
        let b = val.to_le_bytes();
        self.write8(a, b[0]);
        self.write8(a.wrapping_add(1), b[1]);
    }

    pub fn read32(&self, addr: u32) -> u32 {
        let a = addr & !3;
        u32::from_le_bytes([
            self.read8(a),
            self.read8(a.wrapping_add(1)),
            self.read8(a.wrapping_add(2)),
            self.read8(a.wrapping_add(3)),
        ])
    }

    pub fn write32(&mut self, addr: u32, val: u32) {
        let a = addr & !3;
        let b = val.to_le_bytes();
        self.write8(a, b[0]);
        self.write8(a.wrapping_add(1), b[1]);
        self.write8(a.wrapping_add(2), b[2]);
        self.write8(a.wrapping_add(3), b[3]);
    }

    pub fn dispcnt(&self) -> u16 {
        self.read16(0x0400_0000)
    }

    pub fn vcount(&self) -> u16 {
        self.read16(0x0400_0006)
    }

    pub fn set_vcount(&mut self, v: u16) {
        self.write16(0x0400_0006, v);
    }

    pub fn dispstat(&self) -> u16 {
        self.read16(0x0400_0004)
    }

    pub fn set_dispstat(&mut self, v: u16) {
        self.write16(0x0400_0004, v);
    }
}

fn vram_index(addr: u32) -> usize {
    let a = (addr as usize) & 0x1FFFF;
    // mirrors
    if a < VRAM_SIZE {
        a
    } else {
        a % VRAM_SIZE
    }
}

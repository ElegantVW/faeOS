//! GBA memory map (simplified waitstates) + battery-backed cart save.

use crate::battery::{self, FlashChip, SaveType};
use crate::cart::Cart;
use crate::dma;
use std::path::PathBuf;

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
    /// SRAM mirror (also used when SaveType::Sram)
    pub sram: Vec<u8>,
    pub flash: Option<FlashChip>,
    pub save_type: SaveType,
    pub save_path: Option<PathBuf>,
    pub save_dirty: bool,
    /// KEYINPUT active-low bits (0 = pressed)
    pub keyinput: u16,
    /// Timer reload shadow (synced from Emu.timers on write)
    pub timer_reload: [u16; 4],
    /// BIOS IntrWait / Halt: run until these IF bits appear (or VBlank)
    pub halt_wait: bool,
    pub intr_wait_mask: u16,
}

impl Bus {
    pub fn new(cart: &Cart, bios: Option<Vec<u8>>) -> Self {
        let save_type = battery::detect(&cart.data);
        let size = save_type.size().max(64 * 1024);
        let mut b = Self {
            bios: bios.unwrap_or_else(|| vec![0; BIOS_SIZE]),
            ewram: vec![0; EWRAM_SIZE],
            iwram: vec![0; IWRAM_SIZE],
            io: vec![0; IO_SIZE],
            pal: vec![0; PAL_SIZE],
            vram: vec![0; VRAM_SIZE],
            oam: vec![0; OAM_SIZE],
            rom: cart.data.clone(),
            sram: vec![0xFF; size],
            flash: match save_type {
                SaveType::Flash64 => Some(FlashChip::new(64 * 1024)),
                SaveType::Flash128 => Some(FlashChip::new(128 * 1024)),
                _ => None,
            },
            save_type,
            save_path: None,
            save_dirty: false,
            keyinput: 0x03FF,
            timer_reload: [0; 4],
            halt_wait: false,
            intr_wait_mask: 0,
        };
        b.write16_raw(0x0400_0130, 0x03FF);
        b.write16_raw(0x0400_0000, 0x0080);
        b
    }

    /// Attach a .sav path and load battery contents.
    pub fn load_battery(&mut self, sav: PathBuf) {
        let size = self.save_type.size().max(1);
        if self.save_type == SaveType::None {
            self.save_path = Some(sav);
            return;
        }
        let data = battery::load_sav(&sav, size);
        match self.save_type {
            SaveType::Flash64 | SaveType::Flash128 => {
                if let Some(ref mut f) = self.flash {
                    let n = data.len().min(f.data.len());
                    f.data[..n].copy_from_slice(&data[..n]);
                }
            }
            SaveType::Sram(_) => {
                let n = data.len().min(self.sram.len());
                self.sram[..n].copy_from_slice(&data[..n]);
            }
            SaveType::None => {}
        }
        self.save_path = Some(sav);
        self.save_dirty = false;
    }

    /// Flush dirty battery to disk.
    pub fn flush_battery(&mut self) -> anyhow::Result<()> {
        if !self.save_dirty {
            return Ok(());
        }
        let Some(ref path) = self.save_path else {
            return Ok(());
        };
        let data: &[u8] = match self.save_type {
            SaveType::Flash64 | SaveType::Flash128 => {
                if let Some(ref f) = self.flash {
                    &f.data
                } else {
                    &self.sram
                }
            }
            SaveType::Sram(n) => &self.sram[..n.min(self.sram.len())],
            SaveType::None => return Ok(()),
        };
        battery::save_sav(path, data)?;
        self.save_dirty = false;
        Ok(())
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
                    self.io
                        .get((a as usize) & (IO_SIZE - 1))
                        .copied()
                        .unwrap_or(0)
                }
            }
            0x05 => self.pal[(a as usize) & (PAL_SIZE - 1)],
            0x06 => self.vram[vram_index(a)],
            0x07 => self.oam[(a as usize) & (OAM_SIZE - 1)],
            0x08 | 0x09 | 0x0A | 0x0B | 0x0C | 0x0D => {
                let off = (a as usize) & 0x01FF_FFFF;
                self.rom.get(off).copied().unwrap_or(0)
            }
            0x0E | 0x0F => self.read_save(a),
            _ => 0,
        }
    }

    fn read_save(&self, addr: u32) -> u8 {
        if let Some(ref flash) = self.flash {
            return flash.read(addr);
        }
        let idx = if self.sram.len().is_power_of_two() {
            (addr as usize) & (self.sram.len() - 1)
        } else {
            (addr as usize) % self.sram.len().max(1)
        };
        self.sram.get(idx).copied().unwrap_or(0xFF)
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
            0x0E | 0x0F => self.write_save(a, val),
            _ => {}
        }
    }

    fn write_save(&mut self, addr: u32, val: u8) {
        if let Some(ref mut flash) = self.flash {
            if flash.write(addr, val) {
                self.save_dirty = true;
            }
            return;
        }
        let idx = if self.sram.len().is_power_of_two() {
            (addr as usize) & (self.sram.len() - 1)
        } else {
            (addr as usize) % self.sram.len().max(1)
        };
        if let Some(slot) = self.sram.get_mut(idx) {
            if *slot != val {
                *slot = val;
                self.save_dirty = true;
            }
        }
    }

    pub fn read16(&self, addr: u32) -> u16 {
        let a = addr & !1;
        u16::from_le_bytes([self.read8(a), self.read8(a.wrapping_add(1))])
    }

    pub fn write16_raw(&mut self, addr: u32, val: u16) {
        let a = addr & !1;
        let b = val.to_le_bytes();
        let i0 = (a as usize) & (IO_SIZE - 1);
        if (a >> 24) == 0x04 && i0 + 1 < self.io.len() {
            self.io[i0] = b[0];
            self.io[i0 + 1] = b[1];
            return;
        }
        self.write8(a, b[0]);
        self.write8(a.wrapping_add(1), b[1]);
    }

    pub fn write16(&mut self, addr: u32, val: u16) {
        let a = addr & !1;
        if (a >> 24) == 0x04 {
            match a {
                0x0400_0202 => {
                    let cur = self.read16(0x0400_0202);
                    self.write16_raw(a, cur & !val);
                    return;
                }
                0x0400_0100 | 0x0400_0104 | 0x0400_0108 | 0x0400_010C => {
                    let idx = ((a - 0x0400_0100) / 4) as usize;
                    if idx < 4 {
                        self.timer_reload[idx] = val;
                    }
                    self.write16_raw(a, val);
                    return;
                }
                0x0400_00BA | 0x0400_00C6 | 0x0400_00D2 | 0x0400_00DE => {
                    self.write16_raw(a, val);
                    let ch = match a {
                        0x0400_00BA => 0,
                        0x0400_00C6 => 1,
                        0x0400_00D2 => 2,
                        _ => 3,
                    };
                    if val & 0x8000 != 0 {
                        dma::try_start(self, ch);
                    }
                    return;
                }
                _ => {}
            }
        }
        self.write16_raw(a, val);
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
        self.write16(a, u16::from_le_bytes([b[0], b[1]]));
        self.write16(a.wrapping_add(2), u16::from_le_bytes([b[2], b[3]]));
    }

    pub fn dispcnt(&self) -> u16 {
        self.read16(0x0400_0000)
    }

    pub fn set_vcount(&mut self, v: u16) {
        self.write16_raw(0x0400_0006, v);
    }

    pub fn dispstat(&self) -> u16 {
        self.read16(0x0400_0004)
    }

    pub fn set_dispstat(&mut self, v: u16) {
        self.write16_raw(0x0400_0004, v);
    }

    pub fn set_keys_pressed(&mut self, pressed_mask: u16) {
        self.keyinput = (!pressed_mask) & 0x03FF;
    }
}

fn vram_index(addr: u32) -> usize {
    let a = (addr as usize) & 0x1FFFF;
    if a < VRAM_SIZE {
        a
    } else {
        a % VRAM_SIZE
    }
}

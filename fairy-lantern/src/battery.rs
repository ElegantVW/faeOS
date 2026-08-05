//! Cartridge battery saves (SRAM / Flash) + paths for .sav files.

use crate::recents;
use anyhow::{Context, Result};
use std::fs;
use std::path::{Path, PathBuf};

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum SaveType {
    None,
    /// Size in bytes (typically 32 KiB or 64 KiB)
    Sram(usize),
    /// 64 KiB flash
    Flash64,
    /// 128 KiB flash (banked)
    Flash128,
}

impl SaveType {
    pub fn size(self) -> usize {
        match self {
            SaveType::None => 0,
            SaveType::Sram(n) => n,
            SaveType::Flash64 => 64 * 1024,
            SaveType::Flash128 => 128 * 1024,
        }
    }

    pub fn label(self) -> &'static str {
        match self {
            SaveType::None => "none",
            SaveType::Sram(n) if n <= 32 * 1024 => "SRAM 32K",
            SaveType::Sram(_) => "SRAM 64K",
            SaveType::Flash64 => "FLASH 64K",
            SaveType::Flash128 => "FLASH 128K",
        }
    }
}

/// Detect save type from strings embedded in the ROM (Nintendo SDK tags).
pub fn detect(rom: &[u8]) -> SaveType {
    let s = String::from_utf8_lossy(rom);
    // Order matters: more specific first
    if s.contains("FLASH1M_V") || s.contains("FLASH1M") {
        return SaveType::Flash128;
    }
    if s.contains("FLASH512_V") || s.contains("FLASH_V") || s.contains("FLASH512") {
        return SaveType::Flash64;
    }
    if s.contains("SRAM_V") || s.contains("SRAM_F_V") {
        // Most SRAM carts are 32K; some 64K — use 64K buffer, games only use what they need
        return SaveType::Sram(64 * 1024);
    }
    if s.contains("EEPROM_V") {
        // Bit-bang EEPROM not fully emulated yet — still allocate a small buffer
        // so games that also touch SRAM-ish space don't crash; real EEPROM later.
        return SaveType::Sram(8 * 1024);
    }
    // Default: many homebrew / unknown — give SRAM so casual saves can work
    SaveType::Sram(64 * 1024)
}

/// `.sav` next to the ROM, or under data dir if ROM path is weird.
pub fn sav_path_for_rom(rom: &Path) -> PathBuf {
    let stem = rom.file_stem().and_then(|s| s.to_str()).unwrap_or("fable");
    if let Some(parent) = rom.parent() {
        if parent.exists() {
            return parent.join(format!("{stem}.sav"));
        }
    }
    let dir = recents::data_dir().join("saves");
    let _ = fs::create_dir_all(&dir);
    dir.join(format!("{stem}.sav"))
}

pub fn state_path_for_rom(rom: &Path) -> PathBuf {
    let stem = rom.file_stem().and_then(|s| s.to_str()).unwrap_or("fable");
    let dir = recents::data_dir().join("states");
    let _ = fs::create_dir_all(&dir);
    dir.join(format!("{stem}.flst"))
}

pub fn load_sav(path: &Path, size: usize) -> Vec<u8> {
    let mut buf = vec![0xFF; size.max(1)];
    if size == 0 {
        return buf;
    }
    if let Ok(data) = fs::read(path) {
        let n = data.len().min(size);
        buf[..n].copy_from_slice(&data[..n]);
    }
    buf
}

pub fn save_sav(path: &Path, data: &[u8]) -> Result<()> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).ok();
    }
    fs::write(path, data).with_context(|| format!("write battery {}", path.display()))?;
    Ok(())
}

/// Flash command state machine (64K / 128K, simplified).
#[derive(Clone, Debug, Default)]
pub struct FlashChip {
    pub data: Vec<u8>,
    pub bank: usize,
    cmd_step: u8,
    /// 0 = ready, 1 = ID mode, 2 = erase setup, 3 = write byte
    mode: u8,
    manufacturer: u8,
    device: u8,
}

impl FlashChip {
    pub fn new(size: usize) -> Self {
        let (m, d) = if size >= 128 * 1024 {
            (0x62, 0x13) // Sanyo 128K-ish id used by some emus
        } else {
            (0xBF, 0xD4) // SST / Panasonic style 64K
        };
        Self {
            data: vec![0xFF; size.max(64 * 1024)],
            bank: 0,
            cmd_step: 0,
            mode: 0,
            manufacturer: m,
            device: d,
        }
    }

    fn bank_base(&self) -> usize {
        // 128K: two 64K banks
        if self.data.len() >= 128 * 1024 {
            self.bank.saturating_mul(64 * 1024)
        } else {
            0
        }
    }

    pub fn read(&self, addr: u32) -> u8 {
        let off = (addr as usize) & 0xFFFF;
        if self.mode == 1 {
            // ID mode
            return match off {
                0 => self.manufacturer,
                1 => self.device,
                _ => 0xFF,
            };
        }
        let i = self.bank_base() + off;
        self.data.get(i).copied().unwrap_or(0xFF)
    }

    pub fn write(&mut self, addr: u32, val: u8) -> bool {
        let off = (addr as usize) & 0xFFFF;
        // Bank switch (128K): write bank to 0x0E000000 after unlock sequence varies;
        // common: after 0xAA/0x55, command 0xB0 then write bank at 0x0000
        match self.cmd_step {
            0 if off == 0x5555 && val == 0xAA => {
                self.cmd_step = 1;
                return false;
            }
            1 if off == 0x2AAA && val == 0x55 => {
                self.cmd_step = 2;
                return false;
            }
            2 => {
                self.cmd_step = 0;
                match val {
                    0x90 => {
                        self.mode = 1; // ID
                        return false;
                    }
                    0xF0 => {
                        self.mode = 0;
                        return false;
                    }
                    0x80 => {
                        self.mode = 2; // erase prep
                        return false;
                    }
                    0xA0 => {
                        self.mode = 3; // program next byte
                        return false;
                    }
                    0xB0 => {
                        self.mode = 4; // bank
                        return false;
                    }
                    _ => return false,
                }
            }
            _ => {}
        }

        if self.mode == 4 {
            // bank select
            self.bank = (val & 1) as usize;
            self.mode = 0;
            return false;
        }
        if self.mode == 3 {
            let i = self.bank_base() + off;
            if i < self.data.len() {
                self.data[i] &= val; // flash programs 1→0
            }
            self.mode = 0;
            return true;
        }
        if self.mode == 2 {
            // erase commands: 0x30 sector, 0x10 chip after second unlock
            if off == 0x5555 && val == 0xAA {
                self.cmd_step = 1;
                return false;
            }
            // simplify: any 0x30/0x10 erases whole chip or sector
            if val == 0x10 || val == 0x30 {
                if val == 0x10 {
                    self.data.fill(0xFF);
                } else {
                    let base = self.bank_base() + (off & !0xFFF);
                    for b in self.data.iter_mut().skip(base).take(0x1000) {
                        *b = 0xFF;
                    }
                }
                self.mode = 0;
                return true;
            }
        }
        // raw write fallback (some homebrew)
        if self.mode == 0 && self.cmd_step == 0 {
            let i = self.bank_base() + off;
            if i < self.data.len() {
                self.data[i] = val;
                return true;
            }
        }
        false
    }
}

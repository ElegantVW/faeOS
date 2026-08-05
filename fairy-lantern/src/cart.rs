//! Cartridge / ROM loading — each .gba is a fable for the Fairy Lantern.

use anyhow::{bail, Context, Result};
use std::fs;
use std::path::Path;

#[derive(Clone, Debug)]
pub struct Cart {
    pub data: Vec<u8>,
    pub title: String,
    pub game_code: String,
    pub maker: String,
    pub path: String,
}

impl Cart {
    pub fn load(path: &Path) -> Result<Self> {
        let data = fs::read(path)
            .with_context(|| format!("read fable {}", path.display()))?;
        if data.len() < 0xC0 {
            bail!("fable too small ({} bytes) — not a GBA ROM", data.len());
        }
        // Title: 0xA0..0xAC, game code 0xAC..0xB0, maker 0xB0..0xB2
        let title = cstr_field(&data[0xA0..0xAC]);
        let game_code = cstr_field(&data[0xAC..0xB0]);
        let maker = cstr_field(&data[0xB0..0xB2]);
        Ok(Self {
            data,
            title,
            game_code,
            maker,
            path: path.display().to_string(),
        })
    }

    pub fn size(&self) -> usize {
        self.data.len()
    }

    /// Entry point used by many homebrew ROMs (skip full BIOS boot).
    pub fn entry_pc(&self) -> u32 {
        // First word is often B <start>; decode ARM branch if so
        if self.data.len() >= 4 {
            let op = u32::from_le_bytes(self.data[0..4].try_into().unwrap());
            if (op & 0x0E00_0000) == 0x0A00_0000 {
                // B: PC = (PC+8) + sign_extend(offset)*4, PC at fetch = 0
                let imm = (op & 0x00FF_FFFF) as i32;
                let imm = (imm << 8) >> 8; // sign extend 24→32
                let pc = 0u32.wrapping_add(8).wrapping_add((imm * 4) as u32);
                return pc;
            }
        }
        0x0800_0000
    }
}

fn cstr_field(bytes: &[u8]) -> String {
    let end = bytes.iter().position(|&b| b == 0).unwrap_or(bytes.len());
    String::from_utf8_lossy(&bytes[..end])
        .trim()
        .chars()
        .filter(|c| c.is_ascii_graphic() || *c == ' ')
        .collect()
}

pub fn print_info(cart: &Cart) {
    println!("✦ Fairy Lantern — fable info");
    println!("  path:   {}", cart.path);
    println!("  title:  {}", if cart.title.is_empty() { "(none)" } else { &cart.title });
    println!("  code:   {}", if cart.game_code.is_empty() { "(none)" } else { &cart.game_code });
    println!("  maker:  {}", if cart.maker.is_empty() { "(none)" } else { &cart.maker });
    println!("  size:   {} bytes ({:.1} KiB)", cart.size(), cart.size() as f64 / 1024.0);
    println!("  entry:  0x{:08X} (homebrew-style)", cart.entry_pc());
}

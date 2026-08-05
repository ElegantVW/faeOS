//! Fairy Lantern — light a fable; play a pocket world (GBA).

mod bus;
mod cart;
mod cpu;
mod dma;
mod emu;
mod fable;
mod irq;
mod play;
mod ppu;
mod timers;
mod video;

use anyhow::{Context, Result};
use cart::Cart;
use clap::{Parser, Subcommand};
use emu::Emu;
use std::path::PathBuf;

#[derive(Parser, Debug)]
#[command(
    name = "fairy-lantern",
    about = "Fairy Lantern — GBA emulator from scratch (faeOS)",
    long_about = "Light a fable; play a pocket world.\n\
                  From-scratch ARM7TDMI + PPU. No mGBA/libretro."
)]
struct Cli {
    #[command(subcommand)]
    cmd: Option<Commands>,

    /// Fable (.gba) when no subcommand — opens play window
    rom: Option<PathBuf>,

    /// Headless: run N frames then dump (default window when omitted)
    #[arg(long)]
    frames: Option<u32>,

    #[arg(long)]
    dump: Option<PathBuf>,

    #[arg(long)]
    present: bool,

    #[arg(long)]
    bios: Option<PathBuf>,
}

#[derive(Subcommand, Debug)]
enum Commands {
    /// ROM header
    Info { rom: PathBuf },
    /// Self-tests
    Test,
    /// Debug spark ROM stepping
    DebugSpark {
        #[arg(long, default_value_t = 50)]
        steps: u32,
    },
    /// Play a fable (window)
    Play {
        rom: Option<PathBuf>,
        #[arg(long)]
        bios: Option<PathBuf>,
    },
    /// Built-in SPARK fable (always playable)
    Spark {
        #[arg(long)]
        bios: Option<PathBuf>,
    },
    /// Headless run
    Run {
        rom: PathBuf,
        #[arg(long, default_value_t = 3)]
        frames: u32,
        #[arg(long)]
        dump: Option<PathBuf>,
        #[arg(long)]
        present: bool,
        #[arg(long)]
        bios: Option<PathBuf>,
    },
    /// List fables in a directory
    Tui {
        #[arg(long)]
        dir: Option<PathBuf>,
    },
}

fn main() {
    if let Err(e) = real_main() {
        eprintln!("fairy-lantern: {e:#}");
        std::process::exit(1);
    }
}

fn real_main() -> Result<()> {
    let cli = Cli::parse();
    match cli.cmd {
        Some(Commands::Info { rom }) => {
            cart::print_info(&Cart::load(&rom)?);
        }
        Some(Commands::DebugSpark { steps }) => {
            debug_spark(steps);
        }
        Some(Commands::Test) => {
            let n = run_self_tests();
            println!("✦ Fairy Lantern self-tests: {n} passed");
        }
        Some(Commands::Spark { bios }) => {
            play_spark(bios.as_ref())?;
        }
        Some(Commands::Play { rom, bios }) => {
            if let Some(rom) = rom {
                play_rom(&rom, bios.as_ref())?;
            } else {
                play_spark(bios.as_ref())?;
            }
        }
        Some(Commands::Run {
            rom,
            frames,
            dump,
            present,
            bios,
        }) => {
            run_rom(&rom, frames, dump.as_ref(), present, bios.as_ref())?;
        }
        Some(Commands::Tui { dir }) => tui_list(dir)?,
        None => {
            if let Some(rom) = cli.rom {
                if let Some(frames) = cli.frames {
                    run_rom(
                        &rom,
                        frames,
                        cli.dump.as_ref(),
                        cli.present,
                        cli.bios.as_ref(),
                    )?;
                } else {
                    play_rom(&rom, cli.bios.as_ref())?;
                }
            } else {
                println!(
                    "✦ Fairy Lantern — light a fable; play a pocket world\n\
                     \n\
                     Ready to play (built-in):\n\
                       fairy-lantern spark\n\
                     \n\
                     Your ROM:\n\
                       fairy-lantern play game.gba\n\
                       fairy-lantern game.gba\n\
                     \n\
                     Headless:\n\
                       fairy-lantern run game.gba --frames 3 --dump out.ppm\n\
                       fairy-lantern info game.gba\n\
                       fairy-lantern test\n\
                     \n\
                     Controls: arrows/WASD · Z/X A/B · Enter Start · P pause · Esc quit\n"
                );
            }
        }
    }
    Ok(())
}

fn play_spark(bios: Option<&PathBuf>) -> Result<()> {
    let cart = fable::spark_rom();
    cart::print_info(&cart);
    let mut emu = Emu::from_cart(cart, bios.map(|p| p.as_path()));
    play::run_window(&mut emu, "SPARK (built-in)")
}

fn play_rom(rom: &PathBuf, bios: Option<&PathBuf>) -> Result<()> {
    let cart = Cart::load(rom)?;
    cart::print_info(&cart);
    let mut emu = Emu::from_cart(cart, bios.map(|p| p.as_path()));
    let title = if emu.cart_title.is_empty() {
        rom.file_name()
            .and_then(|s| s.to_str())
            .unwrap_or("fable")
            .to_string()
    } else {
        emu.cart_title.clone()
    };
    play::run_window(&mut emu, &title)
}

fn run_rom(
    rom: &PathBuf,
    frames: u32,
    dump: Option<&PathBuf>,
    present: bool,
    bios: Option<&PathBuf>,
) -> Result<()> {
    let cart = Cart::load(rom)?;
    cart::print_info(&cart);
    println!("  lighting lantern for {frames} frame(s)…");
    let mut emu = Emu::from_cart(cart, bios.map(|p| p.as_path()));
    let n = emu.run_frames(frames.max(1));
    println!(
        "  burned {n} frame(s) · cycles {} · pc=0x{:08X}",
        emu.cpu.cycles,
        emu.cpu.pc()
    );
    let dump_path = dump
        .cloned()
        .unwrap_or_else(|| std::env::temp_dir().join("fairy-lantern-last.ppm"));
    video::write_ppm(&dump_path, &emu.ppu.frame)
        .with_context(|| format!("dump {}", dump_path.display()))?;
    println!("  frame → {}", dump_path.display());
    if present && !video::present_terminal(&emu.ppu.frame) {
        println!("  (chafa unavailable)");
    }
    Ok(())
}

fn tui_list(dir: Option<PathBuf>) -> Result<()> {
    let dir = dir.unwrap_or_else(|| {
        std::env::var("FAIRY_LANTERN_ROMS")
            .map(PathBuf::from)
            .unwrap_or_else(|_| {
                let base = std::env::var_os("XDG_DATA_HOME")
                    .map(PathBuf::from)
                    .unwrap_or_else(|| {
                        PathBuf::from(std::env::var_os("HOME").unwrap_or_default())
                            .join(".local/share")
                    });
                base.join("faeos/fairy-lantern/roms")
            })
    });
    println!("✦ Fairy Lantern — fables in {}", dir.display());
    println!("  (built-in)  SPARK   fairy-lantern spark");
    if !dir.is_dir() {
        println!("  (no dir yet — mkdir or set FAIRY_LANTERN_ROMS)");
        return Ok(());
    }
    let mut paths: Vec<_> = std::fs::read_dir(&dir)?
        .filter_map(|e| e.ok())
        .map(|e| e.path())
        .filter(|p| {
            p.extension()
                .and_then(|x| x.to_str())
                .map(|x| x.eq_ignore_ascii_case("gba"))
                .unwrap_or(false)
        })
        .collect();
    paths.sort();
    for (i, p) in paths.iter().enumerate() {
        match Cart::load(p) {
            Ok(c) => println!(
                "  {:3}. {:12}  {}",
                i + 1,
                c.game_code,
                if c.title.is_empty() {
                    p.file_name().and_then(|s| s.to_str()).unwrap_or("?")
                } else {
                    &c.title
                }
            ),
            Err(e) => println!("  ??? {}", e),
        }
    }
    Ok(())
}


fn debug_spark(steps: u32) {
    let cart = fable::spark_rom();
    cart::print_info(&cart);
    let mut emu = Emu::new(&cart, None);
    println!("start pc={:08X}", emu.cpu.pc());
    for i in 0..steps {
        let pc = emu.cpu.pc();
        let op = emu.bus.read32(pc);
        let c = emu.cpu.step(&mut emu.bus);
        emu.ppu.step(&mut emu.bus, c);
        let npc = emu.cpu.pc();
        // dump around wait leave / erase / draw
        if i < 20 || (0x08000134..=0x08000180).contains(&pc) || (0x08000134..=0x08000180).contains(&npc) {
            println!(
                "{:5} pc={:08X} op={:08X} -> {:08X} r0={:08X} r1={:08X} r4={} r5={} r8={:04X} sp={:08X} lr={:08X} vcnt={}",
                i, pc, op, npc, emu.cpu.r[0], emu.cpu.r[1], emu.cpu.r[4], emu.cpu.r[5],
                emu.cpu.r[8], emu.cpu.r[13], emu.cpu.r[14], emu.bus.read16(0x04000006)
            );
        }
    }
    let lit = emu.ppu.frame.iter().filter(|&&p| p != 0).count();
    println!("lit pixels after {} steps: {}", steps, lit);
    println!("vram[0..4]={:02x?}", &emu.bus.vram[0..8]);
    // center pixel offset
    let off = (80 * 240 + 120) * 2;
    println!("vram center={:02x}{:02x}", emu.bus.vram[off], emu.bus.vram[off+1]);
}

fn run_self_tests() -> usize {
    let mut passed = 0;

    {
        let mut rom = vec![0u8; 0x200];
        rom[0..4].copy_from_slice(&0xE3A0_0001u32.to_le_bytes());
        rom[4..8].copy_from_slice(&0xE280_0002u32.to_le_bytes());
        rom[8..12].copy_from_slice(&0xEAFF_FFFEu32.to_le_bytes());
        let cart = Cart {
            data: rom,
            title: "t".into(),
            game_code: "T".into(),
            maker: "00".into(),
            path: "m".into(),
        };
        let mut emu = Emu::new(&cart, None);
        emu.cpu.set_pc(0x0800_0000);
        emu.cpu.step(&mut emu.bus);
        emu.cpu.step(&mut emu.bus);
        assert_eq!(emu.cpu.r[0], 3);
        passed += 1;
    }

    {
        let cart = Cart {
            data: vec![0u8; 0x200],
            title: "t".into(),
            game_code: "T".into(),
            maker: "00".into(),
            path: "m".into(),
        };
        let mut emu = Emu::new(&cart, None);
        emu.bus.write16(0x0300_0000, 0x2005);
        emu.bus.write16(0x0300_0002, 0x3003);
        emu.cpu.cpsr.thumb = true;
        emu.cpu.set_pc(0x0300_0000);
        emu.cpu.step(&mut emu.bus);
        emu.cpu.step(&mut emu.bus);
        assert_eq!(emu.cpu.r[0], 8);
        passed += 1;
    }

    {
        let cart = fable::spark_rom();
        let mut emu = Emu::new(&cart, None);
        let n = emu.run_frames(3);
        assert!(n >= 1, "spark produces frames");
        // Mode 3 should be on; spark near center should be lit
        let dc = emu.bus.dispcnt();
        assert_eq!(dc & 7, 3, "DISPCNT mode3, got {dc:#x}");
        // scan for any bright pixel in framebuffer
        let lit = emu.ppu.frame.iter().any(|&p| p & 0x7FFF != 0);
        assert!(lit, "spark should draw at least one pixel");
        passed += 1;
    }

    {
        let cart = Cart {
            data: vec![0u8; 0x200],
            title: "p".into(),
            game_code: "P".into(),
            maker: "00".into(),
            path: "m".into(),
        };
        let mut emu = Emu::new(&cart, None);
        emu.bus.write16(0x0400_0000, 0x0003);
        emu.bus.write16(0x0600_0000, 0x001F);
        ppu::render::render_scanline(&emu.bus, 0, &mut emu.ppu.frame);
        assert_eq!(emu.ppu.frame[0] & 0x1F, 0x1F);
        passed += 1;
    }

    passed
}

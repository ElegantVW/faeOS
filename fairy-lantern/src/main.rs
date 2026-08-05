//! Fairy Lantern — light a fable; play a pocket world (GBA).
//! From-scratch emulator for faeOS. No foreign cores.

mod bus;
mod cart;
mod cpu;
mod emu;
mod ppu;
mod video;

use anyhow::{bail, Context, Result};
use cart::Cart;
use clap::{Parser, Subcommand};
use emu::Emu;
use std::path::PathBuf;

#[derive(Parser, Debug)]
#[command(
    name = "fairy-lantern",
    about = "Fairy Lantern — GBA emulator from scratch (faeOS)",
    long_about = "Light a fable; play a pocket world.\n\
                  From-scratch ARM7TDMI + PPU. No mGBA/libretro.\n\
                  ROMs are yours alone — never ship copyrighted carts."
)]
struct Cli {
    #[command(subcommand)]
    cmd: Option<Commands>,

    /// Fable to light (.gba) when no subcommand
    rom: Option<PathBuf>,

    /// Frames to run then exit (0 = until interrupted — headless dump mode)
    #[arg(long, default_value_t = 3)]
    frames: u32,

    /// Write final frame to this PPM path
    #[arg(long)]
    dump: Option<PathBuf>,

    /// Show frame in terminal via chafa after run
    #[arg(long)]
    present: bool,

    /// Optional GBA BIOS file (or set FAIRY_LANTERN_BIOS)
    #[arg(long)]
    bios: Option<PathBuf>,
}

#[derive(Subcommand, Debug)]
enum Commands {
    /// Show fable (ROM) header
    Info { rom: PathBuf },
    /// Run CPU/PPU self-tests
    Test,
    /// Light a fable (run ROM)
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
    /// TUI gallery (stub — lists ROMs)
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
            let c = Cart::load(&rom)?;
            cart::print_info(&c);
        }
        Some(Commands::Test) => {
            let n = run_self_tests();
            println!("✦ Fairy Lantern self-tests: {n} passed");
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
        Some(Commands::Tui { dir }) => {
            tui_list(dir)?;
        }
        None => {
            if let Some(rom) = cli.rom {
                run_rom(
                    &rom,
                    cli.frames,
                    cli.dump.as_ref(),
                    cli.present,
                    cli.bios.as_ref(),
                )?;
            } else {
                println!(
                    "✦ Fairy Lantern — light a fable; play a pocket world\n\
                     \n\
                     Usage:\n\
                       fairy-lantern <rom.gba> [--frames N] [--present] [--dump out.ppm]\n\
                       fairy-lantern info <rom.gba>\n\
                       fairy-lantern test\n\
                       fairy-lantern tui [--dir ~/roms]\n\
                       fairy-lantern run <rom.gba> …\n\
                     \n\
                     Controls (interactive window: later phase)\n\
                       Z/X A/B · arrows D-pad · Enter Start · Esc snuff\n"
                );
            }
        }
    }
    Ok(())
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

    let mut emu = Emu::from_path(rom, bios.map(|p| p.as_path()))?;
    let n = emu.run_frames(frames.max(1));
    println!(
        "  burned {n} frame(s) · cpu cycles {} · pc=0x{:08X} thumb={}",
        emu.cpu.cycles,
        emu.cpu.pc(),
        emu.cpu.cpsr.thumb
    );

    let dump_path = dump
        .cloned()
        .unwrap_or_else(|| std::env::temp_dir().join("fairy-lantern-last.ppm"));
    video::write_ppm(&dump_path, &emu.ppu.frame)
        .with_context(|| format!("dump {}", dump_path.display()))?;
    println!("  frame → {}", dump_path.display());

    if present {
        if !video::present_terminal(&emu.ppu.frame) {
            println!("  (chafa not available — open the PPM)");
        }
    }
    Ok(())
}

fn tui_list(dir: Option<PathBuf>) -> Result<()> {
    let dir = dir.unwrap_or_else(|| {
        std::env::var("FAIRY_LANTERN_ROMS")
            .map(PathBuf::from)
            .unwrap_or_else(|_| {
                dirs_roms_default()
            })
    });
    println!("✦ Fairy Lantern — fables in {}", dir.display());
    if !dir.is_dir() {
        bail!("no such directory (set FAIRY_LANTERN_ROMS or pass --dir)");
    }
    let mut found = 0;
    let mut paths: Vec<PathBuf> = std::fs::read_dir(&dir)?
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
            Ok(c) => {
                println!(
                    "  {:3}. {:12}  {}  ({})",
                    i + 1,
                    if c.game_code.is_empty() {
                        "----"
                    } else {
                        &c.game_code
                    },
                    if c.title.is_empty() {
                        p.file_name().and_then(|s| s.to_str()).unwrap_or("?")
                    } else {
                        &c.title
                    },
                    p.file_name().and_then(|s| s.to_str()).unwrap_or("")
                );
                found += 1;
            }
            Err(e) => println!("  ???  {} ({e})", p.display()),
        }
    }
    if found == 0 {
        println!("  (no .gba fables yet — drop ROMs here)");
    } else {
        println!("\n  run: fairy-lantern <path.gba> --present");
    }
    Ok(())
}

fn dirs_roms_default() -> PathBuf {
    let base = std::env::var_os("XDG_DATA_HOME")
        .map(PathBuf::from)
        .unwrap_or_else(|| {
            PathBuf::from(std::env::var_os("HOME").unwrap_or_default()).join(".local/share")
        });
    base.join("faeos/fairy-lantern/roms")
}

fn run_self_tests() -> usize {
    let mut passed = 0;

    // MOV r0, #1 ; ADD r0, r0, #2  → r0=3
    {
        let mut rom = vec![0u8; 0x200];
        // ARM: MOV r0, #1  => E3A00001
        rom[0..4].copy_from_slice(&0xE3A0_0001u32.to_le_bytes());
        // ADD r0, r0, #2 => E2800002
        rom[4..8].copy_from_slice(&0xE280_0002u32.to_le_bytes());
        // B . => EAFFFFFE infinite (won't reach)
        rom[8..12].copy_from_slice(&0xEAFF_FFFEu32.to_le_bytes());
        let cart = Cart {
            data: rom,
            title: "test".into(),
            game_code: "TEST".into(),
            maker: "00".into(),
            path: "mem".into(),
        };
        let mut emu = Emu::new(&cart, None);
        emu.cpu.set_pc(0x0800_0000);
        for _ in 0..2 {
            emu.cpu.step(&mut emu.bus);
        }
        assert_eq!(emu.cpu.r[0], 3, "MOV/ADD");
        passed += 1;
    }

    // Thumb: movs r0, #5
    {
        let mut rom = vec![0u8; 0x200];
        // Need ARM BX to thumb first at 0x08000000
        // LDR r0, [pc, #0]; BX r0 — or just set thumb and PC
        let cart = Cart {
            data: rom.clone(),
            title: "t".into(),
            game_code: "T".into(),
            maker: "00".into(),
            path: "m".into(),
        };
        let mut emu = Emu::new(&cart, None);
        // place thumb code in IWRAM
        // movs r0, #5 = 0x2005
        emu.bus.write16(0x0300_0000, 0x2005);
        // adds r0, #3 = 0x3003
        emu.bus.write16(0x0300_0002, 0x3003);
        emu.cpu.cpsr.thumb = true;
        emu.cpu.set_pc(0x0300_0000);
        emu.cpu.step(&mut emu.bus);
        emu.cpu.step(&mut emu.bus);
        assert_eq!(emu.cpu.r[0], 8, "thumb mov/add");
        passed += 1;
    }

    // Mode 3 pixel write visible in PPU
    {
        let cart = Cart {
            data: vec![0u8; 0x200],
            title: "p".into(),
            game_code: "P".into(),
            maker: "00".into(),
            path: "m".into(),
        };
        let mut emu = Emu::new(&cart, None);
        emu.bus.write16(0x0400_0000, 0x0003); // Mode 3
        // red pixel at 0,0 BGR555: R=31
        emu.bus.write16(0x0600_0000, 0x001F);
        ppu::render::render_scanline(&emu.bus, 0, &mut emu.ppu.frame);
        assert_eq!(emu.ppu.frame[0] & 0x1F, 0x1F, "mode3 red");
        passed += 1;
    }

    passed
}

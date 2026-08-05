//! Home TUI — bare `fairy` / `fairy-lantern` entry.

use crate::cart::Cart;
use crate::recents;
use anyhow::{bail, Result};
use std::io::{self, Read, Write};
use std::path::PathBuf;

#[derive(Clone, Debug)]
enum Item {
    Last(PathBuf),
    Spark,
    Browse(PathBuf),
    OpenPath,
    Recent(PathBuf),
}

pub enum Choice {
    Spark,
    Rom(PathBuf),
    Quit,
}

/// Interactive home screen. Returns what to light.
pub fn run_home() -> Result<Choice> {
    recents::ensure_dirs()?;
    let mut items = build_items();
    if items.is_empty() {
        items.push(Item::Spark);
    }
    let mut sel = 0usize;
    let mut flash = String::new();

    let mut term = RawTerm::new()?;
    loop {
        let frame = draw(&items, sel, &flash);
        term.paint(&frame)?;
        flash.clear();

        match term.read_key()? {
            Key::Quit => {
                term.restore()?;
                return Ok(Choice::Quit);
            }
            Key::Up => {
                if sel > 0 {
                    sel -= 1;
                }
            }
            Key::Down => {
                if sel + 1 < items.len() {
                    sel += 1;
                }
            }
            Key::Home => sel = 0,
            Key::End => sel = items.len().saturating_sub(1),
            Key::Enter | Key::Right => {
                match act_item(&items[sel], &mut term)? {
                    Some(c) => {
                        term.restore()?;
                        return Ok(c);
                    }
                    None => {
                        items = build_items();
                        if sel >= items.len() {
                            sel = items.len().saturating_sub(1);
                        }
                    }
                }
            }
            Key::Char('l') | Key::Char('L') => {
                if let Some(p) = recents::last_rom() {
                    term.restore()?;
                    return Ok(Choice::Rom(p));
                }
                flash = "no last fable yet — open one first".into();
            }
            Key::Char('s') | Key::Char('S') => {
                term.restore()?;
                return Ok(Choice::Spark);
            }
            Key::Char('o') | Key::Char('O') => {
                term.restore_soft()?;
                match prompt_path()? {
                    Some(p) if p.is_file() => {
                        term.restore()?;
                        return Ok(Choice::Rom(p));
                    }
                    Some(_) => {
                        term.re_raw()?;
                        flash = "not a file".into();
                    }
                    None => {
                        term.re_raw()?;
                        flash = "cancelled".into();
                    }
                }
            }
            Key::Char('b') | Key::Char('B') => {
                // jump to first browse item
                if let Some(i) = items.iter().position(|x| matches!(x, Item::Browse(_))) {
                    sel = i;
                } else {
                    flash = "no .gba in roms dir yet".into();
                }
            }
            Key::Char(c @ '1'..='9') => {
                let n = (c as u8 - b'1') as usize;
                if n < items.len() {
                    sel = n;
                    match act_item(&items[sel], &mut term)? {
                        Some(c) => {
                            term.restore()?;
                            return Ok(c);
                        }
                        None => {
                            items = build_items();
                            if sel >= items.len() {
                                sel = items.len().saturating_sub(1);
                            }
                        }
                    }
                }
            }
            _ => {}
        }
    }
}

fn act_item(item: &Item, term: &mut RawTerm) -> Result<Option<Choice>> {
    match item {
        Item::Last(p) | Item::Recent(p) | Item::Browse(p) => Ok(Some(Choice::Rom(p.clone()))),
        Item::Spark => Ok(Some(Choice::Spark)),
        Item::OpenPath => {
            term.restore_soft()?;
            let r = match prompt_path()? {
                Some(p) if p.is_file() => Ok(Some(Choice::Rom(p))),
                Some(_) => {
                    term.re_raw()?;
                    Ok(None)
                }
                None => {
                    term.re_raw()?;
                    Ok(None)
                }
            };
            if matches!(r, Ok(None)) {
                // stay in tui
            } else if matches!(r, Ok(Some(_))) {
                // caller restores fully
            }
            r
        }
    }
}

fn build_items() -> Vec<Item> {
    let mut items = Vec::new();
    if let Some(last) = recents::last_rom() {
        items.push(Item::Last(last));
    }
    items.push(Item::Spark);

    let roms = recents::list_roms_dir();
    for p in roms.iter().take(8) {
        // avoid duplicating last at top of browse if same
        if items.iter().any(|i| match i {
            Item::Last(x) | Item::Recent(x) => x == p,
            _ => false,
        }) {
            continue;
        }
        items.push(Item::Browse(p.clone()));
    }

    for p in recents::load_recents() {
        if items.iter().any(|i| match i {
            Item::Last(x) | Item::Recent(x) | Item::Browse(x) => x == &p,
            _ => false,
        }) {
            continue;
        }
        items.push(Item::Recent(p));
        if items.len() > 16 {
            break;
        }
    }

    items.push(Item::OpenPath);
    items
}

fn label(item: &Item) -> String {
    match item {
        Item::Last(p) => {
            let name = file_label(p);
            format!("Last     ·  {name}")
        }
        Item::Spark => "SPARK    ·  built-in fable (always works)".into(),
        Item::Browse(p) => {
            let name = file_label(p);
            let title = Cart::load(p)
                .ok()
                .map(|c| {
                    if c.title.is_empty() {
                        name.clone()
                    } else {
                        c.title
                    }
                })
                .unwrap_or(name);
            format!("Roms     ·  {title}")
        }
        Item::Recent(p) => format!("Recent   ·  {}", file_label(p)),
        Item::OpenPath => "Open…    ·  type a path to a .gba".into(),
    }
}

fn file_label(p: &std::path::Path) -> String {
    p.file_name()
        .and_then(|s| s.to_str())
        .unwrap_or("?")
        .to_string()
}

fn draw(items: &[Item], sel: usize, flash: &str) -> String {
    let mut lines = Vec::new();
    lines.push("╭─ ✦ Fairy Lantern ✦ home ✦ ─────────────────────────────────╮".into());
    lines.push("│ light a fable · play a pocket world                        │".into());
    if !flash.is_empty() {
        lines.push(format!("│ {}│", pad_fit(flash, 60)));
    } else {
        let last = recents::last_rom()
            .map(|p| file_label(&p))
            .unwrap_or_else(|| "(none yet)".into());
        lines.push(format!("│ last: {}│", pad_fit(&last, 54)));
    }
    lines.push("│                                                            │".into());
    lines.push("│ Choose (↑↓ · enter):                                       │".into());
    for (i, it) in items.iter().enumerate() {
        let mark = if i == sel { "✦" } else { " " };
        let num = i + 1;
        let row = format!(" {mark} {num:2}  {}", label(it));
        lines.push(format!("│ {}│", pad_fit(&row, 60)));
    }
    lines.push("│                                                            │".into());
    lines.push("╰────────────────────────────────────────────────────────────╯".into());
    lines.push("╭─ ✦ Runes ✦ ────────────────────────────────────────────────╮".into());
    lines.push("│ ↑↓ move · enter light · l last · s spark · o path · q quit │".into());
    lines.push("╰────────────────────────────────────────────────────────────╯".into());
    lines.join("\n")
}

fn pad_fit(s: &str, width: usize) -> String {
    let mut out = String::new();
    let mut w = 0;
    for ch in s.chars() {
        let cw = if ch == '\t' { 1 } else { 1 };
        if w + cw > width {
            break;
        }
        out.push(ch);
        w += cw;
    }
    while w < width {
        out.push(' ');
        w += 1;
    }
    out
}

fn prompt_path() -> Result<Option<PathBuf>> {
    print!("\n  ✦ path to .gba (empty cancel): ");
    io::stdout().flush()?;
    let mut line = String::new();
    io::stdin().read_line(&mut line)?;
    let line = line.trim();
    if line.is_empty() {
        return Ok(None);
    }
    let p = PathBuf::from(line.replace('~', &std::env::var("HOME").unwrap_or_default()));
    // expand ~ already rough
    let p = if line.starts_with("~/") {
        PathBuf::from(std::env::var("HOME").unwrap_or_default()).join(&line[2..])
    } else {
        p
    };
    Ok(Some(p))
}

// ── raw terminal ──────────────────────────────────────────────

enum Key {
    Up,
    Down,
    Left,
    Right,
    Home,
    End,
    Enter,
    Quit,
    Char(char),
    Other,
}

struct RawTerm {
    old: libc::termios,
    active: bool,
}

impl RawTerm {
    fn new() -> Result<Self> {
        let mut old: libc::termios = unsafe { std::mem::zeroed() };
        unsafe {
            if libc::tcgetattr(0, &mut old) != 0 {
                bail!("tcgetattr (need a real tty)");
            }
            let mut raw = old;
            raw.c_lflag &= !(libc::ICANON | libc::ECHO | libc::ISIG);
            raw.c_iflag &= !(libc::IXON | libc::ICRNL);
            raw.c_cc[libc::VMIN] = 1;
            raw.c_cc[libc::VTIME] = 0;
            libc::tcsetattr(0, libc::TCSANOW, &raw);
        }
        print!("\x1b[?1049h\x1b[?25l");
        io::stdout().flush()?;
        Ok(Self { old, active: true })
    }

    fn paint(&mut self, s: &str) -> Result<()> {
        print!("\x1b[H\x1b[2J{s}");
        io::stdout().flush()?;
        Ok(())
    }

    fn read_key(&mut self) -> Result<Key> {
        let mut b = [0u8; 1];
        let n = unsafe { libc::read(0, b.as_mut_ptr() as *mut _, 1) };
        if n != 1 {
            return Ok(Key::Quit);
        }
        Ok(match b[0] {
            b'\n' | b'\r' => Key::Enter,
            b'\x03' | b'q' | b'Q' => Key::Quit,
            b'\x1b' => parse_esc(),
            c if c.is_ascii() => Key::Char(c as char),
            _ => Key::Other,
        })
    }

    fn restore_soft(&mut self) -> Result<()> {
        unsafe {
            libc::tcsetattr(0, libc::TCSANOW, &self.old);
        }
        print!("\x1b[?25h\x1b[?1049l\x1b[0m");
        io::stdout().flush()?;
        self.active = false;
        Ok(())
    }

    fn re_raw(&mut self) -> Result<()> {
        let mut raw = self.old;
        raw.c_lflag &= !(libc::ICANON | libc::ECHO | libc::ISIG);
        raw.c_iflag &= !(libc::IXON | libc::ICRNL);
        raw.c_cc[libc::VMIN] = 1;
        raw.c_cc[libc::VTIME] = 0;
        unsafe {
            libc::tcsetattr(0, libc::TCSANOW, &raw);
        }
        print!("\x1b[?1049h\x1b[?25l");
        io::stdout().flush()?;
        self.active = true;
        Ok(())
    }

    fn restore(&mut self) -> Result<()> {
        if self.active {
            self.restore_soft()?;
        } else {
            unsafe {
                libc::tcsetattr(0, libc::TCSANOW, &self.old);
            }
            print!("\x1b[?25h\x1b[0m");
            io::stdout().flush()?;
        }
        Ok(())
    }
}

impl Drop for RawTerm {
    fn drop(&mut self) {
        let _ = self.restore();
    }
}

fn parse_esc() -> Key {
    let mut seq = Vec::new();
    for _ in 0..6 {
        if !wait_stdin(25) {
            break;
        }
        let mut b = [0u8; 1];
        let n = unsafe { libc::read(0, b.as_mut_ptr() as *mut _, 1) };
        if n != 1 {
            break;
        }
        seq.push(b[0]);
        let last = *seq.last().unwrap();
        if seq.len() >= 2 && (0x40..=0x7e).contains(&last) {
            break;
        }
    }
    match seq.as_slice() {
        [b'[', b'A'] | [b'O', b'A'] => Key::Up,
        [b'[', b'B'] | [b'O', b'B'] => Key::Down,
        [b'[', b'C'] | [b'O', b'C'] => Key::Right,
        [b'[', b'D'] | [b'O', b'D'] => Key::Left,
        [b'[', b'H'] | [b'O', b'H'] => Key::Home,
        [b'[', b'F'] | [b'O', b'F'] => Key::End,
        _ => Key::Other,
    }
}

fn wait_stdin(ms: i32) -> bool {
    unsafe {
        let mut pfd = libc::pollfd {
            fd: 0,
            events: libc::POLLIN,
            revents: 0,
        };
        libc::poll(&mut pfd, 1, ms) > 0
    }
}

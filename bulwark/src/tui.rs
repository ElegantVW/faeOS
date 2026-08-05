//! Everyday Bulwark TUI — themed names + plain one-liners + numbered actions.

use crate::aegis;
use crate::paths;
use crate::purity;
use crate::tutorial;
use crate::ward;
use crate::words::{self, Posture};
use anyhow::Result;
use std::io::{self, Read, Write};
use std::process::Command;
use std::fs;

pub const PINK: &str = "\x1b[38;5;175m";
pub const DIM: &str = "\x1b[38;5;245m";
pub const RESET: &str = "\x1b[0m";
pub const BOLD: &str = "\x1b[1m";
const OK: &str = "\x1b[38;5;78m";
const WARN: &str = "\x1b[38;5;214m";

#[derive(Clone, Copy, PartialEq)]
enum Screen {
    Home,
    Help,
    Purity,
    Ward,
    Sentinel,
    AegisOnConfirm,
    AegisOffConfirm,
    AegisDeadman,
    Message,
}

pub fn run() -> Result<()> {
    let _ = paths::ensure_dirs();
    let mut term = Term::new()?;

    // First-time tour
    if !words::tutorial_done() {
        if !tutorial::run_tour(&mut term)? {
            term.restore()?;
            return Ok(());
        }
    }

    let mut screen = Screen::Home;
    let mut flash = String::new();
    let mut msg_lines: Vec<String> = Vec::new();

    loop {
        let posture = words::gather_posture();
        let frame = match screen {
            Screen::Home => draw_home(&posture, &flash),
            Screen::Help => {
                let lines = words::help_lines();
                render_page("Bulwark ✦ help", "keeps this computer safe", &lines, "b back · q leave")
            }
            Screen::Purity => draw_purity(&flash),
            Screen::Ward => draw_ward(&flash),
            Screen::Sentinel => draw_sentinel(&flash),
            Screen::AegisOnConfirm => render_page(
                "Bulwark ✦ Aegis",
                "front-door lock (who can knock)",
                &[
                    "Turn the front-door lock ON?".into(),
                    "".into(),
                    "This blocks strangers on the network.".into(),
                    "We can undo later (home menu 5).".into(),
                    "You may need a grown-up password.".into(),
                    "".into(),
                    "  y  yes, lock the door".into(),
                    "  n  no, go back".into(),
                ],
                "y lock · n back · q leave",
            ),
            Screen::AegisOffConfirm => render_page(
                "Bulwark ✦ Aegis",
                "front-door lock (who can knock)",
                &[
                    "Turn the front-door lock OFF?".into(),
                    "".into(),
                    "Strangers could knock again.".into(),
                    "This undoes Aegis rules (table bulwark).".into(),
                    "".into(),
                    "  y  yes, unlock".into(),
                    "  n  no, go back".into(),
                ],
                "y unlock · n back · q leave",
            ),
            Screen::AegisDeadman => render_page(
                "Bulwark ✦ Aegis",
                "front-door lock (who can knock)",
                &[
                    "Aegis is testing the lock.".into(),
                    "".into(),
                    "If everything still works, press y to KEEP it.".into(),
                    "If something broke, wait — I undo by myself.".into(),
                    "".into(),
                    "  y  keep the lock".into(),
                    "  b  back home (deadman still runs)".into(),
                ],
                "y keep · b home · q leave",
            ),
            Screen::Message => render_page(
                "Bulwark ✦ note",
                "keeps this computer safe",
                &msg_lines,
                "b or enter back home · q leave",
            ),
        };
        term.draw(&frame)?;
        flash.clear();

        match term.read_key()? {
            Key::Char('q') | Key::Ctrl('c') => break,
            Key::Esc | Key::Char('b') => {
                if screen == Screen::Home {
                    break;
                }
                screen = Screen::Home;
            }
            Key::Enter if screen == Screen::Message => screen = Screen::Home,
            Key::Char('?') | Key::Char('h') if screen == Screen::Home => {
                screen = Screen::Help;
            }
            // —— home menu ——
            Key::Char(c) if screen == Screen::Home => match c {
                '1' => screen = Screen::Purity,
                '2' => screen = Screen::Ward,
                '3' => screen = Screen::Sentinel,
                '4' => screen = Screen::AegisOnConfirm,
                '5' => screen = Screen::AegisOffConfirm,
                '6' => {
                    msg_lines = run_install_msg();
                    screen = Screen::Message;
                }
                '7' => {
                    if !tutorial::run_tour(&mut term)? {
                        break;
                    }
                    flash = "Tour finished — press 1 for a Purity photo.".into();
                }
                'r' => flash = "Refreshed.".into(),
                _ => {}
            },
            // —— purity ——
            Key::Char('1') | Key::Char('p') if screen == Screen::Purity => {
                flash = match take_photo() {
                    Ok(n) => format!("Purity photo saved ({n} files)."),
                    Err(e) => format!("Could not take photo: {e}"),
                };
            }
            Key::Char('2') | Key::Char('c') if screen == Screen::Purity => {
                flash = compare_photo();
            }
            // —— ward ——
            Key::Char('1') | Key::Char('w') | Key::Enter if screen == Screen::Ward => {
                flash = format!("Ward searched — see list above.");
                // list refreshes each draw
            }
            // —— aegis on ——
            Key::Char('y') | Key::Char('Y') if screen == Screen::AegisOnConfirm => {
                match run_aegis_apply() {
                    Ok(msg) => {
                        flash = msg;
                        screen = Screen::AegisDeadman;
                    }
                    Err(e) => {
                        msg_lines = vec![
                            "Aegis could not lock the door.".into(),
                            "".into(),
                            e.to_string(),
                            "".into(),
                            "Try with a grown-up password:".into(),
                            "  sudo bulwark aegis apply desktop".into(),
                            "  bulwark aegis confirm".into(),
                        ];
                        screen = Screen::Message;
                    }
                }
            }
            Key::Char('n') | Key::Char('N')
                if matches!(
                    screen,
                    Screen::AegisOnConfirm | Screen::AegisOffConfirm
                ) =>
            {
                screen = Screen::Home;
                flash = "OK — nothing changed.".into();
            }
            Key::Char('y') | Key::Char('Y') if screen == Screen::AegisOffConfirm => {
                match run_aegis_undo() {
                    Ok(m) => {
                        msg_lines = vec![m, "".into(), "Front door lock is OFF.".into()];
                        screen = Screen::Message;
                    }
                    Err(e) => {
                        msg_lines = vec![
                            "Could not unlock.".into(),
                            e.to_string(),
                            "".into(),
                            "Try: sudo bulwark aegis undo".into(),
                        ];
                        screen = Screen::Message;
                    }
                }
            }
            Key::Char('y') | Key::Char('Y') if screen == Screen::AegisDeadman => {
                let marker = paths::data_dir().join("aegis").join("confirm.ok");
                let _ = paths::ensure_dirs();
                let _ = fs::write(&marker, b"ok\n");
                // also run confirm via CLI path
                let _ = Command::new(std::env::current_exe()?)
                    .args(["aegis", "confirm"])
                    .status();
                msg_lines = vec![
                    "Aegis lock KEPT. Nice!".into(),
                    "".into(),
                    "Front-door lock stays ON.".into(),
                ];
                screen = Screen::Message;
            }
            _ => {}
        }
    }
    term.restore()?;
    Ok(())
}

fn draw_home(p: &Posture, flash: &str) -> String {
    let mut lines: Vec<String> = Vec::new();
    lines.push("How safe is this computer?".into());
    lines.push(String::new());
    lines.push(format!("          {}", p.mood.banner()));
    lines.push(String::new());
    lines.push(format!(
        "  Aegis      {}",
        pad_right("front-door lock", 22)
    ));
    lines.push(format!("             {}", p.aegis_line));
    lines.push(format!(
        "  Purity     {}",
        pad_right("file photo", 22)
    ));
    lines.push(format!("             {}", p.purity_line));
    lines.push(format!(
        "  Ward       {}",
        pad_right("sneaky search", 22)
    ));
    lines.push(format!("             {}", p.ward_line));
    lines.push(format!(
        "  Sentinel   {}",
        pad_right("open windows", 22)
    ));
    lines.push(format!("             {}", p.sentinel_line));
    lines.push(String::new());
    if !flash.is_empty() {
        lines.push(format!("{OK}  {flash}{RESET}"));
        lines.push(String::new());
    }
    lines.push("What do you want to do?".into());
    lines.push("  1  Purity — take a photo of important files".into());
    lines.push("  2  Ward — search for sneaky stuff".into());
    lines.push("  3  Sentinel — see open windows".into());
    lines.push("  4  Aegis — turn the lock ON  (may need password)".into());
    lines.push("  5  Aegis — turn the lock OFF / undo".into());
    lines.push("  6  Keep watching (install helper)".into());
    lines.push("  7  Tour — short tutorial".into());
    lines.push("  ?  Help".into());
    lines.push("  q  Leave".into());

    render_page(
        "Bulwark ✦ home",
        words::plain_name("Bulwark"),
        &lines,
        "type a number · ? help · q leave",
    )
}

fn draw_purity(flash: &str) -> String {
    let mut lines = vec![
        "Purity — photo of important files".into(),
        "".into(),
        "  1  Take a photo (remember good files)".into(),
        "  2  Compare to the last photo".into(),
        "  b  Back home".into(),
        "".into(),
    ];
    let path = paths::purity_baseline_path();
    if !path.is_file() {
        lines.push("No photo yet. Press 1.".into());
    } else if let Ok(bl) = purity::load_baseline(&path) {
        let f = purity::check(&bl);
        lines.push(format!("Last photo: {} files.", bl.files.len()));
        if f.is_empty() {
            lines.push(format!("{OK}Photo matches — nothing weird.{RESET}"));
        } else {
            lines.push(format!("{WARN}{} change(s):{RESET}", f.len()));
            for x in f.iter().take(12) {
                lines.push(format!("  · {}", words::purity_plain(x)));
            }
            if f.len() > 12 {
                lines.push(format!("  … and {} more", f.len() - 12));
            }
        }
    }
    if !flash.is_empty() {
        lines.push(String::new());
        lines.push(format!("{OK}{flash}{RESET}"));
    }
    render_page(
        "Bulwark ✦ Purity",
        words::plain_name("Purity"),
        &lines,
        "1 photo · 2 compare · b back",
    )
}

fn draw_ward(flash: &str) -> String {
    let findings = ward::hunt();
    let mut lines = vec![
        "Ward — search for sneaky stuff".into(),
        "".into(),
    ];
    if findings.is_empty() {
        lines.push(format!("{OK}All clear! Nothing sneaky found.{RESET}"));
    } else {
        lines.push(format!("Found {} thing(s):", findings.len()));
        for f in findings.iter().take(14) {
            lines.push(format!("  · {}", words::ward_plain(f)));
        }
        if findings.len() > 14 {
            lines.push(format!("  … and {} more", findings.len() - 14));
        }
    }
    lines.push(String::new());
    lines.push("  1  Search again".into());
    lines.push("  b  Back home".into());
    if !flash.is_empty() {
        lines.push(String::new());
        lines.push(flash.to_string());
    }
    render_page(
        "Bulwark ✦ Ward",
        words::plain_name("Ward"),
        &lines,
        "1 search · b back",
    )
}

fn draw_sentinel(_flash: &str) -> String {
    let mut lines = vec![
        "Sentinel — open network windows".into(),
        "These doors listen on the network right now.".into(),
        "".into(),
    ];
    for row in words::sentinel_plain_lines().into_iter().take(16) {
        lines.push(format!("  {row}"));
    }
    lines.push(String::new());
    lines.push("  b  Back home".into());
    render_page(
        "Bulwark ✦ Sentinel",
        words::plain_name("Sentinel"),
        &lines,
        "b back · r on home refreshes",
    )
}

fn take_photo() -> Result<usize> {
    let roots = purity::default_roots();
    let (bl, _) = purity::build_baseline(&roots);
    let n = bl.files.len();
    purity::save_baseline(&paths::purity_baseline_path(), &bl)?;
    Ok(n)
}

fn compare_photo() -> String {
    let path = paths::purity_baseline_path();
    if !path.is_file() {
        return "No photo yet — press 1 first.".into();
    }
    match purity::load_baseline(&path) {
        Ok(bl) => {
            let f = purity::check(&bl);
            if f.is_empty() {
                "Photo matches — all good!".into()
            } else {
                format!("{} file(s) look different — see list.", f.len())
            }
        }
        Err(e) => format!("Could not read photo: {e}"),
    }
}

fn run_aegis_apply() -> Result<String> {
    // Try in-process apply (needs root). If EPERM, tell user to use sudo.
    let text = aegis::load_bundled_profile("desktop")?;
    let _ = paths::ensure_dirs();
    fs::write(paths::policy_path(), &text)?;
    match aegis::apply_policy_text(&text, &paths::aegis_snapshot_path()) {
        Ok(res) => {
            // start deadman like CLI
            let marker = paths::data_dir().join("aegis").join("confirm.ok");
            let _ = fs::remove_file(&marker);
            let exe = std::env::current_exe()?;
            let _ = Command::new(&exe)
                .args(["aegis", "undo", "--table", "bulwark"])
                .env("BULWARK_DEADMAN", "90")
                .env("BULWARK_CONFIRM_PATH", &marker)
                .stdin(std::process::Stdio::null())
                .stdout(std::process::Stdio::null())
                .stderr(std::process::Stdio::null())
                .spawn();
            Ok(format!("{} — now confirm to keep.", res.message))
        }
        Err(e) => {
            // Try sudo -n first for passwordless
            let status = Command::new("sudo")
                .args(["-n", "bulwark", "aegis", "apply", "desktop", "--deadman", "90"])
                .status();
            match status {
                Ok(s) if s.success() => Ok(
                    "Aegis lock applied with sudo. Press y on next screen to keep it.".into(),
                ),
                _ => Err(e),
            }
        }
    }
}

fn run_aegis_undo() -> Result<String> {
    match aegis::flush_bulwark("bulwark", aegis::policy::Family::Inet) {
        Ok(()) => {
            let _ = fs::remove_file(paths::aegis_snapshot_path());
            Ok("Aegis lock removed.".into())
        }
        Err(e) => {
            let status = Command::new("sudo")
                .args(["-n", "bulwark", "aegis", "undo"])
                .status();
            if status.map(|s| s.success()).unwrap_or(false) {
                let _ = fs::remove_file(paths::aegis_snapshot_path());
                Ok("Aegis lock removed (sudo).".into())
            } else {
                Err(e)
            }
        }
    }
}

fn run_install_msg() -> Vec<String> {
    let exe = std::env::current_exe()
        .map(|p| p.display().to_string())
        .unwrap_or_else(|_| "bulwark".into());
    let status = Command::new(&exe).args(["install"]).status();
    match status {
        Ok(s) if s.success() => vec![
            "Keep watching — helper installed.".into(),
            "".into(),
            "Sentinel will peek every so often.".into(),
            "You can remove it later:".into(),
            "  bulwark uninstall".into(),
        ],
        Ok(_) | Err(_) => vec![
            "Could not install the helper automatically.".into(),
            "".into(),
            "Try in a terminal:".into(),
            "  bulwark install".into(),
        ],
    }
}

fn pad_right(s: &str, w: usize) -> String {
    let mut t = s.to_string();
    while t.chars().count() < w {
        t.push(' ');
    }
    t
}

// —— rendering ——

pub fn render_page(title: &str, subtitle: &str, lines: &[String], runes: &str) -> String {
    let mut body = Vec::new();
    if !subtitle.is_empty() {
        body.push(format!("{DIM}{subtitle}{RESET}"));
        body.push(String::new());
    }
    body.extend(lines.iter().cloned());
    render_simple(title, &body, &[runes])
}

/// Shared frame builder (also used by tutorial).
pub fn render_simple(title: &str, body: &[String], runes: &[&str]) -> String {
    let (cols, rows) = term_size();
    let width = cols.clamp(44, 96);
    let mut out = String::from("\x1b[H\x1b[2J");
    // head with title only
    let empty: &[String] = &[];
    out.push_str(&box_frame(title, empty, width, true));
    out.push('\n');
    let used = 4 + 4 + 2; // head + runes + gaps approx
    let avail = rows.saturating_sub(used).max(6);
    let clipped: Vec<String> = body.iter().take(avail).cloned().collect();
    out.push_str(&box_frame(" leaf ", &clipped, width, false));
    out.push('\n');
    let r: Vec<String> = runes.iter().map(|s| (*s).to_string()).collect();
    out.push_str(&box_frame(" Runes ", &r, width, true));
    out
}

fn box_frame(title: &str, lines: &[impl AsRef<str>], width: usize, pink_title: bool) -> String {
    let inner = width.saturating_sub(2);
    let mut s = String::new();
    let t = title.trim();
    let label = format!(" ✦ {t} ✦ ");
    let lab_len = label.chars().count();
    let fill = inner.saturating_sub(lab_len.max(1));
    let color = if pink_title { PINK } else { DIM };
    s.push_str(&format!(
        "{color}╭─{BOLD}{PINK}{label}{RESET}{color}{}╮{RESET}\n",
        "─".repeat(fill.saturating_sub(1).max(0))
    ));
    for line in lines {
        let plain = strip_ansi_len(line.as_ref());
        let mut content = line.as_ref().to_string();
        // pad visible width
        let vis = plain;
        let max = inner.saturating_sub(2);
        if vis > max {
            // crude truncate plain only
            let trunc: String = line
                .as_ref()
                .chars()
                .take(max.saturating_sub(1))
                .collect();
            content = format!("{trunc}…");
        }
        let pad = max.saturating_sub(strip_ansi_len(&content));
        s.push_str(&format!(
            "{color}│{RESET} {content}{} {color}│{RESET}\n",
            " ".repeat(pad)
        ));
    }
    s.push_str(&format!("{color}╰{}╯{RESET}", "─".repeat(inner)));
    s
}

fn strip_ansi_len(s: &str) -> usize {
    let mut n = 0;
    let mut chars = s.chars().peekable();
    while let Some(c) = chars.next() {
        if c == '\x1b' {
            if chars.peek() == Some(&'[') {
                chars.next();
                for x in chars.by_ref() {
                    if x.is_ascii_alphabetic() {
                        break;
                    }
                }
            }
        } else {
            n += 1;
        }
    }
    n
}

fn term_size() -> (usize, usize) {
    unsafe {
        let mut wsz: libc::winsize = std::mem::zeroed();
        if libc::ioctl(1, libc::TIOCGWINSZ, &mut wsz) == 0 && wsz.ws_col > 0 {
            return (wsz.ws_col as usize, wsz.ws_row as usize);
        }
    }
    (80, 24)
}

// —— terminal raw mode (public for tutorial) ——

pub struct Term {
    old: libc::termios,
}

#[derive(Debug)]
pub enum Key {
    Char(char),
    Ctrl(char),
    Esc,
    Enter,
}

impl Term {
    pub fn new() -> Result<Self> {
        let fd = 0;
        let mut old: libc::termios = unsafe { std::mem::zeroed() };
        unsafe {
            if libc::tcgetattr(fd, &mut old) != 0 {
                anyhow::bail!("tcgetattr");
            }
            let mut raw = old;
            raw.c_lflag &= !(libc::ICANON | libc::ECHO | libc::ISIG);
            raw.c_iflag &= !(libc::IXON);
            raw.c_cc[libc::VMIN] = 1;
            raw.c_cc[libc::VTIME] = 0;
            libc::tcsetattr(fd, libc::TCSANOW, &raw);
        }
        let mut out = io::stdout();
        write!(out, "\x1b[?1049h\x1b[?25l")?;
        out.flush()?;
        Ok(Self { old })
    }

    pub fn draw(&mut self, s: &str) -> Result<()> {
        let mut out = io::stdout();
        write!(out, "{s}")?;
        out.flush()?;
        Ok(())
    }

    pub fn read_key(&mut self) -> Result<Key> {
        let mut buf = [0u8; 8];
        let n = io::stdin().read(&mut buf)?;
        if n == 0 {
            return Ok(Key::Esc);
        }
        Ok(match buf[0] {
            b'\n' | b'\r' => Key::Enter,
            b'\x1b' => Key::Esc,
            b'\x03' => Key::Ctrl('c'),
            c if c.is_ascii() => Key::Char(c as char),
            _ => Key::Char(' '),
        })
    }

    pub fn restore(&mut self) -> Result<()> {
        unsafe {
            libc::tcsetattr(0, libc::TCSANOW, &self.old);
        }
        let mut out = io::stdout();
        write!(out, "\x1b[?25h\x1b[?1049l\x1b[0m")?;
        out.flush()?;
        Ok(())
    }
}

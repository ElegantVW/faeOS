//! Minimal pink TUI (ANSI) — fae chrome without extra UI crates.

use crate::{aegis, paths, purity, sentinel, ward};
use anyhow::Result;
use std::io::{self, Read, Write};
use std::fs;

const PINK: &str = "\x1b[38;5;175m";
const DIM: &str = "\x1b[38;5;245m";
const RESET: &str = "\x1b[0m";
const BOLD: &str = "\x1b[1m";

#[derive(Clone, Copy, PartialEq)]
enum Pane {
    Shield,
    Aegis,
    Purity,
    Ward,
    Ports,
}

impl Pane {
    fn name(self) -> &'static str {
        match self {
            Pane::Shield => "shield",
            Pane::Aegis => "aegis",
            Pane::Purity => "purity",
            Pane::Ward => "ward",
            Pane::Ports => "ports",
        }
    }
    fn next(self) -> Self {
        match self {
            Pane::Shield => Pane::Aegis,
            Pane::Aegis => Pane::Purity,
            Pane::Purity => Pane::Ward,
            Pane::Ward => Pane::Ports,
            Pane::Ports => Pane::Shield,
        }
    }
}

pub fn run() -> Result<()> {
    let _ = paths::ensure_dirs();
    let mut pane = Pane::Shield;
    let mut status = "tab cycle · r refresh · q leave".to_string();
    // raw-ish stdin
    let mut term = Term::new()?;
    loop {
        let body = pane_body(pane);
        let frame = render(pane, &body, &status);
        term.draw(&frame)?;
        status = "tab cycle · r refresh · q leave".into();
        match term.read_key()? {
            Key::Char('q') | Key::Esc | Key::Ctrl('c') => break,
            Key::Char('\t') | Key::Char('t') => pane = pane.next(),
            Key::Char('r') => status = "refreshed".into(),
            Key::Char('1') => pane = Pane::Shield,
            Key::Char('2') => pane = Pane::Aegis,
            Key::Char('3') => pane = Pane::Purity,
            Key::Char('4') => pane = Pane::Ward,
            Key::Char('5') => pane = Pane::Ports,
            Key::Char('b') if pane == Pane::Purity => {
                status = match purity_baseline_now() {
                    Ok(n) => format!("baseline: {n} files"),
                    Err(e) => format!("baseline failed: {e}"),
                };
            }
            Key::Char('c') if pane == Pane::Purity => {
                status = purity_check_now();
            }
            Key::Char('w') if pane == Pane::Ward => {
                status = format!("ward: {} finding(s)", ward::hunt().len());
            }
            _ => {}
        }
    }
    term.restore()?;
    Ok(())
}

fn purity_baseline_now() -> Result<usize> {
    let roots = purity::default_roots();
    let (bl, _) = purity::build_baseline(&roots);
    let n = bl.files.len();
    purity::save_baseline(&paths::purity_baseline_path(), &bl)?;
    Ok(n)
}

fn purity_check_now() -> String {
    let path = paths::purity_baseline_path();
    if !path.is_file() {
        return "no baseline — press b".into();
    }
    match purity::load_baseline(&path) {
        Ok(bl) => {
            let f = purity::check(&bl);
            format!("{} finding(s)", f.len())
        }
        Err(e) => format!("err {e}"),
    }
}

fn pane_body(pane: Pane) -> String {
    match pane {
        Pane::Shield => {
            let n = sentinel::scan_listeners().len();
            let net = if aegis::aegis_available() {
                "netlink ready"
            } else {
                "netlink unavailable"
            };
            let pur = if paths::purity_baseline_path().is_file() {
                "baseline present"
            } else {
                "no purity baseline"
            };
            let w = ward::hunt().len();
            format!(
                "posture\n  listeners     {n}\n  aegis         {net}\n  purity        {pur}\n  ward findings {w}\n  data          {}\n\n  CLI: bulwark status | ports | ward\n       sudo bulwark aegis apply desktop\n       bulwark aegis confirm",
                paths::data_dir().display()
            )
        }
        Pane::Aegis => {
            let pol = paths::policy_path();
            let summary = if pol.is_file() {
                fs::read_to_string(&pol)
                    .ok()
                    .and_then(|t| aegis::parse_policy(&t).ok())
                    .map(|p| aegis::policy_summary(&p))
                    .unwrap_or_else(|| "policy unreadable\n".into())
            } else {
                "no policy applied yet\nprofiles: desktop | strict | server-ssh\n".into()
            };
            format!(
                "{summary}\napply (root):\n  sudo bulwark aegis apply desktop\n  bulwark aegis confirm   # within deadman window\n  sudo bulwark aegis undo\n"
            )
        }
        Pane::Purity => {
            let path = paths::purity_baseline_path();
            if !path.is_file() {
                "no baseline\n  press b — build baseline\n  press c — check (needs baseline)\n".into()
            } else {
                match purity::load_baseline(&path) {
                    Ok(bl) => {
                        let f = purity::check(&bl);
                        format!(
                            "baseline files: {}\n{}\n  b rebuild · c recheck",
                            bl.files.len(),
                            purity::format_findings(&f)
                        )
                    }
                    Err(e) => format!("error: {e}\n"),
                }
            }
        }
        Pane::Ward => ward::format_findings(&ward::hunt()),
        Pane::Ports => sentinel::format_table(&sentinel::scan_listeners()),
    }
}

fn render(pane: Pane, body: &str, status: &str) -> String {
    let (cols, rows) = term_size();
    let width = cols.clamp(44, 96);
    let title = format!(" Bulwark ✦ {} ", pane.name());
    let mut out = String::new();
    out.push_str("\x1b[H\x1b[2J"); // home clear
    out.push_str(&box_frame(&title, &[status], width, true));
    out.push('\n');
    let body_lines: Vec<&str> = body.lines().collect();
    let runes = [
        "tab next pane · 1-5 jump · r refresh · q leave",
        "purity: b baseline · c check",
    ];
    // budget body height
    let used = 6 + 5; // head-ish + runes
    let avail = rows.saturating_sub(used).max(4);
    let clipped: Vec<String> = body_lines
        .iter()
        .take(avail)
        .map(|l| l.to_string())
        .collect();
    out.push_str(&box_frame(" leaf ", &clipped, width, false));
    out.push('\n');
    out.push_str(&box_frame(
        " Runes ",
        &runes.iter().map(|s| s.to_string()).collect::<Vec<_>>(),
        width,
        true,
    ));
    out
}

fn box_frame(title: &str, lines: &[impl AsRef<str>], width: usize, pink_title: bool) -> String {
    let inner = width.saturating_sub(2);
    let mut s = String::new();
    let t = title.trim();
    let label = format!(" ✦ {t} ✦ ");
    let fill = inner.saturating_sub(label.chars().count().max(1));
    let color = if pink_title { PINK } else { DIM };
    s.push_str(&format!(
        "{color}╭─{BOLD}{PINK}{label}{RESET}{color}{}╮{RESET}\n",
        "─".repeat(fill.saturating_sub(1))
    ));
    for line in lines {
        let plain = line.as_ref();
        let mut vis = plain.chars().take(inner.saturating_sub(2)).collect::<String>();
        while vis.chars().count() < inner.saturating_sub(2) {
            vis.push(' ');
        }
        s.push_str(&format!("{color}│{RESET} {vis} {color}│{RESET}\n"));
    }
    s.push_str(&format!("{color}╰{}╯{RESET}", "─".repeat(inner)));
    s
}

fn term_size() -> (usize, usize) {
    // TIOCGWINSZ
    unsafe {
        let mut wsz: libc::winsize = std::mem::zeroed();
        if libc::ioctl(1, libc::TIOCGWINSZ, &mut wsz) == 0 && wsz.ws_col > 0 {
            return (wsz.ws_col as usize, wsz.ws_row as usize);
        }
    }
    (80, 24)
}

struct Term {
    old: libc::termios,
}

impl Term {
    fn new() -> Result<Self> {
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
        // alt screen + hide cursor
        let mut out = io::stdout();
        write!(out, "\x1b[?1049h\x1b[?25l")?;
        out.flush()?;
        Ok(Self { old })
    }

    fn draw(&mut self, s: &str) -> Result<()> {
        let mut out = io::stdout();
        write!(out, "{s}")?;
        out.flush()?;
        Ok(())
    }

    fn read_key(&mut self) -> Result<Key> {
        let mut buf = [0u8; 8];
        let n = io::stdin().read(&mut buf)?;
        if n == 0 {
            return Ok(Key::Esc);
        }
        match buf[0] {
            b'q' => Ok(Key::Char('q')),
            b'\x1b' => Ok(Key::Esc),
            b'\t' => Ok(Key::Char('\t')),
            b'\x03' => Ok(Key::Ctrl('c')),
            c if c.is_ascii() => Ok(Key::Char(c as char)),
            _ => Ok(Key::Char(' ')),
        }
    }

    fn restore(&mut self) -> Result<()> {
        unsafe {
            libc::tcsetattr(0, libc::TCSANOW, &self.old);
        }
        let mut out = io::stdout();
        write!(out, "\x1b[?25h\x1b[?1049l\x1b[0m")?;
        out.flush()?;
        Ok(())
    }
}

enum Key {
    Char(char),
    Ctrl(char),
    Esc,
}

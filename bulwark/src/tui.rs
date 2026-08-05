//! Everyday Bulwark TUI — fixed layout + arrow-key menu navigation.
//! Themed names kept; plain one-liners; digit shortcuts still work.

use crate::aegis;
use crate::paths;
use crate::purity;
use crate::tutorial;
use crate::ward;
use crate::words::{self, Posture};
use anyhow::Result;
use std::fs;
use std::io::{self, Read, Write};
use std::process::Command;
use std::time::Duration;

pub const PINK: &str = "\x1b[38;5;175m";
pub const DIM: &str = "\x1b[38;5;245m";
pub const RESET: &str = "\x1b[0m";
pub const BOLD: &str = "\x1b[1m";
const OK: &str = "\x1b[38;5;78m";
const WARN: &str = "\x1b[38;5;214m";
const REV: &str = "\x1b[7m";
const SGR0: &str = "\x1b[27m";

/// Home menu entries (arrow-selected).
const HOME_MENU: &[&str] = &[
    "1  Purity — take a photo of important files",
    "2  Ward — search for sneaky stuff",
    "3  Sentinel — see open windows",
    "4  Aegis — turn the lock ON  (may need password)",
    "5  Aegis — turn the lock OFF / undo",
    "6  Keep watching (install helper)",
    "7  Tour — short tutorial",
    "?  Help",
];

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

    if !words::tutorial_done() {
        if !tutorial::run_tour(&mut term)? {
            term.restore()?;
            return Ok(());
        }
    }

    let mut screen = Screen::Home;
    let mut sel: usize = 0; // home menu selection
    let mut flash = String::new();
    let mut msg_lines: Vec<String> = Vec::new();
    // detail list selection (ward/sentinel scroll)
    let mut list_sel: usize = 0;
    let mut list_scroll: usize = 0;

    loop {
        let posture = words::gather_posture();
        let frame = match screen {
            Screen::Home => draw_home(&posture, sel, &flash),
            Screen::Help => {
                let lines = words::help_lines();
                page(
                    "Bulwark ✦ help",
                    "keeps this computer safe",
                    &lines,
                    "b / esc back · q leave",
                )
            }
            Screen::Purity => draw_purity(sel.min(1), &flash),
            Screen::Ward => draw_ward(list_sel, list_scroll, &flash),
            Screen::Sentinel => draw_sentinel(list_sel, list_scroll),
            Screen::AegisOnConfirm => page(
                "Bulwark ✦ Aegis",
                "front-door lock (who can knock)",
                &[
                    "Turn the front-door lock ON?".into(),
                    "".into(),
                    "This blocks strangers on the network.".into(),
                    "We can undo later (menu 5).".into(),
                    "You may need a grown-up password.".into(),
                    "".into(),
                    menu_line(0, sel.min(1), "y  yes, lock the door"),
                    menu_line(1, sel.min(1), "n  no, go back"),
                ],
                "↑↓ · enter · y/n · esc back",
            ),
            Screen::AegisOffConfirm => page(
                "Bulwark ✦ Aegis",
                "front-door lock (who can knock)",
                &[
                    "Turn the front-door lock OFF?".into(),
                    "".into(),
                    "Strangers could knock again.".into(),
                    "".into(),
                    menu_line(0, sel.min(1), "y  yes, unlock"),
                    menu_line(1, sel.min(1), "n  no, go back"),
                ],
                "↑↓ · enter · y/n · esc back",
            ),
            Screen::AegisDeadman => page(
                "Bulwark ✦ Aegis",
                "front-door lock (who can knock)",
                &[
                    "Aegis is testing the lock.".into(),
                    "".into(),
                    "If everything still works, keep it.".into(),
                    "If something broke, wait — I undo by myself.".into(),
                    "".into(),
                    menu_line(0, sel.min(1), "y  keep the lock"),
                    menu_line(1, sel.min(1), "b  back home (timer still runs)"),
                ],
                "↑↓ · enter · y keep · b home",
            ),
            Screen::Message => page(
                "Bulwark ✦ note",
                "keeps this computer safe",
                &msg_lines,
                "enter / b back home · q leave",
            ),
        };
        term.draw(&frame)?;
        flash.clear();

        let key = term.read_key()?;
        match screen {
            Screen::Home => match key {
                Key::Char('q') | Key::Ctrl('c') => break,
                Key::Esc => break,
                Key::Up | Key::Char('k') => {
                    sel = sel.saturating_sub(1);
                }
                Key::Down | Key::Char('j') => {
                    if sel + 1 < HOME_MENU.len() {
                        sel += 1;
                    }
                }
                Key::Home => sel = 0,
                Key::End => sel = HOME_MENU.len().saturating_sub(1),
                Key::Enter | Key::Right => {
                    activate_home(sel, &mut screen, &mut flash, &mut msg_lines, &mut term)?;
                    if screen != Screen::Home {
                        list_sel = 0;
                        list_scroll = 0;
                        if matches!(
                            screen,
                            Screen::AegisOnConfirm
                                | Screen::AegisOffConfirm
                                | Screen::AegisDeadman
                                | Screen::Purity
                        ) {
                            sel = 0;
                        }
                    }
                }
                Key::Char(c @ '1'..='7') => {
                    let i = (c as u8 - b'1') as usize;
                    sel = i;
                    activate_home(i, &mut screen, &mut flash, &mut msg_lines, &mut term)?;
                    list_sel = 0;
                    list_scroll = 0;
                    if matches!(
                        screen,
                        Screen::AegisOnConfirm | Screen::AegisOffConfirm | Screen::Purity
                    ) {
                        sel = 0;
                    }
                }
                Key::Char('?') | Key::Char('h') => {
                    screen = Screen::Help;
                }
                Key::Char('r') => flash = "Refreshed.".into(),
                _ => {}
            },
            Screen::Help | Screen::Message => match key {
                Key::Char('q') | Key::Ctrl('c') => break,
                Key::Esc | Key::Char('b') | Key::Enter | Key::Left => {
                    screen = Screen::Home;
                    sel = 0;
                }
                _ => {}
            },
            Screen::Purity => match key {
                Key::Char('q') | Key::Ctrl('c') => break,
                Key::Esc | Key::Char('b') | Key::Left => {
                    screen = Screen::Home;
                    sel = 0;
                }
                Key::Up | Key::Char('k') => sel = 0,
                Key::Down | Key::Char('j') => sel = 1,
                Key::Char('1') | Key::Char('p') => {
                    sel = 0;
                    flash = match take_photo() {
                        Ok(n) => format!("Purity photo saved ({n} files)."),
                        Err(e) => format!("Could not take photo: {e}"),
                    };
                }
                Key::Char('2') | Key::Char('c') => {
                    sel = 1;
                    flash = compare_photo();
                }
                Key::Enter | Key::Right => {
                    if sel == 0 {
                        flash = match take_photo() {
                            Ok(n) => format!("Purity photo saved ({n} files)."),
                            Err(e) => format!("Could not take photo: {e}"),
                        };
                    } else {
                        flash = compare_photo();
                    }
                }
                _ => {}
            },
            Screen::Ward => {
                let n = ward::hunt().len().max(1);
                match key {
                    Key::Char('q') | Key::Ctrl('c') => break,
                    Key::Esc | Key::Char('b') | Key::Left => {
                        screen = Screen::Home;
                        sel = 0;
                    }
                    Key::Up | Key::Char('k') => {
                        list_sel = list_sel.saturating_sub(1);
                        if list_sel < list_scroll {
                            list_scroll = list_sel;
                        }
                    }
                    Key::Down | Key::Char('j') => {
                        if list_sel + 1 < n {
                            list_sel += 1;
                        }
                        let vis = 10usize;
                        if list_sel >= list_scroll + vis {
                            list_scroll = list_sel + 1 - vis;
                        }
                    }
                    Key::Char('1') | Key::Char('w') | Key::Enter => {
                        flash = "Ward searched again.".into();
                        list_sel = 0;
                        list_scroll = 0;
                    }
                    _ => {}
                }
            }
            Screen::Sentinel => {
                let n = words::sentinel_plain_lines().len().max(1);
                match key {
                    Key::Char('q') | Key::Ctrl('c') => break,
                    Key::Esc | Key::Char('b') | Key::Left => {
                        screen = Screen::Home;
                        sel = 0;
                    }
                    Key::Up | Key::Char('k') => {
                        list_sel = list_sel.saturating_sub(1);
                        if list_sel < list_scroll {
                            list_scroll = list_sel;
                        }
                    }
                    Key::Down | Key::Char('j') => {
                        if list_sel + 1 < n {
                            list_sel += 1;
                        }
                        let vis = 12usize;
                        if list_sel >= list_scroll + vis {
                            list_scroll = list_sel + 1 - vis;
                        }
                    }
                    _ => {}
                }
            }
            Screen::AegisOnConfirm => match key {
                Key::Char('q') | Key::Ctrl('c') => break,
                Key::Esc | Key::Char('n') | Key::Char('N') | Key::Left => {
                    screen = Screen::Home;
                    sel = 0;
                    flash = "OK — nothing changed.".into();
                }
                Key::Up | Key::Down | Key::Char('j') | Key::Char('k') => {
                    sel = if sel == 0 { 1 } else { 0 };
                }
                Key::Char('y') | Key::Char('Y') => {
                    sel = 0;
                    match run_aegis_apply() {
                        Ok(msg) => {
                            flash = msg;
                            screen = Screen::AegisDeadman;
                            sel = 0;
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
                Key::Enter | Key::Right => {
                    if sel == 0 {
                        // yes
                        match run_aegis_apply() {
                            Ok(msg) => {
                                flash = msg;
                                screen = Screen::AegisDeadman;
                                sel = 0;
                            }
                            Err(e) => {
                                msg_lines = vec![
                                    "Aegis could not lock the door.".into(),
                                    e.to_string(),
                                    "Try: sudo bulwark aegis apply desktop".into(),
                                ];
                                screen = Screen::Message;
                            }
                        }
                    } else {
                        screen = Screen::Home;
                        sel = 0;
                        flash = "OK — nothing changed.".into();
                    }
                }
                _ => {}
            },
            Screen::AegisOffConfirm => match key {
                Key::Char('q') | Key::Ctrl('c') => break,
                Key::Esc | Key::Char('n') | Key::Char('N') | Key::Left => {
                    screen = Screen::Home;
                    sel = 0;
                    flash = "OK — nothing changed.".into();
                }
                Key::Up | Key::Down | Key::Char('j') | Key::Char('k') => {
                    sel = if sel == 0 { 1 } else { 0 };
                }
                Key::Char('y') | Key::Char('Y') => {
                    match run_aegis_undo() {
                        Ok(m) => {
                            msg_lines = vec![m, "".into(), "Front door lock is OFF.".into()];
                            screen = Screen::Message;
                        }
                        Err(e) => {
                            msg_lines = vec![
                                "Could not unlock.".into(),
                                e.to_string(),
                                "Try: sudo bulwark aegis undo".into(),
                            ];
                            screen = Screen::Message;
                        }
                    }
                }
                Key::Enter | Key::Right => {
                    if sel == 0 {
                        match run_aegis_undo() {
                            Ok(m) => {
                                msg_lines = vec![m, "".into(), "Front door lock is OFF.".into()];
                                screen = Screen::Message;
                            }
                            Err(e) => {
                                msg_lines =
                                    vec!["Could not unlock.".into(), e.to_string()];
                                screen = Screen::Message;
                            }
                        }
                    } else {
                        screen = Screen::Home;
                        sel = 0;
                    }
                }
                _ => {}
            },
            Screen::AegisDeadman => match key {
                Key::Char('q') | Key::Ctrl('c') => break,
                Key::Esc | Key::Char('b') | Key::Left => {
                    screen = Screen::Home;
                    sel = 0;
                }
                Key::Up | Key::Down | Key::Char('j') | Key::Char('k') => {
                    sel = if sel == 0 { 1 } else { 0 };
                }
                Key::Char('y') | Key::Char('Y') => {
                    keep_aegis();
                    msg_lines = vec![
                        "Aegis lock KEPT. Nice!".into(),
                        "".into(),
                        "Front-door lock stays ON.".into(),
                    ];
                    screen = Screen::Message;
                }
                Key::Enter | Key::Right => {
                    if sel == 0 {
                        keep_aegis();
                        msg_lines = vec![
                            "Aegis lock KEPT. Nice!".into(),
                            "".into(),
                            "Front-door lock stays ON.".into(),
                        ];
                        screen = Screen::Message;
                    } else {
                        screen = Screen::Home;
                        sel = 0;
                    }
                }
                _ => {}
            },
        }
    }
    term.restore()?;
    Ok(())
}

fn activate_home(
    i: usize,
    screen: &mut Screen,
    flash: &mut String,
    msg_lines: &mut Vec<String>,
    term: &mut Term,
) -> Result<()> {
    match i {
        0 => *screen = Screen::Purity,
        1 => *screen = Screen::Ward,
        2 => *screen = Screen::Sentinel,
        3 => *screen = Screen::AegisOnConfirm,
        4 => *screen = Screen::AegisOffConfirm,
        5 => {
            *msg_lines = run_install_msg();
            *screen = Screen::Message;
        }
        6 => {
            if !tutorial::run_tour(term)? {
                // user quit app from tour
                term.restore()?;
                std::process::exit(0);
            }
            *flash = "Tour finished — try 1 for a Purity photo.".into();
        }
        7 => *screen = Screen::Help,
        _ => {}
    }
    Ok(())
}

fn menu_line(idx: usize, sel: usize, text: &str) -> String {
    if idx == sel {
        format!("{REV}{PINK} ✦ {text} {SGR0}{RESET}")
    } else {
        format!("   {text}")
    }
}

fn keep_aegis() {
    let marker = paths::data_dir().join("aegis").join("confirm.ok");
    let _ = paths::ensure_dirs();
    let _ = fs::write(&marker, b"ok\n");
    if let Ok(exe) = std::env::current_exe() {
        let _ = Command::new(exe).args(["aegis", "confirm"]).status();
    }
}

// ── home / detail drawers ─────────────────────────────────────────────

fn draw_home(p: &Posture, sel: usize, flash: &str) -> String {
    let mut lines: Vec<String> = Vec::new();
    lines.push("How safe is this computer?".into());
    lines.push(String::new());
    lines.push(format!("        {}", p.mood.banner()));
    lines.push(String::new());
    // compact status rows (one line each)
    lines.push(format!(
        "  Aegis     {}  {}",
        dim("front-door lock"),
        p.aegis_line
    ));
    lines.push(format!(
        "  Purity    {}  {}",
        dim("file photo"),
        p.purity_line
    ));
    lines.push(format!(
        "  Ward      {}  {}",
        dim("sneaky search"),
        p.ward_line
    ));
    lines.push(format!(
        "  Sentinel  {}  {}",
        dim("open windows"),
        p.sentinel_line
    ));
    lines.push(String::new());
    if !flash.is_empty() {
        lines.push(format!("{OK}  {flash}{RESET}"));
        lines.push(String::new());
    }
    lines.push("What do you want to do?  (↑↓ move · enter choose)".into());
    lines.push(String::new());
    for (i, item) in HOME_MENU.iter().enumerate() {
        lines.push(menu_line(i, sel, item));
    }
    page(
        "Bulwark ✦ home",
        words::plain_name("Bulwark"),
        &lines,
        "↑↓ move · enter choose · 1-7 jump · ? help · q leave",
    )
}

fn draw_purity(sel: usize, flash: &str) -> String {
    let mut lines = vec![
        "Purity — photo of important files".into(),
        "".into(),
        menu_line(0, sel, "1  Take a photo (remember good files)"),
        menu_line(1, sel, "2  Compare to the last photo"),
        "".into(),
    ];
    let path = paths::purity_baseline_path();
    if !path.is_file() {
        lines.push("No photo yet. Choose 1 / enter.".into());
    } else if let Ok(bl) = purity::load_baseline(&path) {
        let f = purity::check(&bl);
        lines.push(format!("Last photo: {} files.", bl.files.len()));
        if f.is_empty() {
            lines.push(format!("{OK}Photo matches — nothing weird.{RESET}"));
        } else {
            lines.push(format!("{WARN}{} change(s):{RESET}", f.len()));
            for x in f.iter().take(8) {
                lines.push(format!("  · {}", words::purity_plain(x)));
            }
            if f.len() > 8 {
                lines.push(format!("  … and {} more", f.len() - 8));
            }
        }
    }
    if !flash.is_empty() {
        lines.push(String::new());
        lines.push(format!("{OK}{flash}{RESET}"));
    }
    page(
        "Bulwark ✦ Purity",
        words::plain_name("Purity"),
        &lines,
        "↑↓ · enter · 1 photo · 2 compare · esc back",
    )
}

fn draw_ward(list_sel: usize, scroll: usize, flash: &str) -> String {
    let findings = ward::hunt();
    let mut lines = vec!["Ward — search for sneaky stuff".into(), "".into()];
    if findings.is_empty() {
        lines.push(format!("{OK}All clear! Nothing sneaky found.{RESET}"));
    } else {
        lines.push(format!("Found {} thing(s):  (↑↓ scroll)", findings.len()));
        let vis = 10usize;
        let end = (scroll + vis).min(findings.len());
        for (i, f) in findings.iter().enumerate().skip(scroll).take(end - scroll) {
            let row = format!("  · {}", words::ward_plain(f));
            if i == list_sel {
                lines.push(format!("{REV}{row}{SGR0}"));
            } else {
                lines.push(row);
            }
        }
    }
    lines.push(String::new());
    lines.push("  enter  search again".into());
    lines.push("  esc    back home".into());
    if !flash.is_empty() {
        lines.push(String::new());
        lines.push(flash.to_string());
    }
    page(
        "Bulwark ✦ Ward",
        words::plain_name("Ward"),
        &lines,
        "↑↓ scroll · enter search · esc back",
    )
}

fn draw_sentinel(list_sel: usize, scroll: usize) -> String {
    let rows = words::sentinel_plain_lines();
    let mut lines = vec![
        "Sentinel — open network windows".into(),
        "These doors listen on the network right now.".into(),
        "".into(),
    ];
    let vis = 12usize;
    let end = (scroll + vis).min(rows.len());
    for (i, row) in rows.iter().enumerate().skip(scroll).take(end - scroll) {
        let line = format!("  {row}");
        if i == list_sel {
            lines.push(format!("{REV}{line}{SGR0}"));
        } else {
            lines.push(line);
        }
    }
    lines.push(String::new());
    lines.push("  esc  back home".into());
    page(
        "Bulwark ✦ Sentinel",
        words::plain_name("Sentinel"),
        &lines,
        "↑↓ scroll · esc back",
    )
}

fn dim(s: &str) -> String {
    format!("{DIM}{s}{RESET}")
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
        return "No photo yet — choose 1 first.".into();
    }
    match purity::load_baseline(&path) {
        Ok(bl) => {
            let f = purity::check(&bl);
            if f.is_empty() {
                "Photo matches — all good!".into()
            } else {
                format!("{} file(s) look different.", f.len())
            }
        }
        Err(e) => format!("Could not read photo: {e}"),
    }
}

fn run_aegis_apply() -> Result<String> {
    let text = aegis::load_bundled_profile("desktop")?;
    let _ = paths::ensure_dirs();
    fs::write(paths::policy_path(), &text)?;
    match aegis::apply_policy_text(&text, &paths::aegis_snapshot_path()) {
        Ok(res) => {
            let marker = paths::data_dir().join("aegis").join("confirm.ok");
            let _ = fs::remove_file(&marker);
            if let Ok(exe) = std::env::current_exe() {
                let _ = Command::new(&exe)
                    .args(["aegis", "undo", "--table", "bulwark"])
                    .env("BULWARK_DEADMAN", "90")
                    .env("BULWARK_CONFIRM_PATH", &marker)
                    .stdin(std::process::Stdio::null())
                    .stdout(std::process::Stdio::null())
                    .stderr(std::process::Stdio::null())
                    .spawn();
            }
            Ok(format!("{} — confirm to keep.", res.message))
        }
        Err(e) => {
            let status = Command::new("sudo")
                .args([
                    "-n",
                    "bulwark",
                    "aegis",
                    "apply",
                    "desktop",
                    "--deadman",
                    "90",
                ])
                .status();
            match status {
                Ok(s) if s.success() => {
                    Ok("Aegis lock applied. Press enter/y to keep it.".into())
                }
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
            "Remove later: bulwark uninstall".into(),
        ],
        _ => vec![
            "Could not install automatically.".into(),
            "Try: bulwark install".into(),
        ],
    }
}

// ── layout: ONE main box + runes (fits terminal) ─────────────────────

fn page(title: &str, subtitle: &str, lines: &[String], runes: &str) -> String {
    let mut body = Vec::new();
    if !subtitle.is_empty() {
        body.push(format!("{DIM}{subtitle}{RESET}"));
        body.push(String::new());
    }
    body.extend(lines.iter().cloned());
    render_simple(title, &body, &[runes])
}

/// Single content box + runes footer; body clipped to terminal height.
pub fn render_simple(title: &str, body: &[String], runes: &[&str]) -> String {
    let (cols, rows) = term_size();
    // leave 1 col margin to avoid wrap shatter
    let width = (cols.saturating_sub(1)).clamp(44, 100);

    // Runes box: 1 title + N lines + 1 bottom = N+2, plus gap
    let rune_lines: Vec<String> = runes.iter().map(|s| (*s).to_string()).collect();
    let runes_h = 2 + rune_lines.len(); // top+bottom borders + lines
    let gap = 1;
    // Main box chrome: top + bottom = 2
    let main_chrome = 2;
    let avail = rows
        .saturating_sub(runes_h + gap + main_chrome)
        .max(4);

    let clipped: Vec<String> = body.iter().take(avail).cloned().collect();

    let mut out = String::from("\x1b[H\x1b[2J\x1b[?7l"); // home, clear, no wrap
    out.push_str(&box_frame(title, &clipped, width, true));
    out.push('\n');
    out.push_str(&box_frame("Runes", &rune_lines, width, true));
    out.push_str("\x1b[?7h");
    out
}

fn box_frame(title: &str, lines: &[impl AsRef<str>], width: usize, pink_title: bool) -> String {
    let inner = width.saturating_sub(2); // between borders
    let body_w = inner.saturating_sub(2); // "│ " + content + " │"
    let mut s = String::new();
    let t = title.trim();
    let label = format!(" ✦ {t} ✦ ");
    let lab = visible_width(&label);
    let fill = inner.saturating_sub(1 + lab); // after "─" following ╭
    let color = if pink_title { PINK } else { DIM };

    // top: ╭─ label ────╮
    s.push_str(&format!(
        "{color}╭─{BOLD}{PINK}{label}{RESET}{color}{}╮{RESET}\n",
        "─".repeat(fill)
    ));

    for line in lines {
        let content = fit_ansi(line.as_ref(), body_w);
        let pad = body_w.saturating_sub(visible_width(&content));
        s.push_str(&format!(
            "{color}│{RESET} {content}{} {color}│{RESET}\n",
            " ".repeat(pad)
        ));
    }

    s.push_str(&format!("{color}╰{}╯{RESET}", "─".repeat(inner)));
    s
}

fn visible_width(s: &str) -> usize {
    let mut n = 0usize;
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
            continue;
        }
        // treat most as width 1 (box-drawing / ✦ are 1 on typical terms)
        n += 1;
    }
    n
}

/// Truncate by visible width, keep ANSI when possible (simple path: strip if too long).
fn fit_ansi(s: &str, max: usize) -> String {
    if visible_width(s) <= max {
        return s.to_string();
    }
    // strip and truncate plain
    let plain = strip_ansi(s);
    let mut out: String = plain.chars().take(max.saturating_sub(1)).collect();
    out.push('…');
    out
}

fn strip_ansi(s: &str) -> String {
    let mut out = String::new();
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
            continue;
        }
        out.push(c);
    }
    out
}

fn term_size() -> (usize, usize) {
    unsafe {
        let mut wsz: libc::winsize = std::mem::zeroed();
        // try stdout then stdin
        for fd in [1i32, 0i32] {
            if libc::ioctl(fd, libc::TIOCGWINSZ, &mut wsz) == 0 && wsz.ws_col > 0 {
                return (wsz.ws_col as usize, wsz.ws_row as usize);
            }
        }
    }
    (80, 24)
}

// ── terminal ──────────────────────────────────────────────────────────

pub struct Term {
    old: libc::termios,
}

#[derive(Debug, Clone, Copy, PartialEq)]
pub enum Key {
    Char(char),
    Ctrl(char),
    Esc,
    Enter,
    Up,
    Down,
    Left,
    Right,
    Home,
    End,
    PgUp,
    PgDn,
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
            raw.c_iflag &= !(libc::IXON | libc::ICRNL);
            raw.c_oflag |= libc::OPOST;
            raw.c_cc[libc::VMIN] = 1;
            raw.c_cc[libc::VTIME] = 0;
            libc::tcsetattr(fd, libc::TCSANOW, &raw);
        }
        let mut out = io::stdout();
        write!(out, "\x1b[?1049h\x1b[?25l\x1b[?7l")?;
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
        let mut b0 = [0u8; 1];
        let n = io::stdin().read(&mut b0)?;
        if n == 0 {
            return Ok(Key::Esc);
        }
        match b0[0] {
            b'\n' | b'\r' => return Ok(Key::Enter),
            b'\x03' => return Ok(Key::Ctrl('c')),
            b'\x1b' => {
                // CSI / SS3 — non-blocking peek
                if !wait_stdin(Duration::from_millis(40)) {
                    return Ok(Key::Esc);
                }
                let mut b1 = [0u8; 1];
                if io::stdin().read(&mut b1)? == 0 {
                    return Ok(Key::Esc);
                }
                if b1[0] == b'[' {
                    // gather until final byte
                    let mut seq = Vec::new();
                    loop {
                        if !wait_stdin(Duration::from_millis(40)) {
                            break;
                        }
                        let mut c = [0u8; 1];
                        if io::stdin().read(&mut c)? == 0 {
                            break;
                        }
                        seq.push(c[0]);
                        if c[0] >= 0x40 {
                            break;
                        }
                    }
                    return Ok(match seq.as_slice() {
                        [b'A', ..] => Key::Up,
                        [b'B', ..] => Key::Down,
                        [b'C', ..] => Key::Right,
                        [b'D', ..] => Key::Left,
                        [b'H', ..] | [b'1', b'~', ..] => Key::Home,
                        [b'F', ..] | [b'4', b'~', ..] => Key::End,
                        [b'5', b'~', ..] => Key::PgUp,
                        [b'6', b'~', ..] => Key::PgDn,
                        _ => Key::Esc,
                    });
                }
                if b1[0] == b'O' {
                    if !wait_stdin(Duration::from_millis(40)) {
                        return Ok(Key::Esc);
                    }
                    let mut b2 = [0u8; 1];
                    if io::stdin().read(&mut b2)? == 0 {
                        return Ok(Key::Esc);
                    }
                    return Ok(match b2[0] {
                        b'A' => Key::Up,
                        b'B' => Key::Down,
                        b'C' => Key::Right,
                        b'D' => Key::Left,
                        b'H' => Key::Home,
                        b'F' => Key::End,
                        _ => Key::Esc,
                    });
                }
                return Ok(Key::Esc);
            }
            c if c.is_ascii() => return Ok(Key::Char(c as char)),
            _ => return Ok(Key::Char(' ')),
        }
    }

    pub fn restore(&mut self) -> Result<()> {
        unsafe {
            libc::tcsetattr(0, libc::TCSANOW, &self.old);
        }
        let mut out = io::stdout();
        write!(out, "\x1b[?25h\x1b[?1049l\x1b[?7h\x1b[0m")?;
        out.flush()?;
        Ok(())
    }
}

fn wait_stdin(timeout: Duration) -> bool {
    unsafe {
        let mut pfd = libc::pollfd {
            fd: 0,
            events: libc::POLLIN,
            revents: 0,
        };
        let ms = timeout.as_millis().min(i32::MAX as u128) as i32;
        libc::poll(&mut pfd, 1, ms) > 0
    }
}

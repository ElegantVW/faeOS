//! Plain-language helpers — themed names stay, kid sentences beside them.

use crate::paths;
use crate::purity::{self, Finding as PurityFinding};
use crate::sentinel;
use crate::ward::{self, Finding as WardFinding};
use std::fs;

/// Overall computer mood.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Mood {
    Safe,
    Care,
    Danger,
}

impl Mood {
    pub fn label(self) -> &'static str {
        match self {
            Mood::Safe => "SAFE",
            Mood::Care => "CARE",
            Mood::Danger => "DANGER",
        }
    }

    /// ANSI color for the big mood word.
    pub fn color(self) -> &'static str {
        match self {
            Mood::Safe => "\x1b[38;5;78m",   // green
            Mood::Care => "\x1b[38;5;214m",  // amber
            Mood::Danger => "\x1b[38;5;197m", // red
        }
    }

    pub fn banner(self) -> String {
        let c = self.color();
        format!("{c}✦✦  {}  ✦✦\x1b[0m", self.label())
    }
}

#[derive(Debug, Clone)]
pub struct Posture {
    pub mood: Mood,
    pub aegis_on: bool,
    pub aegis_line: String,
    pub purity_line: String,
    pub purity_changed: usize,
    pub ward_crit: usize,
    pub ward_total: usize,
    pub ward_line: String,
    pub listeners: usize,
    pub sentinel_line: String,
}

pub fn plain_name(layer: &str) -> &'static str {
    match layer {
        "Bulwark" => "keeps this computer safe",
        "Aegis" => "front-door lock (who can knock)",
        "Purity" => "photo of important files",
        "Ward" => "search for sneaky stuff",
        "Sentinel" => "watches open network windows",
        _ => "",
    }
}

pub fn gather_posture() -> Posture {
    let aegis_on = paths::aegis_snapshot_path().is_file();
    let aegis_line = if aegis_on {
        "ON — lock is set".into()
    } else {
        "OFF — door open to the network".into()
    };

    let bl_path = paths::purity_baseline_path();
    let (purity_line, purity_changed) = if !bl_path.is_file() {
        ("none — no photo yet (press 1)".into(), 0usize)
    } else {
        match purity::load_baseline(&bl_path) {
            Ok(bl) => {
                let f = purity::check(&bl);
                let n = f.len();
                if n == 0 {
                    (format!("OK — photo of {} files matches", bl.files.len()), 0)
                } else {
                    (format!("CHANGED! — {n} file(s) look different"), n)
                }
            }
            Err(_) => ("photo unreadable".into(), 0),
        }
    };

    let ward_f = ward::hunt();
    let ward_crit = ward_f
        .iter()
        .filter(|f| f.severity == "crit")
        .count();
    let ward_total = ward_f.len();
    let ward_line = if ward_total == 0 {
        "clean — nothing sneaky found".into()
    } else if ward_crit > 0 {
        format!("found {ward_total} thing(s) · {ward_crit} serious")
    } else {
        format!("found {ward_total} thing(s) — take a look")
    };

    let listeners = sentinel::scan_listeners();
    let n = listeners.len();
    let sentinel_line = if n == 0 {
        "no open windows".into()
    } else {
        format!("{n} open window(s) on the network")
    };

    // Mood
    let mood = if ward_crit > 0 || purity_changed > 0 {
        Mood::Danger
    } else if !aegis_on || !bl_path.is_file() || ward_total > 0 {
        Mood::Care
    } else {
        Mood::Safe
    };

    Posture {
        mood,
        aegis_on,
        aegis_line,
        purity_line,
        purity_changed,
        ward_crit,
        ward_total,
        ward_line,
        listeners: n,
        sentinel_line,
    }
}

/// Map Ward kind → plain sentence.
pub fn ward_plain(f: &WardFinding) -> String {
    let plain = match f.kind.as_str() {
        "path-world-writable" => "A program folder is open so anyone can change it",
        "ld-preload" => "A program loads a secret add-on (LD_PRELOAD)",
        "deleted-exe" => "A program is still running after its file was deleted",
        "timer-tmp-exec" => "A timer may run something from a temp folder",
        "home-bin-writable" => "Your personal tools folder is open to everyone",
        "suid-home-bin" => "A personal tool has super powers (SUID)",
        other => other,
    };
    format!("[{}] {plain}", f.severity)
}

pub fn ward_plain_list(findings: &[WardFinding]) -> Vec<String> {
    findings.iter().map(ward_plain).collect()
}

pub fn purity_plain(f: &PurityFinding) -> String {
    match f {
        PurityFinding::Missing { path } => format!("missing — {path}"),
        PurityFinding::New { path } => format!("new file — {path}"),
        PurityFinding::Changed { path, reason } => {
            format!("changed ({reason}) — {path}")
        }
    }
}

pub fn sentinel_plain_lines() -> Vec<String> {
    let list = sentinel::scan_listeners();
    if list.is_empty() {
        return vec!["(no open windows right now)".into()];
    }
    list.iter()
        .map(|l| {
            let only = if l.local.starts_with("127.0.0.1")
                || l.local.starts_with("[::1]")
                || l.local.contains("127.0.0.1")
            {
                " · only this computer"
            } else {
                " · on the network"
            };
            let prog = l.comm.as_deref().unwrap_or("?");
            format!("{}  ·  {prog}{only}", l.local)
        })
        .collect()
}

pub fn help_lines() -> Vec<String> {
    vec![
        "Bulwark keeps this computer safe.".into(),
        "".into(),
        "Aegis   — front-door lock (firewall)".into(),
        "Purity  — photo of important files".into(),
        "Ward    — search for sneaky stuff".into(),
        "Sentinel— watches open network windows".into(),
        "".into(),
        "SAFE  = looking good".into(),
        "CARE  = something to do (or lock off)".into(),
        "DANGER= look at Ward or Purity soon".into(),
        "".into(),
        "Press a number on the home screen.".into(),
        "Grown-up password (sudo) may be needed for Aegis.".into(),
    ]
}

/// True when the user has finished (or skipped) the first tour.
pub fn tutorial_done() -> bool {
    paths::tutorial_done_path().is_file()
}

pub fn mark_tutorial_done() {
    let _ = paths::ensure_dirs();
    let _ = fs::write(paths::tutorial_done_path(), b"ok\n");
}

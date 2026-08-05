//! Ward — pure-Python-equivalent hunts in Rust (no signature DB).

use std::fs;
use std::os::unix::fs::PermissionsExt;
use std::path::PathBuf;

#[derive(Debug, Clone)]
pub struct Finding {
    pub severity: &'static str, // crit | high | med | low
    pub kind: String,
    pub detail: String,
}

pub fn hunt() -> Vec<Finding> {
    let mut f = Vec::new();
    check_path_dirs(&mut f);
    check_ld_preload(&mut f);
    check_deleted_exe(&mut f);
    check_tmp_exec_timers(&mut f);
    check_world_writable_home_bin(&mut f);
    f
}

fn check_path_dirs(out: &mut Vec<Finding>) {
    let path = std::env::var("PATH").unwrap_or_default();
    for dir in path.split(':').filter(|s| !s.is_empty()) {
        let p = PathBuf::from(dir);
        if let Ok(meta) = fs::metadata(&p) {
            let mode = meta.permissions().mode();
            if mode & 0o002 != 0 {
                out.push(Finding {
                    severity: "crit",
                    kind: "path-world-writable".into(),
                    detail: format!("{dir} is world-writable (mode {mode:o})"),
                });
            }
        }
    }
}

fn check_ld_preload(out: &mut Vec<Finding>) {
    let Ok(entries) = fs::read_dir("/proc") else {
        return;
    };
    for ent in entries.flatten() {
        let name = ent.file_name();
        let s = name.to_string_lossy();
        if !s.chars().all(|c| c.is_ascii_digit()) {
            continue;
        }
        let environ = ent.path().join("environ");
        let Ok(bytes) = fs::read(&environ) else {
            continue;
        };
        for entry in bytes.split(|b| *b == 0) {
            if entry.starts_with(b"LD_PRELOAD=") {
                let val = String::from_utf8_lossy(entry);
                out.push(Finding {
                    severity: "high",
                    kind: "ld-preload".into(),
                    detail: format!("pid {s}: {val}"),
                });
            }
        }
    }
}

fn check_deleted_exe(out: &mut Vec<Finding>) {
    let Ok(entries) = fs::read_dir("/proc") else {
        return;
    };
    for ent in entries.flatten() {
        let name = ent.file_name();
        let s = name.to_string_lossy();
        if !s.chars().all(|c| c.is_ascii_digit()) {
            continue;
        }
        if let Ok(exe) = fs::read_link(ent.path().join("exe")) {
            let ex = exe.to_string_lossy();
            if ex.contains("(deleted)") {
                out.push(Finding {
                    severity: "med",
                    kind: "deleted-exe".into(),
                    detail: format!("pid {s}: {ex}"),
                });
            }
        }
    }
}

fn check_tmp_exec_timers(out: &mut Vec<Finding>) {
    let home = std::env::var("HOME").unwrap_or_default();
    let dirs = [
        format!("{home}/.config/systemd/user"),
        "/etc/systemd/system".into(),
        format!("{home}/.config/cron"),
    ];
    for d in dirs {
        let p = PathBuf::from(&d);
        if !p.is_dir() {
            continue;
        }
        let Ok(rd) = fs::read_dir(&p) else {
            continue;
        };
        for ent in rd.flatten() {
            let path = ent.path();
            if path.extension().and_then(|e| e.to_str()) != Some("service")
                && path.extension().and_then(|e| e.to_str()) != Some("timer")
            {
                // also scan any file
            }
            if let Ok(text) = fs::read_to_string(&path) {
                for needle in ["/tmp/", "/var/tmp/", "/dev/shm/"] {
                    if text.contains(needle) && text.to_lowercase().contains("execstart") {
                        out.push(Finding {
                            severity: "high",
                            kind: "timer-tmp-exec".into(),
                            detail: format!("{} references {needle}", path.display()),
                        });
                        break;
                    }
                }
            }
        }
    }
}

fn check_world_writable_home_bin(out: &mut Vec<Finding>) {
    let Ok(home) = std::env::var("HOME") else {
        return;
    };
    let bin = PathBuf::from(home).join("bin");
    if let Ok(meta) = fs::metadata(&bin) {
        let mode = meta.permissions().mode();
        if mode & 0o002 != 0 {
            out.push(Finding {
                severity: "crit",
                kind: "home-bin-writable".into(),
                detail: format!("{} world-writable", bin.display()),
            });
        }
    }
    if let Ok(rd) = fs::read_dir(&bin) {
        for ent in rd.flatten() {
            if let Ok(meta) = ent.metadata() {
                let mode = meta.permissions().mode();
                if mode & 0o4000 != 0 {
                    out.push(Finding {
                        severity: "high",
                        kind: "suid-home-bin".into(),
                        detail: format!("{} has SUID", ent.path().display()),
                    });
                }
            }
        }
    }
}

pub fn format_findings(f: &[Finding]) -> String {
    if f.is_empty() {
        return "ward: no hostile patterns found\n".into();
    }
    let mut s = format!("ward: {} finding(s)\n", f.len());
    for x in f {
        s.push_str(&format!(
            "  [{:<4}] {:<18} {}\n",
            x.severity, x.kind, x.detail
        ));
    }
    s
}

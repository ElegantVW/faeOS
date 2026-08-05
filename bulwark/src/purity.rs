//! Purity — file integrity baselines (first-party FIM).

use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::collections::BTreeMap;
use std::fs;
use std::os::unix::fs::MetadataExt;
use std::path::{Path, PathBuf};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FileRec {
    pub sha256: String,
    pub size: u64,
    pub mode: u32,
    pub uid: u32,
    pub gid: u32,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Baseline {
    pub ts_unix: i64,
    pub roots: Vec<String>,
    pub files: BTreeMap<String, FileRec>,
}

#[derive(Debug, Clone)]
pub enum Finding {
    Missing { path: String },
    New { path: String },
    Changed { path: String, reason: String },
}

pub fn default_roots() -> Vec<PathBuf> {
    let mut roots = vec![
        PathBuf::from("/etc/passwd"),
        PathBuf::from("/etc/shadow"),
        PathBuf::from("/etc/group"),
        PathBuf::from("/etc/sudoers"),
        PathBuf::from("/etc/ssh"),
    ];
    if let Ok(home) = std::env::var("HOME") {
        roots.push(PathBuf::from(home).join("bin"));
    }
    // faeOS kit if present
    if let Ok(home) = std::env::var("HOME") {
        let fae = PathBuf::from(home).join("faeos").join("bin");
        if fae.is_dir() {
            roots.push(fae);
        }
    }
    roots
}

pub fn hash_file(path: &Path) -> std::io::Result<FileRec> {
    let meta = fs::metadata(path)?;
    let data = fs::read(path)?;
    let mut hasher = Sha256::new();
    hasher.update(&data);
    let sha = hex::encode(hasher.finalize());
    Ok(FileRec {
        sha256: sha,
        size: meta.len(),
        mode: meta.mode(),
        uid: meta.uid(),
        gid: meta.gid(),
    })
}

fn walk_collect(root: &Path, out: &mut BTreeMap<String, FileRec>, errors: &mut Vec<String>) {
    if root.is_file() {
        match hash_file(root) {
            Ok(rec) => {
                out.insert(root.to_string_lossy().to_string(), rec);
            }
            Err(e) => errors.push(format!("{}: {e}", root.display())),
        }
        return;
    }
    if !root.is_dir() {
        return;
    }
    let Ok(rd) = fs::read_dir(root) else {
        errors.push(format!("cannot read {}", root.display()));
        return;
    };
    for ent in rd.flatten() {
        let p = ent.path();
        // skip huge / sensitive caches
        let name = p.file_name().and_then(|s| s.to_str()).unwrap_or("");
        if name == ".git" || name == "target" || name == "__pycache__" {
            continue;
        }
        if p.is_dir() {
            walk_collect(&p, out, errors);
        } else if p.is_file() {
            // skip very large
            if let Ok(meta) = p.metadata() {
                if meta.len() > 64 * 1024 * 1024 {
                    continue;
                }
            }
            match hash_file(&p) {
                Ok(rec) => {
                    out.insert(p.to_string_lossy().to_string(), rec);
                }
                Err(e) => errors.push(format!("{}: {e}", p.display())),
            }
        }
    }
}

pub fn build_baseline(roots: &[PathBuf]) -> (Baseline, Vec<String>) {
    let mut files = BTreeMap::new();
    let mut errors = Vec::new();
    for r in roots {
        walk_collect(r, &mut files, &mut errors);
    }
    let bl = Baseline {
        ts_unix: std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .map(|d| d.as_secs() as i64)
            .unwrap_or(0),
        roots: roots.iter().map(|p| p.to_string_lossy().to_string()).collect(),
        files,
    };
    (bl, errors)
}

pub fn save_baseline(path: &Path, bl: &Baseline) -> std::io::Result<()> {
    if let Some(p) = path.parent() {
        fs::create_dir_all(p)?;
    }
    fs::write(path, serde_json::to_string_pretty(bl).unwrap())
}

pub fn load_baseline(path: &Path) -> std::io::Result<Baseline> {
    let text = fs::read_to_string(path)?;
    Ok(serde_json::from_str(&text)?)
}

pub fn check(baseline: &Baseline) -> Vec<Finding> {
    let mut findings = Vec::new();
    let roots: Vec<PathBuf> = baseline.roots.iter().map(PathBuf::from).collect();
    let (now, _) = build_baseline(&roots);

    for (path, old) in &baseline.files {
        match now.files.get(path) {
            None => findings.push(Finding::Missing {
                path: path.clone(),
            }),
            Some(new) => {
                let mut reasons = Vec::new();
                if new.sha256 != old.sha256 {
                    reasons.push("content");
                }
                if new.mode != old.mode {
                    reasons.push("mode");
                }
                if new.uid != old.uid || new.gid != old.gid {
                    reasons.push("owner");
                }
                // SUID/SGID raised
                if (new.mode & 0o4000) != 0 && (old.mode & 0o4000) == 0 {
                    reasons.push("suid-added");
                }
                if (new.mode & 0o2000) != 0 && (old.mode & 0o2000) == 0 {
                    reasons.push("sgid-added");
                }
                if !reasons.is_empty() {
                    findings.push(Finding::Changed {
                        path: path.clone(),
                        reason: reasons.join(","),
                    });
                }
            }
        }
    }
    for path in now.files.keys() {
        if !baseline.files.contains_key(path) {
            // only report new in watched roots that look executable-ish
            findings.push(Finding::New {
                path: path.clone(),
            });
        }
    }
    findings
}

pub fn format_findings(f: &[Finding]) -> String {
    if f.is_empty() {
        return "purity: clean — no changes vs baseline\n".into();
    }
    let mut s = format!("purity: {} finding(s)\n", f.len());
    for x in f {
        match x {
            Finding::Missing { path } => s.push_str(&format!("  MISSING  {path}\n")),
            Finding::New { path } => s.push_str(&format!("  NEW      {path}\n")),
            Finding::Changed { path, reason } => {
                s.push_str(&format!("  CHANGED  {path}  ({reason})\n"))
            }
        }
    }
    s
}

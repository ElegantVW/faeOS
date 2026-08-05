//! XDG state roots for Bulwark (no external deps).

use std::path::PathBuf;

pub fn data_dir() -> PathBuf {
    if let Ok(p) = std::env::var("BULWARK_DIR") {
        return PathBuf::from(p);
    }
    let base = std::env::var("XDG_DATA_HOME")
        .map(PathBuf::from)
        .unwrap_or_else(|_| {
            dirs_fallback_home().join(".local").join("share")
        });
    base.join("faeos").join("bulwark")
}

fn dirs_fallback_home() -> PathBuf {
    std::env::var("HOME")
        .map(PathBuf::from)
        .unwrap_or_else(|_| PathBuf::from("."))
}

pub fn ensure_dirs() -> std::io::Result<PathBuf> {
    let d = data_dir();
    std::fs::create_dir_all(d.join("purity"))?;
    std::fs::create_dir_all(d.join("sentinel"))?;
    std::fs::create_dir_all(d.join("logs"))?;
    std::fs::create_dir_all(d.join("aegis"))?;
    Ok(d)
}

pub fn policy_path() -> PathBuf {
    data_dir().join("aegis").join("policy.aegis")
}

pub fn aegis_snapshot_path() -> PathBuf {
    data_dir().join("aegis").join("last_apply.json")
}

pub fn purity_baseline_path() -> PathBuf {
    data_dir().join("purity").join("baseline.json")
}

pub fn sentinel_last_path() -> PathBuf {
    data_dir().join("sentinel").join("last.json")
}

pub fn tutorial_done_path() -> PathBuf {
    data_dir().join("tutorial_done")
}

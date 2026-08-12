use anyhow::Result;
use serde::{Deserialize, Serialize};
use std::fs;
use std::path::PathBuf;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LockConfig {
    pub enabled: bool,
    pub ac_idle_seconds: u32,
    pub battery_idle_seconds: u32,
    pub dont_lock: bool,
    pub suspend_on_lock: bool,
    pub guest_enabled: bool,
    pub lock_message: String,
}

impl Default for LockConfig {
    fn default() -> Self {
        Self {
            enabled: true,
            ac_idle_seconds: 600,
            battery_idle_seconds: 120,
            dont_lock: false,
            suspend_on_lock: false,
            guest_enabled: false,
            lock_message: String::new(),
        }
    }
}

fn config_path() -> PathBuf {
    dirs_path().join("lock.json")
}

fn dirs_path() -> PathBuf {
    let base = std::env::var("HOME")
        .map(PathBuf::from)
        .unwrap_or_else(|_| PathBuf::from("/tmp"));
    base.join(".config").join("pixie")
}

pub fn load() -> LockConfig {
    let path = config_path();
    if path.exists() {
        fs::read_to_string(&path)
            .ok()
            .and_then(|s| serde_json::from_str(&s).ok())
            .unwrap_or_default()
    } else {
        LockConfig::default()
    }
}

pub fn save(cfg: &LockConfig) -> Result<()> {
    let path = config_path();
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)?;
    }
    let json = serde_json::to_string_pretty(cfg)?;
    fs::write(&path, json)?;
    Ok(())
}

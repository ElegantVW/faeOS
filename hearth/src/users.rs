use serde::Serialize;
use std::collections::HashMap;
use std::path::PathBuf;

#[derive(Debug, Clone, Serialize)]
pub struct User {
    pub name: String,
    pub uid: u32,
    pub display: String,
    pub shell: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct Session {
    pub id: String,
    pub user: String,
    pub seat: String,
}

pub fn discover_users() -> anyhow::Result<Vec<User>> {
    let overrides = load_overrides();
    let hidden = hidden_users();
    let mut users = Vec::new();

    let passwd = std::fs::read_to_string("/etc/passwd")?;
    for line in passwd.lines() {
        let parts: Vec<&str> = line.split(':').collect();
        if parts.len() < 7 {
            continue;
        }
        let name = parts[0];
        let uid: u32 = match parts[2].parse() {
            Ok(n) => n,
            Err(_) => continue,
        };

        if uid < 1000 || uid >= 65534 {
            continue;
        }
        if name == "nobody" {
            continue;
        }

        let shell = parts[6];
        if shell.contains("nologin") || shell.contains("false") {
            continue;
        }

        if hidden.contains(&name.to_string()) {
            continue;
        }

        let display = overrides
            .get(name)
            .and_then(|v| v.get("display"))
            .cloned()
            .unwrap_or_else(|| name.to_string());

        users.push(User {
            name: name.to_string(),
            uid,
            display,
            shell: shell.to_string(),
        });
    }

    users.sort_by_key(|u| u.uid);
    Ok(users)
}

pub fn list_sessions() -> anyhow::Result<Vec<Session>> {
    let output = std::process::Command::new("loginctl")
        .args(["list-sessions", "--no-legend"])
        .output()?;

    let stdout = String::from_utf8_lossy(&output.stdout);
    let mut sessions = Vec::new();

    for line in stdout.lines() {
        let parts: Vec<&str> = line.split_whitespace().collect();
        if parts.len() >= 3 {
            sessions.push(Session {
                id: parts[0].to_string(),
                user: parts[2].to_string(),
                seat: if parts.len() > 3 {
                    parts[3].to_string()
                } else {
                    String::new()
                },
            });
        }
    }

    Ok(sessions)
}

pub fn activate_session(user: &str) -> anyhow::Result<bool> {
    let sessions = list_sessions()?;
    for s in &sessions {
        if s.user == user {
            let _ = std::process::Command::new("loginctl")
                .args(["activate", &s.id])
                .status();
            return Ok(true);
        }
    }
    Ok(false)
}

fn load_overrides() -> HashMap<String, HashMap<String, String>> {
    let path = overrides_path();
    if let Ok(data) = std::fs::read_to_string(&path) {
        serde_json::from_str(&data).unwrap_or_default()
    } else {
        HashMap::new()
    }
}

fn hidden_users() -> Vec<String> {
    let path = overrides_path();
    if let Ok(data) = std::fs::read_to_string(&path) {
        let map: HashMap<String, HashMap<String, String>> =
            serde_json::from_str(&data).unwrap_or_default();
        map.iter()
            .filter(|(_, v)| v.get("hidden").map_or(false, |h| h == "true"))
            .map(|(k, _)| k.clone())
            .collect()
    } else {
        Vec::new()
    }
}

fn overrides_path() -> PathBuf {
    let home = std::env::var("HOME").unwrap_or_else(|_| "/tmp".into());
    PathBuf::from(home)
        .join(".config")
        .join("pixie")
        .join("hearth.json")
}

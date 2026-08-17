use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::io::{BufRead, BufReader, Write};
use std::os::unix::net::UnixStream;
use std::path::PathBuf;

#[derive(Debug, Clone, Serialize)]
pub struct User {
    pub name: String,
    pub uid: u32,
    pub display: String,
}

#[derive(Deserialize)]
struct Response {
    ok: bool,
    users: Option<Vec<RawUser>>,
    #[allow(dead_code)]
    msg: Option<String>,
}

#[derive(Deserialize)]
struct RawUser {
    name: String,
    uid: u32,
    display: String,
    #[allow(dead_code)]
    shell: String,
}

const SOCKET_PATH: &str = "/tmp/hearth.sock";

fn send_cmd(cmd: &str) -> Option<String> {
    let mut stream = UnixStream::connect(SOCKET_PATH).ok()?;
    let request = format!(r#"{{"cmd":"{}"}}"#, cmd);
    stream.write_all(request.as_bytes()).ok()?;
    stream.write_all(b"\n").ok()?;

    let mut reader = BufReader::new(&stream);
    let mut line = String::new();
    reader.read_line(&mut line).ok()?;
    Some(line)
}

fn send_auth(user: &str, pass: &str) -> Option<bool> {
    let mut stream = UnixStream::connect(SOCKET_PATH).ok()?;
    // JSON-escape minimal: quotes in pass break — hearth path is optional
    let request = format!(
        r#"{{"cmd":"AUTH","user":"{}","pass":"{}"}}"#,
        user.replace('\\', "\\\\").replace('"', "\\\""),
        pass.replace('\\', "\\\\").replace('"', "\\\"")
    );
    stream.write_all(request.as_bytes()).ok()?;
    stream.write_all(b"\n").ok()?;

    let mut reader = BufReader::new(&stream);
    let mut line = String::new();
    reader.read_line(&mut line).ok()?;

    let resp: Response = serde_json::from_str(&line).ok()?;
    Some(resp.ok)
}

fn send_login(user: &str) -> Option<bool> {
    let mut stream = UnixStream::connect(SOCKET_PATH).ok()?;
    let request = format!(r#"{{"cmd":"LOGIN","user":"{}"}}"#, user);
    stream.write_all(request.as_bytes()).ok()?;
    stream.write_all(b"\n").ok()?;

    let mut reader = BufReader::new(&stream);
    let mut line = String::new();
    reader.read_line(&mut line).ok()?;

    let resp: Response = serde_json::from_str(&line).ok()?;
    Some(resp.ok)
}

/// List login-capable users: hearth socket first, else `/etc/passwd` + hearth.json overrides.
pub fn list_users() -> Option<Vec<User>> {
    if let Some(raw) = send_cmd("LIST") {
        if let Ok(resp) = serde_json::from_str::<Response>(&raw) {
            if let Some(us) = resp.users {
                let list: Vec<User> = us
                    .into_iter()
                    .map(|u| User {
                        name: u.name,
                        uid: u.uid,
                        display: u.display,
                    })
                    .collect();
                if !list.is_empty() {
                    return Some(list);
                }
            }
        }
    }
    list_users_from_passwd()
}

fn list_users_from_passwd() -> Option<Vec<User>> {
    let overrides = load_overrides();
    let passwd = std::fs::read_to_string("/etc/passwd").ok()?;
    let mut users = Vec::new();

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
        if uid < 1000 || uid >= 65534 || name == "nobody" {
            continue;
        }
        let shell = parts[6];
        if shell.contains("nologin") || shell.contains("false") {
            continue;
        }

        let ov = overrides.get(name);
        if ov
            .and_then(|m| m.get("hidden"))
            .map(|h| h == "true")
            .unwrap_or(false)
        {
            continue;
        }

        let display = ov
            .and_then(|m| m.get("display"))
            .cloned()
            .unwrap_or_else(|| name.to_string());

        users.push(User {
            name: name.to_string(),
            uid,
            display,
        });
    }

    users.sort_by_key(|u| u.uid);
    if users.is_empty() {
        None
    } else {
        Some(users)
    }
}

fn load_overrides() -> HashMap<String, HashMap<String, String>> {
    let path = overrides_path();
    if let Ok(data) = std::fs::read_to_string(&path) {
        serde_json::from_str(&data).unwrap_or_default()
    } else {
        HashMap::new()
    }
}

fn overrides_path() -> PathBuf {
    let home = std::env::var("HOME").unwrap_or_else(|_| "/tmp".into());
    PathBuf::from(home)
        .join(".config")
        .join("pixie")
        .join("hearth.json")
}

pub fn verify_password(user: &str, password: &str) -> Option<bool> {
    send_auth(user, password)
}

pub fn login_user(user: &str) -> Option<bool> {
    send_login(user)
}

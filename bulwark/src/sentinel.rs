//! Sentinel — listen / connection inventory from /proc (no ss/netstat).

use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::fs;
use std::net::{Ipv4Addr, Ipv6Addr};
use std::path::PathBuf;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Listener {
    pub proto: String,
    pub local: String,
    pub state: String,
    pub inode: u64,
    pub pid: Option<u32>,
    pub comm: Option<String>,
    pub exe: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Snapshot {
    pub ts_unix: i64,
    pub listeners: Vec<Listener>,
}

pub fn scan_listeners() -> Vec<Listener> {
    let mut out = Vec::new();
    out.extend(parse_proc_net("/proc/net/tcp", "tcp", true));
    out.extend(parse_proc_net("/proc/net/tcp6", "tcp6", false));
    out.extend(parse_proc_net("/proc/net/udp", "udp", true));
    out.extend(parse_proc_net("/proc/net/udp6", "udp6", false));
    // only listening / UDP
    out.retain(|l| l.state == "LISTEN" || l.proto.starts_with("udp"));
    let inode_map = map_inode_to_pid();
    for l in &mut out {
        if let Some(pid) = inode_map.get(&l.inode).copied() {
            l.pid = Some(pid);
            l.comm = read_comm(pid);
            l.exe = read_exe(pid);
        }
    }
    out.sort_by(|a, b| a.local.cmp(&b.local));
    out
}

pub fn snapshot() -> Snapshot {
    Snapshot {
        ts_unix: chrono_now(),
        listeners: scan_listeners(),
    }
}

fn chrono_now() -> i64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_secs() as i64)
        .unwrap_or(0)
}

fn parse_proc_net(path: &str, proto: &str, v4: bool) -> Vec<Listener> {
    let Ok(text) = fs::read_to_string(path) else {
        return Vec::new();
    };
    let mut out = Vec::new();
    for (i, line) in text.lines().enumerate() {
        if i == 0 {
            continue;
        }
        let cols: Vec<&str> = line.split_whitespace().collect();
        // local_address remote_address st ... inode
        if cols.len() < 10 {
            continue;
        }
        let local = parse_addr(cols[1], v4).unwrap_or_else(|| cols[1].to_string());
        let st = parse_state(cols[3], proto);
        let inode: u64 = cols[9].parse().unwrap_or(0);
        if inode == 0 {
            continue;
        }
        out.push(Listener {
            proto: proto.to_string(),
            local,
            state: st,
            inode,
            pid: None,
            comm: None,
            exe: None,
        });
    }
    out
}

fn parse_state(hex: &str, proto: &str) -> String {
    if proto.starts_with("udp") {
        return "UDP".into();
    }
    let n = u8::from_str_radix(hex, 16).unwrap_or(0);
    // TCP_LISTEN = 0x0A
    match n {
        0x0A => "LISTEN".into(),
        0x01 => "ESTABLISHED".into(),
        0x06 => "TIME_WAIT".into(),
        0x07 => "CLOSE".into(),
        0x08 => "CLOSE_WAIT".into(),
        _ => format!("0x{n:02x}"),
    }
}

fn parse_addr(s: &str, v4: bool) -> Option<String> {
    let (ip_s, port_s) = s.split_once(':')?;
    let port = u16::from_str_radix(port_s, 16).ok()?;
    if v4 {
        let ip_n = u32::from_str_radix(ip_s, 16).ok()?;
        // little-endian in /proc
        let ip = Ipv4Addr::from(ip_n.to_le_bytes());
        Some(format!("{ip}:{port}"))
    } else {
        // 32 hex chars, 4x u32 LE groups
        if ip_s.len() != 32 {
            return Some(format!("{s}"));
        }
        let mut bytes = [0u8; 16];
        for i in 0..4 {
            let chunk = &ip_s[i * 8..i * 8 + 8];
            let n = u32::from_str_radix(chunk, 16).ok()?;
            bytes[i * 4..i * 4 + 4].copy_from_slice(&n.to_le_bytes());
        }
        let ip = Ipv6Addr::from(bytes);
        Some(format!("[{ip}]:{port}"))
    }
}

fn map_inode_to_pid() -> HashMap<u64, u32> {
    let mut map = HashMap::new();
    let Ok(entries) = fs::read_dir("/proc") else {
        return map;
    };
    for ent in entries.flatten() {
        let name = ent.file_name();
        let name = name.to_string_lossy();
        if !name.chars().all(|c| c.is_ascii_digit()) {
            continue;
        }
        let pid: u32 = match name.parse() {
            Ok(p) => p,
            Err(_) => continue,
        };
        let fd_dir = ent.path().join("fd");
        let Ok(fds) = fs::read_dir(fd_dir) else {
            continue;
        };
        for fd in fds.flatten() {
            let Ok(link) = fs::read_link(fd.path()) else {
                continue;
            };
            let s = link.to_string_lossy();
            // socket:[12345]
            if let Some(rest) = s.strip_prefix("socket:[") {
                if let Some(num) = rest.strip_suffix(']') {
                    if let Ok(inode) = num.parse::<u64>() {
                        map.entry(inode).or_insert(pid);
                    }
                }
            }
        }
    }
    map
}

fn read_comm(pid: u32) -> Option<String> {
    fs::read_to_string(format!("/proc/{pid}/comm"))
        .ok()
        .map(|s| s.trim().to_string())
}

fn read_exe(pid: u32) -> Option<String> {
    fs::read_link(format!("/proc/{pid}/exe"))
        .ok()
        .map(|p| p.to_string_lossy().to_string())
}

pub fn format_table(listeners: &[Listener]) -> String {
    let mut s = String::from("PROTO   STATE        LOCAL                    PID    COMM\n");
    for l in listeners {
        s.push_str(&format!(
            "{:<7} {:<12} {:<24} {:<6} {}\n",
            l.proto,
            l.state,
            l.local,
            l.pid.map(|p| p.to_string()).unwrap_or_else(|| "-".into()),
            l.comm.as_deref().unwrap_or("-")
        ));
    }
    s
}

pub fn save_snapshot(path: &PathBuf, snap: &Snapshot) -> std::io::Result<()> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)?;
    }
    let text = serde_json::to_string_pretty(snap).unwrap_or_else(|_| "{}".into());
    fs::write(path, text)
}

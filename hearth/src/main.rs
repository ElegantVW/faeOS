mod auth;
mod users;

use clap::{Parser, Subcommand};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::io::{BufRead, BufReader, Write};
use std::os::unix::net::{UnixListener, UnixStream};
use std::path::PathBuf;

/// faeOS user manager — multi-user auth, session switching, user CRUD
#[derive(Parser)]
#[command(name = "hearth", about = "faeOS user manager")]
struct Cli {
    #[command(subcommand)]
    command: Option<Command>,
}

#[derive(Subcommand)]
enum Command {
    /// Run as daemon (Unix socket server)
    Daemon,
    /// List all users visible to seal
    List,
    /// Create a new system user
    Add {
        /// Username (a-z, 0-9, _ -)
        name: String,
    },
    /// Delete a system user and their home directory
    Remove {
        /// Username to delete
        name: String,
    },
    /// Hide a user from the seal lock screen
    Hide {
        /// Username to hide
        name: String,
    },
    /// Show a previously hidden user
    Show {
        /// Username to show
        name: String,
    },
    /// Set a user's display name for the lock screen
    Name {
        /// Username
        name: String,
        /// Display name shown on lock screen
        display: String,
    },
    /// Create a temporary guest user
    Guest {
        #[command(subcommand)]
        action: Option<GuestCommand>,
    },
}

#[derive(Subcommand)]
enum GuestCommand {
    Start,
    Stop,
    Status,
}

#[derive(Debug, Deserialize)]
struct Request {
    cmd: String,
    user: Option<String>,
    pass: Option<String>,
}

#[derive(Debug, Serialize)]
struct Response {
    ok: bool,
    msg: Option<String>,
    users: Option<Vec<users::User>>,
    sessions: Option<Vec<users::Session>>,
}

const SOCKET_PATH: &str = "/tmp/hearth.sock";

fn main() -> anyhow::Result<()> {
    let cli = Cli::parse();

    match cli.command.unwrap_or(Command::Daemon) {
        Command::Daemon => run_daemon()?,
        Command::List => cmd_list()?,
        Command::Add { name } => cmd_add(&name)?,
        Command::Remove { name } => cmd_remove(&name)?,
        Command::Hide { name } => cmd_hide(&name)?,
        Command::Show { name } => cmd_show(&name)?,
        Command::Name { name, display } => cmd_name(&name, &display)?,
        Command::Guest { action } => cmd_guest(action)?,
    }
    Ok(())
}

fn cmd_list() -> anyhow::Result<()> {
    for u in users::discover_users()? {
        println!("{:>8} {:>5}  {}", u.name, u.uid, u.display);
    }
    Ok(())
}

fn cmd_add(name: &str) -> anyhow::Result<()> {
    let status = std::process::Command::new("sudo")
        .args(["useradd", "-m", "-s", "/usr/bin/zsh", name])
        .status()?;
    if !status.success() {
        anyhow::bail!("useradd failed");
    }
    set_override(name, "display", name)?;
    set_override(name, "hidden", "false")?;
    println!("created user '{}'", name);
    Ok(())
}

fn cmd_remove(name: &str) -> anyhow::Result<()> {
    let status = std::process::Command::new("sudo")
        .args(["userdel", "-r", name])
        .status()?;
    if !status.success() {
        anyhow::bail!("userdel failed");
    }
    let mut ov = load_overrides();
    ov.remove(name);
    save_overrides(&ov)?;
    println!("deleted user '{}'", name);
    Ok(())
}

fn cmd_hide(name: &str) -> anyhow::Result<()> {
    set_override(name, "hidden", "true")?;
    println!("hidden '{}' from seal", name);
    Ok(())
}

fn cmd_show(name: &str) -> anyhow::Result<()> {
    set_override(name, "hidden", "false")?;
    println!("showing '{}' in seal", name);
    Ok(())
}

fn cmd_name(name: &str, display: &str) -> anyhow::Result<()> {
    set_override(name, "display", display)?;
    println!("'{}' will show as '{}'", name, display);
    Ok(())
}

fn cmd_guest(action: Option<GuestCommand>) -> anyhow::Result<()> {
    match action.unwrap_or(GuestCommand::Status) {
        GuestCommand::Start => guest_start()?,
        GuestCommand::Stop => guest_stop()?,
        GuestCommand::Status => guest_status()?,
    }
    Ok(())
}

fn guest_start() -> anyhow::Result<()> {
    let name = "fae-guest";
    let home = "/tmp/fae-guest";

    let exists = std::process::Command::new("id").arg(name).status()?.success();
    if exists {
        println!("guest already exists");
        return Ok(());
    }

    let status = std::process::Command::new("sudo")
        .args(["useradd", "-M", "-s", "/usr/bin/zsh", "-d", home, "-g", "users", name])
        .status()?;
    if !status.success() {
        anyhow::bail!("failed to create guest");
    }

    std::process::Command::new("sudo")
        .args(["mkdir", "-p", home])
        .status()?;
    std::process::Command::new("sudo")
        .args(["chown", &format!("{}:users", name), home])
        .status()?;
    std::process::Command::new("sudo")
        .args(["chmod", "700", home])
        .status()?;

    let zshrc = r#"export PATH=/usr/local/bin:/usr/bin:/bin
export HOME=/tmp/fae-guest
PS1='guest > '
alias ls='ls --color=auto'
echo "welcome, guest"
echo "type exit or Ctrl-D to leave"
"#;

    let tmp = "/tmp/hearth-guest-zshrc";
    std::fs::write(tmp, zshrc)?;
    std::process::Command::new("sudo")
        .args(["cp", tmp, &format!("{}/.zshrc", home)])
        .status()?;
    std::process::Command::new("sudo")
        .args(["chown", &format!("{}:users", name), &format!("{}/.zshrc", home)])
        .status()?;
    let _ = std::fs::remove_file(tmp);

    for d in std::fs::read_dir("/home")?.flatten() {
        let p = d.path();
        if p.is_dir() && p.file_name().unwrap() != name {
            std::process::Command::new("sudo")
                .args(["chmod", "o-rwx", p.to_str().unwrap_or("")])
                .status()?;
        }
    }

    println!("guest user '{}' created. switch VT (Ctrl+Alt+F3) to log in", name);
    Ok(())
}

fn guest_stop() -> anyhow::Result<()> {
    let name = "fae-guest";
    std::process::Command::new("sudo").args(["pkill", "-u", name]).status().ok();
    std::process::Command::new("sudo").args(["userdel", "-r", name]).status().ok();
    std::process::Command::new("sudo").args(["rm", "-rf", "/tmp/fae-guest"]).status().ok();
    for d in std::fs::read_dir("/home")?.flatten() {
        let p = d.path();
        if p.is_dir() {
            std::process::Command::new("sudo")
                .args(["chmod", "755", p.to_str().unwrap_or("")])
                .status()?;
        }
    }
    println!("guest removed");
    Ok(())
}

fn guest_status() -> anyhow::Result<()> {
    let ok = std::process::Command::new("id").arg("fae-guest").status()?.success();
    if ok {
        println!("guest active");
    } else {
        println!("no guest");
    }
    Ok(())
}

fn overrides_path() -> PathBuf {
    let home = std::env::var("HOME").unwrap_or_else(|_| "/tmp".into());
    PathBuf::from(home).join(".config").join("pixie").join("hearth.json")
}

fn load_overrides() -> HashMap<String, HashMap<String, String>> {
    let path = overrides_path();
    if let Ok(data) = std::fs::read_to_string(&path) {
        serde_json::from_str(&data).unwrap_or_default()
    } else {
        HashMap::new()
    }
}

fn save_overrides(ov: &HashMap<String, HashMap<String, String>>) -> anyhow::Result<()> {
    let path = overrides_path();
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent)?;
    }
    let json = serde_json::to_string_pretty(ov)?;
    std::fs::write(&path, json)?;
    Ok(())
}

fn set_override(name: &str, key: &str, value: &str) -> anyhow::Result<()> {
    let mut ov = load_overrides();
    ov.entry(name.to_string())
        .or_default()
        .insert(key.to_string(), value.to_string());
    save_overrides(&ov)
}

// ── daemon ──

fn run_daemon() -> anyhow::Result<()> {
    let _ = std::fs::remove_file(SOCKET_PATH);
    let listener = UnixListener::bind(SOCKET_PATH)?;
    let perm = std::os::unix::fs::PermissionsExt::from_mode(0o600);
    std::fs::set_permissions(SOCKET_PATH, perm)?;

    for stream in listener.incoming() {
        match stream {
            Ok(stream) => handle_client(stream),
            Err(e) => eprintln!("hearth: connection error: {}", e),
        }
    }
    let _ = std::fs::remove_file(SOCKET_PATH);
    Ok(())
}

fn handle_client(mut stream: UnixStream) {
    let reader = BufReader::new(stream.try_clone().unwrap());
    let mut resp = Response { ok: false, msg: None, users: None, sessions: None };

    for line in reader.lines() {
        let line = match line { Ok(l) => l, Err(_) => break };
        let req: Request = match serde_json::from_str(&line) {
            Ok(r) => r,
            Err(_) => { resp.msg = Some("bad json".into()); send(&mut stream, &resp); break; }
        };

        match req.cmd.as_str() {
            "PING" => { resp.ok = true; resp.msg = Some("pong".into()); }
            "LIST" => {
                match users::discover_users() {
                    Ok(us) => { resp.ok = true; resp.users = Some(us); }
                    Err(e) => { resp.ok = false; resp.msg = Some(format!("{}", e)); }
                }
            }
            "SESSIONS" => {
                match users::list_sessions() {
                    Ok(ss) => { resp.ok = true; resp.sessions = Some(ss); }
                    Err(e) => { resp.ok = false; resp.msg = Some(format!("{}", e)); }
                }
            }
            "AUTH" => {
                let user = req.user.unwrap_or_default();
                let pass = req.pass.unwrap_or_default();
                if auth::verify_password(&user, &pass) {
                    resp.ok = true; resp.msg = Some("ok".into());
                } else {
                    resp.ok = false; resp.msg = Some("auth failed".into());
                }
            }
            "LOGIN" => {
                let user = req.user.unwrap_or_default();
                match users::activate_session(&user) {
                    Ok(true) => { resp.ok = true; resp.msg = Some(format!("switched to {}", user)); }
                    Ok(false) => { resp.ok = false; resp.msg = Some(format!("no session for {}", user)); }
                    Err(e) => { resp.ok = false; resp.msg = Some(format!("{}", e)); }
                }
            }
            _ => { resp.msg = Some(format!("unknown: {}", req.cmd)); }
        }
        send(&mut stream, &resp);
        break;
    }
}

fn send(stream: &mut UnixStream, resp: &Response) {
    let _ = writeln!(stream, "{}", serde_json::to_string(resp).unwrap_or_default());
}

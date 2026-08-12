mod auth;
mod users;

use clap::Parser;
use serde::{Deserialize, Serialize};
use std::io::{BufRead, BufReader, Write};
use std::os::unix::net::{UnixListener, UnixStream};

#[derive(Parser)]
#[command(name = "hearth", about = "faeOS user manager")]
struct Cli {
    #[arg(long)]
    daemon: bool,

    #[arg(long)]
    list: bool,
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

    if cli.list {
        let us = users::discover_users()?;
        for u in &us {
            println!("{:>8}  {:3}  {}", u.name, u.uid, u.display);
        }
        return Ok(());
    }

    run_daemon()
}

fn run_daemon() -> anyhow::Result<()> {
    let _ = std::fs::remove_file(SOCKET_PATH);

    let listener = UnixListener::bind(SOCKET_PATH)?;
    // Restrict socket to current user only
    let perm = std::os::unix::fs::PermissionsExt::from_mode(0o600);
    std::fs::set_permissions(SOCKET_PATH, perm)?;

    for stream in listener.incoming() {
        match stream {
            Ok(stream) => {
                handle_client(stream);
            }
            Err(e) => {
                eprintln!("hearth: connection error: {}", e);
            }
        }
    }

    let _ = std::fs::remove_file(SOCKET_PATH);
    Ok(())
}

fn handle_client(mut stream: UnixStream) {
    let reader = BufReader::new(stream.try_clone().unwrap());
    let mut resp = Response {
        ok: false,
        msg: None,
        users: None,
        sessions: None,
    };

    for line in reader.lines() {
        let line = match line {
            Ok(l) => l,
            Err(_) => break,
        };

        let req: Request = match serde_json::from_str(&line) {
            Ok(r) => r,
            Err(_) => {
                resp.ok = false;
                resp.msg = Some("bad json".into());
                let _ = writeln!(
                    stream,
                    "{}",
                    serde_json::to_string(&resp).unwrap_or_default()
                );
                break;
            }
        };

        match req.cmd.as_str() {
            "PING" => {
                resp.ok = true;
                resp.msg = Some("pong".into());
            }
            "LIST" => {
                match users::discover_users() {
                    Ok(us) => {
                        resp.ok = true;
                        resp.users = Some(us);
                    }
                    Err(e) => {
                        resp.ok = false;
                        resp.msg = Some(format!("{}", e));
                    }
                }
            }
            "SESSIONS" => {
                match users::list_sessions() {
                    Ok(ss) => {
                        resp.ok = true;
                        resp.sessions = Some(ss);
                    }
                    Err(e) => {
                        resp.ok = false;
                        resp.msg = Some(format!("{}", e));
                    }
                }
            }
            "AUTH" => {
                let user = req.user.unwrap_or_default();
                let pass = req.pass.unwrap_or_default();
                if user.is_empty() || pass.is_empty() {
                    resp.ok = false;
                    resp.msg = Some("missing user or pass".into());
                } else if auth::verify_password(&user, &pass) {
                    resp.ok = true;
                    resp.msg = Some("ok".into());
                } else {
                    resp.ok = false;
                    resp.msg = Some("auth failed".into());
                }
            }
            "LOGIN" => {
                let user = req.user.unwrap_or_default();
                match users::activate_session(&user) {
                    Ok(true) => {
                        resp.ok = true;
                        resp.msg = Some(format!("switched to {}", user));
                    }
                    Ok(false) => {
                        resp.ok = false;
                        resp.msg = Some(format!("no session for {}", user));
                    }
                    Err(e) => {
                        resp.ok = false;
                        resp.msg = Some(format!("{}", e));
                    }
                }
            }
            _ => {
                resp.ok = false;
                resp.msg = Some(format!("unknown command: {}", req.cmd));
            }
        };

        let _ = writeln!(stream, "{}", serde_json::to_string(&resp).unwrap_or_default());
        break;
    }
}

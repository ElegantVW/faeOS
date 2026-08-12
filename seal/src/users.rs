use serde::{Deserialize, Serialize};
use std::io::{BufRead, BufReader, Write};
use std::os::unix::net::UnixStream;

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
    let request = format!(
        r#"{{"cmd":"AUTH","user":"{}","pass":"{}"}}"#,
        user, pass
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

pub fn list_users() -> Option<Vec<User>> {
    let raw = send_cmd("LIST")?;
    let resp: Response = serde_json::from_str(&raw).ok()?;
    resp.users.map(|us| {
        us.into_iter()
            .map(|u| User {
                name: u.name,
                uid: u.uid,
                display: u.display,
            })
            .collect()
    })
}

pub fn verify_password(user: &str, password: &str) -> Option<bool> {
    send_auth(user, password)
}

pub fn login_user(user: &str) -> Option<bool> {
    send_login(user)
}

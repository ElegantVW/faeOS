use std::io::Write;
use std::process::{Command, Stdio};

pub fn verify_password(password: &str) -> bool {
    let mut child = match Command::new("sudo")
        .args(["-S", "-k", "-v"])
        .env("LANG", "C")
        .env("LC_ALL", "C")
        .stdin(Stdio::piped())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
    {
        Ok(c) => c,
        Err(_) => return false,
    };

    if let Some(mut stdin) = child.stdin.take() {
        let _ = stdin.write_all(password.as_bytes());
        let _ = stdin.write_all(b"\n");
        let _ = stdin.flush();
    }

    match child.wait() {
        Ok(status) => status.success(),
        Err(_) => false,
    }
}

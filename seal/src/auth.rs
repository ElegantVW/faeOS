use std::io::Write;
use std::process::{Command, Stdio};

pub fn verify_password(password: &str) -> bool {
    let current_user = std::env::var("USER").unwrap_or_else(|_| String::new());
    verify_local(&current_user, password)
}

pub fn verify_user_password(user: &str, password: &str) -> bool {
    if let Some(result) = crate::users::verify_password(user, password) {
        return result;
    }
    verify_local(user, password)
}

pub fn verify_local(user: &str, password: &str) -> bool {
    let current = std::env::var("USER").unwrap_or_default();

    if user == current {
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

        return child.wait().map(|s| s.success()).unwrap_or(false);
    }

    false
}

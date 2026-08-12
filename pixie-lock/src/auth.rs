use anyhow::{anyhow, Result};

pub fn verify_password(password: &str) -> Result<bool> {
    let user = std::env::var("USER").unwrap_or_else(|_| "root".into());

    let service = if std::path::Path::new("/etc/pam.d/pixie-lock").exists() {
        "pixie-lock"
    } else {
        "system-auth"
    };

    match authenticate_with_pam(service, &user, password) {
        Ok(true) => Ok(true),
        Ok(false) => Ok(false),
        Err(e) => {
            eprintln!("pixie-lock: PAM error: {}. Try: sudo setcap cap_dac_read_search+ep $(which pixie-lock)", e);
            fallback_auth(password)
        }
    }
}

fn authenticate_with_pam(_service: &str, user: &str, password: &str) -> Result<bool> {
    use std::io::Write;
    use std::process::{Command, Stdio};

    let mut child = Command::new("su")
        .arg("-c")
        .arg(format!("echo '{}' | su -c true {} 2>/dev/null", "placeholder", user))
        .stdin(Stdio::piped())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
        .map_err(|_| anyhow!("cannot run auth helper"))?;

    if let Some(mut stdin) = child.stdin.take() {
        let _ = writeln!(stdin, "{}", password);
    }

    let status = child.wait()?;
    Ok(status.success())
}

fn fallback_auth(password: &str) -> Result<bool> {
    let user = std::env::var("USER").unwrap_or_else(|_| "root".into());
    let mut pwd = password.as_bytes().to_vec();
    pwd.push(b'\n');

    let ok = std::process::Command::new("su")
        .arg("-c")
        .arg("exit 0")
        .arg(&user)
        .stdin(std::process::Stdio::piped())
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::null())
        .spawn()
        .and_then(|mut child| {
            use std::io::Write;
            if let Some(mut stdin) = child.stdin.take() {
                let _ = stdin.write_all(&pwd);
                let _ = stdin.flush();
            }
            child.wait()
        })
        .map(|s| s.success())
        .unwrap_or(false);

    Ok(ok)
}

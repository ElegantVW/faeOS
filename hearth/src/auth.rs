use portable_pty::{self, CommandBuilder, PtySize, PtySystem};

pub fn verify_password(username: &str, password: &str) -> bool {
    let pty_system = portable_pty::NativePtySystem::default();

    let pair = match pty_system.openpty(PtySize {
        rows: 24,
        cols: 80,
        pixel_width: 0,
        pixel_height: 0,
    }) {
        Ok(p) => p,
        Err(_) => return false,
    };

    let mut cmd = CommandBuilder::new("su");
    cmd.args([username, "-c", "/bin/true"]);

    let mut child = match pair.slave.spawn_command(cmd) {
        Ok(c) => c,
        Err(_) => return false,
    };

    drop(pair.slave);

    {
        let mut writer = pair.master.take_writer().unwrap();
        use std::io::Write;
        let _ = writer.write_all(password.as_bytes());
        let _ = writer.write_all(b"\n");
        let _ = writer.flush();
    }

    let status = child.wait();
    match status {
        Ok(s) => s.success(),
        Err(_) => false,
    }
}

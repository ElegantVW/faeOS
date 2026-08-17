mod auth;
mod battery;
mod clock;
mod config;
mod input;
mod render;
mod users;
mod x11;

use clap::Parser;
use input::PasswordInput;
use std::os::unix::process::CommandExt;
use std::panic::{self, AssertUnwindSafe};
use std::path::PathBuf;
use std::process::{Command, Stdio};
use std::time::{Duration, Instant};

#[derive(Parser)]
#[command(
    name = "seal",
    about = "faeOS seal — lock screen and graphical login face"
)]
struct Cli {
    /// Suspend after a successful unlock
    #[arg(long)]
    suspend: bool,

    /// Idle-watch daemon (locks when idle)
    #[arg(long)]
    daemon: bool,

    /// Graphical login face (greeter). On success execs --session.
    #[arg(long)]
    greeter: bool,

    /// Command to exec after greeter auth (default: i3, or $SEAL_SESSION)
    #[arg(long, default_value = "")]
    session: String,

    /// Unused (kept for CLI compat); face is termart-only
    #[arg(long, default_value = "")]
    message: String,

    /// Unused (kept for CLI compat)
    #[arg(long)]
    guest: bool,
}

fn main() -> anyhow::Result<()> {
    let cli = Cli::parse();

    if cli.daemon {
        return run_daemon();
    }

    lock_or_greet(&cli)
}

fn session_command(cli: &Cli) -> String {
    if !cli.session.is_empty() {
        return cli.session.clone();
    }
    if let Ok(s) = std::env::var("SEAL_SESSION") {
        if !s.trim().is_empty() {
            return s;
        }
    }
    "i3".into()
}

fn lock_or_greet(cli: &Cli) -> anyhow::Result<()> {
    let greeter = cli.greeter;
    let guest = cli.guest;
    let msg = ""; // face ignores messages — termart only

    let mut x11 = x11::X11Lock::new()?;
    x11.create_window()?;

    let user_list = users::list_users().unwrap_or_else(|| {
        let cur = std::env::var("USER").unwrap_or_else(|_| "user".into());
        vec![users::User {
            name: cur.clone(),
            uid: 1000,
            display: cur,
        }]
    });

    let current_user = std::env::var("USER").unwrap_or_else(|_| "user".into());
    let mut user_sel = user_list
        .iter()
        .position(|u| u.name == current_user)
        .unwrap_or(0);

    let mut frame = render::FrameRenderer::new_with_mode(x11.width, x11.height, greeter)?;
    let mut password = PasswordInput::new();

    // Static face — no lock-in animation
    let bat = battery::read();
    frame.render_frame(
        msg,
        &bat,
        &password,
        guest,
        &user_list,
        user_sel,
        render::AnimPhase::Idle,
    );
    x11.show_image(frame.raw_pixels())?;
    x11.grab_inputs()?;

    let result = panic::catch_unwind(AssertUnwindSafe(|| {
        lock_loop(
            &mut x11,
            &mut frame,
            &mut password,
            msg,
            guest,
            greeter,
            &user_list,
            &mut user_sel,
        )
    }));

    match result {
        Ok(Ok(AuthOutcome::Unlocked { user })) => {
            // Only motion: recolor + 1s fade on successful password
            play_unlock_fade(
                &mut x11,
                &mut frame,
                msg,
                guest,
                &user_list,
                user_sel,
                &password,
            )?;
            x11.ungrab_and_destroy()?;
            if greeter {
                let cmd = session_command(cli);
                eprintln!("seal: greeter ok ({user}) → {cmd}");
                return exec_session(&cmd);
            }
            if cli.suspend {
                let _ = Command::new("systemctl").arg("suspend").spawn();
            }
            Ok(())
        }
        Ok(Ok(AuthOutcome::Cancelled)) => {
            x11.ungrab_and_destroy()?;
            if greeter {
                anyhow::bail!("seal greeter cancelled");
            }
            Ok(())
        }
        Ok(Err(e)) => {
            let _ = x11.ungrab_and_destroy();
            Err(e)
        }
        Err(panic_err) => {
            let _ = x11.ungrab_and_destroy();
            let msg = if let Some(s) = panic_err.downcast_ref::<String>() {
                s.clone()
            } else if let Some(s) = panic_err.downcast_ref::<&str>() {
                s.to_string()
            } else {
                "unknown panic".to_string()
            };
            Err(anyhow::anyhow!("lock loop panicked: {}", msg))
        }
    }
}

fn play_unlock_fade(
    x11: &mut x11::X11Lock,
    frame: &mut render::FrameRenderer,
    msg: &str,
    guest: bool,
    user_list: &[users::User],
    user_sel: usize,
    password: &PasswordInput,
) -> anyhow::Result<()> {
    // Start chime first so audio leads the fade; both ~1.5s.
    let _player = spawn_unlock_sound();
    let duration = Duration::from_millis(1500);
    let start = Instant::now();
    loop {
        let t = (start.elapsed().as_secs_f32() / duration.as_secs_f32()).clamp(0.0, 1.0);
        let bat = battery::read();
        frame.render_frame(
            msg,
            &bat,
            password,
            guest,
            user_list,
            user_sel,
            render::AnimPhase::Unlock(t),
        );
        x11.show_image(frame.raw_pixels())?;
        if t >= 1.0 {
            break;
        }
        std::thread::sleep(Duration::from_millis(16));
    }
    // Let short tail of the chime finish if still playing
    if let Some(mut child) = _player {
        let _ = child.try_wait();
    }
    Ok(())
}

/// Locate `seal-unlock.wav` (house assets or XDG share).
fn unlock_sound_path() -> Option<PathBuf> {
    if let Ok(p) = std::env::var("SEAL_UNLOCK_SOUND") {
        let pb = PathBuf::from(p);
        if pb.is_file() {
            return Some(pb);
        }
    }
    let mut candidates: Vec<PathBuf> = Vec::new();
    if let Ok(home) = std::env::var("HOME") {
        let home = PathBuf::from(home);
        candidates.push(home.join(".local/share/faeos/sounds/seal-unlock.wav"));
        candidates.push(home.join("faeos/assets/sounds/seal-unlock.wav"));
        candidates.push(home.join("faeos/assets/sounds/ui/menu_levelup.wav"));
    }
    if let Ok(xdg) = std::env::var("XDG_DATA_HOME") {
        candidates.push(PathBuf::from(xdg).join("faeos/sounds/seal-unlock.wav"));
    }
    // Beside install tree: ../assets/sounds from binary
    if let Ok(exe) = std::env::current_exe() {
        if let Some(bin) = exe.parent() {
            candidates.push(bin.join("../assets/sounds/seal-unlock.wav"));
            candidates.push(bin.join("sounds/seal-unlock.wav"));
        }
    }
    candidates.into_iter().find(|p| p.is_file())
}

/// Fire-and-forget unlock chime (paplay → mpv → aplay). Returns child if spawned.
fn spawn_unlock_sound() -> Option<std::process::Child> {
    let path = unlock_sound_path()?;
    let path_str = path.to_string_lossy().into_owned();

    let try_spawn = |prog: &str, args: &[&str]| -> Option<std::process::Child> {
        Command::new(prog)
            .args(args)
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .spawn()
            .ok()
    };

    if let Some(c) = try_spawn("paplay", &[&path_str]) {
        return Some(c);
    }
    if let Some(c) = try_spawn(
        "mpv",
        &["--no-video", "--really-quiet", "--no-terminal", &path_str],
    ) {
        return Some(c);
    }
    if let Some(c) = try_spawn("aplay", &["-q", &path_str]) {
        return Some(c);
    }
    eprintln!(
        "seal: unlock sound found but not playable (need paplay/mpv/aplay): {}",
        path.display()
    );
    None
}

enum AuthOutcome {
    Unlocked { user: String },
    #[allow(dead_code)]
    Cancelled,
}

fn exec_session(cmd: &str) -> anyhow::Result<()> {
    let err = Command::new("sh")
        .arg("-c")
        .arg(format!("exec {cmd}"))
        .exec();
    Err(anyhow::anyhow!("failed to exec session `{cmd}`: {err}"))
}

fn lock_loop(
    x11: &mut x11::X11Lock,
    frame: &mut render::FrameRenderer,
    password: &mut PasswordInput,
    msg: &str,
    guest: bool,
    greeter: bool,
    user_list: &[users::User],
    user_sel: &mut usize,
) -> anyhow::Result<AuthOutcome> {
    let mut fail_count: u32 = 0;
    let mut lockout_until: Option<Instant> = None;
    let _ = greeter;
    let mut dirty = true;

    loop {
        if dirty {
            let bat = battery::read();
            frame.render_frame(
                msg,
                &bat,
                password,
                guest,
                user_list,
                *user_sel,
                render::AnimPhase::Idle,
            );
            let _ = x11.show_image(frame.raw_pixels());
            dirty = false;
        }

        let locked_out = lockout_until
            .map(|until| Instant::now() < until)
            .unwrap_or(false);
        if !locked_out {
            lockout_until = None;
        }

        if !locked_out {
            match poll_events(x11)? {
                Some(EventResult::Enter) => {
                    let pw = password.submit();
                    let selected = &user_list[*user_sel];
                    if auth::verify_user_password(&selected.name, &pw) {
                        let _ = users::login_user(&selected.name);
                        return Ok(AuthOutcome::Unlocked {
                            user: selected.name.clone(),
                        });
                    }
                    // Wrong password: clear, stay on black + termart (no feedback UI)
                    password.set_error();
                    password.clear();
                    dirty = true;
                    fail_count = fail_count.saturating_add(1);
                    let wait = if fail_count >= 8 {
                        15
                    } else if fail_count >= 5 {
                        5
                    } else if fail_count >= 3 {
                        2
                    } else {
                        0
                    };
                    if wait > 0 {
                        lockout_until = Some(Instant::now() + Duration::from_secs(wait));
                        eprintln!("seal: auth failed ({fail_count}) — wait {wait}s");
                    }
                }
                Some(EventResult::Up) | Some(EventResult::TabPrev) => {
                    if !user_list.is_empty() {
                        *user_sel = if *user_sel == 0 {
                            user_list.len() - 1
                        } else {
                            *user_sel - 1
                        };
                        password.clear();
                        dirty = true;
                    }
                }
                Some(EventResult::Down) | Some(EventResult::TabNext) => {
                    if !user_list.is_empty() {
                        *user_sel = (*user_sel + 1) % user_list.len();
                        password.clear();
                        dirty = true;
                    }
                }
                Some(EventResult::Escape) => {
                    password.clear();
                    dirty = true;
                }
                Some(EventResult::Backspace) => {
                    password.backspace();
                    dirty = true;
                }
                Some(EventResult::CapsLock) => {
                    password.set_caps_lock(!password.caps_lock_on());
                    dirty = true;
                }
                Some(EventResult::Char(c)) => {
                    password.push_char(c);
                    dirty = true;
                }
                None => {}
            }
        } else {
            let _ = poll_events(x11);
        }

        std::thread::sleep(Duration::from_millis(16));
    }
}

enum EventResult {
    Enter,
    Escape,
    Backspace,
    CapsLock,
    Char(char),
    Up,
    Down,
    TabNext,
    TabPrev,
}

fn poll_events(x11: &x11::X11Lock) -> anyhow::Result<Option<EventResult>> {
    use x11rb::protocol::Event;

    while let Ok(Some(event)) = x11.poll_event() {
        match event {
            Event::KeyPress(kp) => {
                let keycode = kp.detail;
                let state: u16 = u16::from(kp.state);
                // Shift mask — cycle users backward on Shift+Tab
                let shift = state & 0x1 != 0;

                match keycode {
                    36 | 104 => return Ok(Some(EventResult::Enter)),
                    9 => return Ok(Some(EventResult::Escape)),
                    22 => return Ok(Some(EventResult::Backspace)),
                    66 => return Ok(Some(EventResult::CapsLock)),
                    111 => return Ok(Some(EventResult::Up)),
                    116 => return Ok(Some(EventResult::Down)),
                    23 => {
                        // Tab
                        return Ok(Some(if shift {
                            EventResult::TabPrev
                        } else {
                            EventResult::TabNext
                        }));
                    }
                    _ => {
                        if let Some(c) = x11.keycode_to_char(keycode, state) {
                            if !c.is_control() {
                                return Ok(Some(EventResult::Char(c)));
                            }
                        }
                    }
                }
            }
            _ => {}
        }
    }

    Ok(None)
}

fn run_daemon() -> anyhow::Result<()> {
    use std::sync::atomic::{AtomicBool, Ordering};
    use std::sync::Arc;

    let running = Arc::new(AtomicBool::new(true));
    let r = running.clone();

    std::thread::spawn(move || {
        use std::io::Read;
        let mut buf = [0u8; 1];
        let _ = std::io::stdin().read(&mut buf);
        r.store(false, Ordering::SeqCst);
    });

    let self_bin = std::env::current_exe().unwrap_or_else(|_| "seal".into());
    let mut cooldown_until = Instant::now();

    while running.load(Ordering::SeqCst) {
        let cfg = config::load();
        if !cfg.enabled || cfg.dont_lock {
            std::thread::sleep(Duration::from_secs(2));
            continue;
        }

        if Instant::now() < cooldown_until {
            std::thread::sleep(Duration::from_secs(1));
            continue;
        }

        if is_screen_locked() {
            std::thread::sleep(Duration::from_secs(2));
            continue;
        }

        let idle_ms = get_idle_ms();
        let battery = battery::read();
        let timeout_ms = if battery.present && !battery.on_ac {
            cfg.battery_idle_seconds as u64 * 1000
        } else {
            cfg.ac_idle_seconds as u64 * 1000
        };

        if idle_ms >= timeout_ms {
            let status = Command::new(&self_bin).spawn().and_then(|mut c| c.wait());

            match status {
                Ok(s) if s.success() => {
                    cooldown_until = Instant::now() + Duration::from_secs(5);
                    if cfg.suspend_on_lock {
                        let _ = Command::new("systemctl").arg("suspend").spawn();
                    }
                }
                Ok(_) => {
                    cooldown_until = Instant::now() + Duration::from_secs(3);
                }
                Err(e) => {
                    eprintln!("seal daemon: spawn lock failed: {e}");
                    std::thread::sleep(Duration::from_secs(5));
                }
            }
        }

        std::thread::sleep(Duration::from_secs(2));
    }

    Ok(())
}

fn get_idle_ms() -> u64 {
    Command::new("xprintidle")
        .output()
        .ok()
        .and_then(|out| String::from_utf8_lossy(&out.stdout).trim().parse().ok())
        .unwrap_or(0)
}

fn is_screen_locked() -> bool {
    let self_pid = std::process::id();
    Command::new("pgrep")
        .args(["-x", "seal"])
        .output()
        .ok()
        .map(|o| {
            String::from_utf8_lossy(&o.stdout)
                .split_whitespace()
                .filter_map(|s| s.parse::<u32>().ok())
                .any(|pid| pid != self_pid)
        })
        .unwrap_or(false)
}

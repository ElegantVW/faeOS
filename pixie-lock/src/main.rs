mod auth;
mod battery;
mod clock;
mod config;
mod input;
mod render;
mod x11;

use clap::Parser;
use input::PasswordInput;
use std::time::{Duration, Instant};

#[derive(Parser)]
#[command(name = "pixie-lock", about = "faeOS lock screen")]
struct Cli {
    #[arg(long)]
    suspend: bool,

    #[arg(long)]
    daemon: bool,

    #[arg(long, default_value = "")]
    message: String,

    #[arg(long)]
    guest: bool,
}

fn main() -> anyhow::Result<()> {
    let cli = Cli::parse();

    if cli.daemon {
        return run_daemon();
    }

    lock_screen(&cli)
}

fn lock_screen(cli: &Cli) -> anyhow::Result<()> {
    let cfg = config::load();
    let guest = cli.guest || cfg.guest_enabled;
    let msg = if cli.message.is_empty() {
        &cfg.lock_message
    } else {
        &cli.message
    };

    let mut x11 = x11::X11Lock::new()?;

    x11.create_window()?;

    let mut frame = render::FrameRenderer::new(x11.width, x11.height)?;
    let mut password = PasswordInput::new();
    let battery_info = battery::read();

    frame.render_frame(msg, &battery_info, &password, guest);
    x11.show_image(frame.raw_pixels())?;

    x11.grab_inputs()?;

    let mut last_tick = Instant::now();
    let mut authenticated = false;

    loop {
        while let Ok(Some(event)) = x11.poll_event() {
            use x11rb::protocol::Event;
            match event {
                Event::KeyPress(kp) => {
                    let keycode = kp.detail;
                    let state: u16 = u16::from(kp.state);

                    match keycode {
                        9 => {
                            password.clear();
                        }
                        22 => {
                            password.backspace();
                        }
                        36 | 104 => {
                            let pw = password.submit();
                            match auth::verify_password(&pw) {
                                Ok(true) => {
                                    authenticated = true;
                                    break;
                                }
                                Ok(false) => {
                                    password.set_error();
                                }
                                Err(_) => {
                                    password.set_error();
                                }
                            }
                        }
                        66 => {
                            password.set_caps_lock(!password.caps_lock_on());
                        }
                        _ => {
                            if let Some(c) = x11.keycode_to_char(keycode, state) {
                                if !c.is_control() {
                                    password.push_char(c);
                                }
                            }
                        }
                    }

                    let bat = battery::read();
                    frame.render_frame(msg, &bat, &password, guest);
                    x11.show_image(frame.raw_pixels())?;
                }
                _ => {}
            }
        }

        if authenticated {
            break;
        }

        let now = Instant::now();
        if now.duration_since(last_tick) >= Duration::from_secs(1) {
            last_tick = now;
            password.tick_error();
            let bat = battery::read();
            frame.render_frame(msg, &bat, &password, guest);
            x11.show_image(frame.raw_pixels())?;
        }

        std::thread::sleep(Duration::from_millis(50));
    }

    x11.ungrab_and_destroy()?;

    if authenticated && cli.suspend {
        std::process::Command::new("systemctl")
            .arg("suspend")
            .spawn()?;
    }

    Ok(())
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

    let mut locked = false;

    while running.load(Ordering::SeqCst) {
        let cfg = config::load();
        if !cfg.enabled || cfg.dont_lock {
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

        if idle_ms >= timeout_ms && !locked {
            let status = std::process::Command::new("pixie-lock")
                .spawn()
                .and_then(|mut c| c.wait());

            match status {
                Ok(s) if s.success() => {
                    locked = true;
                    if cfg.suspend_on_lock {
                        let _ = std::process::Command::new("systemctl")
                            .arg("suspend")
                            .spawn();
                    }
                }
                _ => std::thread::sleep(Duration::from_secs(2)),
            }
        }

        if locked {
            locked = is_screen_locked();
        }

        std::thread::sleep(Duration::from_secs(2));
    }

    Ok(())
}

fn get_idle_ms() -> u64 {
    std::process::Command::new("xprintidle")
        .output()
        .ok()
        .and_then(|out| String::from_utf8_lossy(&out.stdout).trim().parse().ok())
        .unwrap_or(0)
}

fn is_screen_locked() -> bool {
    std::process::Command::new("pgrep")
        .args(["-x", "pixie-lock"])
        .output()
        .map(|o| o.status.success())
        .unwrap_or(false)
}

mod battery;
mod clock;
mod config;
mod render;

use clap::Parser;
use std::process::Command;

#[derive(Parser)]
#[command(name = "pixie-lock", about = "faeOS lock screen")]
struct Cli {
    #[arg(long, default_value_t = false)]
    suspend: bool,

    #[arg(long, default_value_t = false)]
    daemon: bool,

    #[arg(long, default_value = "")]
    message: String,

    #[arg(long, default_value_t = false)]
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
    let battery = battery::read();
    let guest = cli.guest || cfg.guest_enabled;
    let msg = if cli.message.is_empty() {
        &cfg.lock_message
    } else {
        &cli.message
    };

    let image_data = render::generate(msg, &battery, guest)?;
    let lock_path = "/tmp/pixie-lock.png";
    std::fs::write(lock_path, &image_data)?;

    let mut child = Command::new("i3lock")
        .args(["-i", lock_path, "-n", "-e"])
        .arg("--nofork")
        .spawn()
        .map_err(|e| anyhow::anyhow!("i3lock not found: {}", e))?;

    let status = child.wait()?;

    if cli.suspend && status.success() {
        Command::new("systemctl").arg("suspend").spawn()?;
    }

    Ok(())
}

fn run_daemon() -> anyhow::Result<()> {
    use std::sync::atomic::{AtomicBool, Ordering};
    use std::sync::Arc;
    use std::time::Duration;

    let running = Arc::new(AtomicBool::new(true));
    let r = running.clone();

    ctrlc::set_handler(move || {
        r.store(false, Ordering::SeqCst);
    })?;

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
            let guest = cfg.guest_enabled;
            let msg = if cfg.lock_message.is_empty() {
                "away gathering moonlight..."
            } else {
                &cfg.lock_message
            };

            if let Ok(image_data) = render::generate(msg, &battery, guest) {
                std::fs::write("/tmp/pixie-lock.png", &image_data).ok();
            }

            let status = Command::new("i3lock")
                .args(["-i", "/tmp/pixie-lock.png", "-n", "-e"])
                .arg("--nofork")
                .spawn()
                .and_then(|mut c| c.wait());

            match status {
                Ok(s) if s.success() => {
                    locked = true;
                    if cfg.suspend_on_lock {
                        Command::new("systemctl").arg("suspend").spawn()?;
                    }
                }
                _ => {
                    std::thread::sleep(Duration::from_secs(2));
                }
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
    Command::new("xprintidle")
        .output()
        .ok()
        .and_then(|out| {
            String::from_utf8_lossy(&out.stdout)
                .trim()
                .parse()
                .ok()
        })
        .unwrap_or(0)
}

fn is_screen_locked() -> bool {
    Command::new("pgrep")
        .args(["-x", "i3lock"])
        .output()
        .map(|o| o.status.success())
        .unwrap_or(false)
}

mod display;
mod font;
mod term;

use clap::Parser;
use font::Font;
use portable_pty::PtySystem;
use std::io::{Read, Write};
use std::time::{Duration, Instant};
use term::Grid;
use x11rb::protocol::xproto::ConnectionExt;

static BG: [u8; 3] = [0x12, 0x08, 0x0e];
static FG: [u8; 3] = [0xff, 0x9c, 0xc4];

#[derive(Parser)]
#[command(name = "rift", about = "faeOS terminal emulator")]
struct Cli {
    #[arg(short, long, default_value = "zsh")]
    shell: String,
    #[arg(long, default_value_t = 13.0)]
    font_size: f32,
    #[arg(long, default_value_t = 120)]
    cols: usize,
    #[arg(long, default_value_t = 36)]
    rows: usize,
}

fn main() -> anyhow::Result<()> {
    let cli = Cli::parse();
    let mut font = Font::new(cli.font_size)
        .ok_or_else(|| anyhow::anyhow!("no font found"))?;

    let cw = font.cell_w;
    let ch = font.cell_h;
    let cols = cli.cols;
    let rows = cli.rows;
    let img_w = cols as u32 * cw;
    let img_h = rows as u32 * ch;

    // Spawn shell via PTY
    let shell = std::env::var("SHELL").unwrap_or(cli.shell);
    let pty = portable_pty::NativePtySystem::default();
    let pair = pty.openpty(portable_pty::PtySize {
        rows: rows as u16, cols: cols as u16,
        pixel_width: 0, pixel_height: 0,
    })?;

    let mut cmd = portable_pty::CommandBuilder::new(&shell);
    cmd.env("TERM", "xterm-256color");
    cmd.env("COLORTERM", "truecolor");
    let mut child = pair.slave.spawn_command(cmd)?;
    drop(pair.slave);

    let master = pair.master;
    let reader_fd = master.as_raw_fd().expect("no PTY fd");
    let mut reader = master.try_clone_reader()?;
    let mut writer = master.take_writer()?;
    // Set non-blocking
    unsafe {
        let flags = libc::fcntl(reader_fd, libc::F_GETFL, 0);
        libc::fcntl(reader_fd, libc::F_SETFL, flags | libc::O_NONBLOCK);
    }

    let mut grid = Grid::new(cols, rows);

    // Display
    let mut display = display::Display::new()?;
    display.create_window("✦ Rift", img_w, img_h)?;

    let stride = img_w * 4;
    let mut buf = vec![0u8; (stride * img_h) as usize];
    let mut running = true;
    let mut needs_render = true;
    let mut last_blink = Instant::now();
    let mut cursor_on = true;

    while running {
        // Read PTY → grid
        let mut pty_buf = [0u8; 4096];
        loop {
            match reader.read(&mut pty_buf) {
                Ok(0) => { running = false; break; }
                Ok(n) => {
                    grid.write(&pty_buf[..n]);
                    needs_render = true;
                }
                Err(ref e) if e.kind() == std::io::ErrorKind::WouldBlock => break,
                Err(_) => break,
            }
        }

        // Process X11 events
        while let Ok(Some(event)) = display.poll_event() {
            use x11rb::protocol::Event;
            match event {
                Event::KeyPress(kp) => {
                    let seq = term::key_to_input(kp.detail, u16::from(kp.state));
                    if !seq.is_empty() {
                        let _ = writer.write_all(&seq);
                        let _ = writer.flush();
                    }
                }
                Event::ClientMessage(cm) => {
                    let wm_delete = display.conn
                        .intern_atom(false, b"WM_DELETE_WINDOW")
                        .map(|r| r.reply().map(|r| r.atom).unwrap_or(0))
                        .unwrap_or(0);
                    if cm.data.as_data32()[0] == wm_delete {
                        running = false;
                    }
                }
                Event::ConfigureNotify(cn) => {
                    let nw = cn.width as u32;
                    let nh = cn.height as u32;
                    let nc = (nw / cw) as usize;
                    let nr = (nh / ch) as usize;
                    if nc != grid.cols || nr != grid.rows {
                        grid.resize(nc, nr);
                        let niw = nc as u32 * cw;
                        let nih = nr as u32 * ch;
                        buf.resize((niw * nih * 4) as usize, 0);
                    }
                }
                Event::Expose(_) => needs_render = true,
                _ => {}
            }
        }

        // Cursor blink
        if last_blink.elapsed() >= Duration::from_millis(530) {
            cursor_on = !cursor_on;
            last_blink = Instant::now();
            needs_render = true;
        }

        // Render frame
        if needs_render && running {
            let w_px = grid.cols as u32 * cw;
            let h_px = grid.rows as u32 * ch;
            let stride = w_px * 4;

            // Clear
            for i in (0..buf.len()).step_by(4) {
                buf[i] = BG[2]; buf[i+1] = BG[1]; buf[i+2] = BG[0];
            }

            // Draw cells
            for r in 0..grid.rows {
                for c in 0..grid.cols {
                    let cell = &grid.cells[r][c];
                    if cell.ch == ' ' {
                        continue;
                    }

                    let px = c as u32 * cw;
                    let py = r as u32 * ch;
                    let fg = cell.attrs.fg.to_rgb(FG, BG);
                    let bg = cell.attrs.bg.to_rgb(BG, BG);

                    // Background
                    for dy in 0..ch {
                        for dx in 0..cw {
                            let idx = ((py + dy) * stride + (px + dx) * 4) as usize;
                            if idx + 3 < buf.len() {
                                buf[idx] = bg[2]; buf[idx+1] = bg[1]; buf[idx+2] = bg[0];
                            }
                        }
                    }

                    // Glyph
                    if let Some(glyph) = font.get_glyph(cell.ch).as_ref() {
                        let gx = px as i32 + glyph.x_off;
                        let gy = py as i32 + glyph.y_off + ch as i32 - 2;

                        // Bold: double-strike
                        for _pass in 0..if cell.attrs.bold { 2 } else { 1 } {
                            let ox = if cell.attrs.bold && _pass == 1 { 1 } else { 0 };
                            for (i, &a) in glyph.bitmap.iter().enumerate() {
                                let dx = gx + (i as u32 % glyph.w) as i32 + ox;
                                let dy = gy + (i as u32 / glyph.w) as i32;
                                if dx >= 0 && dy >= 0 && (dx as u32) < w_px && (dy as u32) < h_px {
                                    let idx = (dy as u32 * stride + dx as u32 * 4) as usize;
                                    if idx + 3 < buf.len() {
                                        let alpha = a as f32 / 255.0;
                                        buf[idx] = blend(buf[idx], fg[2], alpha);
                                        buf[idx+1] = blend(buf[idx+1], fg[1], alpha);
                                        buf[idx+2] = blend(buf[idx+2], fg[0], alpha);
                                    }
                                }
                            }
                        }

                        // Italic: shear right per row
                    if cell.attrs.italic {
                        let skew = glyph.h / 3;
                            for (i, &a) in glyph.bitmap.iter().enumerate() {
                                let row = i as u32 / glyph.w;
                                let dx = gx + (i as u32 % glyph.w) as i32 + (row as i32 * skew as i32 / glyph.h as i32);
                                let dy = gy + row as i32;
                                if dx >= 0 && dy >= 0 && (dx as u32) < w_px && (dy as u32) < h_px {
                                    let idx = (dy as u32 * stride + dx as u32 * 4) as usize;
                                    if idx + 3 < buf.len() {
                                        let alpha = a as f32 / 255.0;
                                        buf[idx] = blend(buf[idx], fg[2], alpha);
                                        buf[idx+1] = blend(buf[idx+1], fg[1], alpha);
                                        buf[idx+2] = blend(buf[idx+2], fg[0], alpha);
                                    }
                                }
                            }
                        }
                    }

                    // Underline
                    if cell.attrs.underline {
                        for dx in 0..cw {
                            let idx = ((py + ch - 1) * stride + (px + dx) * 4) as usize;
                            if idx + 3 < buf.len() {
                                buf[idx] = fg[2]; buf[idx+1] = fg[1]; buf[idx+2] = fg[0];
                            }
                        }
                    }
                }
            }

            // Cursor
            if cursor_on && grid.cursor_visible {
                let cx = grid.cursor_col as u32 * cw;
                let cy = grid.cursor_row as u32 * ch;
                for dy in 0..2 {
                    for dx in 0..cw {
                        let idx = ((cy + ch - 2 + dy) * stride + (cx + dx) * 4) as usize;
                        if idx + 3 < buf.len() {
                            buf[idx] = 0xe8; buf[idx+1] = 0x79; buf[idx+2] = 0xa0;
                        }
                    }
                }
            }

            display.show(&buf[..(w_px * h_px * 4) as usize], w_px, h_px)?;
            needs_render = false;
        }

        // Check if child process died
        if let Ok(Some(_)) = child.try_wait() {
            running = false;
        }

        std::thread::sleep(Duration::from_millis(4));
    }

    display.destroy()?;
    Ok(())
}

fn blend(a: u8, b: u8, alpha: f32) -> u8 {
    (b as f32 * alpha + a as f32 * (1.0 - alpha)) as u8
}

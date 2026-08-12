use anyhow::{Context, Result};
use x11rb::connection::Connection;
use x11rb::connection::RequestConnection;
use x11rb::protocol::xproto::*;
use x11rb::rust_connection::RustConnection;

pub struct X11Lock {
    pub conn: RustConnection,
    screen: Screen,
    pub window: u32,
    pub width: u32,
    pub height: u32,
    grabbed: bool,
    root: u32,
}

impl X11Lock {
    pub fn new() -> Result<Self> {
        let (conn, screen_num) = x11rb::connect(None)
            .context("cannot open X11 display")?;

        let screen = conn.setup().roots[screen_num].clone();
        let w = screen.width_in_pixels as u32;
        let h = screen.height_in_pixels as u32;
        let root = screen.root;

        Ok(Self {
            conn,
            screen,
            window: 0,
            width: w,
            height: h,
            grabbed: false,
            root,
        })
    }

    pub fn create_window(&mut self) -> Result<()> {
        let wid = self.conn.generate_id()?;

        let attrs = CreateWindowAux::new()
            .override_redirect(1u32)
            .background_pixel(self.screen.black_pixel)
            .event_mask(
                EventMask::EXPOSURE
                    | EventMask::KEY_PRESS
                    | EventMask::KEY_RELEASE
                    | EventMask::VISIBILITY_CHANGE,
            );

        self.conn.create_window(
            self.screen.root_depth,
            wid,
            self.root,
            0,
            0,
            self.width as u16,
            self.height as u16,
            0,
            WindowClass::INPUT_OUTPUT,
            self.screen.root_visual,
            &attrs,
        )?;

        let configure = ConfigureWindowAux::new().stack_mode(StackMode::ABOVE);
        self.conn.map_window(wid)?;
        self.conn.configure_window(wid, &configure)?;

        self.window = wid;
        self.conn.flush()?;
        Ok(())
    }

    pub fn grab_inputs(&mut self) -> Result<()> {
        self.conn.flush()?;

        for _ in 0..10 {
            let kb = self.conn.grab_keyboard(
                true,
                self.window,
                x11rb::CURRENT_TIME,
                GrabMode::ASYNC,
                GrabMode::ASYNC,
            );

            if let Ok(reply) = kb?.reply() {
                if reply.status == GrabStatus::SUCCESS {
                    break;
                }
            }
        }

        let ptr = self.conn.grab_pointer(
            true,
            self.window,
            EventMask::BUTTON_PRESS | EventMask::BUTTON_RELEASE | EventMask::POINTER_MOTION,
            GrabMode::ASYNC,
            GrabMode::ASYNC,
            self.window,
            x11rb::NONE,
            x11rb::CURRENT_TIME,
        );

        if let Ok(reply) = ptr?.reply() {
            if reply.status != GrabStatus::SUCCESS {
                self.conn.ungrab_keyboard(x11rb::CURRENT_TIME)?;
                anyhow::bail!("pointer grab failed");
            }
        }

        self.conn.flush()?;
        self.grabbed = true;
        Ok(())
    }

    pub fn keycode_to_char(&self, keycode: u8, state: u16) -> Option<char> {
        let shifted = state & 1 != 0;
        let caps = state & 2 != 0;

        match keycode {
            24 => Some(shift(caps, shifted, 'q', 'Q')),
            25 => Some(shift(caps, shifted, 'w', 'W')),
            26 => Some(shift(caps, shifted, 'e', 'E')),
            27 => Some(shift(caps, shifted, 'r', 'R')),
            28 => Some(shift(caps, shifted, 't', 'T')),
            29 => Some(shift(caps, shifted, 'y', 'Y')),
            30 => Some(shift(caps, shifted, 'u', 'U')),
            31 => Some(shift(caps, shifted, 'i', 'I')),
            32 => Some(shift(caps, shifted, 'o', 'O')),
            33 => Some(shift(caps, shifted, 'p', 'P')),
            38 => Some(shift(caps, shifted, 'a', 'A')),
            39 => Some(shift(caps, shifted, 's', 'S')),
            40 => Some(shift(caps, shifted, 'd', 'D')),
            41 => Some(shift(caps, shifted, 'f', 'F')),
            42 => Some(shift(caps, shifted, 'g', 'G')),
            43 => Some(shift(caps, shifted, 'h', 'H')),
            44 => Some(shift(caps, shifted, 'j', 'J')),
            45 => Some(shift(caps, shifted, 'k', 'K')),
            46 => Some(shift(caps, shifted, 'l', 'L')),
            52 => Some(shift(caps, shifted, 'z', 'Z')),
            53 => Some(shift(caps, shifted, 'x', 'X')),
            54 => Some(shift(caps, shifted, 'c', 'C')),
            55 => Some(shift(caps, shifted, 'v', 'V')),
            56 => Some(shift(caps, shifted, 'b', 'B')),
            57 => Some(shift(caps, shifted, 'n', 'N')),
            58 => Some(shift(caps, shifted, 'm', 'M')),
            10 => Some(if shifted { '!' } else { '1' }),
            11 => Some(if shifted { '@' } else { '2' }),
            12 => Some(if shifted { '#' } else { '3' }),
            13 => Some(if shifted { '$' } else { '4' }),
            14 => Some(if shifted { '%' } else { '5' }),
            15 => Some(if shifted { '^' } else { '6' }),
            16 => Some(if shifted { '&' } else { '7' }),
            17 => Some(if shifted { '*' } else { '8' }),
            18 => Some(if shifted { '(' } else { '9' }),
            19 => Some(if shifted { ')' } else { '0' }),
            20 => Some(if shifted { '_' } else { '-' }),
            21 => Some(if shifted { '+' } else { '=' }),
            34 => Some(if shifted { '{' } else { '[' }),
            35 => Some(if shifted { '}' } else { ']' }),
            47 => Some(if shifted { ':' } else { ';' }),
            48 => Some(if shifted { '"' } else { '\'' }),
            49 => Some(if shifted { '~' } else { '`' }),
            51 => Some(if shifted { '|' } else { '\\' }),
            59 => Some(if shifted { '<' } else { ',' }),
            60 => Some(if shifted { '>' } else { '.' }),
            61 => Some(if shifted { '?' } else { '/' }),
            65 => Some(' '),
            _ => None,
        }
    }

    pub fn poll_event(&self) -> Result<Option<x11rb::protocol::Event>> {
        Ok(self.conn.poll_for_event()?)
    }

    pub fn flush(&self) -> Result<()> {
        Ok(self.conn.flush()?)
    }

    pub fn show_image(&self, data: &[u8]) -> Result<()> {
        let gc = self.conn.generate_id()?;
        self.conn.create_gc(gc, self.window, &CreateGCAux::new())?;

        let bytes_per_line = self.width * 4;
        let mut buf = Vec::with_capacity(data.len() / 3 * 4);
        for chunk in data.chunks_exact(3) {
            buf.extend_from_slice(&[chunk[2], chunk[1], chunk[0], 0]);
        }

        let max_req = self.conn.maximum_request_bytes() as usize;
        let row_max = (max_req.saturating_sub(64)) / bytes_per_line as usize;
        let row_max = row_max.max(1);

        for y in (0..self.height).step_by(row_max) {
            let rows = row_max.min(self.height as usize - y as usize) as u16;
            let start = (y * self.width * 4) as usize;
            let end = start + (rows as u32 * self.width * 4) as usize;
            let slice = &buf[start..end.min(buf.len())];

            self.conn.put_image(
                ImageFormat::Z_PIXMAP,
                self.window,
                gc,
                self.width as u16,
                rows,
                0,
                y as i16,
                0,
                self.screen.root_depth,
                slice,
            )?;
        }

        self.conn.free_gc(gc)?;
        self.conn.flush()?;
        Ok(())
    }

    pub fn ungrab_and_destroy(&mut self) -> Result<()> {
        if self.grabbed {
            let _ = self.conn.ungrab_keyboard(x11rb::CURRENT_TIME);
            let _ = self.conn.ungrab_pointer(x11rb::CURRENT_TIME);
            self.grabbed = false;
        }
        if self.window != 0 {
            self.conn.destroy_window(self.window)?;
            self.window = 0;
        }
        self.conn.flush()?;
        Ok(())
    }
}

impl Drop for X11Lock {
    fn drop(&mut self) {
        let _ = self.ungrab_and_destroy();
    }
}

fn shift(caps: bool, shifted: bool, lower: char, upper: char) -> char {
    if caps ^ shifted {
        upper
    } else {
        lower
    }
}

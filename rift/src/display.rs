use anyhow::{Context, Result};
use x11rb::connection::Connection;
use x11rb::protocol::xproto::*;
use x11rb::rust_connection::RustConnection;

pub struct Display {
    pub conn: RustConnection,
    screen: Screen,
    window: u32,
    pub width: u32,
    pub height: u32,
}

impl Display {
    pub fn new() -> Result<Self> {
        let (conn, screen_num) = x11rb::connect(None)
            .context("cannot open X11 display")?;
        let screen = conn.setup().roots[screen_num].clone();
        let w = screen.width_in_pixels as u32;
        let h = screen.height_in_pixels as u32;
        Ok(Self { conn, screen, window: 0, width: w, height: h })
    }

    pub fn create_window(&mut self, title: &str, w: u32, h: u32) -> Result<()> {
        let wid = self.conn.generate_id()?;
        let x = ((self.width - w) / 2) as i16;
        let y = ((self.height - h) / 2) as i16;

        self.conn.create_window(
            self.screen.root_depth, wid, self.screen.root,
            x, y, w as u16, h as u16, 0,
            WindowClass::INPUT_OUTPUT, self.screen.root_visual,
            &CreateWindowAux::new()
                .background_pixel(self.screen.black_pixel)
                .event_mask(EventMask::EXPOSURE | EventMask::KEY_PRESS
                    | EventMask::KEY_RELEASE | EventMask::STRUCTURE_NOTIFY
                    | EventMask::VISIBILITY_CHANGE),
        )?;

        // WM_NAME
        self.conn.change_property(
            PropMode::REPLACE, wid, AtomEnum::WM_NAME,
            AtomEnum::STRING, 8, title.len() as u32, title.as_bytes(),
        )?;

        // WM_CLASS
        let class = b"rift\0Rift";
        self.conn.change_property(
            PropMode::REPLACE, wid, AtomEnum::WM_CLASS,
            AtomEnum::STRING, 8, class.len() as u32, class,
        )?;

        // WM_PROTOCOLS
        let wm_proto = self.conn.intern_atom(false, b"WM_PROTOCOLS")?.reply()?.atom;
        let wm_del = self.conn.intern_atom(false, b"WM_DELETE_WINDOW")?.reply()?.atom;
        self.conn.change_property(
            PropMode::REPLACE, wid, wm_proto,
            AtomEnum::ATOM, 32, 1,
            &wm_del.to_ne_bytes(),
        )?;

        self.conn.map_window(wid)?;
        self.conn.flush()?;
        self.window = wid;
        Ok(())
    }

    pub fn show(&self, data: &[u8], w: u32, h: u32) -> Result<()> {
        let gc = self.conn.generate_id()?;
        self.conn.create_gc(gc, self.window, &CreateGCAux::new())?;
        self.conn.put_image(ImageFormat::Z_PIXMAP, self.window, gc,
            w as u16, h as u16, 0, 0, 0, self.screen.root_depth, data)?;
        self.conn.free_gc(gc)?;
        self.conn.flush()?;
        Ok(())
    }

    pub fn poll_event(&self) -> Result<Option<x11rb::protocol::Event>> {
        Ok(self.conn.poll_for_event()?)
    }

    pub fn destroy(&self) -> Result<()> {
        if self.window != 0 {
            self.conn.destroy_window(self.window)?;
            self.conn.flush()?;
        }
        Ok(())
    }
}

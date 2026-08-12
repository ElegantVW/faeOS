pub struct PasswordInput {
    buffer: String,
    caps_lock: bool,
    error_frames: u8,
    pub submitted: bool,
}

impl PasswordInput {
    pub fn new() -> Self {
        Self {
            buffer: String::new(),
            caps_lock: false,
            error_frames: 0,
            submitted: false,
        }
    }

    pub fn push_char(&mut self, c: char) {
        if self.buffer.len() < 128 {
            self.buffer.push(c);
        }
    }

    pub fn backspace(&mut self) {
        self.buffer.pop();
    }

    pub fn clear(&mut self) {
        self.buffer.clear();
        self.error_frames = 0;
    }

    pub fn submit(&mut self) -> String {
        self.submitted = true;
        self.buffer.clone()
    }

    pub fn reset_submitted(&mut self) {
        self.submitted = false;
    }

    pub fn set_error(&mut self) {
        self.error_frames = 20;
        self.buffer.clear();
    }

    pub fn tick_error(&mut self) {
        if self.error_frames > 0 {
            self.error_frames -= 1;
        }
    }

    pub fn has_error(&self) -> bool {
        self.error_frames > 0
    }

    pub fn error_glow(&self) -> bool {
        self.error_frames > 0 && (self.error_frames / 2) % 2 == 0
    }

    pub fn dots(&self) -> String {
        "●".repeat(self.buffer.len())
    }

    pub fn is_empty(&self) -> bool {
        self.buffer.is_empty()
    }

    pub fn set_caps_lock(&mut self, on: bool) {
        self.caps_lock = on;
    }

    pub fn caps_lock_on(&self) -> bool {
        self.caps_lock
    }
}

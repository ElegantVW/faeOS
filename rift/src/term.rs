pub const COLORS: [[u8; 3]; 16] = [
    [0x1a, 0x0a, 0x12], [0xff, 0x2d, 0x55], [0x3d, 0xd6, 0x8c], [0xff, 0xb0, 0x20],
    [0xc4, 0x4d, 0x7a], [0xe8, 0x79, 0xa0], [0x9d, 0x5c, 0x75], [0xd8, 0xa0, 0xc0],
    [0x5a, 0x3a, 0x48], [0xff, 0x6b, 0x8a], [0x6e, 0xec, 0xc0], [0xff, 0xd0, 0x78],
    [0xe8, 0x79, 0xa0], [0xf0, 0xb4, 0xc8], [0xc4, 0x4d, 0x7a], [0xff, 0xe3, 0xee],
];

#[derive(Clone, Copy, PartialEq, Default)]
pub enum Color {
    #[default]
    Default,
    Indexed(u8),
    True([u8; 3]),
}

impl Color {
    pub fn to_rgb(&self, default_fg: [u8; 3], _default_bg: [u8; 3]) -> [u8; 3] {
        match self {
            Color::Default => default_fg,
            Color::Indexed(i) if *i < 16 => COLORS[*i as usize],
            Color::Indexed(i) => {
                let i = *i as u32;
                if i < 232 {
                    let i = i - 16;
                    let r = (i / 36) as u8 * 51;
                    let g = ((i / 6) % 6) as u8 * 51;
                    let b = (i % 6) as u8 * 51;
                    [r, g, b]
                } else {
                    let v = ((i - 232) * 10 + 8) as u8;
                    [v, v, v]
                }
            }
            Color::True(rgb) => *rgb,
        }
    }
}

#[derive(Clone, Copy, Default)]
pub struct Attrs {
    pub fg: Color,
    pub bg: Color,
    pub bold: bool,
    pub italic: bool,
    pub underline: bool,
    pub reverse: bool,
}

#[derive(Clone)]
pub struct Cell {
    pub ch: char,
    pub attrs: Attrs,
}

impl Default for Cell {
    fn default() -> Self {
        Self { ch: ' ', attrs: Attrs::default() }
    }
}

pub struct Grid {
    pub cells: Vec<Vec<Cell>>,
    pub cols: usize,
    pub rows: usize,
    pub cursor_row: usize,
    pub cursor_col: usize,
    pub scroll_top: usize,
    pub scroll_bottom: usize,
    pub attrs: Attrs,
    pub cursor_visible: bool,
    saved_cursor: Option<(usize, usize, Attrs)>,
    alt_screen: Option<Vec<Vec<Cell>>>,
    main_cells: Option<Vec<Vec<Cell>>>,
    pub title: String,
}

impl Grid {
    pub fn new(cols: usize, rows: usize) -> Self {
        let cells = vec![vec![Cell::default(); cols]; rows];
        Self {
            cells,
            cols, rows,
            cursor_row: 0, cursor_col: 0,
            scroll_top: 0, scroll_bottom: rows.saturating_sub(1),
            attrs: Attrs::default(),
            cursor_visible: true,
            saved_cursor: None,
            alt_screen: None,
            main_cells: None,
            title: String::new(),
        }
    }

    pub fn resize(&mut self, cols: usize, rows: usize) {
        let mut new_cells = vec![vec![Cell::default(); cols]; rows];
        for r in 0..self.rows.min(rows) {
            for c in 0..self.cols.min(cols) {
                new_cells[r][c] = self.cells[r][c].clone();
            }
        }
        self.cells = new_cells;
        self.cols = cols;
        self.rows = rows;
        self.cursor_row = self.cursor_row.min(rows.saturating_sub(1));
        self.cursor_col = self.cursor_col.min(cols.saturating_sub(1));
        self.scroll_bottom = rows.saturating_sub(1);
    }

    fn scroll_up(&mut self) {
        let top = self.scroll_top;
        let bot = self.scroll_bottom;
        for r in top..bot {
            self.cells[r] = self.cells[r + 1].clone();
        }
        self.cells[bot] = vec![Cell::default(); self.cols];
    }

    fn scroll_down(&mut self) {
        let top = self.scroll_top;
        let bot = self.scroll_bottom;
        for r in (top + 1..=bot).rev() {
            self.cells[r] = self.cells[r - 1].clone();
        }
        self.cells[top] = vec![Cell::default(); self.cols];
    }

    fn advance_cursor(&mut self) {
        self.cursor_col += 1;
        if self.cursor_col >= self.cols {
            self.cursor_col = 0;
            if self.cursor_row == self.scroll_bottom {
                self.scroll_up();
            } else {
                self.cursor_row += 1;
            }
        }
    }

    pub fn put_char(&mut self, ch: char) {
        match ch {
            '\r' => self.cursor_col = 0,
            '\n' => {
                if self.cursor_row == self.scroll_bottom {
                    self.scroll_up();
                } else {
                    self.cursor_row += 1;
                }
            }
            '\t' => {
                let next = ((self.cursor_col / 8) + 1) * 8;
                self.cursor_col = next.min(self.cols.saturating_sub(1));
            }
            '\x08' => {
                if self.cursor_col > 0 {
                    self.cursor_col -= 1;
                }
            }
            _ => {
                let mut attrs = self.attrs;
                if attrs.reverse {
                    std::mem::swap(&mut attrs.fg, &mut attrs.bg);
                }
                let r = self.cursor_row;
                let c = self.cursor_col;
                if r < self.rows && c < self.cols {
                    self.cells[r][c] = Cell { ch, attrs };
                }
                self.advance_cursor();
            }
        }
    }

    fn erase_display(&mut self, n: u32) {
        match n {
            0 => {
                for r in self.cursor_row..self.rows {
                    let start = if r == self.cursor_row { self.cursor_col } else { 0 };
                    for c in start..self.cols {
                        self.cells[r][c] = Cell::default();
                    }
                }
            }
            1 => {
                for r in 0..=self.cursor_row {
                    let end = if r == self.cursor_row { self.cursor_col } else { self.cols };
                    for c in 0..end {
                        self.cells[r][c] = Cell::default();
                    }
                }
            }
            _ => {
                for r in 0..self.rows {
                    for c in 0..self.cols {
                        self.cells[r][c] = Cell::default();
                    }
                }
            }
        }
    }

    fn erase_line(&mut self, n: u32) {
        let r = self.cursor_row;
        match n {
            0 => {
                for c in self.cursor_col..self.cols {
                    self.cells[r][c] = Cell::default();
                }
            }
            1 => {
                for c in 0..=self.cursor_col {
                    self.cells[r][c] = Cell::default();
                }
            }
            _ => {
                for c in 0..self.cols {
                    self.cells[r][c] = Cell::default();
                }
            }
        }
    }

    fn set_attr(&mut self, n: u32) {
        match n {
            0 => self.attrs = Attrs::default(),
            1 => self.attrs.bold = true,
            3 => self.attrs.italic = true,
            4 => self.attrs.underline = true,
            7 => self.attrs.reverse = true,
            22 => self.attrs.bold = false,
            23 => self.attrs.italic = false,
            24 => self.attrs.underline = false,
            27 => self.attrs.reverse = false,
            30 => self.attrs.fg = Color::Indexed(0),
            31 => self.attrs.fg = Color::Indexed(1),
            32 => self.attrs.fg = Color::Indexed(2),
            33 => self.attrs.fg = Color::Indexed(3),
            34 => self.attrs.fg = Color::Indexed(4),
            35 => self.attrs.fg = Color::Indexed(5),
            36 => self.attrs.fg = Color::Indexed(6),
            37 => self.attrs.fg = Color::Indexed(7),
            39 => self.attrs.fg = Color::Default,
            40 => self.attrs.bg = Color::Indexed(0),
            41 => self.attrs.bg = Color::Indexed(1),
            42 => self.attrs.bg = Color::Indexed(2),
            43 => self.attrs.bg = Color::Indexed(3),
            44 => self.attrs.bg = Color::Indexed(4),
            45 => self.attrs.bg = Color::Indexed(5),
            46 => self.attrs.bg = Color::Indexed(6),
            47 => self.attrs.bg = Color::Indexed(7),
            49 => self.attrs.bg = Color::Default,
            90 => self.attrs.fg = Color::Indexed(8),
            91 => self.attrs.fg = Color::Indexed(9),
            92 => self.attrs.fg = Color::Indexed(10),
            93 => self.attrs.fg = Color::Indexed(11),
            94 => self.attrs.fg = Color::Indexed(12),
            95 => self.attrs.fg = Color::Indexed(13),
            96 => self.attrs.fg = Color::Indexed(14),
            97 => self.attrs.fg = Color::Indexed(15),
            100 => self.attrs.bg = Color::Indexed(8),
            101 => self.attrs.bg = Color::Indexed(9),
            102 => self.attrs.bg = Color::Indexed(10),
            103 => self.attrs.bg = Color::Indexed(11),
            104 => self.attrs.bg = Color::Indexed(12),
            105 => self.attrs.bg = Color::Indexed(13),
            106 => self.attrs.bg = Color::Indexed(14),
            107 => self.attrs.bg = Color::Indexed(15),
            _ => {}
        }
    }

    fn csi_control(&mut self, cmd: char, args: &[u32]) {
        let a0 = args.first().copied().unwrap_or(1);
        let a1 = args.get(1).copied().unwrap_or(1);

        match cmd {
            'A' => self.cursor_row = self.cursor_row.saturating_sub(a0 as usize),
            'B' => self.cursor_row = (self.cursor_row + a0 as usize).min(self.rows.saturating_sub(1)),
            'C' => self.cursor_col = (self.cursor_col + a0 as usize).min(self.cols.saturating_sub(1)),
            'D' => self.cursor_col = self.cursor_col.saturating_sub(a0 as usize),
            'E' => {
                self.cursor_col = 0;
                self.cursor_row = (self.cursor_row + a0 as usize).min(self.rows.saturating_sub(1));
            }
            'F' => {
                self.cursor_col = 0;
                self.cursor_row = self.cursor_row.saturating_sub(a0 as usize);
            }
            'G' => self.cursor_col = (a0 as usize).saturating_sub(1).min(self.cols.saturating_sub(1)),
            'H' | 'f' => {
                self.cursor_row = (a0 as usize).saturating_sub(1).min(self.rows.saturating_sub(1));
                self.cursor_col = (a1 as usize).saturating_sub(1).min(self.cols.saturating_sub(1));
            }
            'J' => self.erase_display(a0),
            'K' => self.erase_line(a0),
            'L' => {
                for _ in 0..a0 {
                    self.scroll_down();
                }
            }
            'M' => {
                for _ in 0..a0 {
                    self.scroll_up();
                }
            }
            'P' => {
                for c in self.cursor_col..self.cols.saturating_sub(a0 as usize) {
                    self.cells[self.cursor_row][c] = self.cells[self.cursor_row][c + a0 as usize].clone();
                }
                for c in self.cols.saturating_sub(a0 as usize)..self.cols {
                    self.cells[self.cursor_row][c] = Cell::default();
                }
            }
            'S' => {
                for _ in 0..a0 {
                    self.scroll_up();
                }
            }
            'T' => {
                for _ in 0..a0 {
                    self.scroll_down();
                }
            }
            'd' => {
                self.cursor_row = (a0 as usize).saturating_sub(1).min(self.rows.saturating_sub(1));
            }
            'm' => {
                if args.is_empty() {
                    self.attrs = Attrs::default();
                } else {
                    for &a in args {
                        self.set_attr(a);
                    }
                }
            }
            'r' => {
                self.scroll_top = (a0 as usize).saturating_sub(1);
                self.scroll_bottom = if a1 > 0 {
                    (a1 as usize).saturating_sub(1)
                } else {
                    self.rows.saturating_sub(1)
                };
                self.cursor_row = 0;
                self.cursor_col = 0;
            }
            's' => {
                self.saved_cursor = Some((self.cursor_row, self.cursor_col, self.attrs));
            }
            'u' => {
                if let Some((r, c, a)) = self.saved_cursor {
                    self.cursor_row = r;
                    self.cursor_col = c;
                    self.attrs = a;
                }
            }
            _ => {}
        }
    }

    fn csi_ext(&mut self, cmd: char, args: &[u32], _rest: &[u8]) {
        match (cmd, args.first().copied()) {
            ('h', Some(25)) => self.cursor_visible = true,
            ('l', Some(25)) => self.cursor_visible = false,
            ('h', Some(1049)) => self.alt_enter(),
            ('l', Some(1049)) => self.alt_leave(),
            _ => {}
        }
        if cmd == ';' || cmd == ':' {
            // Sub-parameter separator — handled in 256/TrueColor below
        }
    }

    fn alt_enter(&mut self) {
        if self.alt_screen.is_some() {
            return;
        }
        let current = std::mem::replace(
            &mut self.cells,
            vec![vec![Cell::default(); self.cols]; self.rows],
        );
        self.main_cells = Some(current);
        self.cursor_row = 0;
        self.cursor_col = 0;
        self.alt_screen = Some(self.cells.clone());
    }

    fn alt_leave(&mut self) {
        if let Some(main) = self.main_cells.take() {
            self.cells = main;
        }
        self.alt_screen = None;
        self.cursor_row = 0;
        self.cursor_col = 0;
    }

    // Process a byte slice — handles escape sequences inline
    pub fn write(&mut self, data: &[u8]) {
        let mut i = 0;
        while i < data.len() {
            let b = data[i];
            match b {
                0x1b => {
                    i += 1;
                    if i >= data.len() { break; }
                    match data[i] {
                        b'[' => {
                            i = self.parse_csi(data, i + 1);
                        }
                        b']' => {
                            i = self.parse_osc(data, i + 1);
                        }
                        b'(' | b')' => {
                            i += 2; // skip charset designation
                        }
                        b'7' => {
                            self.saved_cursor = Some((self.cursor_row, self.cursor_col, self.attrs));
                            i += 1;
                        }
                        b'8' => {
                            if let Some((r, c, a)) = self.saved_cursor {
                                self.cursor_row = r;
                                self.cursor_col = c;
                                self.attrs = a;
                            }
                            i += 1;
                        }
                        _ => {
                            i += 1;
                        }
                    }
                }
                _ => {
                    self.put_char(b as char);
                    i += 1;
                }
            }
        }
    }

    fn parse_csi(&mut self, data: &[u8], start: usize) -> usize {
        let mut i = start;
        let mut args: Vec<u32> = Vec::new();
        let mut num = 0u32;
        let mut has_num = false;

        while i < data.len() {
            let b = data[i];
            match b {
                b'0'..=b'9' => {
                    num = num * 10 + (b - b'0') as u32;
                    has_num = true;
                    i += 1;
                }
                b';' => {
                    args.push(if has_num { num } else { 0 });
                    num = 0;
                    has_num = false;
                    i += 1;
                }
                b'?' => {
                    i += 1;
                }
                b' ' => {
                    i += 1;
                    if i < data.len() && data[i] == b'q' {
                        i += 1;
                        if args.len() >= 2 {
                            let n = args[0];
                            if n == 38 && args.len() >= 3 {
                                let code = args[1];
                                if code == 5 && args.len() >= 3 {
                                    self.attrs.fg = Color::Indexed(args[2] as u8);
                                } else if code == 2 && args.len() >= 5 {
                                    self.attrs.fg = Color::True([args[2] as u8, args[3] as u8, args[4] as u8]);
                                }
                            } else if n == 48 && args.len() >= 3 {
                                let code = args[1];
                                if code == 5 && args.len() >= 3 {
                                    self.attrs.bg = Color::Indexed(args[2] as u8);
                                } else if code == 2 && args.len() >= 5 {
                                    self.attrs.bg = Color::True([args[2] as u8, args[3] as u8, args[4] as u8]);
                                }
                            }
                        }
                        return i;
                    }
                    return i + 1;
                }
                _ => {
                    if has_num {
                        args.push(num);
                    }
                    // Check for extended CSI with semicolons in args
                    // Handle 38;5;N and 38;2;R;G;B
                    if i + 1 < data.len() && b';' == data[i + 1] && (num == 38 || num == 48) {
                        // This is a sub-CSI — we need to read more args
                        // The full sequence is: ESC[38;5;Nm or ESC[38;2;R;G;Bm
                        let code = num;
                        i += 1;
                        let mut ext_args = vec![code];
                        let mut en = 0u32;
                        let mut ehas = false;
                        i += 1;
                        while i < data.len() {
                            let eb = data[i];
                            match eb {
                                b'0'..=b'9' => {
                                    en = en * 10 + (eb - b'0') as u32;
                                    ehas = true;
                                    i += 1;
                                }
                                b';' => {
                                    ext_args.push(if ehas { en } else { 0 });
                                    en = 0;
                                    ehas = false;
                                    i += 1;
                                }
                                b'm' => {
                                    if ehas { ext_args.push(en); }
                                    if code == 38 && ext_args.len() >= 2 {
                                        match ext_args[1] {
                                            5 if ext_args.len() >= 3 => {
                                                self.attrs.fg = Color::Indexed(ext_args[2] as u8);
                                            }
                                            2 if ext_args.len() >= 5 => {
                                                self.attrs.fg = Color::True([
                                                    ext_args[2] as u8, ext_args[3] as u8, ext_args[4] as u8
                                                ]);
                                            }
                                            _ => {}
                                        }
                                    } else if code == 48 && ext_args.len() >= 2 {
                                        match ext_args[1] {
                                            5 if ext_args.len() >= 3 => {
                                                self.attrs.bg = Color::Indexed(ext_args[2] as u8);
                                            }
                                            2 if ext_args.len() >= 5 => {
                                                self.attrs.bg = Color::True([
                                                    ext_args[2] as u8, ext_args[3] as u8, ext_args[4] as u8
                                                ]);
                                            }
                                            _ => {}
                                        }
                                    }
                                    return i + 1;
                                }
                                _ => {
                                    if ehas { ext_args.push(en); }
                                    self.csi_ext(eb as char, &ext_args, &[]);
                                    return i + 1;
                                }
                            }
                        }
                        return i;
                    }
                    self.csi_control(b as char, &args);
                    return i + 1;
                }
            }
        }
        i
    }

    fn parse_osc(&mut self, data: &[u8], start: usize) -> usize {
        let mut i = start;
        while i < data.len() {
            if data[i] == 0x07 || (i + 1 < data.len() && data[i] == 0x1b && data[i + 1] == b'\\') {
                return if data[i] == 0x07 { i + 1 } else { i + 2 };
            }
            i += 1;
        }
        i
    }
}

pub fn key_to_input(keycode: u8, state: u16) -> Vec<u8> {
    let ctrl = state & 4 != 0;
    match keycode {
        36 | 104 => b"\r".to_vec(),
        22 => b"\x7f".to_vec(),
        23 => b"\t".to_vec(),
        9 => b"\x1b".to_vec(),
        111 => b"\x1b[A".to_vec(),
        116 => b"\x1b[B".to_vec(),
        113 => b"\x1b[C".to_vec(),
        114 => b"\x1b[D".to_vec(),
        110 => b"\x1b[H".to_vec(),
        115 => b"\x1b[F".to_vec(),
        112 => b"\x1b[5~".to_vec(),
        117 => b"\x1b[6~".to_vec(),
        119 => b"\x1b[3~".to_vec(),
        67 => b"\x1bOP".to_vec(),
        68 => b"\x1bOQ".to_vec(),
        69 => b"\x1bOR".to_vec(),
        70 => b"\x1bOS".to_vec(),
        _ => {
            let shifted = state & 1 != 0;
            let caps = state & 2 != 0;
            let upper = caps ^ shifted;
            let c = match keycode {
                24..=33 => {
                    let base = if upper { b'Q' } else { b'q' };
                    (base + (keycode - 24)) as char
                }
                38..=46 => {
                    let base = if upper { b'A' } else { b'a' };
                    (base + (keycode - 38)) as char
                }
                52..=58 => {
                    let base = if upper { b'Z' } else { b'z' };
                    (base + (keycode - 52)) as char
                }
                10 => if shifted { '!' } else { '1' },
                11 => if shifted { '@' } else { '2' },
                12 => if shifted { '#' } else { '3' },
                13 => if shifted { '$' } else { '4' },
                14 => if shifted { '%' } else { '5' },
                15 => if shifted { '^' } else { '6' },
                16 => if shifted { '&' } else { '7' },
                17 => if shifted { '*' } else { '8' },
                18 => if shifted { '(' } else { '9' },
                19 => if shifted { ')' } else { '0' },
                20 => if shifted { '_' } else { '-' },
                21 => if shifted { '+' } else { '=' },
                34 => if shifted { '{' } else { '[' },
                35 => if shifted { '}' } else { ']' },
                47 => if shifted { ':' } else { ';' },
                48 => if shifted { '"' } else { '\'' },
                49 => if shifted { '~' } else { '`' },
                51 => if shifted { '|' } else { '\\' },
                59 => if shifted { '<' } else { ',' },
                60 => if shifted { '>' } else { '.' },
                61 => if shifted { '?' } else { '/' },
                65 => ' ',
                _ => return vec![],
            };
            if ctrl && c.is_ascii_alphabetic() {
                vec![(c as u8) & 0x1f]
            } else {
                c.to_string().into_bytes()
            }
        }
    }
}

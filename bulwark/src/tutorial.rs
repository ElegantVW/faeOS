//! First-time tour — optional, themed, short pages.

use crate::words;
use anyhow::Result;

const DIM: &str = "\x1b[38;5;245m";
const RESET: &str = "\x1b[0m";

const PAGES: &[&[&str]] = &[
    &[
        "Hi! I'm Bulwark.",
        "I help keep this computer safe.",
        "My tools have magic names — easy to learn.",
        "",
        "enter  next page",
        "s      skip the tour",
        "q      leave Bulwark",
    ],
    &[
        "Aegis — front-door lock",
        "",
        "Aegis decides who can knock on the network.",
        "When the lock is ON, strangers stay outside.",
        "You can turn it OFF later if you need to.",
    ],
    &[
        "Purity — photo of important files",
        "",
        "Purity takes a photo of important files.",
        "Later we compare: did anything change?",
        "That catches sneaky changes to your tools.",
    ],
    &[
        "Ward & Sentinel",
        "",
        "Ward searches for sneaky stuff",
        "  (open folders, secret add-ons, odd timers).",
        "Sentinel watches open network windows",
        "  (what is listening right now).",
    ],
    &[
        "The home screen",
        "",
        "You will see SAFE, CARE, or DANGER.",
        "Then a list of numbers — just type one.",
        "  1 Purity photo · 2 Ward search · 3 windows",
        "  4 lock ON · 5 lock OFF · 7 this tour again",
    ],
    &[
        "Grown-up password",
        "",
        "Turning Aegis ON may ask for a password.",
        "That is normal — a grown-up can type it.",
        "If something goes wrong, Aegis can undo.",
    ],
    &[
        "Your first quest",
        "",
        "When the tour ends, press 1 on the home screen.",
        "That takes a Purity photo of important files.",
        "",
        "Ready? enter finishes the tour.",
    ],
];

/// Run the tour. Returns true if the user finished or skipped (marker written).
/// Returns false if they quit the whole app (q).
pub fn run_tour(term: &mut crate::tui::Term) -> Result<bool> {
    let mut page = 0usize;
    loop {
        let lines = PAGES[page];
        let title = format!(" Bulwark ✦ tour {}/{} ", page + 1, PAGES.len());
        let mut body: Vec<String> = lines.iter().map(|s| (*s).to_string()).collect();
        body.push(String::new());
        body.push(format!(
            "{}enter next · s skip · q leave{}",
            DIM, RESET
        ));
        let frame = crate::tui::render_simple(&title, &body, &["tour · learn the names"]);
        term.draw(&frame)?;
        match term.read_key()? {
            crate::tui::Key::Char('q') | crate::tui::Key::Esc | crate::tui::Key::Ctrl('c') => {
                return Ok(false);
            }
            crate::tui::Key::Char('s') | crate::tui::Key::Char('S') => {
                words::mark_tutorial_done();
                return Ok(true);
            }
            crate::tui::Key::Char('\n')
            | crate::tui::Key::Char('\r')
            | crate::tui::Key::Enter => {
                if page + 1 >= PAGES.len() {
                    words::mark_tutorial_done();
                    return Ok(true);
                }
                page += 1;
            }
            crate::tui::Key::Char('n') | crate::tui::Key::Char(' ') => {
                if page + 1 >= PAGES.len() {
                    words::mark_tutorial_done();
                    return Ok(true);
                }
                page += 1;
            }
            crate::tui::Key::Char('b') | crate::tui::Key::Char('p') => {
                page = page.saturating_sub(1);
            }
            _ => {}
        }
    }
}


#!/usr/bin/env python3
"""Scroll encyclopedia — dossiers for every faeOS app.

Authoring: fae voice, concise, keyboard bindings in `how`, runes run on activate.
New shipped app ⇒ add an AppPage here before calling it done.

If you sought a dragon, you are reading the wrong scroll.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Rune:
    """Footer chip. `insert` is argv string to run (shlex); empty = special."""

    label: str
    insert: str  # command line to run, or "" for back
    kind: str = "run"  # run | back


@dataclass(frozen=True)
class AppPage:
    id: str
    name: str
    domain: str  # index group
    tagline: str
    intro: list[str]
    how: list[str]
    cli: list[tuple[str, str]]
    runes: list[Rune] = field(default_factory=list)


def R(label: str, cmd: str) -> Rune:
    return Rune(label=label, insert=cmd, kind="run")


def B() -> Rune:
    return Rune(label="back", insert="", kind="back")


# Domain order for index
DOMAINS = (
    "Discover",
    "Mind",
    "Media",
    "Net",
    "House",
    "Ward",
    "Play",
    "System",
)

PAGES: list[AppPage] = [
    # ── Discover ───────────────────────────────────────────────────────
    AppPage(
        id="scroll",
        name="Scroll",
        domain="Discover",
        tagline="The living book of faeOS — one page per familiar, Tab turns the leaves.",
        intro=[
            "✦ Scroll ✦ is how the house teaches itself. Each page is one creature:",
            "who she is, how to live with her (keys included), which spells to type,",
            "and runes that cast her. The last leaf is PATH — every tool on $PATH,",
            "printed to your prompt so you may finish the line yourself.",
        ],
        how=[
            "Tab / Shift-Tab — next / previous page (the lesson path).",
            "j/k or wheel — scroll long pages · 1–9 — cast footer runes · q — close the book.",
            "m or Ctrl-p — play/pause book ambience (own mpv; leaves Siren alone).",
            "Page jump (vim-style): g then 1–9 or 0 → pages 11–20; G then digit → 21–30.",
            "Digits alone always mean runes on this page, not page numbers.",
            "summon / scroll --path open the final PATH leaf directly.",
        ],
        cli=[
            ("scroll", "Open the book on page one"),
            ("scroll --path", "Open the PATH leaf (same as summon)"),
            ("scroll list", "Print every page as text (for grepping)"),
            ("summon", "PATH leaf short name"),
            ("summon -x <cmd>", "Run a PATH match without the TUI"),
        ],
        runes=[R("path leaf", "scroll --path"), R("list text", "scroll list"), B()],
    ),
    AppPage(
        id="summon",
        name="Summon",
        domain="Discover",
        tagline="The PATH door — Summon is Scroll wearing a shorter cloak.",
        intro=[
            "✦ Summon ✦ does not keep her own library anymore. She opens Scroll",
            "straight on the PATH tab: type a few letters, cast any tool the",
            "system knows. Fae creatures still live under Scroll's other pages.",
        ],
        how=[
            "`summon` → PATH leaf · type to filter · Enter prints the name on your prompt.",
            "`summon -x true` runs without a TUI. Creatures live earlier in Scroll (Tab).",
            "Want Siren or Pixie lore? Tab through the book; PATH is always last.",
        ],
        cli=[
            ("summon", "PATH launcher TUI"),
            ("summon <filter>", "PATH TUI pre-filtered"),
            ("summon -x <cmd> [args…]", "Exec first match (no TUI)"),
            ("summon --list", "Dump every PATH name"),
            ("summon --refresh", "Rescan $PATH cache (~6h TTL)"),
        ],
        runes=[R("open PATH", "summon"), R("refresh", "summon --refresh"), B()],
    ),
    # ── Mind ───────────────────────────────────────────────────────────
    AppPage(
        id="pixie",
        name="Pixie",
        domain="Mind",
        tagline="Local agent — tools, files, and pink chat without the cloud.",
        intro=[
            "✦ Pixie ✦ is your household familiar. She thinks on a local model",
            "(via Menagerie), can touch files and tools, and answers in the",
            "same crystal frames as the rest of the house. Offline by default.",
        ],
        how=[
            'pixie "what is eating my disk?" — ask in quotes.',
            "She may call tools; `-v` shows the wires. Models wake through Menagerie.",
            "If she is silent, try: menagerie ensure pixie",
        ],
        cli=[
            ('pixie "…"', "Chat / agent turn"),
            ("pixie -v \"…\"", "Same, show tool calls"),
            ("ask \"…\"", "Sibling entry to the same engine"),
            ("menagerie ensure pixie", "Wake her model if sleeping"),
        ],
        runes=[R("open", "pixie"), R("ensure model", "menagerie ensure pixie"), B()],
    ),
    AppPage(
        id="menagerie",
        name="Menagerie",
        domain="Mind",
        tagline="AI control center — which model each familiar wears, and RAM.",
        intro=[
            "✦ Menagerie ✦ keeps the living models in their pens. Pixie, Imp,",
            "and friends each get a port and a budget so the house does not",
            "drown in GGUFs. This is the switchboard, not the chat itself.",
        ],
        how=[
            "`menagerie` opens the TUI: apps, models, budget.",
            "ensure <app> wakes a pen · set <app> <model> rebinds · status all surveys.",
            "Keys follow the pink list pattern: ↑↓ · Enter · q.",
        ],
        cli=[
            ("menagerie", "Control-center TUI"),
            ("menagerie status all", "Table: app · model · port · status"),
            ("menagerie ensure <app>", "Start that app's llama-server"),
            ("menagerie set <app> <model>", "Rebind model id"),
            ("menagerie models", "Registered GGUFs"),
            ("menagerie budget", "RAM budget for loaded models"),
        ],
        runes=[R("open", "menagerie"), R("status", "menagerie status all"), B()],
    ),
    AppPage(
        id="imp",
        name="Imp",
        domain="Mind",
        tagline="Terminal art spirit — wish aloud, receive a crystal of ANSI.",
        intro=[
            "✦ Imp ✦ paints for the prompt. Speak a wish; a local coder-model",
            "fills a fixed grid; a grumpy haiku cousin may snark in the margin.",
            "Pieces land in ~/pixie_art. Oh — and he only trusts loopback LLMs.",
        ],
        how=[
            "`imp` — TUI · type a wish · Enter conjures.",
            "Keys: a animate frames · r refine · s save · g gallery · Tab style · q quit.",
            'One-shot: imp "a moonlit mushroom"  ·  human voice: imp paint "…"',
        ],
        cli=[
            ("imp", "Art TUI"),
            ('imp "wish"', "One-shot conjure + gallery save"),
            ("imp --gallery", "List saved pieces"),
            ("imp --demo", "Sample frame without a model"),
            ("imp --style ascii|unicode|…", "Pick a palette mode"),
        ],
        runes=[R("open", "imp"), R("demo", "imp --demo"), R("gallery", "imp --gallery"), B()],
    ),
    # ── Media ──────────────────────────────────────────────────────────
    AppPage(
        id="siren",
        name="Siren",
        domain="Media",
        tagline="The music vessel — offline library, queue, waves, free trove.",
        intro=[
            "✦ Siren ✦ is faeOS's media player. She sails ~/Music, speaks to mpv",
            "through a socket, and shows browser · queue · waves in crystal panes.",
            "Oh! She also keeps a lot of free stuff in her trove — try",
            "`siren trove` when the shelves feel empty.",
        ],
        how=[
            "`siren` — full TUI. Mouse: click select · double-click play · wheel.",
            "Keys: j/k browse · Enter/o play · Tab focus · a add · / filter · w EQ · q quit.",
            "f/F open Spellbook to pick a file or whole folder of audio.",
            "CLI happy path: siren play lofi",
        ],
        cli=[
            ("siren", "Interactive player TUI"),
            ("siren play <query>", "Fuzzy-play from the library"),
            ("siren random", "Shuffle everything"),
            ("siren pause | next | prev | now", "Transport / status"),
            ("siren queue list", "Show the queue"),
            ("siren playlist load <name>", "Load a saved list"),
            ("siren trove 10 music lofi", "Browse free Internet Archive audio"),
            ("siren config set <key> <val>", "volume · mouse · gapless · …"),
        ],
        runes=[
            R("open TUI", "siren"),
            R("random", "siren random"),
            R("now", "siren now"),
            R("trove", "siren trove 10 music"),
            B(),
        ],
    ),
    # ── Net ────────────────────────────────────────────────────────────
    AppPage(
        id="ether",
        name="Ether",
        domain="Net",
        tagline="Network weaves — bluetooth, wifi, lan, veil, bridge.",
        intro=[
            "✦ Ether ✦ tends the invisible roads. Live TUI for bt · wifi · lan,",
            "a VPN veil when you want privacy, and a phone-hotspot bridge when",
            "the house wifi sulks. Whisper and listen tune your speakers.",
        ],
        how=[
            "`ether` — live TUI (w/l weave · s scan · n new · d remove · R restart · q).",
            "`ether status` one-shot report · `ether veil on|off` for the VPN.",
            "Headphones: whisper ether · speaker: listen ether.",
        ],
        cli=[
            ("ether", "Live network TUI"),
            ("ether status", "bt · wifi · lan snapshot"),
            ("ether net", "Reachability check"),
            ("ether veil on|off", "VPN up/down"),
            ("ether bridge", "Phone hotspot fallback"),
            ("whisper ether", "ANC headphones default sink"),
            ("listen ether", "JBL Go default sink"),
        ],
        runes=[R("open", "ether"), R("status", "ether status"), R("veil on", "ether veil on"), B()],
    ),
    AppPage(
        id="goblin",
        name="Goblin",
        domain="Net",
        tagline="Mail spirit — aerc IMAP into local text the house can read.",
        intro=[
            "✦ Goblin ✦ steals letters from the sky (IMAP) and stacks them as",
            "plain text under his nest. Sync for new mail, list to peek, bundle",
            "when Pixie should summarize the unread pile.",
        ],
        how=[
            "`goblin` — mail TUI · `goblin sync` — pull UNSEEN to unread/*.txt.",
            "Keys follow list TUIs (j/k · Enter · q). IDLE watcher can squeak on new mail.",
        ],
        cli=[
            ("goblin", "Mail TUI"),
            ("goblin sync", "Download unseen mail"),
            ("goblin list", "List local mail files"),
            ("goblin bundle", "Unread digest for summarization"),
            ("goblin show <file>", "Print one message"),
        ],
        runes=[R("open", "goblin"), R("sync", "goblin sync"), R("list", "goblin list"), B()],
    ),
    AppPage(
        id="magpie",
        name="Magpie",
        domain="Net",
        tagline="Private search — shiny links without feeding the big birds.",
        intro=[
            "✦ Magpie ✦ hops the open web for you (DuckDuckGo / friends), never",
            "Google-as-a-product. She can deepen pages and ask a local model for",
            "a summary when you pass `-a`. `duck` is her old nickname.",
        ],
        how=[
            "magpie something interesting — search.",
            "magpie -a query — fetch top pages + one local AI summary.",
            "--tor if you have Tor; --deep N to pull more bodies.",
        ],
        cli=[
            ("magpie <query>", "Privacy search"),
            ("magpie -a <query>", "Deep + local AI summary"),
            ("magpie --deep 3 <query>", "Fetch more page bodies"),
            ("magpie --tor <query>", "Via Tor when available"),
            ("duck <query>", "Alias → magpie"),
        ],
        runes=[R("search help", "magpie --help"), B()],
    ),
    # ── House ──────────────────────────────────────────────────────────
    AppPage(
        id="spellbook",
        name="Spellbook",
        domain="House",
        tagline="File manager — shelves, scrolls, and a clickable parent stair.",
        intro=[
            "✦ Spellbook ✦ is the house library. Browse directories in pink frames,",
            "open files, rename, delete carefully. Other apps call her with",
            "--pick when they need you to choose a path (Siren loves this).",
        ],
        how=[
            "`spellbook` or `spellbook ~` · j/k or wheel · Enter/l open · h or click ↑ parent.",
            "Mouse: click select · double-click open · ? help · q quit.",
            "Pick mode: spellbook --pick --output /tmp/out (used by friends).",
        ],
        cli=[
            ("spellbook", "File manager TUI"),
            ("spellbook <path>", "Open a shelf"),
            ("spellbook --pick", "Return a chosen path on stdout"),
        ],
        runes=[R("open", "spellbook"), R("home", "spellbook ~"), B()],
    ),
    AppPage(
        id="tome",
        name="Tome",
        domain="House",
        tagline="Document reader — open a page of markdown or text.",
        intro=[
            "✦ Tome ✦ reads. Point her at a file or a directory of readable",
            "scrolls; she frames them for the terminal. Plans under",
            "~/faeos/docs/plans are excellent late-night material.",
        ],
        how=[
            "tome ~/faeos/faeOSplan.md — read the plan.",
            "tome  alone browses readable files nearby. Keys: scroll · q leave.",
        ],
        cli=[
            ("tome <file>", "Read a document"),
            ("tome", "Browse readable files here"),
            ("tome ~/faeos/docs/plans", "All app plans"),
        ],
        runes=[R("plan", "tome ~/faeos/faeOSplan.md"), R("plans dir", "tome ~/faeos/docs/plans"), B()],
    ),
    AppPage(
        id="grimoire",
        name="Grimoire",
        domain="House",
        tagline="Markdown notes — pages under ~/notes.",
        intro=[
            "✦ Grimoire ✦ binds your own spells as markdown. New pages open in",
            "your editor; the TUI helps you wander the shelf of notes.",
        ],
        how=[
            "`grimoire` — notes TUI · `grimoire new my idea` — create + edit.",
            "Keep secrets out of the grimoire if the disk is not your confidant.",
        ],
        cli=[
            ("grimoire", "Notes TUI"),
            ("grimoire new <title>", "Create a note and open the editor"),
        ],
        runes=[R("open", "grimoire"), B()],
    ),
    AppPage(
        id="scry",
        name="Scry",
        domain="House",
        tagline="Visions of what you already typed — command and output history.",
        intro=[
            "✦ Scry ✦ keeps the after-images of your shell: commands and their",
            "answers. Shift-Tab often summons her. Useful when a spell worked",
            "once and the wording has fled your mind.",
        ],
        how=[
            "`scry` — interactive visions (needs a real TTY).",
            "Shift-Tab in the fae shell may open her without typing.",
            "↑↓ browse · Enter expand/use · q leave.",
        ],
        cli=[
            ("scry", "History TUI"),
            ("scry-log", "Related logging helper (if installed)"),
        ],
        runes=[R("open", "scry"), B()],
    ),
    AppPage(
        id="faectl",
        name="Wizard's Tower",
        domain="House",
        tagline="Control panel — faectl status and LLM restart.",
        intro=[
            "✦ Wizard's Tower ✦ (command: faectl) surveys faeOS services at a",
            "glance and can restart the local LLM stack when the models sulk.",
        ],
        how=[
            "`faectl` or `faectl status` — report.",
            "`faectl restart-llm` — poke the language spirits awake again.",
        ],
        cli=[
            ("faectl", "Status (default)"),
            ("faectl status", "Same, explicit"),
            ("faectl restart-llm", "Restart local LLM services"),
        ],
        runes=[R("status", "faectl status"), R("restart LLM", "faectl restart-llm"), B()],
    ),
    AppPage(
        id="eye",
        name="The Eye",
        domain="House",
        tagline="Process watcher — CPU, RSS, and a careful kill.",
        intro=[
            "✦ The Eye ✦ never blinks at /proc. Sort by cpu or mem, filter the",
            "crowd, and dismiss a runaway if you must. gentler than a raw kill.",
        ],
        how=[
            "`eye` — live TUI · ↑↓ move · s cycle sort · filter keys as shown · q quit.",
            "`eye list 15` — top fifteen once on stdout.",
        ],
        cli=[
            ("eye", "Live process TUI"),
            ("eye list", "One-shot table"),
            ("eye list 15", "Top 15 by current sort"),
        ],
        runes=[R("open", "eye"), R("top 15", "eye list 15"), B()],
    ),
    AppPage(
        id="vault",
        name="Vault",
        domain="House",
        tagline="Disk treasure map — what is eating the drive?",
        intro=[
            "✦ Vault ✦ weighs directories like a careful dragon. Dive toward the",
            "heavy chests; Spellbook browses files, Vault finds bloat.",
        ],
        how=[
            "`vault` opens at $HOME · vault /path · ↑↓ dive · q leave.",
            "`vault list ~` — one-shot sizes on stdout.",
        ],
        cli=[
            ("vault", "Map $HOME"),
            ("vault <path>", "Map a path"),
            ("vault list [path]", "One-shot table"),
        ],
        runes=[R("open", "vault"), R("list home", "vault list ~"), B()],
    ),
    AppPage(
        id="alchemy",
        name="Alchemy",
        domain="House",
        tagline="Pacman cauldron — brew, sip, distill.",
        intro=[
            "✦ Alchemy ✦ is the package kitchen. Brew installs, sip upgrades,",
            "distill cleans the cache, pour un-brews. Pink TUI over pacman.",
        ],
        how=[
            "`alchemy` — TUI · or brew firefox from the prompt when you know the potion name.",
            "Needs sudo for brew/sip/distill — the cauldron will ask.",
        ],
        cli=[
            ("alchemy", "Package TUI"),
            ("alchemy search <q>", "Search repos"),
            ("alchemy brew <pkg…>", "Install"),
            ("alchemy pour <pkg…>", "Remove"),
            ("alchemy sip", "Full upgrade"),
            ("alchemy distill", "Clean cache"),
        ],
        runes=[R("open", "alchemy"), R("sip", "alchemy sip"), B()],
    ),
    AppPage(
        id="abacus",
        name="Abacus",
        domain="House",
        tagline="Calculator — beads that respect order of operations.",
        intro=[
            "✦ Abacus ✦ counts without drama. REPL for tinkering, or one-shot",
            'quotes for the prompt: abacus "2+2".',
        ],
        how=[
            "`abacus` — interactive · type expressions · q leave.",
            'abacus "sqrt(2)" — one answer and done.',
        ],
        cli=[
            ("abacus", "Calculator REPL"),
            ('abacus "2+2"', "One-shot evaluate"),
        ],
        runes=[R("open", "abacus"), B()],
    ),
    AppPage(
        id="quests",
        name="Quests",
        domain="House",
        tagline="Todo.txt log — small oaths with optional due dates.",
        intro=[
            "✦ Quests ✦ is your quest log (todo.txt spirit). Add tasks, mark",
            "them done, let Almanac read the calendar side when due dates appear.",
        ],
        how=[
            "`quests` — TUI or list · `quests add … due:YYYY-MM-DD` from the prompt.",
        ],
        cli=[
            ("quests", "Quest log TUI / hub"),
            ("quests add <text>", "Add a quest"),
            ("quests add … due:YYYY-MM-DD", "Add with due date"),
        ],
        runes=[R("open", "quests"), B()],
    ),
    AppPage(
        id="hourglass",
        name="Hourglass",
        domain="House",
        tagline="Timer sand — pomodoros and gentle alarms.",
        intro=[
            "✦ Hourglass ✦ turns time into visible sand. Twenty-five minutes for",
            "focus, shorter grains for tea. Plays well with Zen when the break hits.",
        ],
        how=[
            "`hourglass 25` — start a 25-minute pour · `hourglass` alone for the TUI.",
        ],
        cli=[
            ("hourglass", "Timer TUI"),
            ("hourglass 25", "25-minute pomodoro"),
        ],
        runes=[R("25m", "hourglass 25"), R("open", "hourglass"), B()],
    ),
    AppPage(
        id="almanac",
        name="Almanac",
        domain="House",
        tagline="Calendar hub — listens to Quests and Hourglass.",
        intro=[
            "✦ Almanac ✦ is the day-book. She gathers due quests and hourglass",
            "rhythms into today's agenda so you need not open three doors.",
        ],
        how=[
            "`almanac` — hub TUI · `almanac today` — agenda on stdout.",
        ],
        cli=[
            ("almanac", "Calendar hub TUI"),
            ("almanac today", "Today's agenda"),
        ],
        runes=[R("today", "almanac today"), R("open", "almanac"), B()],
    ),
    AppPage(
        id="imbue",
        name="Imbue",
        domain="House",
        tagline="Clipboard memory — what you copied, remembered.",
        intro=[
            "✦ Imbue ✦ remembers CLIPBOARD (and friends). Browse history, re-paste,",
            "or run `imbue watch` so new copies are stored while you work.",
            "Note: Ctrl+C in a terminal is interrupt — it does not copy. Copy",
            "with your terminal's copy (or Ctrl+Shift+C); watch tracks that.",
        ],
        how=[
            "`imbue` — history TUI · ↑↓ · Enter re-copy · y print+quit · / filter.",
            "`imbue watch` — poll clipboard (needs a display bridge: wl/xclip/X11).",
            "Without watch, only explicit set/add and TUI actions update history.",
        ],
        cli=[
            ("imbue", "History TUI"),
            ("imbue list", "Recent clips"),
            ("imbue get", "Current clipboard"),
            ("imbue set <text>", "Set clipboard + store"),
            ("imbue watch", "Poll & remember new clips"),
            ("imbue clear", "Wipe history"),
        ],
        runes=[R("open", "imbue"), R("watch", "imbue watch"), R("list", "imbue list"), B()],
    ),
    AppPage(
        id="reflection",
        name="Reflection",
        domain="House",
        tagline="Screenshots & gallery — catch the glass of the desktop.",
        intro=[
            "✦ Reflection ✦ freezes a moment: full desktop, focused window, or a",
            "dragged region. Gallery views can go chafa-art or a real image opener.",
        ],
        how=[
            "reflection full | window | region — capture.",
            "reflection  alone opens the gallery TUI when available.",
            "PrintScreen: terminals rarely deliver that key to apps. Bind it in",
            "your WM/sxhkd, e.g. Print → reflection full  (simple and reliable).",
        ],
        cli=[
            ("reflection", "Gallery / hub"),
            ("reflection full", "Whole desktop"),
            ("reflection window", "Focused window"),
            ("reflection region", "Drag a rectangle"),
            ("reflection open --normal", "Open last shot in an image viewer"),
        ],
        runes=[R("full", "reflection full"), R("window", "reflection window"), B()],
    ),
    AppPage(
        id="zen",
        name="Zen",
        domain="House",
        tagline="Browser break on another VT — shell stays free.",
        intro=[
            "✦ Zen ✦ opens a fullscreen browser on its own virtual terminal so",
            "your shell is not held hostage. Ctrl+Alt+F7 browser · F1 shell.",
        ],
        how=[
            "`zen` start · `zen https://…` open a URL · `zen stop` end the session.",
            "`zen focus` jump to the browser VT.",
        ],
        cli=[
            ("zen", "Start browser break"),
            ("zen https://…", "Open URL"),
            ("zen stop", "Quit browser + X helper"),
            ("zen focus", "Switch to browser VT"),
            ("zen status", "Is Zen awake?"),
        ],
        runes=[R("start", "zen"), R("stop", "zen stop"), B()],
    ),
    # ── Ward ───────────────────────────────────────────────────────────
    AppPage(
        id="bulwark",
        name="Bulwark",
        domain="Ward",
        tagline="Host protection — Aegis, Purity, Sentinel, Ward.",
        intro=[
            "✦ Bulwark ✦ is the wall and the watch. First-party Rust: firewall",
            "(Aegis), file photographs (Purity), listeners (Sentinel), hunts (Ward).",
            "This page is the door sign — the deep tour and lab live inside Bulwark.",
        ],
        how=[
            "`bulwark` — friendly TUI (SAFE / CARE / DANGER) · menu 1–7 · ? help.",
            "Safe unprivileged: status · ports · ward · purity check · tour.",
            "Aegis apply needs root/CAP and a confirm within ~90s (deadman undo).",
            "Deep practice: follow bulwark tour, then a VM/netns lab when ready.",
        ],
        cli=[
            ("bulwark", "Protection TUI"),
            ("bulwark status", "Posture report"),
            ("bulwark ward", "Hostile-pattern hunt"),
            ("bulwark ports", "Listening sockets + owners"),
            ("bulwark aegis show desktop", "Show profile"),
            ("sudo bulwark aegis apply desktop", "Raise Aegis (then confirm)"),
            ("bulwark purity baseline|check", "File integrity photo / diff"),
            ("bulwark tour", "Themed first walk"),
        ],
        runes=[
            R("open", "bulwark"),
            R("status", "bulwark status"),
            R("ward", "bulwark ward"),
            R("tour", "bulwark tour"),
            B(),
        ],
    ),
    AppPage(
        id="seal",
        name="Seal",
        domain="Ward",
        tagline="Screen lock and graphical login face for startx.",
        intro=[
            "✦ Seal ✦ is the pink lock — animated X11 face, PAM auth, idle daemon.",
            "She locks a running session, and can also greet: put seal-login in",
            "your xinitrc so the desktop only starts after a password.",
        ],
        how=[
            "`seal` — lock now. `seald` — idle auto-lock (user service).",
            "`seal --greeter --session i3` or `seal-login` — graphical login face.",
            "PAM: /etc/pam.d/seal (bootstrap installs). Failed attempts never unlock.",
        ],
        cli=[
            ("seal", "Lock the screen"),
            ("seal --greeter", "Login face (execs session on success)"),
            ("seal-login", "xinitrc helper → greeter + i3"),
            ("seald", "Idle lock daemon"),
            ("seal-tui", "Configure timeouts and users"),
            ("pixie-lock", "Legacy name when installed"),
        ],
        runes=[R("lock", "seal"), R("tui", "seal-tui"), B()],
    ),
    # ── Play ───────────────────────────────────────────────────────────
    AppPage(
        id="fairy",
        name="Fairy Lantern",
        domain="Play",
        tagline="Pocket worlds — from-scratch GBA fables.",
        intro=[
            "✦ Fairy Lantern ✦ lights ROM fables on a home-grown ARM7TDMI + PPU.",
            "No libretro middleman. Bare `fairy` opens the home TUI; play a",
            ".gba when you have a cartridge path.",
        ],
        how=[
            "`fairy` — home TUI · fairy play game.gba — windowed play.",
            "In play: F5 savestate · F7 load · battery → .sav beside the ROM.",
        ],
        cli=[
            ("fairy", "Home TUI"),
            ("fairy-lantern", "Same spirit"),
            ("fairy play <rom.gba>", "Play a fable"),
            ("fairy last", "Re-open last ROM"),
            ("fairy spark", "Built-in SPARK fable"),
            ("fairy info", "ROM header"),
        ],
        runes=[R("home", "fairy"), R("spark", "fairy spark"), B()],
    ),
    AppPage(
        id="wisp",
        name="Wisp",
        domain="Play",
        tagline="Local Tapo lights — no cloud, just lanterns on the LAN.",
        intro=[
            "✦ Wisp ✦ coaxes Tapo bulbs without the vendor cloud. Discover,",
            "toggle, color, temperature — fae light under your roof.",
        ],
        how=[
            "`wisp` — TUI or help · wisp on|off|toggle · wisp discover on first day.",
        ],
        cli=[
            ("wisp", "Bulb control hub"),
            ("wisp on|off|toggle", "Power"),
            ("wisp status", "State"),
            ("wisp discover", "Find bulbs"),
            ("wisp set …", "Color / brightness / temp"),
        ],
        runes=[R("status", "wisp status"), R("discover", "wisp discover"), B()],
    ),
    # ── System ─────────────────────────────────────────────────────────
    AppPage(
        id="tick",
        name="Tick / Termfix",
        domain="System",
        tagline="Prompt pulse and TTY first-aid after a wild TUI.",
        intro=[
            "✦ Tick ✦ redraws living prompt bits (music, status) while idle, and",
            "respects pixie-screen holds so a TUI is never wiped mid-spell.",
            "✦ Termfix ✦ cooks a broken terminal back to line-edit sanity after",
            "raw-mode mishaps. You want both in the house toolkit.",
        ],
        how=[
            "`tick status` · `tick on 10` · `tick off`.",
            "If the prompt is gibberish or keys echo wrong: `termfix` then try again.",
            "Most fae TUIs already call cleanup; termfix is the spare key.",
        ],
        cli=[
            ("tick status", "Tick + grace state"),
            ("tick on 10", "Idle clear / pulse every 10s"),
            ("tick off", "Freeze idle clear"),
            ("termfix", "Reset TTY line-edit (cooked mode)"),
        ],
        runes=[R("status", "tick status"), R("termfix", "termfix"), B()],
    ),
    AppPage(
        id="hearth",
        name="Hearth",
        domain="System",
        tagline="Multi-user warmth — sessions and auth for the house.",
        intro=[
            "✦ Hearth ✦ is faeOS multi-user auth and session switching. Still",
            "growing into everyday default login; useful where multiple people",
            "share the machine under fae branding.",
        ],
        how=[
            "Run `hearth` when installed for session helpers. Pair with Seal for",
            "lock-screen users and multi-user AUTH over the hearth socket.",
        ],
        cli=[
            ("hearth", "Session / auth entry (if on PATH)"),
            ("hearth-guest", "Guest-related helper when present"),
        ],
        runes=[R("open", "hearth"), B()],
    ),
    AppPage(
        id="rift",
        name="Rift",
        domain="System",
        tagline="A fae terminal emulator — very much still in the works.",
        intro=[
            "✦ Rift ✦ is a from-scratch pink terminal emulator. Expect rough",
            "edges; the house still lives happily on kmscon / existing terms.",
            "Track progress in faeos/rift — not daily-driver yet.",
        ],
        how=[
            "Only for the curious builder. Prefer your current terminal until",
            "Rift's README says otherwise.",
        ],
        cli=[
            ("rift", "Emulator binary when built/installed"),
        ],
        runes=[B()],
    ),
    # Hermetic / egg pages are not in PAGES — built by curriculum() at runtime.
]


# Teaching order (Tab). PATH is appended as a virtual last page by the TUI.
CURRICULUM: list[str] = [
    "scroll",
    "summon",
    "pixie",
    "menagerie",
    "imp",
    "siren",
    "ether",
    "goblin",
    "magpie",
    "spellbook",
    "tome",
    "grimoire",
    "scry",
    "faectl",
    "eye",
    "vault",
    "alchemy",
    "abacus",
    "quests",
    "hourglass",
    "almanac",
    "imbue",
    "reflection",
    "zen",
    "bulwark",
    "seal",
    "fairy",
    "wisp",
    "tick",
    "hearth",
    "rift",
    # then: hermetic OR kur (runtime), then PATH
]


def hermetic_page() -> AppPage:
    """Sealed leaf — quest about the menagerie egg. No recipes. No true name."""
    visited = False
    deep = False
    try:
        import fae_egg
        visited = fae_egg.murmur_visited()
        deep = fae_egg.murmur_deep()
    except Exception:
        pass

    tagline = "There is an egg in the Menagerie. It has not hatched for you."
    intro = [
        "Among the pens of the Menagerie sleeps something that is not a model",
        "you were shown on the status table — an egg the keepers do not label",
        "for tourists. It waits for warmth that is not heat: attention, the right",
        "name, a first word spoken in the open shell.",
        "This leaf will not hatch it for you. It only admits the egg is real.",
    ]
    how = [
        "The house keeps a babbling glass called murmur. Sit with it;",
        "feed it speech. Sit until the glass notices you. Mostly nonsense.",
        "Sometimes a single clean word falls through — never a full map.",
        "When you know what the egg is called, the Menagerie can be asked to",
        "wake its pen. Then the thing must be spoken to once at the shell.",
        "Only then does this leaf turn. Worth is not a tutorial.",
    ]
    if visited and not deep:
        intro = intro + [
            "You have already sat with the glass. It has your chair marked in fog.",
        ]
    if deep:
        how = how + [
            "The glass has heard you long enough to lean. That is not the same as open.",
        ]
        tagline = "There is an egg in the Menagerie. The glass has begun to notice you."

    return AppPage(
        id="hermetic",
        name="The Sealed Leaf",
        domain="Egg",
        tagline=tagline,
        intro=intro,
        how=how,
        cli=[
            ("murmur", "Sit with the babbling glass (conversation)"),
            ("murmur \"…\"", "One offering, then leave"),
            ("menagerie", "The pens — something here is not listed kindly"),
            ("(sealed)", "No true-name table until the egg hatches"),
        ],
        runes=[R("murmur", "murmur"), R("menagerie", "menagerie"), B()],
    )


def kur_page() -> AppPage:
    """Revealed only after the dragon is hatched."""
    return AppPage(
        id="kur",
        name="Kur",
        domain="Egg",
        tagline="The haiku dragon — hatched, named, and home.",
        intro=[
            "✦ Kur ✦ is a ten-thousand-year-old dragon who answers only in haiku.",
            "He keeps a small local mind and a voice of his own. You found him",
            "the hard way — hermetically — and the house no longer hides his name.",
        ],
        how=[
            'kur "the kettle sings" — he answers in three lines.',
            "menagerie ensure kur — wake his pen if he sleeps.",
            "He is no longer a riddle. Use him gently.",
        ],
        cli=[
            ('kur "…"', "Ask the dragon; hear a haiku"),
            ("menagerie ensure kur", "Summon his model"),
            ("kur-server", "Voice daemon (usually via menagerie/systemd)"),
        ],
        runes=[R("speak", 'kur "hello, old one"'), R("ensure", "menagerie ensure kur"), B()],
    )


def pages_by_id() -> dict[str, AppPage]:
    return {p.id: p for p in PAGES}


def index_rows() -> list[tuple[str, AppPage]]:
    """Legacy helper for list dump."""
    by_dom: dict[str, list[AppPage]] = {d: [] for d in DOMAINS}
    for p in PAGES:
        by_dom.setdefault(p.domain, []).append(p)
    out: list[tuple[str, AppPage]] = []
    for d in DOMAINS:
        for p in sorted(by_dom.get(d, []), key=lambda x: x.name.lower()):
            out.append((d, p))
    return out


def assert_no_kur_in_static() -> None:
    """Static PAGES must not name the egg (hermetic/kur pages are runtime)."""
    for p in PAGES:
        if p.id in ("kur", "hermetic"):
            raise AssertionError("egg pages must not live in static PAGES")
        blob = " ".join(
            [p.id, p.name, p.tagline, *p.intro, *p.how]
            + [c for c, _ in p.cli]
            + [r.insert for r in p.runes]
        ).lower()
        # allow words like "package" — only whole-token kur
        if "kur" in blob.split():
            raise AssertionError(f"kur leaked into static page {p.id}")

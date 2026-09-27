# faeOS changelog

## tests-unblocked (2026-09-27)

Supersedes the 2026-09-26 note that said *"pytest absent on this box (unittest
only) — recorded gap"*. That line is left where it was, in its dated entry,
because rewriting a dated record is not the same as correcting a claim — but
it stopped being true today.

- **pytest installed** (`extra/python-pytest 9.1.1`). The suite is now
  **203 tests, all passing**, run with `python3 -m pytest tests/`.
- The gap was bigger than the old entry implied. It was not 44 dormant tests,
  it was **93 that had never executed**: two whole files
  (`test_fae_termart.py`, `test_imp.py`) could not even be imported by
  `unittest`, and pytest's `parametrize` expands cases the stdlib runner
  collapses. The old runner reported `Ran 110 tests`; that was never the size
  of this suite.
  ```
  per file, under pytest        unittest saw
    test_fae_termart.py   65          — (import error)
    test_magpie_browse.py 59         57
    test_pixie_mind.py    41         41
    test_murmur.py        15         15
    test_spellbook.py     10         10
    test_scroll_pages.py   7          7
    test_imp.py            6          — (import error)
                          203        130 collected, 110 ran
  ```
- **65 of those cover `fae_termart`** — `tui_read_key`, `box`, `paint_frame` —
  the shared layer every TUI in the house draws through. It had never been run
  on any machine. **It passes.** That is the good outcome and it is worth
  stating plainly, because "never executed" is exactly the condition under
  which you expect to find something.
- **Two tests were passing without asserting anything.**
  `AIBarTests` is a plain `unittest.TestCase` but held two `async def test_*`
  methods. A coroutine returned from a sync test case is never awaited, so both
  reported green while running zero lines — one of them covers
  `run_page_scripts` and DOM mutation, which is real code. They now live in
  `AIBarAsyncTests(unittest.IsolatedAsyncioTestCase)`, matching what
  `JSTests` in the same file already did correctly. **Both pass when actually
  executed**, so the code was fine and only the tests were lying.

  This is the third time this class of bug appeared in one week, after
  fairy-lantern's ROM test: a test that cannot fail is worse than no test,
  because it is counted. `py_compile` is not a sufficient check for a
  refactor like this — a misplaced dedent still compiles and silently collects
  nothing. `--collect-only` is the check that catches it.

`python3 -m unittest discover -s tests` still works and still passes 110; it
just cannot see the two pytest files. The house runner is now pytest.

## exposure-cleanup (2026-09-27)

Follow-up to a GitHub exposure audit of the whole `ElegantVW` account. The
audit and its coordination log are **local-only and not in any repository** —
they quote the values they are about. This entry records what changed in the
public tree; the evidence lives in the audit report and in git history.

- **Tests no longer assert against this machine's home directory.**
  `test_spellbook.py` used the operator's real home as a breadcrumb sample, and
  `test_magpie_browse.py` loaded a real wallpaper by absolute path and asserted
  the loader decoded it. Both published the username and local layout (audit
  F-5), and both were tests that could not pass anywhere but here. Now
  `/srv/faeos/bin` and a repo-tracked PNG resolved relative to the test file,
  with the fixture asserted to exist first so a missing file fails as a missing
  file rather than as a loader bug. **0 occurrences of the operator's home path
  remain in any public repo's tracked files, down from 8.**
- The re-audit criterion is "no absolute home path in any public repository",
  so the changelog line describing the systemd fix no longer repeats the path
  either. The evidence is preserved in this repository's history.
- `fairy-lantern`: the fight-savestate test hardcoded a ROM path and had two
  silent `return`s, so its assertion had never executed anywhere while still
  being counted. Now `#[ignore]`d and driven by `FAIRY_ROM`/`FAIRY_STATE`.
  `cargo test --bin fairy` reports **136 passed, 1 ignored** — previously 137
  passed, where the 137th asserted nothing. The total dropping by one is the
  first honest number that suite has produced.
- `mourama`: `tools/isolate_icons.py` hardcoded a path into an agent session
  directory, session id included. It now takes the directory as an argument or
  `$MOURAMA_ICON_SHEETS`, and exits with usage when given neither — the sheets
  are a local screenshot drop and are deliberately not in the repo, so there is
  no portable default to fall back to.
- **Not closed:** network infrastructure and corporate mailboxes are still
  public in `goblin` on the `goblind` branch, reachable with no auth. Removing
  them means rewriting history and force-pushing, which is a human decision
  and has not been taken. It is the live finding.

## siren-retired-and-units-portable (2026-09-27)

An audit of all ten repos found the kit quietly undoing a sibling engine, four
systemd units that only work on one machine, and a launcher install that
silently no-ops. All three fixed.

- **The Python siren player is gone: `bin/siren` (2477 lines, 86KB).**
  `install.sh:66` copies `bin/` over `~/bin` unconditionally, so every
  `./install.sh` replaced the 856-byte Rust launcher with the archived Python
  player — reverting the 2026-09-23 cutover. `siren/build.sh:31-32` explicitly
  refuses to overwrite that file and says why, so the kit was breaking a
  contract a sibling repo had deliberately kept. The fallback existed on
  purpose, as a documented rollback, which is why the fix is removal rather
  than a guard: the trap is gone instead of worked around. Verified by
  simulating `install.sh:66` against a stand-in launcher — md5 unchanged,
  still the Rust launcher. The five bulwark launchers the kit also ships are
  byte-identical to their repo, so no `install.sh` change was needed at all.
  Went with it: `tests/test_siren.py` (25 tests, it loaded `bin/siren` through
  a `SourceFileLoader` and had no subject left) and
  `docs/SIREN_QUICK_START.md` (a dev guide to the retired player).
  `docs/plans/siren.md` — a 267-line plan for that player — is now a short
  stub pointing at `ElegantVW/siren`.
  **Consequence, recorded not hidden: siren now has 2 unit tests in
  `src/spectrum.rs` and no integration coverage.** The content pipeline is
  unaffected: `tools/content/make.sh:96,101,102` and `shots.yaml:35` all
  invoke `~/bin/siren`, the launcher.
- **Four systemd units no longer hardcode an absolute home path.** (The path
  itself is deliberately not repeated here: this is a public repository and the
  2026-09-27 exposure audit's re-audit criterion is that no absolute home path
  appears in any public repo. The evidence is preserved in the audit report and
  in this repository's git history.)
  `ether-bridge.service:8`, `goblin-idle.service:8`, `goblin-sync.service:7`
  and `kur-server.service:6` used absolute paths while the other four already
  used `%h`, and `install.sh:106` copies them verbatim — so
  `README.md:133`'s `systemctl --user enable --now goblin-idle.service`
  installed a broken unit on any other machine. All eight now use `%h`;
  `systemd-analyze --user verify` clean on every one. `kur-server` also pinned
  `/usr/bin/python3`; kur's own unit uses `%h/bin/kur-server`, so the kit was
  shipping a *worse* unit than the engine it wraps.
- Test inventory after the removal: 165 test functions, 121 run under
  `unittest`, 44 still blocked on a missing `pytest` (was 69 — 25 of them were
  in the deleted `test_siren.py`). The blocked remainder includes
  `test_fae_termart.py`'s 38 tests covering `tui_read_key` and
  `box`/`paint_frame`, the shared TUI layer every TUI depends on.
  `pacman -Ss python-pytest` offers `extra/python-pytest 1:9.1.1-1`; the tests
  use three pytest features total (`mark`, `raises`, `fixture`). The changelog
  has called this an environmental gap since 2026-09-26 and it is not one.
  Left alone this round because the chosen scope was the install path and the
  units; recorded here so it is not lost.

Verified: `bash -n install.sh` clean; `bash -n goblin/build.sh` clean; all 8
units verify; install.sh:66 simulation leaves the launcher untouched; faeOS
suite still runs 112 cases green; switcher cold start visits 4 of 4 windows
distinctly; Escape still cancels without moving focus; `fae-cascade` still
refuses a second instance and still cascading; picom up.

`faeOSplan.md:139` still says siren v2 was a single-file `bin/siren` with 31
test cases and a 78-test suite. That is a dated 2026-08-05 history entry and
has been left alone rather than rewritten — the current numbers are above.

## switcher-cycles (2026-09-27)

`fae-hud` was rebuilt around a macOS-style strip and then had to be taught to
actually cycle. Four defects, all found by measuring rather than looking.

- **One entry per window, not per application.** The per-app dedupe collapsed
  five kitty windows on one workspace into a single row, so `sel` was 0 and
  Alt+Tab re-focused the app you were already in — taps two through eight did
  literally nothing. Row labels are now the window's own title, with the
  selected window's full title repeated on a line underneath because a 16-char
  cell cannot make `OC | System audit, documentation update…` distinct, and
  five terminals are all titled `~`. The count badge is gone; it only existed
  because one row had to stand in for several windows.
- **New `mru.c`: the ring.** `_NET_CLIENT_LIST_STACKING` is not recency —
  measured by focusing the bottom-most window in the stack and re-reading the
  property, it came back byte-for-byte identical — so the switcher keeps its
  own ring at `$XDG_RUNTIME_DIR/fae-hud.mru`, pruned of dead ids, order
  preserved, new windows appended. The list is then *rotated* cyclically from
  the focused window. Move-to-front is wrong here: it rewrites `[A,B,C,D]` to
  `[B,A,C,D]` and the next gesture lands back on A. A toggle, not a walk.
  Verified: 6 windows, 6 distinct hops, hop 7 back to hop 1; 28 windows, 28
  distinct hops, hop 29 back to hop 1.
- **Escape no longer commits.** The cancel branch set `cancelled = 1` and then
  called `commit()`, so Escape moved focus to the highlighted window while the
  release-commit below it was correctly skipped — cancel and commit at once.
  Verified at 20/50/120/300ms holds: all four previously moved focus, all four
  now leave it alone.
- **One window is a no-op.** `n <= 1` opens the strip briefly and changes
  nothing, rather than re-focusing the window you are already in.
- **picom was drawing a shadow around the strip.** `shadow = true`,
  `shadow-radius = 12`, `shadow-offset-x/y = -8`, and `shadow-exclude` listed
  only i3bar and rofi. The result read exactly like the panel being inset
  inside its own window — measured, `c_void` filled the window edge to edge
  while the panel sat 396x126 inside 432x164. The window was never the wrong
  size; X and cairo both said 432x164. `rounding-exclude` did not cover this,
  shadows are a separate rule. Now excluded by name: 0 void pixels inside the
  window, was a full 18px band on all four sides. `config/picom/picom.conf`
  was also stale in the kit and is now synced with the live copy.
- **Makefile** now lists every header (`hold.h entry.h icon.h mru.h`) so
  editing one triggers a rebuild. `CC ?= gcc` never took effect — make
  predefines `CC = cc`, so `?=` leaves it alone; harmless, but do not be
  surprised by `cc` in the build line.
- `XGetGeometry` writes to *both* trailing out-parameters. Passing `NULL` for
  the depth segfaults inside Xlib; found by ASan while adding the geometry log.

Verified: clean build 0 warnings; ASan clean; 40 forward and 40 reverse taps
under churn, 0 failures, 0.4s each (no failsafe hits); Shift+Tab is the exact
reverse; SIGKILL and SIGTERM mid-grab leave the keyboard free (proved by
typing into `cat` and reading the file); no keyboard grab left behind;
single-window guard on an otherwise empty workspace; `--dump`, `--opaque`.

## housekeeping (2026-09-26)

- Kur splits to `ElegantVW/kur` (client + voice daemon + redacted quest).
  Hatch help now names both daemons (`:8083` pen vs `:8081` mind).
- Scroll gains Mourama + Grove pages; Seal/Pixie pages note their repos;
  curriculum grows two slots. Installed book refreshed via `install.sh`.
- New `tv` command: persistent CRT shader toggle (`on/off/status`).
- Content pipeline: `shots.yaml` recipes, `sequence` runner, `sigil2svg`,
  `sigil2story`, `story2clip`, `storyify` + batch log.
- Tests: pytest absent on this box (unittest only) — recorded gap.

## seal-moved (2026-09-26)

- Seal source leaves `faeOS/seal/` for `ElegantVW/bulwark` `glass/`.
  faeOS keeps thin launchers; `docs/engines.md` + `install.sh` updated.
- Pixie canonical repo: `ElegantVW/pixie`. Hearth/rift marked incomplete.
- Goblin `steal` naming; magpie TUI-browser surface.

## keys-2026-09-27
- Super+Return/Shift+Return/Ctrl+Shift+Return open kitty (nothing was bound).
- Super+drag move/resize via --whole-window (verified: xdotool drag moved a
  test window 12,12 -> 12,49 and flipped it floating).
- fae-cycle cue: plain-ascii toast, targeted pid -> socket -> kitty-window-id.

## cues-2026-09-27
- fae-cycle: added an audit log ($XDG_RUNTIME_DIR/fae-cycle.log). i3 runs
  `exec` with stderr inherited from i3, and i3's fd 2 is /dev/tty1 — so the
  stderr cue has been invisible since it was written. The log is how we tell
  "binding never fired" from "fired and you could not see it".
- fae-cycle: new visible cue — kitty `set-tab-color` tints the tab bar of the
  window you land in, reverted after 0.9s by a short-lived background sleep
  (no resident process). This build has no `set-tint`.
- i3: mouse_warping output -> none (matches the comment's stated intent).
- Diagnosis: i3's `drag` is inert on this machine. The press reaches i3 and
  `floating enable` runs (floating goes auto_off -> user_on), but `drag move`
  and `drag resize` both produce exactly 0px of movement. Tried: bare drag,
  floating-enable chain, explicit `drag button1 move`, with and without
  --whole-window, from the border and the window body, mouse_warping output
  and none, picom running and killed. Config is clean; cause unknown.
- Also: XTEST synthetic KEY events do not reach i3 in this environment (even
  a bare F9). XTEST mouse events do. So keyboard bindings cannot be verified
  by injection and need a real keypress.

## hud-2026-09-27
- NEW bin/fae-hud: themed X11 window-cycler panel in C. Xlib + Xft only, no
  other runtime deps. Viewer only: never focuses, kills, moves or resizes.
  Spawned per Alt+Tab by fae-cycle; paints, holds, fades, exits. No resident
  process (the i3bar lesson). Reads EWMH only, so it is WM-agnostic.
  `fae-hud --dump` prints the raw window list, because the first question
  about a window list is "is the data there", not "does it look right".
- fae-cycle: spawn fae-hud with the window it just focused. The HUD paints
  BEFORE the kitty toast, so a cue exists even when the target is not kitty.
- BUGFIX (fae-cycle, latent): `set -euo pipefail` plus any pipeline where one
  stage fails aborted the script with no message and rc=1, after focus had
  already moved. Two triggers, both hit in normal use:
    * `kitty @ send-key ... && toasted=1` — the `&&` list fails when the target
      is not kitty (no @faeos-kitty-<pid> socket), so `set -e` exited.
    * `kid=$(kitty @ ... ls | python3 ...)`, `name=$(xprop ... | cut)`,
      `con=$(tree | python3 ...)`, `state=$(...)` — pipefail propagates a
      non-zero from any stage.
  Every pipeline assignment is now guarded. Symptom before the fix: Alt+Tab
  moved focus and then silently did nothing, and stderr was invisible anyway
  because i3's fd 2 is /dev/tty1. Verified: 67/67 invocations succeed, in
  both directions, including while windows are created and destroyed.
- BUGFIX (i3 config): Super+drag was broken because this file had been
  slimmed from the 2026-09-23 backup and dropped `tiling_drag modifier`,
  `floating_modifier $mod` and `for_window [class=".*"] floating enable`.
  Those three are the whole reason Super+drag works. Rebuilt the config from
  the Sep 23 baseline (198 lines) and restored them. Also: an explicit
  `bindsym $mod+button1 ... drag move` SHADOWS tiling_drag, which is what
  made the breakage look like "i3 ignores my drag".
  Measured: floating_modifier + drag on a floating window moves it exactly
  the dragged distance; the `drag` *command* produces 0px on this machine.

## hud-crystal-2026-09-27
- fae-hud rebuilt on cairo + pangocairo. Xft cannot round a corner — it has
  no arc primitive, only Rect/String/Glyphs — so the panel had been a hard
  rectangle and any softness was picom's shadow, not our drawing. Cairo also
  gives genuine per-pixel alpha, which plain X11 cannot do on its own.
  README amended: the old "no runtime deps beyond X11" claim is no longer
  true, and it says so rather than letting it quietly become false.
- Shape: rows are now two lines (title, then `workspace · app class`), so the
  panel spends height instead of width — 470..560 wide by ~235 tall for three
  windows, against 1220x120 before. Content-driven width with a 470 floor so
  short titles are not stubby, capped at min(560, 34% of screen). Past 14 rows
  it says `+N more` instead of outgrowing the screen.
- Crystal: 14px round corners, four drawn corner diamonds, a hairline under
  the header and above the footer, a hairline splitting the glyph column from
  the text, and a soft pink glow (concentric strokes, not a cairo shadow, so it
  survives without a compositor). Glyphs are U+25C8/U+25C7/U+00B7, all verified
  present in DejaVu Sans Mono; the hexagons U+2B21/2B22 are NOT, which is why
  the vocabulary is diamonds. All in THEME_GLYPH_* in theme.h.
- Motion: panel blooms from a 14px inset (no window resize, so no flicker),
  rows cascade 22ms apart, the focused band wipes in from the left, hold, fade.
  ~1.65s for two windows.
- Translucent via an ARGB32 visual when a compositor is present, detected by
  looking for an owned _NET_WM_CM_S* selection. Plain X11 has no per-window
  alpha, so with no compositor it falls back to a solid fill rather than
  black holes. FAE_HUD_VERBOSE=1 reports the choice; --opaque forces the
  fallback so it can be tested without stopping picom.
- BUGFIX (hud): the header, footer and corner facets rode the global fade
  envelope while the rows had their own stagger, so at ~80ms you got a
  fully-lit footer sitting under an empty body. They now join the cascade.
  Only visible by capturing frames across the timeline, not one screenshot.
- BUGFIX (hud): the focused band was drawn row_h tall, and row_h includes the
  gap *under* a row, so it reached up over the title into the header rule.
  It now hugs the row's two lines.
- HUD now sets WM_NAME as well as _NET_WM_NAME; with only the latter the
  window is invisible to `xdotool search` and `wmctrl`.
- BUGFIX (fae-cycle): a client that exits between reading _NET_CLIENT_LIST and
  scraping the tree left us holding an X id with no container, and the script
  exited 1 having done nothing. Now resolve_con/pick_target are functions and a
  dead target is retried, with the dead ids remembered — re-reading the list
  alone was not enough, because _NET_CLIENT_LIST keeps listing a window for a
  moment after its client exits, so the retry re-picked the same corpse (5
  failures in 30 under churn; now 0 in 40 each way under the same churn).

## hold-2026-09-27
Alt+Tab is now one gesture, not a keypress. `fae-hud --cycle` opens a themed
panel, holds it while Alt is down, moves the highlight on Tab / Shift+Tab,
cancels on Esc, and focuses the selection only on release. One panel for the
whole gesture: Tab repaints only the two rows whose highlight moved, so there
are no stacked panels and nothing re-animates. A quick tap still steps one
window and exits, so the old muscle memory keeps working.
- Browsing is scoped to the current workspace (`--all-workspaces` opts out).
  Focus not moving while you browse is the point: i3 follows focus across
  workspaces, so a switcher that focuses on every press drags you around the
  machine and hides everything you started from. That, plus three windows
  sharing one identical rect, is what "the other windows got minimized" was.
- fae-hud now focuses on commit, via the EWMH _NET_ACTIVE_WINDOW client
  message. Deliberately not i3-msg: it still does not know i3 exists. The old
  "never mutates anything" rule is now "mutates exactly one thing, through the
  documented interface".
- Keyboard handling: XGrabKeyboard for the duration, with a self-pipe so
  signals are handled in normal context and ungrabbing always happens, an
  alarm() failsafe so a stuck Alt cannot hold the keyboard for more than 8s,
  and a 30ms poll of the real key state to decide when the gesture ends.
- fae-cycle lost its kitty dependency entirely (send-text toast, set-tab-color
  flash). Those were the only reason it could die under `set -euo pipefail` —
  `kitty @` exits non-zero for any non-kitty target and pipefail turned that
  into a silent exit 1. Removing them deletes that whole failure class.
  Mod1+Tab now goes to fae-hud; Mod1+c keeps fae-cycle for scripting.

### Bugs found and fixed in this pass
- PangoFontDescription is a BOXED type, not a GObject. g_object_unref on it
  read a GTypeInstance out of memory that has none; it survived several runs by
  luck and then segfaulted in g_type_check_instance_is_fundamentally_a. Now
  pango_font_description_free. Found with ASan, not by reading the code.
- BadWindow killed the panel. _NET_CLIENT_LIST is read, then properties are
  read off each window in it, and a client can exit in between — which is a
  race, not a bug, and Xlib's default handler calls exit(). The panel died
  mid-paint at the exact moment you press Alt+Tab. All X errors are now
  absorbed and reported under FAE_HUD_VERBOSE.
- A KeyRelease for the Alt keycode arrives the instant the grab takes. Acting
  on it ended the whole gesture before the user had pressed anything — the
  panel would flash and commit. The gesture now ends when Alt is *physically*
  up, decided by polling XQueryKeymap, not by trusting the event stream.
- A bare `break` inside the event-drain loop only left that loop; the outer
  loop went straight back to select() and waited out the 8s failsafe. A single
  Alt+Tab took 8.3s to respond. Needed an explicit `done` flag. Now 756ms.
- fae-cycle still bailed with "no focused window" on an empty workspace, which
  is NORMAL: i3 focuses the workspace node itself when a workspace is empty,
  so _NET_ACTIVE_WINDOW is empty while _NET_CLIENT_LIST still lists windows
  elsewhere. The explanation printed to /dev/tty1, so it just looked broken.
  Now it starts at the top of the list.
- fae-cascade's first tick treated every existing window as new and went after
  all of them. It now adopts what is already there and touches nothing.
- fae-cascade's move-only cascade could never work: i3 floats a new window at
  the full container rect, 1873px wide on a 1920px screen, so there is no room
  to shift it. It now shrinks as it offsets, giving a real staircase
  (153,153 1723x853) -> (183,183 1693x823) -> (213,213 1663x793).

### Verified
Quick tap 756ms; tap+3 Tabs lands on 4 of 5; Shift+Tab reverses with wrap;
Esc cancels and focus does not move; SIGKILL and SIGTERM mid-grab both leave
the keyboard free and typing into `cat` still works; the 8s failsafe fires;
no leftover processes or stray X windows; ASan clean on the cycle path; both
binaries build from scratch with zero warnings; fae-cycle 30/30 and 12/12 on
an empty workspace.

## fix-2026-09-27
- BUGFIX (fae-hud): the panel drew itself at h->px,h->py — the window's
  position ON SCREEN — instead of surface coordinates. cairo's origin is the
  surface, so every fill, stroke, facet and glyph landed outside its own
  470x235 canvas and was clipped away. The only thing that survived was
  cairo_paint(), which fills the clip regardless of coordinates, so Alt+Tab
  produced a void-coloured rectangle with no text at all. Introduced when
  hud.c was rewritten into the hud_t handle: the old code drew at local
  `px,py` variables that held *insets* (~0), and the rewrite reused those names
  for the window position. paint_chrome/paint_row/repaint_rows and body_top are
  now surface-relative, with a comment saying why so it is not reintroduced.
- BUGFIX (fae-hud): the bottom corner facets sat on top of the footer's first
  character — a diamond overdrawing the "t" of "tab next". THEME_FACET_INSET
  had been raised to 21 to clear the corner arc, which is exactly what pushed
  them over the text at THEME_PAD_X=20. Back to 14, which clears both.
- fae-hud: a quick tap now dwells ~850ms before closing (THEME_TAP_HOLD).
  Measured before: 211ms on screen, which is a blink, not a cue. If Alt comes
  back down during the dwell the wait stops, so a hold still works.
  Now 1061ms on a tap.
- Verified by pixel-diffing the panel region against a no-panel frame and
  counting lit pixels — the check that would have caught the coordinate bug.
  Lit: 0 windows (message), 1, 2, 6 rows, ARGB32 and --opaque.

## strip-2026-09-27
Alt+Tab is now a macOS-style strip: one icon per APPLICATION, centred, a fifth
of the way down, opaque, no backdrop dim. Deduped by WM_CLASS and ordered MRU,
so the row is as short as the number of apps rather than the number of
windows. Icons come from _NET_WM_ICON, cropped to their visible content and
scaled to fit so they line up; apps that publish nothing get a monogram disc
so a row never has a hole. A count badge appears when an app owns more than one
window.
- FOCUS NOW COMMITS FIRST AND THE STRIP FADES AFTER. The previous version sat
  for 850ms on screen before moving focus, which read as lag and stacked a
  panel on every tap. Every modern switcher commits on release and uses the
  panel as confirmation. This was my worst call in the switcher work.
- The row scrolls (ensure_visible) when there are more apps than fit, and the
  icons shrink down to a floor before that.
- BUGFIX (picom.conf): the strip declares _NET_WM_WINDOW_TYPE_DOCK, so picom
  treated it as an INACTIVE window and applied inactive-opacity = 0.92 — the
  panel was see-through no matter what alpha cairo used. round-borders = 12 was
  also rounding the strip's corners, clipping cairo's and cutting the corner
  facets. Now inactive-opacity = 1.0 and rounding-exclude for fae-hud.
- BUGFIX: pango_cairo_show_layout() positions by the layout's top-left, not the
  text baseline. Every y in the paint path is a top edge; treating it as a
  baseline put the window-count number underneath its badge.
- Icons: _NET_WM_ICON is populated (kitty ships 128x128 + three small images).
  xprop on this system renders CARDINAL icon data as coloured blocks and looks
  empty, which is what made me nearly abandon the icon path.

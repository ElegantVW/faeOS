# Magpie — browser/search

**Role:** Privacy web access: search via DuckDuckGo (no trackers), no accounts. A real TUI browser feel: read pages, inline images, hand video to mpv, run page scripts in Magpie's own JS engine, summarize with local Pixie.

**Status:** search stable; browse v0.1 built (2026-09-24)

## Current
- `magpie` (bare) — opens the TUI den; `magpie "query"` / `duck` (alias) — DDG search, link scraping, local summaries (Pixie, offline)
- `magpie browse [url]` / `magpie --browse [words]` — full TUI browser:
  tabs, address bar, history, bookmarks (incl. lynx import), reader view,
  find-in-page, per-site script consent, fullscreen images, mpv playback,
  downloads, Pixie page notes, zen handoff
- `magpie browse --dump URL` — pipeable page text (no TUI)
- `magpie config …` — settings (below); first `browse` offers the wizard once
- Integrated with ether (net diagnosis for IPv4 HTTPS)

## Settings (one file, CLI + TUI)
- `~/.config/magpie/config.json` — search engine/results/Tor default,
  JS mode, homepage, AI bar side, AI on/off, media caps.
  Precedence: flags > env (`MAGPIE_ENGINE`, `MAGPIE_RESULTS`, `MAGPIE_TOR`,
  `MAGPIE_JS`, `MAGPIE_HOMEPAGE`, `MAGPIE_AI_BAR`, `MAGPIE_AI`) > file > builtins.
- `magpie config list|get|set|reset|wizard [section…]`; `;` opens the same
  settings inside the TUI (live-apply where safe).

## Pixie bar (decision: her persona, Menagerie's model)
- `A` toggles a dockable panel (`browse.ai_bar: left|right`, set in the
  wizard or `;`); `a` summarizes the page into it, then asks follow-ups —
  multi-turn against the article, one local model call per turn.
- Magpie holds no model setting: it talks to its own `:8091` instance and
  whatever `menagerie set magpie <model>` points at answers. The bar shows
  model state (ready/asleep) and labels itself local; page text never leaves
  loopback. `ai.enabled: false` parks the whole bar.

## Architecture (all ours, stdlib-only)
- `bin/magpie` — search/AI half (unchanged behavior) + browse entry
- `bin/magpie_fetch.py` — URLs, manual redirects, ephemeral cookie jar,
  strict `--tor` (never silent clearnet), history/bookmarks/cache
- `bin/magpie_dom.py` — own HTML tokenizer/DOM, selector engine, CSS subset,
  terminal layout, forms, media discovery, article extraction
- `bin/magpie_image.py` — own PNG/GIF/BMP decoders, native Kitty graphics
  protocol framing, ANSI half-block fallback; ffmpeg/ffprobe/mpv are host
  OS capabilities (already in pkglist.txt), not browser dependencies
- `bin/magpie_jslex.py` / `jsparse` / `jsval` / `jsrun` / `jslib` — own
  JavaScript engine: lexer, parser, async interpreter, builtins, timers,
  promises; `bin/magpie_jsdom.py` — DOM/browser bindings;
  `bin/magpie_script.py` — page-script runner (classic + modules, budgets)
- `bin/magpie_tui.py` — browser chrome on shared `fae_termart` (pink boxes,
  mouse, runes); own UTF-8 input layer (PT keyboards type ç/ã/õ)
- Tests: `tests/test_magpie_browse.py` — 59 cases, `python3 -m unittest`

## Robustness (2026-09-24 hang post-mortem)
- A malformed GIF (lying 65535×65535 header) inflated ~43 GiB and spun the
  den at 90% CPU. Fixed: GIF/PNG/BMP share the 64M-pixel cap, the LZW
  decoder returns `bytes` (never a multi-GB list), gzip/deflate inflation is
  capped at 64 MiB, headers are sanity-checked before any decode or ffmpeg.
- Render path never blocks on network anymore: images/posters load on a
  background thread (shared cookie jar under lock), markers paint instantly,
  `media.inline_images` (default 8) caps auto-loads, failures are cached as
  failures (no per-frame refetch storms), `Esc` cancels pending loads.
- AI summaries/follow-ups run on a worker thread (`Esc` abandons the result);
  model state is probed on tick, never inside a frame.
- `faulthandler` writes `~/.cache/magpie/crash.log` on fatal signals; the
  event loop degrades single-key failures to flashes instead of tracebacks.
- Regression tests: lying-GIF refusal, gzip bomb cap, loader fill/failure,
  threaded AI completion.

## Privacy rules (kept)
- Search HTTP stays cookie-less. Browse cookies live in memory only, die on quit.
- No Google anywhere. No persistent profiles/accounts.
- Scripts are per-site opt-in (`ask` default); `off` disables; `on` allows.
  The engine is sandboxed: no filesystem/process access, budgets always on.
- Media cache is content-addressed under `~/.cache/magpie` (bounded LRU).

## Next
- [ ] Read-later queue (local)
- [ ] Save pages as text for offline reading (have `s` per-page save; want queue)
- [ ] Animated GIF posters (first frame today; mpv plays full motion)
- [ ] JS gaps to close: generators, Proxy, for-await, Web Workers (clear errors today)
- [ ] Scroll section refresh with new commands

## Anti-goals
- Trackers, ads, persistent browser profiles/accounts.
- JS-heavy web *apps* as a target: Magpie runs page scripts for reading and
  light interaction; the `e` key hands truly app-shaped pages to zen.

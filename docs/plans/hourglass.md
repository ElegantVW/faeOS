# Hourglass — timer

**Role:** Countdown sand. Pomodoro and custom durations. Fully independent.

**Status:** new (v1)

## Current
- Dir: `$XDG_DATA_HOME/faeos/hourglass/` (override `HOURGLASS_DIR`)
- Log: `sessions.jsonl` — `{ts, label, seconds, completed}`
- TUI presets + custom minutes; live bar + mm:ss; pause; abort logs incomplete
- CLI: `hourglass 25` · `pomodoro` · `break` · `log`
- **Export for Almanac:** `sessions_on_day("YYYY-MM-DD")` · `load_sessions()`

## Independence
Almanac may read the log. Hourglass never imports Almanac.

## Next
- [ ] Desktop/notify on complete
- [ ] Chain: pomodoro → break auto

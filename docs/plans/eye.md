# The Eye — process watcher

**Role:** htop-like gaze over the machine: CPU, RSS, commands; sort/filter/kill. The pair to Menagerie when a model is eating RAM.

**Status:** new (v1)

## Current
- Live TUI (`eye`) on shared `fae_termart` layer; hold name `eye`
- Header: loadavg · ncpu · mem used/total bar · avail · buff/cache
- Table: PID · CPU% (one-core scale, jiffie deltas) · RSS · state · cmdline
- Sort: `s` cycles cpu→mem→pid→name; `1`–`4` jump; `r` reverse (cpu/mem default biggest-first)
- `/` filter mode (tokens match pid/name/cmdline); ^U clear; sticky sel by pid
- `space` pause refresh; `k` SIGTERM / `K` SIGKILL with y/n confirm (won't kill self)
- One-shot: `eye list` / `eye list 15` / `eye 15` → stdout table after a short sample

## Next
- [ ] Tree / threads toggle (show `task/` kids)
- [ ] Disk I/O column (`/proc/pid/io`) when readable
- [ ] Menagerie-aware highlight (llama-server rows tagged)
- [ ] Send arbitrary signal menu

## Notes
- Pure `/proc` + stdlib; no psutil.
- CPU% needs ≥1 refresh interval to settle; first paint warms with a 150ms double sample.

# Pixie — local AI assistant

**Role:** Local AI assistant with tools (files, shell), fully offline. Integrated into Magpie summaries. `pixie "…"`, `menagerie` server on 127.0.0.1:8080.

**Status:** stable

## Current
- Model: **qwen2.5-coder-3b-instruct** — code-focused agent; no fallback (mistral removed 2026-08-03)
- `pixie` with **no args** → interactive chat TUI with **Runes** (agent modes, switch with `r`/`tab`, `╭─ ✦ Runes ✦ ╮` footer):
  - **Chat** — friendly assistant, systemd/file tools
  - **Deep** — internet research (`web_research`: DDG html → DDG lite → Wikipedia API fallback; `fetch_web_page`) with Sources
  - **Build** — coding agent (inspect → write → run → verify; `write_local_file`), opencode-build-style
  - **Plan** — investigate + plan only, no mutations, opencode-plan-style
  - Bubbles are content-sized and live-streaming; tool calls appear as centered `Calling tools ✦ thought for Xs ✦` boxes with history
- Chat uses the **OpenAI-style `/v1/chat/completions`** endpoint (proper roles incl. `tool`); one-shot `pixie "…"` still on `/completion`
- Tool protocol is JSON-object calls. Small-model armor: narrated tool calls extracted (`extract_all_tool_calls`), Cline-style tool/arg aliases mapped (`code_editor`, `file_path`…), unknown tools get a corrective error, 3x-repeat loop guard, 6-round cap
- `menagerie start|stop|status|chat|path` — profiles: qwen/coder (8080), kur (8081), imp (8082)
- RAM: `--sleep-idle-seconds` default 300 (env `PIXIE_LLM_SLEEP_IDLE`; 0 = keep loaded); server wakes on next request
- Systemd: `menagerie.service` (ctx 4096)
- Agent: `ask` (tools incl. art preview via pixie-art); `menagerie-run` is the systemd launcher

## Next
- [x] **Model upgrade for tool reliability** — qwen3-4b (unsloth 2507 Q4_K_M, 2.5GB) now default pixie profile: native tool names first-try (`write_local_file`), real files created, self-corrects unknown tools (verified 2026-08-04)
- [ ] Context/prompt hygiene: template for tools verified with qwen chat format
- [ ] Model fetch wizard (choose size/quant) — distro phase
- [ ] Memory: session continuity across reboots

## Notes
- Kur is a separate tiny model (smollm2-360m) on 8081 — do not conflate.
- `menagerie chat kur` garbage is a pre-existing template mismatch (kur's real path = `/generate` via kur-server).

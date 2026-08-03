# Pixie — local AI assistant

**Role:** Local AI assistant with tools (files, shell), fully offline. Integrated into Magpie summaries. `pixie "…"`, `pixie-llm` server on 127.0.0.1:8080.

**Status:** stable

## Current
- Model: **qwen2.5-coder-3b-instruct** (being downloaded 2026-08-03) — code-focused agent; fallback mistral-7b
- `pixie-llm start|stop|status|chat|path` — profiles: qwen/coder (8080), kur (8081), mistral (8080)
- RAM: `--sleep-idle-seconds` default 300 (env `PIXIE_LLM_SLEEP_IDLE`; 0 = keep loaded); server wakes on next request
- Systemd: `pixie-llm.service` (ctx 4096) + `pixie-llm.socket` (disabled)
- Agent: `ask` (tools incl. art preview via pixie-art); `pixie-llm-run` is the systemd launcher

## Next
- [ ] Verify coder model end-to-end (tool calls, agent loop)
- [ ] Context/prompt hygiene: template for tools verified with qwen chat format
- [ ] Model fetch wizard (choose size/quant) — distro phase
- [ ] Memory: session continuity across reboots

## Notes
- Kur is a separate tiny model (smollm2-360m) on 8081 — do not conflate.
- `pixie-llm chat kur` garbage is a pre-existing template mismatch (kur's real path = `/generate` via kur-server).

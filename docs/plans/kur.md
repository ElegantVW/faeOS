# Kur — haiku dragon (easter egg)

**Role:** 10,000-year-old dragon who only speaks in haiku. Local LLM (smollm2-360m) + TTS voice. **Easter egg — hidden from `scroll`, discovered by the curious.**

**Status:** stable

## Current
- `kur` — haiku generation (local LLM + voice), `kur-server` (systemd, port 8083, `/generate`), `kur_voice.py`
- Model: `smollm2-360m-instruct-q4_k_m.gguf` (~350MB) on port 8081 (menagerie `kur` profile); loaded on demand via `menagerie start kur`; unloaded via `ExecStopPost` on daemon stop
- AI apps are independent: kur talks to menagerie's kur profile, not imp's server

## Next
- [ ] Haiku quality pass (prompt/temperature tuning)
- [ ] **Better TTS** — current piper voice "sucks"; candidates: kokoro (local, better quality, ~350MB) or higher-quality piper voice models. Until then piper libs stay local in `~/bin` (not shipped by install.sh)
- [ ] Keep hidden: no scroll entry, no README table row (only plan docs)

## Notes
- If someone runs `scroll` and finds no kur, that's the feature.

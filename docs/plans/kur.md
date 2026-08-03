# Kur — haiku dragon (easter egg)

**Role:** 10,000-year-old dragon who only speaks in haiku. Local LLM (smollm2-360m) + TTS voice. **Easter egg — hidden from `scroll`, discovered by the curious.**

**Status:** stable

## Current
- `kur` — haiku generation (local LLM + voice), `kur-server` (systemd, port 8081, `/generate`), `kur_voice.py`
- Model: `smollm2-360m-instruct-q4_k_m.gguf` (~350MB) on port 8081; loaded on demand via `pixie-llm start kur`

## Next
- [ ] Haiku quality pass (prompt/temperature tuning)
- [ ] More voices; speak on boot greeting?
- [ ] Keep hidden: no scroll entry, no README table row (only plan docs)

## Notes
- If someone runs `scroll` and finds no kur, that's the feature.

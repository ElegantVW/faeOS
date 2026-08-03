# Imp — terminal art generator

**Role:** Terminal art generator (ASCII/ANSI art) for faeOS — the playful side of the prompt. In development (separate opencode instance).

**Status:** in dev

## Current
- Precursor: `pixie-art` (art preview with pixie-screen hold; wired into ask tool use)

## Next (to confirm with the Imp instance)
- [ ] Command surface (`imp <prompt>`?)
- [ ] Art engine: patterns/palettes/seed + prompt variants
- [ ] Output targets: prompt decoration, siren cover art, spellbook icons
- [ ] Screen policy: holds via `pixie-screen` (see screen-policy.md)
- [ ] Scroll section (once it's a real app)

## Notes
- Must respect `PIXIE_UNICODE` and kmscon-safe output (like pixie-art).

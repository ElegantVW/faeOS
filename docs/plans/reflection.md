# Reflection — screenshots & gallery

**Role:** Capture the screen (full · window · region) and keep a pink-framed gallery of past mirrors. The looking-glass for faeOS.

**Status:** new (v1)

## Current
- `reflection` — TUI gallery (↑↓ · enter open · **v** toggle chafa|normal · f/w/r · d · **o** always real image)
- View modes (saved in `config.json`, env `REFLECTION_VIEW=`):
  - **chafa** — terminal art (symbols) in looking glass; enter = fullscreen chafa
  - **normal** — real image scaled into the looking glass (kitty icat / chafa sixel|kitty|iterm); enter = fullscreen scaled image
- `reflection full|window|region [--open|--normal|--chafa]`
- `reflection open [--chafa|--normal] [path]`
- `reflection view [chafa|normal]` — show/set default
- `reflection list [N]` · `last` · `backend`

## Capture backends (first that works)
1. **ImageMagick** `import` / `magick import` (full, window, interactive region)
2. `scrot` / `maim` / `grim` when present
3. Pure **ctypes + libX11** full-screen grab (PNG via Pillow if available, else ppm)

## Storage
`$XDG_DATA_HOME/faeos/reflection/shots/`  
Names: `YYYYMMDD-HHMMSS-mode.png`  
Index: `index.jsonl` (path, mode, ts, bytes, size)

## Next
- [ ] Delay countdown (`reflection full -d 3`)
- [ ] Copy path / image to Imbue
- [ ] Animated region highlight (optional)

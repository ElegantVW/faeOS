# Scroll — living book (page carousel)

**Role:** One **page per app**; Tab teaches faeOS; last leaf is PATH (print to prompt).  
**Status:** carousel + hermetic egg leaf (2026-08-16)

## Navigation
- **Tab / Shift-Tab** — next / previous page (curriculum order)  
- **1–9** — cast footer runes (**run** the spell)  
- **g / G + digit** — vim-style page jump (11–20 / 21–30)  
- **j/k · wheel** — scroll within a long page  
- **PATH leaf** — filter · Enter → print name for shell `print -z`  
- Layout: near-fullscreen panels with small margin so box edges show  

## Curriculum
See `CURRICULUM` in `scroll_pages.py`. Ends with **Sealed Leaf** (or **Kur** if hatched), then **PATH**.

## Sealed Leaf / egg
- Story: an **egg in the Menagerie** to hatch; points at **`murmur`** (babbling glass).  
- No hand-holding, no true name, no solve path in docs.  
- Leaf turns only after the player completes hatch tasks (not from murmur alone).  

## Content
`scroll_pages.py` — dossiers; fae tone; keys in How.  
Egg: `fae_egg.py` + hermetic/kur runtime pages · `murmur` oracle.

## Rule
New app ⇒ page in `PAGES` + slot in `CURRICULUM` before “shipped.”

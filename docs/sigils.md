# Sigils — one mark per app, pixels in the 16

House law (from `fae-kernel/docs/identity/IDENTITY.md`): the identity must
survive VGA text, serial ANSI, and a dumb 16-color terminal. Sources are
CP437-safe text. PNGs are derived, never the source of truth.

## Accent per app (ANSI code in brackets)

| App | Sigil | Accent |
|-----|-------|--------|
| Kindling | `fae-kernel/docs/identity/logo.txt` (the struck flame, keep) | Lilac 13 (`95`) |
| Bulwark house | `bulwark/assets/sigils/house.txt` (battlements) | Gold 14 (`93`) |
| Seal glass | `bulwark/assets/sigils/glass.txt` (padlock) | Ice 11 (`96`) |
| Pixie | `pixie/assets/sigils/pixie.txt` (spark) | Rose 4 (`31`) |
| Fairy Lantern | `fairy-lantern/assets/sigils/fairy.txt` (lantern) | Honey 6 (`33`) |
| Goblin | `goblin/assets/sigils/goblin.txt` (eared head) | Moss 2 (`32`) |
| Mourama | `mourama/assets/sigils/mourama.txt` (hillfort) | Dusk 1 (`34`) |
| Siren | `siren/assets/sigils/siren.txt` (waves) | Mist 3 (`36`) |
| Grove / faeOS | `faeOS/assets/sigils/grove.txt` (clearing) | Violet 5 (`35`) |
| Kur (later) | three lines 5-7-5 | Moon 15 (`97`) |
| Magpie (later) | forked feather | Periwinkle 9 (`94`) |

Night (`40` bg) behind all. Lilac stays Kindling's first-glyph color.

## Mascots

`pixie-art` renders committed term mascots (`assets/mascots/pixie.txt`,
`wizard.txt`, Rose/Violet). v1, hand-drawn, CP437. The old JPG/chafa path
is retired — the images were never committed and are gone.

## Derived visuals (policy)

Richer art (Perchance/FLUX generations, painted sets like Mourama's icons)
is welcome as *decoration*, chafa-rendered or shipped beside the client —
never as the identity source. A generator may produce PNGs; a script
(`sigil2png.py`, later) renders canonical previews from the `.txt` +
palette above. Vanguarda is excluded entirely (own branding book).

/* theme.h — the house palette, shape and motion, in one place.
 *
 * Every colour, dimension, duration and glyph the HUD uses is defined here.
 * If the house moves, this is the only file that changes.
 *
 * Colours are the i3 config's client.* colours, so the panel and the window
 * borders agree (faeOS/config/i3/config).
 */
#ifndef FAE_HUD_THEME_H
#define FAE_HUD_THEME_H

/* ── palette ─────────────────────────────────────────────────────────────── */

/* the void the panel blooms out of */
#define THEME_VOID      "#0a0508"
#define THEME_PANEL     "#2a1520"

#define THEME_PINK      "#ff2d55"   /* focus: border, selected row */
#define THEME_PINK_SOFT "#e879a0"
#define THEME_FG        "#ffe3ee"
#define THEME_FG_DIM    "#b0b0b8"
#define THEME_LILAC     "#d4b4e8"   /* header, hairlines, corner facets */

/* a row whose window lives on another workspace */
#define THEME_FAR       "#9d5c75"

/* ── type ────────────────────────────────────────────────────────────────── */

/* all-mono type, house rule */
#define THEME_FONT       "DejaVu Sans Mono"
#define THEME_SIZE_TITLE 13
#define THEME_SIZE_META  11

/* ── glyphs ──────────────────────────────────────────────────────────────── */

/* Verified present in DejaVu Sans Mono on this machine with
 * `fc-list ':charset=2B21' family`. The face does NOT have the hexagons
 * (U+2B21/2B22), so the crystal vocabulary is built from diamonds — which is
 * luckier, because a diamond inside a diamond is the most gem-like thing the
 * house face actually has. */
#define THEME_GLYPH_FOCUS "\xe2\x97\x88"   /* ◈ U+25C8 */
#define THEME_GLYPH_IDLE  "\xe2\x97\x87"   /* ◇ U+25C7 */
#define THEME_GLYPH_DOT   "\xc2\xb7"       /* · U+00B7 */

/* ── shape ───────────────────────────────────────────────────────────────── */

#define THEME_RADIUS      14   /* round corners; the Xft version had none */
#define THEME_PAD_X       20
#define THEME_PAD_Y       18
#define THEME_GLYPH_COL    2   /* cells reserved for ◈ / ◇ */
#define THEME_GAP         10
#define THEME_LINE_GAP     5   /* title to meta, inside a row */
#define THEME_ROW_GAP     12   /* row to row */
#define THEME_RULE_GAP     9   /* around the header/footer hairlines */
/* Corner diamonds. 14 keeps them inside the 14px corner arc AND clear of the
 * text, which starts at THEME_PAD_X=20. At 21 they sat on top of the first
 * character of the footer — a diamond overdrawing the "t" of "tab next". */
#define THEME_FACET_INSET 14
#define THEME_FACET_R      5
/* The bottom corner facets sit THEME_FACET_INSET from the edge, and the footer
 * used to land right on top of them — the first character of "tab next" was
 * being overdrawn by a diamond. */
#define THEME_FOOTER_CLEAR 18
#define THEME_GLOW_STEPS   5

/* Narrower and taller than the first version: the rows are two lines now, so
 * the panel spends its height instead of its width. */
#define THEME_MAX_W        560
#define THEME_MIN_W        470  /* short titles should not look stubby */
#define THEME_W_FRACTION  0.34   /* or this share of the screen, whichever is less */

/* more rows than this and the panel would outgrow the screen */
#define THEME_MAX_ROWS     14

/* ── motion, milliseconds ────────────────────────────────────────────────── */

#define THEME_BLOOM_IN     130   /* inset 14 -> 0, alpha 0 -> 1 */
#define THEME_ROW_START     60   /* first row begins here */
#define THEME_ROW_LAG       22   /* each row starts this much later */
#define THEME_ROW_FADE     130   /* one row's own fade */
#define THEME_WIPE_START   200   /* selected band begins wiping in */
#define THEME_WIPE         180
#define THEME_HOLD        1200   /* measured from the last row landing */

/* A quick tap still has to be readable. Measured before this existed: the
 * panel was on screen for 211ms — just the fade — which is a blink, not a
 * cue. The whole reason the panel exists is to say where you landed. */
#define THEME_TAP_HOLD     850
#define THEME_FADE_OUT     220

/* Failsafe for the keyboard grab: a stuck Alt can never hold the keyboard for
 * longer than this, whatever else goes wrong. See hold.c. */
#define THEME_MAX_HOLD     8

#endif /* FAE_HUD_THEME_H */

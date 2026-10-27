/* theme.h — house pink-chrome for the switcher, in one place.
 *
 * 256-color approximations of the same hues live in ~/bin/fae_termart.py
 * (PINK 175, BLUSH 218, PINK_DIM 132, SILVER 252, MUTED 245); these are the
 * truecolor originals for cairo. Surfaces match the kitty/i3 dark plum
 * family so the panel agrees with the desktop around it.
 */
#ifndef FAE_HUD_THEME_H
#define FAE_HUD_THEME_H

/* ── palette ─────────────────────────────────────────────────────────────── */

#define THEME_BG     "#1a0a12"   /* panel surface */
#define THEME_PINK   "#e879a0"   /* selection text + marker */
#define THEME_FG     "#ffe3ee"   /* selected-row text */
#define THEME_SILVER "#d0d0d0"   /* row text */
#define THEME_MUTED  "#8a8a8a"   /* footer labels */
#define THEME_ROSE   "#af5f87"   /* border + footer keys */

/* ── type ────────────────────────────────────────────────────────────────── */

#define THEME_FONT       "DejaVu Sans Mono"
#define THEME_SIZE_ROW   13
#define THEME_SIZE_FOOT  10

#define THEME_STR_(x) #x
#define THEME_STR(x)  THEME_STR_(x)
#define THEME_FONT_ROW  THEME_FONT ":size=" THEME_STR(THEME_SIZE_ROW)
#define THEME_FONT_FOOT THEME_FONT ":size=" THEME_STR(THEME_SIZE_FOOT)

/* ── the list ────────────────────────────────────────────────────────────── */
/* One full window title per row, "» " marking the selection. No icons, no
 * plates, no facets: the row text is the whole entry. DejaVu Sans Mono has
 * no ✦ U+2726 (checked with fc-list), so the marker is » U+00BB. */

#define THEME_PAD_X            18
#define THEME_PAD_Y            14
#define THEME_RADIUS           10
#define THEME_ROW_TOP_FRACTION 0.20
#define THEME_MIN_W            360
#define THEME_MAX_W            760
#define THEME_MAX_ROWS         16
#define THEME_ROW_GAP          4
#define THEME_FOOT_GAP         10

/* ── motion, milliseconds ────────────────────────────────────────────────── */

#define THEME_OUT         250   /* fade after focus has already moved */
#define THEME_MAX_HOLD    8     /* keyboard-grab failsafe, seconds */
#define TAB_REPEAT_MS     240   /* held Tab re-steps at this cadence */

#endif /* FAE_HUD_THEME_H */

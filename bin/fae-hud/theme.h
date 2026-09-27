/* theme.h — the house palette, shape and motion, in one place.
 *
 * Colours are the i3 config's client.* colours, so the panel and the window
 * borders agree (faeOS/config/i3/config).
 */
#ifndef FAE_HUD_THEME_H
#define FAE_HUD_THEME_H

/* ── palette ─────────────────────────────────────────────────────────────── */

#define THEME_VOID      "#0a0508"
#define THEME_PANEL     "#2a1520"
#define THEME_PINK      "#ff2d55"   /* the selection */
#define THEME_PINK_SOFT "#e879a0"
#define THEME_FG        "#ffe3ee"
#define THEME_FG_DIM    "#b0b0b8"
#define THEME_LILAC     "#d4b4e8"
#define THEME_FAR       "#9d5c75"

/* ── type ────────────────────────────────────────────────────────────────── */

/* all-mono type, house rule. Icons are images, so nothing here bends it. */
#define THEME_FONT       "DejaVu Sans Mono"
#define THEME_SIZE_LABEL 12
#define THEME_SIZE_META  10

#define THEME_STR_(x) #x
#define THEME_STR(x)  THEME_STR_(x)
#define THEME_FONT_LABEL THEME_FONT ":size=" THEME_STR(THEME_SIZE_LABEL)
#define THEME_FONT_META  THEME_FONT ":size=" THEME_STR(THEME_SIZE_META)

/* ── the strip ───────────────────────────────────────────────────────────── */

/* A macOS Cmd+Tab row: one icon per application, centred horizontally and
 * about a fifth of the way down, which is where macOS actually puts it. Not a
 * third down — that put it over the work without ever being a focal point. */
#define THEME_ROW_TOP_FRACTION 0.20
#define THEME_ICON_PX       64      /* icon size, and the _NET_WM_ICON target */
#define THEME_ICON_SEL_SCALE 1.15   /* the constant box; artwork scales inside it */
#define THEME_CELL_W        92      /* icon box + gaps: the per-entry stride  */
#define THEME_PAD_X         18
#define THEME_PAD_Y         16
#define THEME_RADIUS        18
#define THEME_LABEL_GAP     7
#define THEME_GLOW_STEPS    3
#define THEME_FACET_R       4
#define THEME_FACET_INSET   12

/* A strip never grows without bound: past this many apps the icons shrink,
 * and past this they would be unreadable so the row scrolls instead. */
#define THEME_MAX_FIT_SHRINK 14
#define THEME_MIN_ICON_PX     28

/* ── motion, milliseconds ────────────────────────────────────────────────── */

#define THEME_IN          110   /* bloom */
#define THEME_OUT         250   /* fade after the focus has already moved   */
#define THEME_MAX_HOLD    8     /* keyboard-grab failsafe; see hold.c        */

#endif /* FAE_HUD_THEME_H */

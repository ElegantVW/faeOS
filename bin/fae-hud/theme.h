/* theme.h — the house palette, in one place.
 *
 * Every colour the HUD paints comes from here. If the house palette moves,
 * this file is the only thing that changes.
 *
 * Values are the i3 config's client.* colours, so the HUD and the window
 * borders agree (faeOS/config/i3/config).
 */
#ifndef FAE_HUD_THEME_H
#define FAE_HUD_THEME_H

/* the void the HUD fades up out of */
#define THEME_VOID      "#0a0508"

/* panel */
#define THEME_PANEL     "#2a1520"
#define THEME_PANEL_DIM "#1a0a12"

/* the accent: focused window, highlighted row */
#define THEME_PINK      "#ff2d55"
#define THEME_PINK_SOFT "#e879a0"

/* text */
#define THEME_FG        "#ffe3ee"
#define THEME_FG_DIM    "#b0b0b8"
#define THEME_LILAC     "#d4b4e8"

/* a row whose window lives on another workspace */
#define THEME_FAR       "#9d5c75"

/* all-mono type, house rule */
#define THEME_FONT      "DejaVu Sans Mono"
#define THEME_FONT_SIZE 13

/* stringify, so the font pattern is built from the two macros above */
#define THEME_STR_(x) #x
#define THEME_STR(x)  THEME_STR_(x)
#define THEME_FONT_PATTERN THEME_FONT ":size=" THEME_STR(THEME_FONT_SIZE)

/* metrics, in pixels */
#define THEME_PAD_X     16
#define THEME_PAD_Y     12
#define THEME_LINE_GAP  7

/* timing, milliseconds */
#define THEME_FADE_IN   90
#define THEME_HOLD      1100
#define THEME_FADE_OUT  260

#endif /* FAE_HUD_THEME_H */

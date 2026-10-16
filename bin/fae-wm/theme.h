/* theme.h — house pink-chrome for fae-wm, in one place. */
#ifndef FAE_WM_THEME_H
#define FAE_WM_THEME_H

#define THEME_BG     "#1a0a12"   /* switcher panel surface */
#define THEME_PINK   "#e879a0"   /* selection + focused border */
#define THEME_FG     "#ffe3ee"
#define THEME_SILVER "#d0d0d0"   /* switcher rows */
#define THEME_MUTED  "#8a8a8a"   /* switcher footer */
#define THEME_ROSE   "#af5f87"   /* switcher border + footer keys */

#define THEME_FONT       "DejaVu Sans Mono"
#define THEME_SIZE_ROW   13
#define THEME_SIZE_FOOT  10

#define THEME_STR_(x) #x
#define THEME_STR(x)  THEME_STR_(x)
#define THEME_FONT_ROW  THEME_FONT ":size=" THEME_STR(THEME_SIZE_ROW)
#define THEME_FONT_FOOT THEME_FONT ":size=" THEME_STR(THEME_SIZE_FOOT)

#define THEME_PAD_X            18
#define THEME_PAD_Y            14
#define THEME_RADIUS           10
#define THEME_ROW_TOP_FRACTION 0.20
#define THEME_MIN_W            360
#define THEME_MAX_W            760
#define THEME_MAX_ROWS         16
#define THEME_ROW_GAP          4
#define THEME_FOOT_GAP         10

#define THEME_OUT         250
#define THEME_MAX_HOLD    8
#define TAB_REPEAT_MS     240

/* window chrome */
#define WM_BORDER_W     2
#define WM_GAP_OUTER    4
#define WM_NUDGE        20
#define WM_RESIZE_STEP  10
#define WM_CASCADE_STEP 32
#define WM_TITLE_H      0
#define WM_BTN_W        22

#endif /* FAE_WM_THEME_H */

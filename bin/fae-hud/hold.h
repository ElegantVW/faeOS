/* hold.h — the Alt+Tab gesture: open once, browse, commit once. */
#ifndef FAE_HUD_HOLD_H
#define FAE_HUD_HOLD_H

#include <X11/Xlib.h>
#include "entry.h"

/* Opens the strip, owns the keyboard while Alt is held, moves focus exactly
 * once — immediately, before the strip fades — and returns. */
int hold_cycle(Display *dpy, int scr, elist_t *apps);

#endif /* FAE_HUD_HOLD_H */

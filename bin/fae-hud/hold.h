/* hold.h — the Alt+Tab gesture: open once, browse, commit once. */
#ifndef FAE_HUD_HOLD_H
#define FAE_HUD_HOLD_H

#include <X11/Xlib.h>
#include "wm.h"

/* Returns 0 normally. Opens the panel, owns the keyboard while Alt is held,
 * moves focus exactly once on release (or not at all if cancelled). */
int hold_cycle(Display *dpy, int scr, wlist_t *list);

#endif /* FAE_HUD_HOLD_H */

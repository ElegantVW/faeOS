/* gesture.h — the Alt+Tab gesture: open once, browse, commit once. */
#ifndef FAE_HUD_GESTURE_H
#define FAE_HUD_GESTURE_H

#include <X11/Xlib.h>
#include "list.h"

/* Opens the panel, owns the keyboard while Alt is held, commits focus
 * exactly once on release (tap commits immediately), Esc cancels silent. */
int gesture_cycle(Display *dpy, int scr, winlist_t *apps);

#endif /* FAE_HUD_GESTURE_H */

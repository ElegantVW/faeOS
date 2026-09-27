/* hud.h — the overlay panel.
 */
#ifndef FAE_HUD_HUD_H
#define FAE_HUD_HUD_H

#include <X11/Xlib.h>
#include "wm.h"

/* Paint the panel for `list`, hold it, fade it, and return. Short-lived by
 * design: no resident process, nothing to keep alive. */
int hud_run(Display *dpy, int scr, wlist_t *list);

#endif /* FAE_HUD_HUD_H */

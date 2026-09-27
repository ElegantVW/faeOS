/* hud.h — the overlay panel.
 */
#ifndef FAE_HUD_HUD_H
#define FAE_HUD_HUD_H

#include <X11/Xlib.h>
#include "wm.h"

/* Paint the panel for `list`, hold it, fade it, and return. Short-lived by
 * design: no resident process, nothing to keep alive.
 *
 * force_opaque: skip the ARGB32 visual and paint a solid panel. Plain X11 has
 * no per-window alpha, so this is what you get on a server with no compositor.
 * Also settable with FAE_HUD_FORCE_OPAQUE=1, which is how the fallback gets
 * tested without stopping picom. */
int hud_run(Display *dpy, int scr, wlist_t *list, int force_opaque);

#endif /* FAE_HUD_HUD_H */

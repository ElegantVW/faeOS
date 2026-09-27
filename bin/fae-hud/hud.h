/* hud.h — the overlay panel.
 *
 * Two ways to use it:
 *
 *   hud_run()   paint, hold, fade, exit. Non-interactive, used by nothing
 *               that matters any more but kept because it is a useful
 *               "show me the list" for debugging and for scripts.
 *
 *   hud_open()  an interactive handle. The panel appears once, stays up, and
 *               hud_select() moves the highlight without re-animating. This is
 *               what the Alt+Tab cycler drives: one panel for the whole
 *               gesture, repainting only the two rows whose highlight moved.
 */
#ifndef FAE_HUD_HUD_H
#define FAE_HUD_HUD_H

#include <X11/Xlib.h>
#include "wm.h"

typedef struct hud hud_t;

/* force_opaque: skip the ARGB32 visual and paint a solid panel. Plain X11 has
 * no per-window alpha, so this is what you get with no compositor. Also
 * settable with FAE_HUD_FORCE_OPAQUE=1. */
hud_t *hud_open(Display *dpy, int scr, wlist_t *list, int sel, int force_opaque);

/* Move the highlight. Repaints only the rows that changed. */
void   hud_select(hud_t *h, int sel);

int    hud_rows(hud_t *h);
int    hud_selection(hud_t *h);

/* Fade out and destroy. Safe to call with h == NULL. */
void   hud_close(hud_t *h);

/* Convenience: the old non-interactive behaviour. */
int    hud_run(Display *dpy, int scr, wlist_t *list, int force_opaque);

#endif /* FAE_HUD_HUD_H */

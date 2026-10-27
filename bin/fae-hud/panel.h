/* panel.h — the minimal switcher panel. Draws the list, highlights one row. */
#ifndef FAE_HUD_PANEL_H
#define FAE_HUD_PANEL_H

#include <X11/Xlib.h>
#include "list.h"

typedef struct panel panel_t;

/* Opens the panel with `sel` highlighted. force_opaque drops the ARGB32
 * visual and paints solid, for a server with no compositor. */
panel_t   *panel_open(Display *dpy, int scr, winlist_t *apps, int sel,
                      int force_opaque);
void       panel_select(panel_t *p, int sel);
int        panel_count(panel_t *p);
Window     panel_target(panel_t *p);   /* selected window, or None */
Window     panel_xid_at(panel_t *p, int i); /* entry i's window, or None */
const char *panel_title(panel_t *p);  /* selected title, never NULL */
void       panel_close(panel_t *p);   /* 250ms fade, then destroy */

#endif /* FAE_HUD_PANEL_H */

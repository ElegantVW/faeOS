/* hud.h — the switcher strip. */
#ifndef FAE_HUD_HUD_H
#define FAE_HUD_HUD_H

#include <X11/Xlib.h>
#include "entry.h"

typedef struct hud hud_t;   /* defined in hud.c */

/* Opens the strip with `sel` highlighted. force_opaque drops the ARGB32
 * visual and paints solid, for a server with no compositor. */
hud_t *hud_open(Display *dpy, int scr, elist_t *apps, int sel,
                int force_opaque);

void    hud_select(hud_t *h, int sel);
int     hud_count(hud_t *h);
int     hud_selection(hud_t *h);
Window  hud_target(hud_t *h);      /* the X window to focus, or None */
const char *hud_label(hud_t *h);
void    hud_close(hud_t *h);

#endif /* FAE_HUD_HUD_H */

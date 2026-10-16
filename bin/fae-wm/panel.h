/* panel.h — the built-in switcher panel. Rows come from the WM's own
 * client list (exact recency, no ring file, no EWMH round-trips). */
#ifndef FAE_WM_PANEL_H
#define FAE_WM_PANEL_H

#include <X11/Xlib.h>
#include "client.h"

typedef struct panel panel_t;

panel_t   *panel_open(wm_t *wm, int sel, int force_opaque);
void       panel_select(panel_t *p, int sel);
int        panel_count(panel_t *p);
client_t  *panel_target(panel_t *p);
const char *panel_title(panel_t *p);
void       panel_close(panel_t *p);   /* 250ms fade, then destroy */

#endif /* FAE_WM_PANEL_H */

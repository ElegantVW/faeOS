/* dock.h — autohide glass pill. Round wells, hover scale, no status strip. */
#ifndef FAE_WM_DOCK_H
#define FAE_WM_DOCK_H

#include <X11/Xlib.h>
#include "client.h"

/* Reconcile tiles (pins + running). Shows/flashes as appropriate. */
void dock_refresh(wm_t *wm);
/* Destroy the dock window (WM shutdown). */
void dock_teardown(wm_t *wm);
/* Click / hover at root coords. */
void dock_click(wm_t *wm, int x_root, int y_root);
void dock_hover(wm_t *wm, int x_root, int y_root);
/* Bottom-edge proximity (root motion outside the dock). */
void dock_edge(wm_t *wm, int x_root, int y_root);
/* Tick: slide, hide timers, hover ease. Paint only while ease is live. */
void dock_tick(wm_t *wm);
/* Flash visible briefly (e.g. something just minimized). */
void dock_flash(wm_t *wm);
/* Super+= / Super+- : step the dock size and persist it. */
void dock_scale_nudge(wm_t *wm, int dir);
/* The dock window, for routing. None when never built. */
Window dock_win(wm_t *wm);
/* Reserved strip height (0: overlaying autohide needs none). */
int dock_reserve(wm_t *wm);

#endif /* FAE_WM_DOCK_H */

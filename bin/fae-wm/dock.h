/* dock.h — the macOS-type dock. Bottom-center pill, autohiding: surfaces
 * on a bottom-edge hover with a slide, hides after you leave. Tiles are
 * app sigils (ASCII art where the apps publish it, big initials otherwise)
 * with shimmer sweeps, labels beneath, pink dots for running. Click toggles
 * focus/minimize; click an idle pin to launch it. */
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
/* 50ms-tick driver: slide, hide timers, shimmer frames. */
void dock_tick(wm_t *wm);
/* Flash visible briefly (e.g. something just minimized). */
void dock_flash(wm_t *wm);
/* The dock window, for routing. None when never built. */
Window dock_win(wm_t *wm);
/* Reserved strip height (0: overlaying autohide needs none). */
int dock_reserve(wm_t *wm);

#endif /* FAE_WM_DOCK_H */

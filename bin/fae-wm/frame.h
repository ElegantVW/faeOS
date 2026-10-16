/* frame.h — titlebar frames: toolbar with – ▢ ×, painted on a frame window
 * the client is reparented into. House rule: »-style ASCII-safe glyphs drawn
 * as cairo paths, never font glyphs. */
#ifndef FAE_WM_FRAME_H
#define FAE_WM_FRAME_H

#include <X11/Xlib.h>
#include "client.h"

typedef enum { BTN_NONE, BTN_MIN, BTN_MAX, BTN_CLOSE } btn_t;

/* Outer frame geometry from the client area. */
void frame_outer(client_t *c, int bw, int th, int *x, int *y, int *w, int *h);

/* Build/destroy the frame around an already-placed client. */
int  frame_create(wm_t *wm, client_t *c);
void frame_destroy(wm_t *wm, client_t *c);   /* unreparents client to root */
void frame_layout(wm_t *wm, client_t *c);    /* re-fit after move/resize/state */
void frame_paint(wm_t *wm, client_t *c);     /* titlebar redraw */

/* Hit-test frame-relative coords. */
btn_t frame_hit(client_t *c, int bw, int th, int fx, int fy);
/* Press/release feed the click state machine; release fires the action. */
void frame_press(wm_t *wm, client_t *c, int fx, int fy);
void frame_release(wm_t *wm, client_t *c, int fx, int fy);

/* Route a subwindow xid to its client when it is a frame. */
client_t *frame_client(wm_t *wm, Window xid);

#endif /* FAE_WM_FRAME_H */

/* entry.h — the macOS-style model: one entry per APPLICATION, not per window.
 *
 * The previous panel listed every window, so three terminals meant three
 * near-identical rows and the list grew without bound. Deduplicating by
 * WM_CLASS is what makes a horizontal strip possible: the row stays as short
 * as the number of *apps*, which is the thing a human actually counts.
 *
 * The cost is real and worth stating: you cannot reach the second kitty
 * window with Tab. macOS solves that with Cmd+` — a separate "cycle within
 * this app" gesture — and `fae-hud --within` is that gesture.
 */
#ifndef FAE_HUD_ENTRY_H
#define FAE_HUD_ENTRY_H

#include <X11/Xlib.h>
#include <cairo/cairo.h>

typedef struct {
    char            *cls;      /* WM_CLASS instance half, e.g. "kitty"   */
    char            *label;    /* tidied for display, e.g. "Kitty"       */
    Window           xid;      /* topmost window belonging to this app   */
    int              count;    /* how many windows it owns               */
    cairo_surface_t *icon;     /* NULL when the client published none    */
} entry_t;

typedef struct {
    entry_t *v;
    int      n;
    int      cap;
} elist_t;

/* Applications, ordered most-recently-used first, with the app owning the
 * given focus rotated to the front. focus_xid may be None. */
elist_t *wm_list_apps(Display *dpy, Window root, Window focus_xid);

void     wm_apps_free(elist_t *l);

/* Windows of a single application, for --within. */
typedef struct {
    Window *v;
    char  **title;
    int     n;
} wlist_within_t;

wlist_within_t *wm_windows_of(Display *dpy, Window root, const char *cls);
void            wm_within_free(wlist_within_t *l);

#endif /* FAE_HUD_ENTRY_H */

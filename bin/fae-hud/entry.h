/* entry.h — one entry per WINDOW, ordered by recency.
 *
 * This was per-application first, as a macOS Cmd+Tab strip. That was wrong
 * for this machine: five kitty windows on one workspace collapsed into a
 * single "kitty" row, so the strip had one entry and Alt+Tab had nowhere to go
 * — it re-focused the app you were already in, and taps two through eight did
 * literally nothing. A switcher has to enumerate what you can actually switch
 * between, and on a terminal machine that is windows, not apps.
 *
 * The app icon still rides along, because it is the fastest way to recognise a
 * row. The label is the window's own title.
 */
#ifndef FAE_HUD_ENTRY_H
#define FAE_HUD_ENTRY_H

#include <X11/Xlib.h>
#include <cairo/cairo.h>

typedef struct {
    char            *cls;      /* WM_CLASS instance, e.g. "kitty"         */
    char            *label;    /* the window's own title                   */
    Window           xid;
    cairo_surface_t *icon;     /* NULL when the client published none      */
} entry_t;

typedef struct {
    entry_t *v;
    int      n;
    int      cap;
} elist_t;

/* Windows, most-recently-used first, with `focus_xid` forced to index 0.
 * same_workspace_only scopes browsing to _NET_CURRENT_DESKTOP. */
elist_t *wm_list_entries(Display *dpy, Window root, Window focus_xid,
                         int same_workspace_only);

void     wm_entries_free(elist_t *l);

#endif /* FAE_HUD_ENTRY_H */

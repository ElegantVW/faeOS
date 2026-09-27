/* wm.h — the window model, read-only.
 *
 * See wm.c for why this layer is EWMH-only and never mutates anything.
 */
#ifndef FAE_HUD_WM_H
#define FAE_HUD_WM_H

#include <X11/Xlib.h>

typedef struct {
    Window   xid;
    char    *title;          /* never NULL */
    char    *cls;            /* never NULL, WM_CLASS instance half */
    unsigned long desktop;   /* _NET_WM_DESKTOP */
    int      desktop_known;  /* 0 if the property was absent */
    int      on_current_workspace;
    int      is_active;      /* == _NET_ACTIVE_WINDOW */
    int      is_focus_target;/* == the window fae-cycle just focused */
} win_t;

typedef struct {
    win_t    *v;
    int       n;
    int       cap;
    Window    active;
    Window    focus_xid;
    int       has_explicit_focus; /* 1 when fae-cycle named the window */
    unsigned long current_desktop;
} wlist_t;

unsigned long wm_cardinal(Display *dpy, Window w, const char *name, int *ok);
Window        wm_window_prop(Display *dpy, Window w, const char *name);
char         *wm_text_prop(Display *dpy, Window w, const char *name);
char         *wm_title(Display *dpy, Window w);
char         *wm_class(Display *dpy, Window w);

/* Small accessors the switcher and the app model need. */
Window        wm_active(Display *dpy, Window root);
unsigned long wm_current_desktop(Display *dpy, Window root);
Window       *wm_stacking(Display *dpy, Window root, unsigned long *n);

/* 1 when the window belongs to `current`. A window with no _NET_WM_DESKTOP at
 * all counts as belonging: some WMs do not set it, and dropping those would
 * silently hide real clients from the switcher. */
int           wm_desktop_of(Display *dpy, Window xid, unsigned long current);

wlist_t *wm_list_windows(Display *dpy, Window root, Window focus_xid);

/* Only the windows on the current workspace. Cycling is scoped this way so
 * that browsing can never make the WM follow focus onto another workspace and
 * hide everything you were looking at — which is what read as "the other
 * windows got minimized".
 *
 * A window whose _NET_WM_DESKTOP is absent is kept: some WMs do not set it,
 * and dropping those windows would silently hide real clients. */
wlist_t *wm_list_workspace(Display *dpy, Window root, Window focus_xid);

void     wm_list_free_titles(wlist_t *l);
void     wm_list_free(wlist_t *l);

#endif /* FAE_HUD_WM_H */

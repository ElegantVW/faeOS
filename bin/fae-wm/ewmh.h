/* ewmh.h — atoms and root properties we serve. Clients (bars, pagers,
 * screenshot scripts) read these; the WM itself keeps its own state. */
#ifndef FAE_WM_EWMH_H
#define FAE_WM_EWMH_H

#include <X11/Xlib.h>

typedef struct {
    Atom supported;
    Atom client_list, client_list_stacking;
    Atom active_window, current_desktop, number_of_desktops, desktop_names;
    Atom wm_desktop, wm_state, wm_state_fullscreen;
    Atom wm_state_maxv, wm_state_maxh;
    Atom wm_window_type, wm_window_type_dock, wm_window_type_desktop;
    Atom wm_window_type_dialog, wm_window_type_utility, wm_window_type_splash;
    Atom close_window;
    Atom wm_name, wm_class, utf8_string;
    Atom wm_protocols, wm_delete_window;
} atoms_t;

void atoms_init(Display *dpy, atoms_t *a);

/* Publish the static root properties (supported list, desktop count). */
void ewmh_publish(Display *dpy, Window root, atoms_t *a, int ndesks);

/* Refresh per-state root properties from the WM's own lists. */
void ewmh_update_clients(Display *dpy, Window root, atoms_t *a,
                         Window *stack, int n);
void ewmh_update_active(Display *dpy, Window root, atoms_t *a, Window active);
void ewmh_update_desktop(Display *dpy, Window root, atoms_t *a, int desk);

/* Ask a client to take focus (pager source), or to close itself. */
void ewmh_request_focus(Display *dpy, Window root, atoms_t *a, Window w);
void ewmh_request_close(Display *dpy, Window root, atoms_t *a, Window w);

/* Window title, UTF-8 preferred. Never NULL. Caller frees. */
char *ewmh_title(Display *dpy, atoms_t *a, Window w);
/* Instance/class string (before the NUL), or "app". Caller frees. */
char *ewmh_class(Display *dpy, Window w);
/* _NET_WM_PID, or -1. */
long ewmh_pid(Display *dpy, Window w);

#endif /* FAE_WM_EWMH_H */

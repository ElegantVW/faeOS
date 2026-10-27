/* ewmh.c — the atoms we serve and the messages we send. */
#include "ewmh.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include <X11/Xlib.h>
#include <X11/Xatom.h>

void atoms_init(Display *dpy, atoms_t *a)
{
    memset(a, 0, sizeof *a);
    a->supported            = XInternAtom(dpy, "_NET_SUPPORTED", False);
    a->client_list          = XInternAtom(dpy, "_NET_CLIENT_LIST", False);
    a->client_list_stacking = XInternAtom(dpy, "_NET_CLIENT_LIST_STACKING", False);
    a->active_window        = XInternAtom(dpy, "_NET_ACTIVE_WINDOW", False);
    a->current_desktop      = XInternAtom(dpy, "_NET_CURRENT_DESKTOP", False);
    a->number_of_desktops   = XInternAtom(dpy, "_NET_NUMBER_OF_DESKTOPS", False);
    a->desktop_names        = XInternAtom(dpy, "_NET_DESKTOP_NAMES", False);
    a->wm_desktop           = XInternAtom(dpy, "_NET_WM_DESKTOP", False);
    a->wm_state             = XInternAtom(dpy, "_NET_WM_STATE", False);
    a->wm_state_fullscreen  = XInternAtom(dpy, "_NET_WM_STATE_FULLSCREEN", False);
    a->wm_state_maxv        = XInternAtom(dpy, "_NET_WM_STATE_MAXIMIZED_VERT", False);
    a->wm_state_maxh        = XInternAtom(dpy, "_NET_WM_STATE_MAXIMIZED_HORZ", False);
    a->wm_window_type       = XInternAtom(dpy, "_NET_WM_WINDOW_TYPE", False);
    a->wm_window_type_dock  = XInternAtom(dpy, "_NET_WM_WINDOW_TYPE_DOCK", False);
    a->wm_window_type_desktop = XInternAtom(dpy, "_NET_WM_WINDOW_TYPE_DESKTOP", False);
    a->wm_window_type_dialog  = XInternAtom(dpy, "_NET_WM_WINDOW_TYPE_DIALOG", False);
    a->wm_window_type_utility = XInternAtom(dpy, "_NET_WM_WINDOW_TYPE_UTILITY", False);
    a->wm_window_type_splash  = XInternAtom(dpy, "_NET_WM_WINDOW_TYPE_SPLASH", False);
    a->close_window         = XInternAtom(dpy, "_NET_CLOSE_WINDOW", False);
    a->wm_name              = XInternAtom(dpy, "_NET_WM_NAME", False);
    a->wm_class             = XInternAtom(dpy, "WM_CLASS", False);
    a->utf8_string          = XInternAtom(dpy, "UTF8_STRING", False);
    a->wm_protocols         = XInternAtom(dpy, "WM_PROTOCOLS", False);
    a->wm_delete_window     = XInternAtom(dpy, "WM_DELETE_WINDOW", False);
}

void ewmh_publish(Display *dpy, Window root, atoms_t *a, int ndesks)
{
    Atom supported[] = {
        a->client_list, a->client_list_stacking, a->active_window,
        a->current_desktop, a->number_of_desktops, a->desktop_names,
        a->wm_desktop, a->wm_state, a->wm_state_fullscreen,
        a->wm_state_maxv, a->wm_state_maxh,
        a->wm_window_type, a->close_window,
    };
    XChangeProperty(dpy, root, a->supported, XA_ATOM, 32, PropModeReplace,
                    (unsigned char *)supported,
                    sizeof supported / sizeof supported[0]);
    unsigned long n = (unsigned long)ndesks;
    XChangeProperty(dpy, root, a->number_of_desktops, XA_CARDINAL, 32,
                    PropModeReplace, (unsigned char *)&n, 1);
    char names[256] = { 0 };
    int at = 0;
    for (int i = 1; i <= ndesks && at < (int)sizeof names - 4; i++)
        at += snprintf(names + at, sizeof names - (size_t)at, "%d", i) + 1;
    XChangeProperty(dpy, root, a->desktop_names, a->utf8_string, 8,
                    PropModeReplace, (unsigned char *)names, at);
    XChangeProperty(dpy, root, a->current_desktop, XA_CARDINAL, 32,
                    PropModeReplace, (unsigned char *)&n, 0);
    unsigned long zero = 0;
    XChangeProperty(dpy, root, a->current_desktop, XA_CARDINAL, 32,
                    PropModeReplace, (unsigned char *)&zero, 1);
}

void ewmh_update_clients(Display *dpy, Window root, atoms_t *a,
                         Window *stack, int n)
{
    XChangeProperty(dpy, root, a->client_list, XA_WINDOW, 32,
                    PropModeReplace, (unsigned char *)stack, n);
    XChangeProperty(dpy, root, a->client_list_stacking, XA_WINDOW, 32,
                    PropModeReplace, (unsigned char *)stack, n);
}

void ewmh_update_active(Display *dpy, Window root, atoms_t *a, Window active)
{
    if (active == None) {
        XDeleteProperty(dpy, root, a->active_window);
        return;
    }
    XChangeProperty(dpy, root, a->active_window, XA_WINDOW, 32,
                    PropModeReplace, (unsigned char *)&active, 1);
}

void ewmh_update_desktop(Display *dpy, Window root, atoms_t *a, int desk)
{
    unsigned long d = (unsigned long)desk;
    XChangeProperty(dpy, root, a->current_desktop, XA_CARDINAL, 32,
                    PropModeReplace, (unsigned char *)&d, 1);
}

static void send_client(Display *dpy, Window root, Window w, Atom msg,
                        long d0, long d1)
{
    XEvent e;
    memset(&e, 0, sizeof e);
    e.xclient.type = ClientMessage;
    e.xclient.window = w;
    e.xclient.message_type = msg;
    e.xclient.format = 32;
    e.xclient.data.l[0] = d0;
    e.xclient.data.l[1] = d1;
    XSendEvent(dpy, root, False,
               SubstructureNotifyMask | SubstructureRedirectMask, &e);
    XFlush(dpy);
}

void ewmh_request_focus(Display *dpy, Window root, atoms_t *a, Window w)
{
    send_client(dpy, root, w, a->active_window, 2, CurrentTime);
}

void ewmh_request_close(Display *dpy, Window root, atoms_t *a, Window w)
{
    send_client(dpy, root, w, a->close_window, CurrentTime, 2);
}

char *ewmh_class(Display *dpy, Window w)
{
    Atom actual_type;
    int actual_format;
    unsigned long nitems, bytes_after;
    unsigned char *data = NULL;
    Atom a = XInternAtom(dpy, "WM_CLASS", False);
    if (XGetWindowProperty(dpy, w, a, 0, 256, False, AnyPropertyType,
                           &actual_type, &actual_format, &nitems,
                           &bytes_after, &data) != Success)
        return strdup("app");
    char *out = strdup("app");
    if (data) {
        if (nitems > 0 && data[0]) {
            free(out);
            out = calloc(nitems + 1, 1);
            memcpy(out, data, nitems);
        }
        XFree(data);
    }
    return out;
}

long ewmh_pid(Display *dpy, Window w)
{
    Atom a = XInternAtom(dpy, "_NET_WM_PID", False);
    Atom actual_type;
    int actual_format;
    unsigned long nitems, bytes_after;
    unsigned char *data = NULL;
    long pid = -1;
    if (XGetWindowProperty(dpy, w, a, 0, 1, False, XA_CARDINAL,
                           &actual_type, &actual_format, &nitems,
                           &bytes_after, &data) == Success) {
        if (data && nitems >= 1 && actual_format == 32)
            pid = (long)*(unsigned long *)data;
        if (data) XFree(data);
    }
    return pid;
}

char *ewmh_title(Display *dpy, atoms_t *a, Window w)
{
    const Atom names[] = { a->wm_name, XA_WM_NAME };
    for (int k = 0; k < 2; k++) {
        Atom actual_type;
        int actual_format;
        unsigned long nitems, bytes_after;
        unsigned char *data = NULL;
        if (XGetWindowProperty(dpy, w, names[k], 0, 1024, False,
                               AnyPropertyType, &actual_type, &actual_format,
                               &nitems, &bytes_after, &data) != Success)
            continue;
        if (data) {
            if (nitems > 0) {
                char *out = calloc(nitems + 1, 1);
                memcpy(out, data, nitems);
                XFree(data);
                if (*out) return out;
                free(out);
                continue;
            }
            XFree(data);
        }
    }
    return strdup("window");
}

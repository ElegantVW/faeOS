/* wm.c — the window model.
 *
 * Read-only. This file never focuses, kills, moves or resizes anything; it
 * only asks X what is true. That separation is deliberate: fae-cycle owns
 * state changes, the HUD only draws them. A drawing bug can therefore never
 * cost you a window.
 *
 * Everything here is EWMH (Extended Window Manager Hints), which every X
 * window manager implements. That is the point: this file has no idea i3
 * exists, and would work unchanged under any other WM.
 */
#include "wm.h"

#include <stdlib.h>
#include <string.h>
#include <stdio.h>

#include <X11/Xlib.h>
#include <X11/Xatom.h>

/* ── raw property readers ─────────────────────────────────────────────────── */

/* Read a CARDINAL/ATOM property. Returns 0 and sets *ok=0 when absent. */
unsigned long wm_cardinal(Display *dpy, Window w, const char *name, int *ok)
{
    Atom a = XInternAtom(dpy, name, False);
    Atom actual_type;
    int actual_format;
    unsigned long nitems, bytes_after;
    unsigned char *data = NULL;

    *ok = 0;
    if (a == None) return 0;
    if (XGetWindowProperty(dpy, w, a, 0, 1, False, AnyPropertyType,
                           &actual_type, &actual_format, &nitems,
                           &bytes_after, &data) != Success)
        return 0;
    if (data) {
        if (nitems >= 1 && actual_format == 32) {
            unsigned long v = *(unsigned long *)data;
            XFree(data);
            *ok = 1;
            return v;
        }
        XFree(data);
    }
    return 0;
}

Window wm_window_prop(Display *dpy, Window w, const char *name)
{
    Atom a = XInternAtom(dpy, name, False);
    Atom actual_type;
    int actual_format;
    unsigned long nitems, bytes_after;
    unsigned char *data = NULL;

    if (a == None) return None;
    if (XGetWindowProperty(dpy, w, a, 0, 1, False, AnyPropertyType,
                           &actual_type, &actual_format, &nitems,
                           &bytes_after, &data) != Success)
        return None;
    Window v = None;
    if (data) {
        if (nitems >= 1 && actual_format == 32) v = *(Window *)data;
        XFree(data);
    }
    return v;
}

/* Read a text property. _NET_WM_NAME is UTF8_STRING and is preferred over
 * WM_NAME, which is latin-1 and frequently useless. Caller frees. */
char *wm_text_prop(Display *dpy, Window w, const char *name)
{
    Atom a = XInternAtom(dpy, name, False);
    Atom actual_type;
    int actual_format;
    unsigned long nitems, bytes_after;
    unsigned char *data = NULL;
    char *out = NULL;

    if (a == None) return NULL;
    if (XGetWindowProperty(dpy, w, a, 0, 1024, False, AnyPropertyType,
                           &actual_type, &actual_format, &nitems,
                           &bytes_after, &data) != Success)
        return NULL;
    if (data) {
        if (nitems > 0) {
            out = calloc(nitems + 1, 1);
            memcpy(out, data, nitems);
        }
        XFree(data);
    }
    return out;
}

char *wm_title(Display *dpy, Window w)
{
    char *t = wm_text_prop(dpy, w, "_NET_WM_NAME");
    if (t && *t) return t;
    if (t) { free(t); t = NULL; }
    t = wm_text_prop(dpy, w, "WM_NAME");
    if (t) return t;
    return strdup("window");
}

char *wm_class(Display *dpy, Window w)
{
    char *c = wm_text_prop(dpy, w, "WM_CLASS");
    if (!c || !*c) { free(c); return strdup("app"); }
    /* WM_CLASS is "instance\0class\0" — the instance is the friendlier half */
    return c;
}

/* ── the list ────────────────────────────────────────────────────────────── */

void wm_list_free(wlist_t *l)
{
    if (!l) return;
    free(l->v);
    free(l);
}

static void push(wlist_t *l, const win_t *w)
{
    if (l->n == l->cap) {
        l->cap = l->cap ? l->cap * 2 : 16;
        l->v = realloc(l->v, (size_t)l->cap * sizeof(win_t));
    }
    l->v[l->n++] = *w;
}

/* Read _NET_CLIENT_LIST_STACKING (bottom-to-top). Fall back to
 * _NET_CLIENT_LIST, which is the same list without stacking order. */
static Window *stacking_list(Display *dpy, Window root, unsigned long *out_n)
{
    for (int pass = 0; pass < 2; pass++) {
        const char *name = pass == 0 ? "_NET_CLIENT_LIST_STACKING"
                                     : "_NET_CLIENT_LIST";
        Atom a = XInternAtom(dpy, name, False);
        Atom actual_type;
        int actual_format;
        unsigned long nitems, bytes_after;
        unsigned char *data = NULL;
        if (a == None) continue;
        if (XGetWindowProperty(dpy, root, a, 0, 4096, False, AnyPropertyType,
                               &actual_type, &actual_format, &nitems,
                               &bytes_after, &data) != Success)
            continue;
        if (data) {
            if (nitems > 0 && actual_format == 32) {
                Window *wins = calloc(nitems, sizeof(Window));
                memcpy(wins, data, nitems * sizeof(Window));
                XFree(data);
                *out_n = nitems;
                return wins;
            }
            XFree(data);
        }
    }
    *out_n = 0;
    return NULL;
}

wlist_t *wm_list_windows(Display *dpy, Window root, Window focus_xid)
{
    int ok = 0;
    wlist_t *l = calloc(1, sizeof(wlist_t));
    unsigned long n = 0;
    Window *wins = stacking_list(dpy, root, &n);

    l->current_desktop = wm_cardinal(dpy, root, "_NET_CURRENT_DESKTOP", &ok);
    if (!ok) l->current_desktop = 0;
    l->active = wm_window_prop(dpy, root, "_NET_ACTIVE_WINDOW");
    if (focus_xid != None) {
        l->focus_xid = focus_xid;
        l->has_explicit_focus = 1;
    }

    for (unsigned long i = 0; i < n; i++) {
        win_t w;
        memset(&w, 0, sizeof w);
        w.xid = wins[i];
        w.title = wm_title(dpy, wins[i]);
        w.cls = wm_class(dpy, wins[i]);
        w.desktop = wm_cardinal(dpy, wins[i], "_NET_WM_DESKTOP", &ok);
        w.desktop_known = ok ? 1 : 0;
        w.on_current_workspace =
            (ok && w.desktop == l->current_desktop) ? 1 : 0;
        w.is_active = (wins[i] == l->active) ? 1 : 0;
        w.is_focus_target = (wins[i] == l->focus_xid) ? 1 : 0;
        push(l, &w);
    }
    free(wins);

    /* Rotate so the window we are highlighting sits at the top of the list.
     * Tap-to-cycle then reads naturally: row 0 is "you are here", row 1 is
     * where the next Alt+Tab lands. Without this the highlight jumps around
     * the panel on every press and the list is unreadable. */
    if (l->n > 1) {
        int at = -1;
        for (int i = 0; i < l->n; i++) {
            int hit = l->has_explicit_focus ? l->v[i].is_focus_target
                                            : l->v[i].is_active;
            if (hit) { at = i; break; }
        }
        if (at > 0) {
            win_t *tmp = malloc((size_t)l->n * sizeof(win_t));
            for (int i = 0; i < l->n; i++) tmp[i] = l->v[(at + i) % l->n];
            free(l->v);
            l->v = tmp;
        }
    }
    return l;
}

void wm_list_free_titles(wlist_t *l)
{
    for (int i = 0; i < l->n; i++) {
        free(l->v[i].title);
        free(l->v[i].cls);
    }
}

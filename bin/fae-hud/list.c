/* list.c — the window list: EWMH reads, focus-first rotation, MRU ring file.
 *
 * Ordering (this order matters, see below):
 *   1. ring: persisted order pruned to live windows, then anything unseen in
 *      stacking order, topmost first (seeds a cold login)
 *   2. rotated cyclically so the focused window is index 0 — a rotation, not
 *      a re-sort. Prepending focus and emitting the ring minus it destroys the
 *      cyclic order and Alt+Tab toggles between two windows forever.
 *   3. scoped to _NET_CURRENT_DESKTOP (missing _NET_WM_DESKTOP counts as here;
 *      better a window on the wrong workspace than a hidden client).
 */
#include "list.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#include <X11/Xlib.h>
#include <X11/Xatom.h>

/* ── raw property readers ────────────────────────────────────────────────── */

static unsigned long prop_cardinal(Display *dpy, Window w, const char *name,
                                   int *ok)
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
    unsigned long v = 0;
    if (data) {
        if (nitems >= 1 && actual_format == 32) {
            v = *(unsigned long *)data;
            *ok = 1;
        }
        XFree(data);
    }
    return v;
}

static Window prop_window(Display *dpy, Window w, const char *name)
{
    Atom a = XInternAtom(dpy, name, False);
    Atom actual_type;
    int actual_format;
    unsigned long nitems, bytes_after;
    unsigned char *data = NULL;
    Window v = None;
    if (a == None) return None;
    if (XGetWindowProperty(dpy, w, a, 0, 1, False, AnyPropertyType,
                           &actual_type, &actual_format, &nitems,
                           &bytes_after, &data) != Success)
        return None;
    if (data) {
        if (nitems >= 1 && actual_format == 32) v = *(Window *)data;
        XFree(data);
    }
    return v;
}

/* _NET_WM_NAME (UTF-8) preferred; WM_NAME fallback; never empty. */
static char *prop_title(Display *dpy, Window w)
{
    const char *names[] = { "_NET_WM_NAME", "WM_NAME" };
    for (int k = 0; k < 2; k++) {
        Atom a = XInternAtom(dpy, names[k], False);
        Atom actual_type;
        int actual_format;
        unsigned long nitems, bytes_after;
        unsigned char *data = NULL;
        if (a == None) continue;
        if (XGetWindowProperty(dpy, w, a, 0, 1024, False, AnyPropertyType,
                               &actual_type, &actual_format, &nitems,
                               &bytes_after, &data) != Success)
            continue;
        if (data) {
            if (nitems > 0) {
                char *out = calloc(nitems + 1, 1);
                memcpy(out, data, nitems);
                XFree(data);
                if (*out) return out;
                free(out);
                if (k == 0) continue;
                break;
            }
            XFree(data);
        }
    }
    return strdup("window");
}

/* _NET_CLIENT_LIST_STACKING (bottom-to-top), else _NET_CLIENT_LIST. */
static Window *stacking_list(Display *dpy, Window root, unsigned long *out_n)
{
    const char *names[] = { "_NET_CLIENT_LIST_STACKING", "_NET_CLIENT_LIST" };
    for (int pass = 0; pass < 2; pass++) {
        Atom a = XInternAtom(dpy, names[pass], False);
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

static int contains(const Window *v, int n, Window w)
{
    for (int i = 0; i < n; i++) if (v[i] == w) return 1;
    return 0;
}

/* ── the list ────────────────────────────────────────────────────────────── */

winlist_t *list_windows(Display *dpy, Window root, Window focus, int all_ws)
{
    winlist_t *l = calloc(1, sizeof *l);
    if (!l) return NULL;
    unsigned long nlive = 0;
    Window *live = stacking_list(dpy, root, &nlive);
    if (!live) return l;

    int ok = 0;
    unsigned long cur = prop_cardinal(dpy, root, "_NET_CURRENT_DESKTOP", &ok);
    if (!ok) cur = 0;

    Window scope[MRU_MAX];
    int nscope = 0;
    for (unsigned long i = 0; i < nlive && nscope < MRU_MAX; i++) {
        if (all_ws) { scope[nscope++] = live[i]; continue; }
        int dok = 0;
        unsigned long d = prop_cardinal(dpy, live[i], "_NET_WM_DESKTOP", &dok);
        if (!dok || d == cur) scope[nscope++] = live[i];
    }

    Window ring[MRU_MAX];
    int nring = 0;
    Window seen[MRU_MAX];
    int nseen = 0;
    Window prev[MRU_MAX];
    int nprev = mru_load(prev, MRU_MAX);
    for (int i = 0; i < nprev && nring < MRU_MAX; i++)
        if (contains(scope, nscope, prev[i]) && !contains(seen, nseen, prev[i])) {
            seen[nseen++] = prev[i];
            ring[nring++] = prev[i];
        }
    for (unsigned long i = nlive; i > 0 && nring < MRU_MAX; i--)
        if (contains(scope, nscope, live[i - 1]) &&
            !contains(seen, nseen, live[i - 1])) {
            seen[nseen++] = live[i - 1];
            ring[nring++] = live[i - 1];
        }

    int start = 0;
    if (focus != None)
        for (int i = 0; i < nring; i++)
            if (ring[i] == focus) { start = i; break; }

    for (int k = 0; k < nring; k++) {
        Window w = ring[(start + k) % nring];
        win_t e;
        e.xid = w;
        e.title = prop_title(dpy, w);
        win_t *nv = realloc(l->v, (size_t)(l->n + 1) * sizeof(win_t));
        if (!nv) { free(e.title); break; }
        l->v = nv;
        l->v[l->n++] = e;
    }
    free(live);
    return l;
}

void list_free(winlist_t *l)
{
    if (!l) return;
    for (int i = 0; i < l->n; i++) free(l->v[i].title);
    free(l->v);
    free(l);
}

Window list_active(Display *dpy, Window root)
{
    return prop_window(dpy, root, "_NET_ACTIVE_WINDOW");
}

/* ── MRU ring file ───────────────────────────────────────────────────────── */

const char *mru_path(void)
{
    static char buf[512];
    const char *d = getenv("XDG_RUNTIME_DIR");
    if (!d || !*d) d = "/tmp";
    snprintf(buf, sizeof buf, "%s/fae-hud.mru", d);
    return buf;
}

int mru_load(Window *out, int max)
{
    FILE *f = fopen(mru_path(), "r");
    int n = 0;
    if (!f) return 0;
    while (n < max && n < MRU_MAX) {
        unsigned long v;
        if (fscanf(f, "%lx", &v) != 1) break;
        if (v) out[n++] = (Window)v;
    }
    fclose(f);
    return n;
}

void mru_note(const Window *live, int nlive)
{
    Window prev[MRU_MAX];
    int nprev = mru_load(prev, MRU_MAX);
    Window next[MRU_MAX];
    int nnext = 0;
    /* Survivors keep their slots, in order. */
    for (int i = 0; i < nprev && nnext < MRU_MAX; i++)
        if (contains(live, nlive, prev[i]) && !contains(next, nnext, prev[i]))
            next[nnext++] = prev[i];
    /* The new appends. Never prepend: front-insertion reverses the cyclic
     * order and Alt+Tab toggles between two windows forever. */
    for (int i = 0; i < nlive && nnext < MRU_MAX; i++)
        if (!contains(next, nnext, live[i]))
            next[nnext++] = live[i];
    FILE *f = fopen(mru_path(), "w");
    if (!f) return;
    for (int i = 0; i < nnext; i++) fprintf(f, "%lx\n", (unsigned long)next[i]);
    fclose(f);
}

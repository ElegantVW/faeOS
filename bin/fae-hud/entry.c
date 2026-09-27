/* entry.c — build the application list.
 *
 * Reads only EWMH, and has no idea a window manager exists beyond the root
 * window. Order is most-recently-used: _NET_CLIENT_LIST_STACKING is
 * bottom-to-top, so walking it backwards gives the topmost window first, and
 * the first window seen for a class is that app's most recent one.
 */
#include "entry.h"
#include "icon.h"
#include "wm.h"
#include "theme.h"

#include <ctype.h>
#include <stdlib.h>
#include <string.h>

static void push(elist_t *l, const entry_t *e)
{
    if (l->n == l->cap) {
        l->cap = l->cap ? l->cap * 2 : 8;
        l->v = realloc(l->v, (size_t)l->cap * sizeof(entry_t));
    }
    l->v[l->n++] = *e;
}

/* "kitty" -> "Kitty", "org.mozilla.firefox" -> "Firefox" */
static char *tidy(const char *cls)
{
    const char *base = cls;
    const char *p;
    for (p = cls; *p; p++)
        if (*p == '.') base = p + 1;
    size_t n = strlen(base);
    char *out = malloc(n + 1);
    for (size_t i = 0; i < n; i++) {
        char c = base[i];
        if (c == '-' || c == '_') c = ' ';
        out[i] = (char)tolower((unsigned char)c);
    }
    out[n] = '\0';
    if (n > 0) out[0] = (char)toupper((unsigned char)out[0]);
    return out;
}

elist_t *wm_list_apps(Display *dpy, Window root, Window focus_xid)
{
    elist_t *l = calloc(1, sizeof *l);
    unsigned long n = 0;
    Window *wins = wm_stacking(dpy, root, &n);   /* bottom-to-top */
    if (!wins) return l;

    /* reverse: topmost first */
    for (unsigned long k = n; k > 0; k--) {
        Window w = wins[k - 1];
        char *cls = wm_class(dpy, w);
        if (!cls || !*cls) cls = strdup("app");

        int seen = -1;
        for (int i = 0; i < l->n; i++)
            if (strcmp(l->v[i].cls, cls) == 0) { seen = i; break; }

        if (seen >= 0) {
            l->v[seen].count++;
            free(cls);
            continue;
        }
        entry_t e;
        memset(&e, 0, sizeof e);
        e.cls   = cls;
        e.label = tidy(cls);
        e.xid   = w;
        e.count = 1;
        e.icon  = icon_load(dpy, w, THEME_ICON_PX);
        push(l, &e);
    }
    free(wins);

    /* Rotate so the app that has focus is first; the initial selection is
     * then index 1, which is the next app — Windows/macOS semantics, where a
     * single Alt+Tab has already moved you one step. */
    if (l->n > 1) {
        int at = -1;
        for (int i = 0; i < l->n; i++)
            if (l->v[i].xid == focus_xid) { at = i; break; }
        if (at > 0) {
            entry_t *tmp = malloc((size_t)l->n * sizeof(entry_t));
            for (int i = 0; i < l->n; i++) tmp[i] = l->v[(at + i) % l->n];
            free(l->v);
            l->v = tmp;
        }
    }
    return l;
}

void wm_apps_free(elist_t *l)
{
    if (!l) return;
    for (int i = 0; i < l->n; i++) {
        free(l->v[i].cls);
        free(l->v[i].label);
        if (l->v[i].icon) cairo_surface_destroy(l->v[i].icon);
    }
    free(l->v);
    free(l);
}

/* ── --within: the windows of one app, for Alt+backtick ───────────────────── */

wlist_within_t *wm_windows_of(Display *dpy, Window root, const char *cls)
{
    wlist_within_t *l = calloc(1, sizeof *l);
    unsigned long n = 0;
    Window *wins = wm_stacking(dpy, root, &n);
    if (!wins) return l;
    for (unsigned long k = 0; k < n; k++) {
        char *c = wm_class(dpy, wins[k]);
        if (c && cls && strcmp(c, cls) == 0) {
            l->v = realloc(l->v, (size_t)(l->n + 1) * sizeof(Window));
            l->title = realloc(l->title, (size_t)(l->n + 1) * sizeof(char *));
            l->v[l->n] = wins[k];
            l->title[l->n] = wm_title(dpy, wins[k]);
            l->n++;
        }
        free(c);
    }
    free(wins);
    return l;
}

void wm_within_free(wlist_within_t *l)
{
    if (!l) return;
    for (int i = 0; i < l->n; i++) free(l->title[i]);
    free(l->v);
    free(l->title);
    free(l);
}

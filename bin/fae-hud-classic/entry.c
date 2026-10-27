/* entry.c — build the window list as a ring, rotated to start at the current
 * window.
 *
 * Reads only EWMH and our own ring file, and has no idea a window manager
 * exists. Ordering:
 *
 *   1. the ring: our persisted order, pruned to windows that still exist,
 *      then anything it has never seen in stacking order (topmost first),
 *      which seeds it on a cold login
 *   2. rotated so the focused window is index 0, carrying on round to the
 *      front — a rotation, not a re-sort
 *   3. scoped to _NET_CURRENT_DESKTOP, because i3 follows focus across
 *      workspaces and a switcher that spans them drags you around the machine
 *
 * Step 2 is where the order of operations matters. Prepending the focused
 * window and then emitting the ring minus it destroys the cyclic order and
 * produces a two-window toggle that looks exactly like working code. See the
 * comment at the rotation below.
 */
#include "entry.h"
#include "icon.h"
#include "mru.h"
#include "theme.h"
#include "wm.h"

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

static int contains(const Window *v, int n, Window w)
{
    for (int i = 0; i < n; i++) if (v[i] == w) return 1;
    return 0;
}

elist_t *wm_list_entries(Display *dpy, Window root, Window focus_xid,
                         int same_workspace_only)
{
    elist_t *l = calloc(1, sizeof *l);
    unsigned long nlive = 0;
    Window *live = wm_stacking(dpy, root, &nlive);
    if (!live) return l;

    unsigned long cd = wm_current_desktop(dpy, root);

    /* The live, in-scope set. */
    Window scope[MRU_MAX];
    int nscope = 0;
    for (unsigned long i = 0; i < nlive && nscope < MRU_MAX; i++)
        if (!same_workspace_only ||
            wm_desktop_of(dpy, live[i], cd))
            scope[nscope++] = live[i];

    /* Build the ring first, THEN rotate it. The order of those two steps is
     * the whole bug, and getting it wrong looks like correct MRU while
     * toggling between two windows forever.
     *
     * Ring [tE,tD,tC,tB,tA] with tD current. Prepending tD and then emitting
     * the ring minus tD gives [tD,tE,tC,tB,tA] — tE jumps ahead of tC purely
     * because it sat at the front of the ring. sel=1 then picks tE, and from
     * tE it picks tD, and you are back where you started. Measured, exactly:
     * tD->tE->tD->tE across 8 taps.
     *
     * The ring is cyclic, so rotate it: start at the current window's slot and
     * carry on round to the front. That yields [tD,tC,tB,tA,tE] and sel=1 is
     * tC, the genuine next one.
     */
    Window ring[MRU_MAX];
    int nring = 0;
    Window seen[MRU_MAX];
    int nseen = 0;

    /* The ring: our persisted order first, then anything it has never seen in
     * stacking order (topmost first), which seeds it on a cold login. */
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
    if (focus_xid != None)
        for (int i = 0; i < nring; i++)
            if (ring[i] == focus_xid) { start = i; break; }

    for (int k = 0; k < nring; k++) {
        Window w = ring[(start + k) % nring];
        entry_t e;
        memset(&e, 0, sizeof e);
        e.xid  = w;
        e.cls  = wm_class(dpy, w);
        if (!e.cls || !*e.cls) e.cls = strdup("app");
        e.label = wm_title(dpy, w);
        e.icon  = icon_load(dpy, w, THEME_ICON_PX);
        push(l, &e);
    }

    free(live);
    return l;
}

void wm_entries_free(elist_t *l)
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

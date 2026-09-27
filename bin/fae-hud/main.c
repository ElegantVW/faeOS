/* main.c — fae-hud, the house switcher.
 *
 *   fae-hud --cycle        the Alt+Tab gesture (this is what i3 calls)
 *   fae-hud --dump         print the application list, draw nothing
 *   fae-hud --opaque       the no-compositor fallback
 *   fae-hud --all-workspaces
 *
 * Read-only except for the one focus request on commit, which goes through the
 * EWMH _NET_ACTIVE_WINDOW message rather than i3-msg: this program has no idea
 * which window manager is running.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#include <X11/Xlib.h>

#include "entry.h"
#include "hud.h"
#include "hold.h"
#include "theme.h"
#include "wm.h"

/* Xlib's default error handler calls exit() on any protocol error, and that is
 * fatal for a window list: we read _NET_CLIENT_LIST and then read properties
 * off each window in it, and a client can exit in between. That is a race, not
 * a bug, and it killed the strip mid-paint at the exact moment you press
 * Alt+Tab. Every X error is absorbed here. */
static int on_x_error(Display *dpy, XErrorEvent *e)
{
    if (getenv("FAE_HUD_VERBOSE"))
        fprintf(stderr, "fae-hud: X error code=%d request=%d resource=0x%lx\n",
                e->error_code, e->request_code, e->resourceid);
    return 0;
}

static void usage(void)
{
    fprintf(stderr,
        "fae-hud — the house switcher\n"
        "  --cycle          open, browse, commit once (bound to Alt+Tab)\n"
        "  --dump           print the application list, draw nothing\n"
        "  --opaque         skip translucency (the no-compositor fallback)\n"
        "  --all-workspaces include other workspaces (default: current only)\n"
        "  --display=:N\n");
}

int main(int argc, char **argv)
{
    const char *dpy_name = NULL;
    int dump = 0, force_opaque = 0, cycle = 0, all_ws = 0;

    for (int i = 1; i < argc; i++) {
        if (strncmp(argv[i], "--display=", 10) == 0)      dpy_name = argv[i] + 10;
        else if (strcmp(argv[i], "--cycle") == 0)         cycle = 1;
        else if (strcmp(argv[i], "--dump") == 0)          dump = 1;
        else if (strcmp(argv[i], "--opaque") == 0)        force_opaque = 1;
        else if (strcmp(argv[i], "--all-workspaces") == 0) all_ws = 1;
        else if (strcmp(argv[i], "--help") == 0) { usage(); return 0; }
        else { fprintf(stderr, "fae-hud: unknown argument '%s'\n", argv[i]);
               usage(); return 2; }
    }

    Display *dpy = XOpenDisplay(dpy_name);
    if (!dpy) return 1;          /* i3 sends stderr to /dev/tty1: stay quiet */
    XSetErrorHandler(on_x_error);

    int scr = DefaultScreen(dpy);
    Window root = RootWindow(dpy, scr);
    Window focus = wm_active(dpy, root);
    elist_t *apps = wm_list_apps(dpy, root, focus);

    /* Browsing is scoped to the current workspace: i3 follows focus across
     * workspaces, so a switcher that spans them drags you around the machine
     * and hides everything you started from. */
    if (!all_ws) {
        elist_t *cur = calloc(1, sizeof(elist_t));
        unsigned long cd = wm_current_desktop(dpy, root);
        for (int i = 0; i < apps->n; i++) {
            if (wm_desktop_of(dpy, apps->v[i].xid, cd)) {
                cur->v = realloc(cur->v, (size_t)(cur->n + 1) * sizeof(entry_t));
                cur->v[cur->n++] = apps->v[i];
                /* ownership moved: clear every owned pointer so the old list
                 * does not free what we just took */
                apps->v[i].cls = apps->v[i].label = NULL;
                apps->v[i].icon = NULL;
            }
        }
        wm_apps_free(apps);
        apps = cur;
    }

    int rc = 0;
    if (dump) {
        printf("apps=%d\n", apps->n);
        for (int i = 0; i < apps->n; i++)
            printf("  [%d] %-14s xid=0x%lx windows=%d icon=%s\n", i + 1,
                   apps->v[i].label, (unsigned long)apps->v[i].xid,
                   apps->v[i].count, apps->v[i].icon ? "yes" : "NO");
    } else if (cycle) {
        rc = hold_cycle(dpy, scr, apps);
    } else {
        hud_t *h = hud_open(dpy, scr, apps, apps->n > 1 ? 1 : 0, force_opaque);
        if (h) {
            struct timespec nap = { 0, 900L * 1000L * 1000L };
            nanosleep(&nap, NULL);
            while (XPending(dpy)) { XEvent ev; XNextEvent(dpy, &ev); }
            hud_close(h);
        } else rc = 1;
    }

    wm_apps_free(apps);
    XCloseDisplay(dpy);
    return rc;
}

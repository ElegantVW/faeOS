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
        "  --dump           print the window list, draw nothing\n"
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
    /* One entry per window, scoped to the current workspace by default:
     * i3 follows focus across workspaces, so a switcher that spans them
     * drags you around the machine and hides what you started from. */
    elist_t *apps = wm_list_entries(dpy, root, focus, !all_ws);

    if (dump) {
        printf("apps=%d current=0x%lx\n", apps->n, (unsigned long)focus);
        for (int i = 0; i < apps->n; i++)
            printf("  [%d] %-28s xid=0x%lx %-10s icon=%s\n", i + 1,
                   apps->v[i].label, (unsigned long)apps->v[i].xid,
                   apps->v[i].cls, apps->v[i].icon ? "yes" : "NO");
    }

    int rc = 0;
    if (!dump) {
        if (cycle) {
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
    }

    wm_entries_free(apps);
    XCloseDisplay(dpy);
    return rc;
}

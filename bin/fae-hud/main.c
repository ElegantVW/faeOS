/* fae-hud — the visible layer of the house desktop.
 *
 * Usage:  fae-hud [--focus=0x240000e] [--hold=1100]
 *
 * Spawned by fae-cycle after it moves focus. It reads the window list from
 * X (EWMH) and paints it. It never focuses, kills, moves or resizes anything,
 * so a bug in here cannot cost you a window.
 *
 * Not a resident process: it paints, holds, fades, exits. That is deliberate
 * — the house rule that came out of the i3bar incident is that nothing on
 * this desktop needs to stay running.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include <X11/Xlib.h>

#include "wm.h"
#include "hud.h"

static void usage(void)
{
    fprintf(stderr,
        "fae-hud — themed window cycler panel\n"
        "  --focus=0xID   highlight this X window (default: _NET_ACTIVE_WINDOW)\n"
        "  --dump         print the EWMH window list, draw nothing\n"
        "  --display=:N   X display (default: $DISPLAY)\n"
        "  --help\n");
}

int main(int argc, char **argv)
{
    Window focus = None;
    const char *dpy_name = NULL;
    int dump = 0;

    for (int i = 1; i < argc; i++) {
        if (strncmp(argv[i], "--focus=", 8) == 0) {
            focus = (Window)strtoul(argv[i] + 8, NULL, 0);
        } else if (strncmp(argv[i], "--display=", 10) == 0) {
            dpy_name = argv[i] + 10;
        } else if (strcmp(argv[i], "--dump") == 0) {
            dump = 1;
        } else if (strcmp(argv[i], "--help") == 0) {
            usage();
            return 0;
        } else {
            fprintf(stderr, "fae-hud: unknown argument '%s'\n", argv[i]);
            usage();
            return 2;
        }
    }

    /* --dump: print what EWMH actually says, and draw nothing. This exists
     * because the first honest question about a window list is not "does it
     * look right" but "is the data there" — _NET_WM_DESKTOP in particular is
     * optional and a pretty render of absent data is still wrong. */
    Display *dpy = XOpenDisplay(dpy_name);
    if (!dpy) {
        /* No display is not an error worth printing anywhere the user can
         * see: i3's stderr is /dev/tty1, so anything here is invisible. */
        return 1;
    }

    int scr = DefaultScreen(dpy);
    Window root = RootWindow(dpy, scr);

    wlist_t *list = wm_list_windows(dpy, root, focus);

    int rc;
    if (dump) {
        printf("current_desktop=%lu active=0x%lx focus_arg=0x%lx windows=%d\n",
               list->current_desktop, (unsigned long)list->active,
               (unsigned long)list->focus_xid, list->n);
        for (int i = 0; i < list->n; i++)
            printf("  [%d] 0x%lx ws=%s%-2lu %-10s |%s|%s%s\n", i + 1,
                   (unsigned long)list->v[i].xid,
                   list->v[i].desktop_known ? "" : "?",
                   list->v[i].desktop,
                   list->v[i].title,
                   list->v[i].cls,
                   list->v[i].is_focus_target ? "  <- highlight" :
                   (list->v[i].is_active ? "  <- active" : ""),
                   list->v[i].on_current_workspace ? "" : "  (other ws)");
        rc = 0;
    } else {
        rc = hud_run(dpy, scr, list);
    }

    wm_list_free_titles(list);
    wm_list_free(list);
    XCloseDisplay(dpy);
    return rc;
}

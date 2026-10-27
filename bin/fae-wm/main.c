/* main.c — Jana, the house window manager. Tiling by default, EWMH, with
 * the Alt+Tab switcher built in (Mod1+Tab). */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include <X11/Xlib.h>

#include "config.h"
#include "wm.h"

static void usage(void)
{
    fprintf(stderr,
        "fae-wm — Jana, the house window manager\n"
        "  fae-wm             run (fails if another WM owns the display)\n"
        "  fae-wm --check    validate the config file and exit\n"
        "  fae-wm --help     this\n"
        "\n"
        "Config: $FAE_WM_CONFIG or ~/.config/fae-wm/config (optional;\n"
        "built-in house defaults stand in when it is missing).\n");
}

int main(int argc, char **argv)
{
    int check = 0;
    for (int i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--check")) check = 1;
        else if (!strcmp(argv[i], "--help")) { usage(); return 0; }
        else { fprintf(stderr, "fae-wm: unknown argument '%s'\n", argv[i]);
               usage(); return 2; }
    }

    config_t cfg;
    const char *errpath = NULL;
    config_load(&cfg, &errpath);
    if (check) {
        printf("binds=%d autostart=%d gap=%d border=%d focus=%s unfocus=%s%s%s\n",
               cfg.nbinds, cfg.nauto, cfg.gap_outer, cfg.border_w,
               cfg.color_focus, cfg.color_unfocus,
               errpath ? " config=" : "", errpath ? errpath : "");
        config_free(&cfg);
        return 0;
    }

    Display *dpy = XOpenDisplay(NULL);
    if (!dpy) {
        fprintf(stderr, "fae-wm: cannot open display\n");
        return 1;
    }
    int scr = DefaultScreen(dpy);
    int rc = wm_run(dpy, scr, &cfg);
    XCloseDisplay(dpy);
    config_free(&cfg);
    return rc;
}

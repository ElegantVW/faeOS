/* launch.c — Super+d overlay: dock pins + .desktop, house chrome. */
#include "launch.h"
#include "launch_geom.h"
#include "theme.h"
#include "wm.h"
#include "help.h"

#include <dirent.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#include <X11/Xlib.h>
#include <X11/Xatom.h>
#include <X11/Xutil.h>
#include <X11/keysym.h>
#include <cairo/cairo-xlib.h>
#include <pango/pangocairo.h>

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

#define LAUNCH_W     520
#define LAUNCH_H     420
#define LAUNCH_MS    180
#define LAUNCH_ROWS  12
#define LAUNCH_MAX   512
#define LAUNCH_Q     96

typedef struct {
    char name[LAUNCH_NAME_MAX];
    char exec[LAUNCH_EXEC_MAX + 64];
    int  pin;
} launch_item_t;

static Window launch_w = None;
static Pixmap launch_pix = None;
static cairo_surface_t *launch_surf = NULL;
static GC launch_gc = None;
static Visual *launch_vis;
static int launch_depth;
static Colormap launch_cmap;
static int launch_out;
static int launch_grabbed;
static long launch_t0;
static char launch_q[LAUNCH_Q];
static int launch_sel;
static launch_item_t launch_items[LAUNCH_MAX];
static int launch_n;
static int launch_vis_i[LAUNCH_MAX];
static int launch_nv;

static long now_ms(void)
{
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return ts.tv_sec * 1000L + ts.tv_nsec / 1000000L;
}

static double ease(double t)
{
    if (t < 0) t = 0;
    if (t > 1) t = 1;
    return 1.0 - (1.0 - t) * (1.0 - t);
}

int launch_visible(void)
{
    return launch_w != None;
}

static void round_rect(cairo_t *cr, double x, double y, double w, double h, double rad)
{
    cairo_new_sub_path(cr);
    cairo_arc(cr, x + w - rad, y + h - rad, rad, 0.0, M_PI / 2);
    cairo_arc(cr, x + w - rad, y + rad, rad, M_PI / 2, M_PI);
    cairo_arc(cr, x + rad, y + rad, rad, M_PI, 3 * M_PI / 2);
    cairo_arc(cr, x + rad, y + h - rad, rad, 3 * M_PI / 2, 2 * M_PI);
    cairo_close_path(cr);
}

static int already_named(const char *name, const char *exec)
{
    int i;
    for (i = 0; i < launch_n; i++)
        if (!strcmp(launch_items[i].name, name) ||
            !strcmp(launch_items[i].exec, exec))
            return 1;
    return 0;
}

static void add_item(const char *name, const char *exec, int pin)
{
    launch_item_t *it;
    if (launch_n >= LAUNCH_MAX || !name || !*name || !exec || !*exec) return;
    if (already_named(name, exec)) return;
    it = &launch_items[launch_n++];
    snprintf(it->name, sizeof it->name, "%s", name);
    snprintf(it->exec, sizeof it->exec, "%s", exec);
    it->pin = pin;
}

static void add_pins(void)
{
    config_t *cfg = fae_cfg();
    int i;
    if (!cfg) return;
    for (i = 0; i < cfg->npins; i++) {
        pin_t *p = &cfg->pins[i];
        if (p->label && p->cmd)
            add_item(p->label, p->cmd, 1);
    }
}

static void scan_dir(const char *dir)
{
    DIR *d;
    struct dirent *e;
    if (!dir || !*dir) return;
    d = opendir(dir);
    if (!d) return;
    while ((e = readdir(d))) {
        char path[1024], body[8192];
        char name[LAUNCH_NAME_MAX], exec[LAUNCH_EXEC_MAX];
        FILE *f;
        size_t n;
        int term = 0;
        size_t len = strlen(e->d_name);
        if (len < 9 || strcmp(e->d_name + len - 8, ".desktop") != 0) continue;
        snprintf(path, sizeof path, "%s/%s", dir, e->d_name);
        f = fopen(path, "r");
        if (!f) continue;
        n = fread(body, 1, sizeof body - 1, f);
        fclose(f);
        body[n] = 0;
        if (!launch_parse_desktop(body, name, sizeof name, exec, sizeof exec, &term))
            continue;
        if (term) {
            char wrapped[LAUNCH_EXEC_MAX + 64];
            snprintf(wrapped, sizeof wrapped, "kitty -e sh -c '%s'", exec);
            add_item(name, wrapped, 0);
        } else {
            add_item(name, exec, 0);
        }
    }
    closedir(d);
}

static void scan_apps(void)
{
    const char *home = getenv("HOME");
    const char *xd = getenv("XDG_DATA_HOME");
    const char *dirs = getenv("XDG_DATA_DIRS");
    char buf[4096];
    launch_n = 0;
    add_pins();
    if (xd && *xd) {
        snprintf(buf, sizeof buf, "%s/applications", xd);
        scan_dir(buf);
    } else if (home) {
        snprintf(buf, sizeof buf, "%s/.local/share/applications", home);
        scan_dir(buf);
    }
    if (!dirs || !*dirs) dirs = "/usr/local/share:/usr/share";
    {
        char copy[4096];
        char *p;
        snprintf(copy, sizeof copy, "%s", dirs);
        p = copy;
        while (*p) {
            char *colon = strchr(p, ':');
            if (colon) *colon = 0;
            if (strlen(p) < sizeof buf - 16) {
                snprintf(buf, sizeof buf, "%s/applications", p);
                scan_dir(buf);
            }
            if (!colon) break;
            p = colon + 1;
        }
    }
}

static void relist(void)
{
    int i;
    launch_nv = 0;
    for (i = 0; i < launch_n; i++) {
        if (launch_match(launch_items[i].name, launch_items[i].exec, launch_q))
            launch_vis_i[launch_nv++] = i;
    }
    if (launch_sel >= launch_nv) launch_sel = launch_nv ? launch_nv - 1 : 0;
    if (launch_sel < 0) launch_sel = 0;
}

static void launch_ungrab(Display *dpy)
{
    if (launch_grabbed) {
        XUngrabKeyboard(dpy, CurrentTime);
        launch_grabbed = 0;
    }
}

static void launch_buffer_free(Display *dpy)
{
    if (launch_surf) { cairo_surface_destroy(launch_surf); launch_surf = NULL; }
    if (launch_pix != None) { XFreePixmap(dpy, launch_pix); launch_pix = None; }
}

static int launch_buffer_ok(Display *dpy, Window root)
{
    if (launch_pix != None && launch_surf) return 1;
    launch_buffer_free(dpy);
    {
        int depth = launch_depth ? launch_depth : DefaultDepth(dpy, DefaultScreen(dpy));
        Visual *vis = launch_vis ? launch_vis : DefaultVisual(dpy, DefaultScreen(dpy));
        launch_pix = XCreatePixmap(dpy, launch_w ? launch_w : root,
                                   LAUNCH_W, LAUNCH_H, (unsigned)depth);
        launch_surf = cairo_xlib_surface_create(dpy, launch_pix, vis, LAUNCH_W, LAUNCH_H);
        if (launch_gc == None && launch_w != None)
            launch_gc = XCreateGC(dpy, launch_w, 0, NULL);
    }
    return launch_pix != None && launch_surf != NULL;
}

static double launch_alpha(void)
{
    double t = (double)(now_ms() - launch_t0) / (double)LAUNCH_MS;
    t = ease(t);
    if (launch_out) return 1.0 - t;
    return t;
}

static void launch_paint(wm_t *wm)
{
    cairo_t *cr;
    PangoContext *ctx;
    PangoLayout *lay;
    PangoFontDescription *desc, *desc_s;
    int top, row_h, i, start;
    if (launch_w == None || !launch_buffer_ok(wm->dpy, wm->root)) return;
    cr = cairo_create(launch_surf);
    cairo_set_operator(cr, CAIRO_OPERATOR_SOURCE);
    cairo_set_source_rgba(cr, 0, 0, 0, 0);
    cairo_paint(cr);
    cairo_set_operator(cr, CAIRO_OPERATOR_OVER);

    cairo_push_group(cr);
    round_rect(cr, 1, 1, LAUNCH_W - 2, LAUNCH_H - 2, 14);
    cairo_set_source_rgba(cr, 0x1a / 255.0, 0x0a / 255.0, 0x12 / 255.0, 0.88);
    cairo_fill_preserve(cr);
    cairo_set_source_rgba(cr, 0xe8 / 255.0, 0x79 / 255.0, 0xa0 / 255.0, 0.85);
    cairo_set_line_width(cr, 1.5);
    cairo_stroke(cr);

    ctx = pango_font_map_create_context(pango_cairo_font_map_get_default());
    lay = pango_layout_new(ctx);
    desc = pango_font_description_from_string(THEME_FONT ":size=12");
    desc_s = pango_font_description_from_string(THEME_FONT ":size=10");

    pango_layout_set_font_description(lay, desc);
    cairo_set_source_rgb(cr, 0xe8 / 255.0, 0x79 / 255.0, 0xa0 / 255.0);
    pango_layout_set_text(lay, "✦ Jana ✦", -1);
    cairo_move_to(cr, 22, 14);
    pango_cairo_show_layout(cr, lay);

    round_rect(cr, 18, 42, LAUNCH_W - 36, 32, 8);
    cairo_set_source_rgba(cr, 0x2a / 255.0, 0x15 / 255.0, 0x20 / 255.0, 0.95);
    cairo_fill(cr);
    {
        const char *qshow = launch_q[0] ? launch_q : "type to spin…";
        pango_layout_set_text(lay, qshow, -1);
        if (launch_q[0])
            cairo_set_source_rgb(cr, 0xff / 255.0, 0xe3 / 255.0, 0xee / 255.0);
        else
            cairo_set_source_rgb(cr, 0x9d / 255.0, 0x5c / 255.0, 0x75 / 255.0);
        cairo_move_to(cr, 28, 48);
        pango_cairo_show_layout(cr, lay);
    }

    top = 84;
    row_h = 24;
    start = 0;
    if (launch_sel >= LAUNCH_ROWS)
        start = launch_sel - LAUNCH_ROWS + 1;
    pango_layout_set_font_description(lay, desc_s);
    for (i = 0; i < LAUNCH_ROWS && start + i < launch_nv; i++) {
        int idx = launch_vis_i[start + i];
        int y = top + i * row_h;
        int sel = (start + i == launch_sel);
        char line[LAUNCH_NAME_MAX + 8];
        if (sel) {
            round_rect(cr, 18, y, LAUNCH_W - 36, row_h - 2, 6);
            cairo_set_source_rgba(cr, 0xc4 / 255.0, 0x4d / 255.0, 0x7a / 255.0, 0.90);
            cairo_fill(cr);
        }
        snprintf(line, sizeof line, "%s%s", launch_items[idx].pin ? "✦ " : "  ",
                 launch_items[idx].name);
        pango_layout_set_text(lay, line, -1);
        cairo_set_source_rgb(cr, 0xff / 255.0, 0xe3 / 255.0, 0xee / 255.0);
        cairo_move_to(cr, 28, y + 3);
        pango_cairo_show_layout(cr, lay);
    }

    pango_layout_set_font_description(lay, desc_s);
    cairo_set_source_rgb(cr, 0x9d / 255.0, 0x5c / 255.0, 0x75 / 255.0);
    pango_layout_set_text(lay, "enter run  ·  esc close  ·  super+d", -1);
    cairo_move_to(cr, 22, LAUNCH_H - 28);
    pango_cairo_show_layout(cr, lay);

    cairo_pop_group_to_source(cr);
    cairo_paint_with_alpha(cr, launch_alpha());

    cairo_destroy(cr);
    pango_font_description_free(desc);
    pango_font_description_free(desc_s);
    g_object_unref(lay);
    g_object_unref(ctx);
    cairo_surface_flush(launch_surf);
    if (launch_gc == None)
        launch_gc = XCreateGC(wm->dpy, launch_w, 0, NULL);
    XCopyArea(wm->dpy, launch_pix, launch_w, launch_gc, 0, 0,
              LAUNCH_W, LAUNCH_H, 0, 0);
    XFlush(wm->dpy);
}

static void launch_destroy(wm_t *wm)
{
    launch_ungrab(wm->dpy);
    launch_buffer_free(wm->dpy);
    if (launch_gc != None) {
        XFreeGC(wm->dpy, launch_gc);
        launch_gc = None;
    }
    if (launch_w != None) {
        XDestroyWindow(wm->dpy, launch_w);
        launch_w = None;
    }
    launch_out = 0;
    launch_n = 0;
    launch_nv = 0;
    launch_q[0] = 0;
}

void launch_hide(wm_t *wm)
{
    if (launch_w == None) return;
    if (launch_out) return;
    launch_ungrab(wm->dpy);
    launch_out = 1;
    launch_t0 = now_ms();
    launch_paint(wm);
}

static void launch_run_sel(wm_t *wm)
{
    if (launch_sel < 0 || launch_sel >= launch_nv) return;
    {
        int idx = launch_vis_i[launch_sel];
        spawn_cmd(launch_items[idx].exec);
    }
    launch_hide(wm);
}

void launch_toggle(wm_t *wm)
{
    int x, y;
    Display *dpy;
    int scr;
    XSetWindowAttributes attr;
    unsigned vmask;
    Visual *vis;
    int depth;
    XVisualInfo tpl, *vi;
    int nvi = 0;
    XClassHint ch;

    if (launch_w != None && !launch_out) {
        launch_hide(wm);
        return;
    }
    if (launch_w != None)
        launch_destroy(wm);
    if (help_visible())
        help_hide(wm);

    scan_apps();
    launch_q[0] = 0;
    launch_sel = 0;
    relist();

    x = (wm->sw - LAUNCH_W) / 2;
    y = (wm->sh - LAUNCH_H) / 3;
    dpy = wm->dpy;
    scr = wm->scr;
    memset(&attr, 0, sizeof attr);
    attr.override_redirect = True;
    attr.background_pixel = 0;
    attr.border_pixel = 0;
    attr.event_mask = ExposureMask | KeyPressMask | ButtonPressMask;
    vmask = CWOverrideRedirect | CWBackPixel | CWBorderPixel | CWEventMask;
    vis = DefaultVisual(dpy, scr);
    depth = DefaultDepth(dpy, scr);
    memset(&tpl, 0, sizeof tpl);
    tpl.screen = scr;
    tpl.depth = 32;
    tpl.class = TrueColor;
    vi = XGetVisualInfo(dpy,
        VisualScreenMask | VisualDepthMask | VisualClassMask, &tpl, &nvi);
    if (vi && nvi > 0) {
        vis = vi[0].visual;
        depth = 32;
        launch_vis = vis;
        launch_depth = 32;
        launch_cmap = XCreateColormap(dpy, wm->root, vis, AllocNone);
        attr.colormap = launch_cmap;
        vmask |= CWColormap;
        XFree(vi);
    } else {
        if (vi) XFree(vi);
        launch_vis = vis;
        launch_depth = depth;
    }
    launch_w = XCreateWindow(dpy, wm->root, x, y, LAUNCH_W, LAUNCH_H, 0,
                             depth, InputOutput, vis, vmask, &attr);
    XStoreName(dpy, launch_w, "fae-launch");
    ch.res_name = "fae-launch";
    ch.res_class = "fae-launch";
    XSetClassHint(dpy, launch_w, &ch);
    XMapRaised(dpy, launch_w);
    launch_out = 0;
    launch_t0 = now_ms();
    launch_grabbed = 0;
    if (XGrabKeyboard(dpy, launch_w, True, GrabModeAsync, GrabModeAsync,
                      CurrentTime) == GrabSuccess)
        launch_grabbed = 1;
    else
        XSetInputFocus(dpy, launch_w, RevertToParent, CurrentTime);
    launch_paint(wm);
}

int launch_is_win(Window w)
{
    return launch_w != None && w == launch_w;
}

void launch_expose(wm_t *wm)
{
    if (launch_w != None) launch_paint(wm);
}

void launch_tick(wm_t *wm)
{
    long el;
    if (launch_w == None) return;
    el = now_ms() - launch_t0;
    if (el < LAUNCH_MS) {
        launch_paint(wm);
        return;
    }
    if (launch_out)
        launch_destroy(wm);
}

void launch_on_key(wm_t *wm, XKeyEvent *ev)
{
    KeySym ks;
    char buf[8];
    int n;
    unsigned state;
    if (launch_w == None || launch_out) return;
    state = ev->state;
    ks = XLookupKeysym(ev, 0);
    if (ks == XK_Escape ||
        (ks == XK_d && (state & Mod4Mask) && !(state & ControlMask))) {
        launch_hide(wm);
        return;
    }
    if (ks == XK_Return || ks == XK_KP_Enter) {
        launch_run_sel(wm);
        return;
    }
    if (ks == XK_Up || ((state & ControlMask) && ks == XK_p)) {
        if (launch_sel > 0) launch_sel--;
        launch_paint(wm);
        return;
    }
    if (ks == XK_Down || ((state & ControlMask) && ks == XK_n)) {
        if (launch_sel + 1 < launch_nv) launch_sel++;
        launch_paint(wm);
        return;
    }
    if (ks == XK_BackSpace) {
        size_t L = strlen(launch_q);
        if (L > 0) {
            launch_q[L - 1] = 0;
            launch_sel = 0;
            relist();
            launch_paint(wm);
        }
        return;
    }
    if (state & (Mod4Mask | ControlMask | Mod1Mask)) return;
    n = XLookupString(ev, buf, sizeof buf - 1, &ks, NULL);
    if (n == 1 && buf[0] >= 32 && buf[0] < 127) {
        size_t L = strlen(launch_q);
        if (L + 1 < sizeof launch_q) {
            launch_q[L] = buf[0];
            launch_q[L + 1] = 0;
            launch_sel = 0;
            relist();
            launch_paint(wm);
        }
    }
}

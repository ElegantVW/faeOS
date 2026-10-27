/* help.c — Super+h overlay: Grove mark, crystal frame, fade. */
#include "help.h"
#include "theme.h"

#include <string.h>
#include <time.h>
#include <X11/Xlib.h>
#include <X11/Xatom.h>
#include <X11/Xutil.h>
#include <cairo/cairo-xlib.h>
#include <pango/pangocairo.h>

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

#define HELP_W  460
#define HELP_H  470
#define HELP_MS 180

static const char *GROVE[] = {
    "\\  |  /",
    " \\| |/ ",
    "---+---",
    " / | \\ ",
    "/  |  \\",
};

static const char *HELP =
    "✦ Jana ✦          spins the rooms\n"
    "Super+d           launch\n"
    "Super+Shift+q     close\n"
    "Super+m           minimize\n"
    "Super+Shift+f     maximize\n"
    "Super+f           fullscreen\n"
    "Super+v / s       next split stacked / columns\n"
    "Super+e           even this split\n"
    "Super+t           dwindle / master-stack\n"
    "Super+r then hjkl grow (tile) or resize (float)\n"
    "Super+Shift+Space float / tile\n"
    "Super+j k l ;     focus\n"
    "Super+Shift+jkl;  swap (tiled) or nudge\n"
    "Super+1..0        workspace\n"
    "Super+Return      terminal\n"
    "Super+= / -       dock size\n"
    "\n"
    "Super+h or Esc    close this";

static Window help_w = None;
static Pixmap help_pix = None;
static cairo_surface_t *help_surf = NULL;
static GC help_gc = None;
static Visual *help_vis;
static int help_depth;
static Colormap help_cmap;
static int help_on;
static int help_out; /* fading out */
static long help_t0;

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

int help_visible(void)
{
    return help_w != None;
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

static void help_buffer_free(Display *dpy)
{
    if (help_surf) { cairo_surface_destroy(help_surf); help_surf = NULL; }
    if (help_pix != None) { XFreePixmap(dpy, help_pix); help_pix = None; }
}

static int help_buffer_ok(Display *dpy, Window root)
{
    if (help_pix != None && help_surf) return 1;
    help_buffer_free(dpy);
    int depth = help_depth ? help_depth : DefaultDepth(dpy, DefaultScreen(dpy));
    Visual *vis = help_vis ? help_vis : DefaultVisual(dpy, DefaultScreen(dpy));
    help_pix = XCreatePixmap(dpy, help_w ? help_w : root, HELP_W, HELP_H, (unsigned)depth);
    help_surf = cairo_xlib_surface_create(dpy, help_pix, vis, HELP_W, HELP_H);
    if (help_gc == None && help_w != None)
        help_gc = XCreateGC(dpy, help_w, 0, NULL);
    return help_pix != None && help_surf != NULL;
}

static double help_alpha(void)
{
    double t = (double)(now_ms() - help_t0) / (double)HELP_MS;
    t = ease(t);
    if (help_out) return 1.0 - t;
    return t;
}

static void help_paint(wm_t *wm)
{
    if (help_w == None || !help_buffer_ok(wm->dpy, wm->root)) return;
    cairo_t *cr = cairo_create(help_surf);
    cairo_set_operator(cr, CAIRO_OPERATOR_SOURCE);
    cairo_set_source_rgba(cr, 0, 0, 0, 0);
    cairo_paint(cr);
    cairo_set_operator(cr, CAIRO_OPERATOR_OVER);

    cairo_push_group(cr);
    round_rect(cr, 1, 1, HELP_W - 2, HELP_H - 2, 14);
    cairo_set_source_rgba(cr, 0x1a / 255.0, 0x0a / 255.0, 0x12 / 255.0, 0.82);
    cairo_fill_preserve(cr);
    cairo_set_source_rgba(cr, 0xe8 / 255.0, 0x79 / 255.0, 0xa0 / 255.0, 0.85);
    cairo_set_line_width(cr, 1.5);
    cairo_stroke(cr);

    PangoContext *ctx =
        pango_font_map_create_context(pango_cairo_font_map_get_default());
    PangoLayout *lay = pango_layout_new(ctx);
    PangoFontDescription *desc_g =
        pango_font_description_from_string(THEME_FONT ":size=8");
    PangoFontDescription *desc =
        pango_font_description_from_string(THEME_FONT ":size=11");

    pango_layout_set_font_description(lay, desc_g);
    cairo_set_source_rgb(cr, 0xe8 / 255.0, 0x79 / 255.0, 0xa0 / 255.0);
    int gy = 16;
    for (int i = 0; i < 5; i++) {
        pango_layout_set_text(lay, GROVE[i], -1);
        int tw = 0, th = 0;
        pango_layout_get_pixel_size(lay, &tw, &th);
        cairo_move_to(cr, (HELP_W - tw) / 2, gy);
        pango_cairo_show_layout(cr, lay);
        gy += th;
    }

    pango_layout_set_font_description(lay, desc);
    pango_layout_set_text(lay, HELP, -1);
    cairo_move_to(cr, 22, gy + 10);
    pango_cairo_show_layout(cr, lay);

    cairo_pop_group_to_source(cr);
    cairo_paint_with_alpha(cr, help_alpha());

    cairo_destroy(cr);
    pango_font_description_free(desc_g);
    pango_font_description_free(desc);
    g_object_unref(lay);
    g_object_unref(ctx);
    cairo_surface_flush(help_surf);
    if (help_gc == None)
        help_gc = XCreateGC(wm->dpy, help_w, 0, NULL);
    XCopyArea(wm->dpy, help_pix, help_w, help_gc, 0, 0, HELP_W, HELP_H, 0, 0);
    XFlush(wm->dpy);
}

static void help_destroy(wm_t *wm)
{
    help_buffer_free(wm->dpy);
    if (help_gc != None) {
        XFreeGC(wm->dpy, help_gc);
        help_gc = None;
    }
    if (help_w != None) {
        XDestroyWindow(wm->dpy, help_w);
        help_w = None;
    }
    help_on = 0;
    help_out = 0;
}

void help_hide(wm_t *wm)
{
    if (help_w == None) return;
    if (help_out) return;
    help_out = 1;
    help_t0 = now_ms();
    help_paint(wm);
}

void help_toggle(wm_t *wm)
{
    if (help_w != None && !help_out) {
        help_hide(wm);
        return;
    }
    if (help_w != None)
        help_destroy(wm);

    int x = (wm->sw - HELP_W) / 2, y = (wm->sh - HELP_H) / 2;
    Display *dpy = wm->dpy;
    int scr = wm->scr;
    XSetWindowAttributes attr;
    memset(&attr, 0, sizeof attr);
    attr.override_redirect = True;
    attr.background_pixel = 0;
    attr.border_pixel = 0;
    attr.event_mask = ExposureMask | KeyPressMask;
    unsigned vmask = CWOverrideRedirect | CWBackPixel | CWBorderPixel | CWEventMask;
    Visual *vis = DefaultVisual(dpy, scr);
    int depth = DefaultDepth(dpy, scr);
    XVisualInfo tpl;
    memset(&tpl, 0, sizeof tpl);
    tpl.screen = scr;
    tpl.depth = 32;
    tpl.class = TrueColor;
    int nvi = 0;
    XVisualInfo *vi = XGetVisualInfo(dpy,
        VisualScreenMask | VisualDepthMask | VisualClassMask, &tpl, &nvi);
    if (vi && nvi > 0) {
        vis = vi[0].visual;
        depth = 32;
        help_vis = vis;
        help_depth = 32;
        help_cmap = XCreateColormap(dpy, wm->root, vis, AllocNone);
        attr.colormap = help_cmap;
        vmask |= CWColormap;
        XFree(vi);
    } else {
        if (vi) XFree(vi);
        help_vis = vis;
        help_depth = depth;
    }
    help_w = XCreateWindow(dpy, wm->root, x, y, HELP_W, HELP_H, 0,
                           depth, InputOutput, vis, vmask, &attr);
    XMapRaised(dpy, help_w);
    help_on = 1;
    help_out = 0;
    help_t0 = now_ms();
    help_paint(wm);
}

int help_is_win(Window w)
{
    return help_w != None && w == help_w;
}

void help_expose(wm_t *wm)
{
    if (help_w != None) help_paint(wm);
}

void help_tick(wm_t *wm)
{
    if (help_w == None) return;
    long el = now_ms() - help_t0;
    if (el < HELP_MS) {
        help_paint(wm);
        return;
    }
    if (help_out)
        help_destroy(wm);
}

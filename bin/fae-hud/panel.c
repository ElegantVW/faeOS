/* panel.c — the minimal switcher panel.
 *
 * A vertical list on a dark plum box: one full window title per row, "» "
 * marking the selection, a dim runes footer naming the keys. Override
 * redirect so it floats without taking focus; it selects no button events,
 * so clicks pass through to whatever is under it.
 *
 * cairo's origin is the SURFACE. px/py place the window on the desktop and
 * are NOT drawing coordinates — everything below is 0,0-based.
 */
#include "panel.h"
#include "theme.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#include <X11/Xlib.h>
#include <X11/Xatom.h>
#include <X11/X.h>
#include <X11/Xutil.h>
#include <cairo/cairo-xlib.h>
#include <pango/pangocairo.h>

#ifndef TrueClass
#define TrueClass 4
#endif
#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

typedef struct { double r, g, b; } rgb_t;

static rgb_t hex_rgb(const char *hex)
{
    rgb_t c = { 0, 0, 0 };
    unsigned v = 0;
    if (hex[0] == '#' && strlen(hex) >= 7 && sscanf(hex + 1, "%06x", &v) == 1) {
        c.r = ((v >> 16) & 0xff) / 255.0;
        c.g = ((v >> 8) & 0xff) / 255.0;
        c.b = (v & 0xff) / 255.0;
    }
    return c;
}

static void set_rgba(cairo_t *cr, rgb_t c, double a)
{
    if (a < 0) a = 0;
    if (a > 1) a = 1;
    cairo_set_source_rgba(cr, c.r, c.g, c.b, a);
}

static void round_rect(cairo_t *cr, double x, double y, double w, double h,
                       double r)
{
    if (r > w / 2) r = w / 2;
    if (r > h / 2) r = h / 2;
    cairo_new_sub_path(cr);
    cairo_arc(cr, x + w - r, y + h - r, r, 0.0, M_PI / 2);
    cairo_arc(cr, x + w - r, y + r,     r, M_PI / 2, M_PI);
    cairo_arc(cr, x + r,     y + r,     r, M_PI, 3 * M_PI / 2);
    cairo_arc(cr, x + r,     y + h - r, r, 3 * M_PI / 2, 2 * M_PI);
    cairo_close_path(cr);
}

typedef struct {
    PangoLayout          *lay;
    PangoFontDescription *desc;
} type_t;

/* NB: pango_cairo_show_layout() positions the layout by its TOP-LEFT at the
 * current cairo point, not by baseline — every y here is a top edge. */
static void type_open(type_t *t, PangoContext *ctx, const char *font)
{
    t->desc = pango_font_description_from_string(font);
    t->lay = pango_layout_new(ctx);
    pango_layout_set_font_description(t->lay, t->desc);
    pango_layout_set_single_paragraph_mode(t->lay, TRUE);
}

static void type_free(type_t *t)
{
    if (t->lay) g_object_unref(t->lay);
    /* PangoFontDescription is boxed: g_object_unref segfaults. */
    if (t->desc) pango_font_description_free(t->desc);
    t->lay = NULL;
    t->desc = NULL;
}

static void type_text(type_t *t, const char *s, int max_px)
{
    pango_layout_set_text(t->lay, s, -1);
    if (max_px > 0) {
        pango_layout_set_ellipsize(t->lay, PANGO_ELLIPSIZE_END);
        pango_layout_set_width(t->lay, max_px * PANGO_SCALE);
    } else {
        pango_layout_set_ellipsize(t->lay, PANGO_ELLIPSIZE_NONE);
        pango_layout_set_width(t->lay, -1);
    }
}

static void type_draw(type_t *t, cairo_t *cr, rgb_t col, double a,
                      double x, double top)
{
    set_rgba(cr, col, a);
    cairo_move_to(cr, x, top);
    pango_cairo_show_layout(cr, t->lay);
}

static int type_h(type_t *t)
{
    int w = 0, h = 0;
    pango_layout_get_pixel_size(t->lay, &w, &h);
    return h;
}

/* Footer names the keys the way the house TUIs do. Static text only, so
 * markup is safe (titles go through set_text, never markup). Capped to the
 * panel's inner width like every row. */
static void foot_text(type_t *t, int max_px)
{
    pango_layout_set_markup(t->lay,
        "<span fgcolor=\"" THEME_ROSE "\">tab</span>"
        "<span fgcolor=\"" THEME_MUTED "\"> next · </span>"
        "<span fgcolor=\"" THEME_ROSE "\">shift+tab</span>"
        "<span fgcolor=\"" THEME_MUTED "\"> prev · </span>"
        "<span fgcolor=\"" THEME_ROSE "\">esc</span>"
        "<span fgcolor=\"" THEME_MUTED "\"> cancel</span>", -1);
    pango_layout_set_ellipsize(t->lay, PANGO_ELLIPSIZE_END);
    pango_layout_set_width(t->lay, max_px * PANGO_SCALE);
}

struct panel {
    Display   *dpy;
    int        scr;
    Window     win;
    cairo_surface_t *surf;
    cairo_t   *cr;
    PangoContext *ctx;
    type_t     row, foot;
    winlist_t *apps;
    int        sel;
    int        first;      /* first visible row when scrolling */
    int        have_cx;
    int        want_w, want_h, px, py;
    int        row_h, inner_w;
    rgb_t c_bg, c_pink, c_fg, c_silver, c_muted, c_rose;
};

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
    return t * t * (3.0 - 2.0 * t);
}

static int compositor_present(Display *dpy)
{
    for (int i = 0; i < 32; i++) {
        char name[32];
        snprintf(name, sizeof name, "_NET_WM_CM_S%d", i);
        Atom a = XInternAtom(dpy, name, False);
        if (a != None && XGetSelectionOwner(dpy, a) != None) return 1;
    }
    return 0;
}

/* Keep `sel` on screen by sliding the visible window. */
static void ensure_visible(panel_t *p)
{
    int n = p->apps->n;
    if (n <= 0) return;
    if (n <= THEME_MAX_ROWS) { p->first = 0; return; }
    if (p->sel < p->first) p->first = p->sel;
    if (p->sel >= p->first + THEME_MAX_ROWS)
        p->first = p->sel - THEME_MAX_ROWS + 1;
    if (p->first > n - THEME_MAX_ROWS) p->first = n - THEME_MAX_ROWS;
    if (p->first < 0) p->first = 0;
}

static int visible_rows(panel_t *p)
{
    int n = p->apps->n - p->first;
    if (n > THEME_MAX_ROWS) n = THEME_MAX_ROWS;
    return n < 0 ? 0 : n;
}

static void paint_all(panel_t *p, double a)
{
    cairo_t *cr = p->cr;
    cairo_set_operator(cr, CAIRO_OPERATOR_SOURCE);
    set_rgba(cr, (rgb_t){ 0, 0, 0 }, 0.0);
    cairo_paint(cr);
    cairo_set_operator(cr, CAIRO_OPERATOR_OVER);

    set_rgba(cr, p->c_bg, p->have_cx ? a : 1.0);
    round_rect(cr, 0, 0, p->want_w, p->want_h, THEME_RADIUS);
    cairo_fill(cr);
    cairo_set_line_width(cr, 1.0);
    set_rgba(cr, p->c_rose, a * 0.9);
    round_rect(cr, 0.5, 0.5, p->want_w - 1, p->want_h - 1, THEME_RADIUS);
    cairo_stroke(cr);

    double y = THEME_PAD_Y;
    if (p->apps->n == 0) {
        type_text(&p->row, "no windows on this workspace", 0);
        int tw = 0, th = 0;
        pango_layout_get_pixel_size(p->row.lay, &tw, &th);
        type_draw(&p->row, cr, p->c_muted, a * 0.9,
                  (p->want_w - tw) / 2, y);
    } else {
        for (int r = 0; r < visible_rows(p); r++) {
            int i = p->first + r;
            int sel = (i == p->sel);
            char line[1152];
            snprintf(line, sizeof line, "%s %s", sel ? "»" : " ",
                     p->apps->v[i].title);
            type_text(&p->row, line, p->inner_w);
            type_draw(&p->row, cr, sel ? p->c_pink : p->c_silver,
                      a * (sel ? 1.0 : 0.9), THEME_PAD_X, y);
            y += p->row_h + THEME_ROW_GAP;
        }
    }
    foot_text(&p->foot, p->inner_w);
    type_draw(&p->foot, cr, p->c_muted, a * 0.9, THEME_PAD_X, y + 2);

    cairo_surface_flush(p->surf);
    XSync(p->dpy, False);
}

panel_t *panel_open(Display *dpy, int scr, winlist_t *apps, int sel,
                    int force_opaque)
{
    int screen_w = DisplayWidth(dpy, scr);
    int screen_h = DisplayHeight(dpy, scr);

    panel_t *p = calloc(1, sizeof *p);
    p->dpy = dpy;
    p->scr = scr;
    p->apps = apps;
    p->sel = (sel >= 0 && sel < apps->n) ? sel : 0;

    if (force_opaque)                  p->have_cx = 0;
    else if (compositor_present(dpy))  p->have_cx = 1;
    else if (getenv("FAE_HUD_FORCE_OPAQUE")) p->have_cx = 0;

    XVisualInfo vinfo, *vi = NULL;
    int depth = CopyFromParent;
    Visual *visual = DefaultVisual(dpy, scr);
    if (p->have_cx && XMatchVisualInfo(dpy, scr, 32, TrueClass, &vinfo)) {
        vi = &vinfo;
        visual = vinfo.visual;
        depth = vinfo.depth;
    }

    p->ctx = pango_font_map_create_context(pango_cairo_font_map_get_default());
    type_open(&p->row, p->ctx, THEME_FONT_ROW);
    type_open(&p->foot, p->ctx, THEME_FONT_FOOT);

    /* Width fits the longest title, clamped. Height fits the rows. */
    int max_tw = 0;
    for (int i = 0; i < apps->n; i++) {
        type_text(&p->row, apps->v[i].title, 0);
        int w = 0, h = 0;
        pango_layout_get_pixel_size(p->row.lay, &w, &h);
        if (w > max_tw) max_tw = w;
    }
    p->row_h = type_h(&p->row);
    if (p->row_h <= 0) p->row_h = THEME_SIZE_ROW + 8;
    p->inner_w = max_tw + 30;   /* room for the » marker */
    p->want_w = THEME_PAD_X * 2 + p->inner_w;
    if (p->want_w < THEME_MIN_W) p->want_w = THEME_MIN_W;
    if (p->want_w > THEME_MAX_W) {
        p->want_w = THEME_MAX_W;
        p->inner_w = p->want_w - THEME_PAD_X * 2;
    }
    int rows = visible_rows(p);
    if (rows == 0) rows = 1;
    p->want_h = THEME_PAD_Y * 2 + rows * (p->row_h + THEME_ROW_GAP)
              - THEME_ROW_GAP + THEME_FOOT_GAP + THEME_SIZE_FOOT + 8;

    p->px = (screen_w - p->want_w) / 2;
    p->py = (int)(screen_h * THEME_ROW_TOP_FRACTION);
    if (p->px < 0) p->px = 0;
    if (p->py < 0) p->py = 0;
    ensure_visible(p);

    XSetWindowAttributes attr;
    memset(&attr, 0, sizeof attr);
    attr.override_redirect = True;
    attr.background_pixel  = 0;
    attr.border_pixel      = 0;
    attr.colormap = vi ? XCreateColormap(dpy, DefaultRootWindow(dpy), visual,
                                         AllocNone)
                       : DefaultColormap(dpy, scr);
    attr.event_mask = ExposureMask | StructureNotifyMask;

    p->win = XCreateWindow(dpy, DefaultRootWindow(dpy), p->px, p->py,
                           (unsigned)p->want_w, (unsigned)p->want_h, 0,
                           depth, InputOutput, visual,
                           CWOverrideRedirect | CWBackPixel | CWBorderPixel
                               | CWColormap | CWEventMask, &attr);
    if (!p->win) {
        type_free(&p->row); type_free(&p->foot);
        g_object_unref(p->ctx); free(p); return NULL;
    }

    Atom wtype = XInternAtom(dpy, "_NET_WM_WINDOW_TYPE_DOCK", False);
    XChangeProperty(dpy, p->win, XInternAtom(dpy, "_NET_WM_WINDOW_TYPE", False),
                    XA_ATOM, 32, PropModeReplace, (unsigned char *)&wtype, 1);
    XChangeProperty(dpy, p->win, XInternAtom(dpy, "_NET_WM_NAME", False),
                    XInternAtom(dpy, "UTF8_STRING", False), 8,
                    PropModeReplace, (unsigned char *)"fae-hud", 7);
    XChangeProperty(dpy, p->win, XA_WM_NAME, XA_STRING, 8, PropModeReplace,
                    (unsigned char *)"fae-hud", 7);

    XMapRaised(dpy, p->win);
    XSync(dpy, False);
    p->surf = cairo_xlib_surface_create(dpy, p->win, visual,
                                        p->want_w, p->want_h);
    p->cr = cairo_create(p->surf);

    p->c_bg     = hex_rgb(THEME_BG);
    p->c_pink   = hex_rgb(THEME_PINK);
    p->c_fg     = hex_rgb(THEME_FG);
    p->c_silver = hex_rgb(THEME_SILVER);
    p->c_muted  = hex_rgb(THEME_MUTED);
    p->c_rose   = hex_rgb(THEME_ROSE);

    if (getenv("FAE_HUD_VERBOSE"))
        fprintf(stderr, "fae-hud: panel at (%d,%d) %dx%d apps=%d sel=%d\n",
                p->px, p->py, p->want_w, p->want_h, apps->n, p->sel);

    paint_all(p, 1.0);
    return p;
}

int panel_count(panel_t *p) { return p ? p->apps->n : 0; }

Window panel_xid_at(panel_t *p, int i)
{
    return (p && i >= 0 && i < p->apps->n) ? p->apps->v[i].xid : None;
}

void panel_select(panel_t *p, int sel)
{
    if (!p || p->apps->n <= 0) return;
    if (sel < 0) sel = 0;
    if (sel >= p->apps->n) sel = p->apps->n - 1;
    if (sel == p->sel) return;
    p->sel = sel;
    ensure_visible(p);
    paint_all(p, 1.0);
}

Window panel_target(panel_t *p)
{
    if (!p || p->apps->n <= 0) return None;
    if (p->sel < 0 || p->sel >= p->apps->n) return None;
    return p->apps->v[p->sel].xid;
}

const char *panel_title(panel_t *p)
{
    if (!p || p->apps->n <= 0) return "";
    if (p->sel < 0 || p->sel >= p->apps->n) return "";
    return p->apps->v[p->sel].title;
}

void panel_close(panel_t *p)
{
    if (!p) return;
    long t0 = now_ms();
    for (;;) {
        long el = now_ms() - t0;
        if (el >= THEME_OUT) break;
        paint_all(p, 1.0 - ease((double)el / THEME_OUT));
        struct timespec nap = { 0, 16L * 1000L * 1000L };
        nanosleep(&nap, NULL);
        while (XPending(p->dpy)) { XEvent ev; XNextEvent(p->dpy, &ev); }
    }
    cairo_destroy(p->cr);
    cairo_surface_destroy(p->surf);
    XDestroyWindow(p->dpy, p->win);
    XSync(p->dpy, False);
    type_free(&p->row);
    type_free(&p->foot);
    g_object_unref(p->ctx);
    free(p);
}

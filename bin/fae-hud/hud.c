/* hud.c — the switcher strip.
 *
 * A macOS-style row: one icon per application, centred, ~20% down. Override
 * redirect, so it floats above everything the window manager manages without
 * taking focus, and it selects no button events so clicks pass through.
 *
 * Drawn with cairo and pango. Xft has no arc primitive — only Rect, String,
 * Glyphs — so it cannot round a corner, and it cannot composite a window icon
 * either.
 *
 * It never moves, kills or resizes anything. It draws a list and highlights an
 * entry; committing is hold.c's job, through the EWMH _NET_ACTIVE_WINDOW
 * message.
 *
 * cairo's origin is the SURFACE. h->px/h->py place the window on the desktop
 * and are NOT drawing coordinates — using them here put every shape outside
 * its own canvas and left a blank rectangle. Everything below is 0,0-based.
 */
#include "hud.h"
#include "theme.h"

#include <ctype.h>
#include <math.h>
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

/* ── colour ──────────────────────────────────────────────────────────────── */

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

static rgb_t mix(rgb_t a, rgb_t b, double t)
{
    if (t < 0) t = 0;
    if (t > 1) t = 1;
    rgb_t c = { 0, 0, 0 };
    c.r = a.r + (b.r - a.r) * t;
    c.g = a.g + (b.g - a.g) * t;
    c.b = a.b + (b.b - a.b) * t;
    return c;
}

static void set_rgba(cairo_t *cr, rgb_t c, double a)
{
    if (a < 0) a = 0;
    if (a > 1) a = 1;
    cairo_set_source_rgba(cr, c.r, c.g, c.b, a);
}

/* ── shape ───────────────────────────────────────────────────────────────── */

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

/* ── type ────────────────────────────────────────────────────────────────── */

typedef struct {
    PangoLayout           *lay;
    PangoFontDescription *desc;
} type_t;

static void type_open(type_t *t, PangoContext *ctx, int px)
{
    t->desc = pango_font_description_new();
    pango_font_description_set_family(t->desc, THEME_FONT);
    pango_font_description_set_absolute_size(t->desc, px * PANGO_SCALE);
    t->lay = pango_layout_new(ctx);
    pango_layout_set_font_description(t->lay, t->desc);
    pango_layout_set_single_paragraph_mode(t->lay, TRUE);
}

static void type_free(type_t *t)
{
    if (t->lay)  g_object_unref(t->lay);
    /* PangoFontDescription is boxed, not a GObject: g_object_unref on it
     * segfaults inside g_type_check_instance_is_fundamentally_a. */
    if (t->desc) pango_font_description_free(t->desc);
    t->lay = NULL;
    t->desc = NULL;
}

static void type_set(type_t *t, const char *s, int max_px)
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

static int type_w(type_t *t)
{
    int w = 0, h = 0;
    pango_layout_get_pixel_size(t->lay, &w, &h);
    return w;
}

static int type_h(type_t *t)
{
    int w = 0, h = 0;
    pango_layout_get_pixel_size(t->lay, &w, &h);
    return h;
}

/* NB: pango_cairo_show_layout() positions the layout by its TOP-LEFT at the
 * current cairo point. It does NOT treat y as a text baseline. Every `y` in
 * this file is therefore a top edge, not a baseline — getting that backwards
 * put the window-count number underneath its badge instead of inside it. */
static void type_draw(type_t *t, cairo_t *cr, rgb_t col, double a,
                      double x, double top)
{
    set_rgba(cr, col, a);
    cairo_move_to(cr, x, top);
    pango_cairo_show_layout(cr, t->lay);
}

/* ── the strip ───────────────────────────────────────────────────────────── */

struct hud {
    Display   *dpy;
    int        scr;
    Window     win;
    cairo_surface_t *surf;
    cairo_t   *cr;
    PangoContext *ctx;
    type_t     label, meta;
    elist_t   *apps;
    int        sel;
    int        have_cx;
    int        want_w, want_h, px, py;
    int        icon_px, cell_w, label_h, count_h;
    int        first;        /* leftmost visible entry, for scrolling */
    const char *message;
    rgb_t c_void, c_panel, c_pink, c_psoft, c_fg, c_dim, c_lilac, c_far;
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

/* Keep `sel` on screen by sliding the window of visible entries. */
static void ensure_visible(hud_t *h)
{
    int n = h->apps->n;
    if (n <= 0) return;
    int visible = h->want_w / (h->cell_w ? h->cell_w : 1);
    if (visible < 1) visible = 1;
    if (visible >= n) { h->first = 0; return; }
    if (h->sel < h->first) h->first = h->sel;
    if (h->sel >= h->first + visible) h->first = h->sel - visible + 1;
    if (h->first > n - visible) h->first = n - visible;
    if (h->first < 0) h->first = 0;
}

/* one entry: icon (or a drawn monogram) plus its label */
static void paint_entry(hud_t *h, int i, double a)
{
    cairo_t *cr = h->cr;
    entry_t *e = &h->apps->v[i];
    int sel = (i == h->sel);
    double s = sel ? 1.0 : 0.78;   /* artwork scale inside the constant box */
    double dim = sel ? 1.0 : 0.55;

    int x = THEME_PAD_X + (i - h->first) * h->cell_w;
    if (x + h->cell_w < 0 || x > h->want_w) return;      /* scrolled out */

    /* One constant box for every entry, with only the artwork scaled inside
     * it. Scaling the box too made the selected entry's label sit lower than
     * every other label, so the row's baseline jumped on every Tab. */
    int box = (int)(h->icon_px * THEME_ICON_SEL_SCALE);
    int isz = (int)(h->icon_px * s);
    int cx = x + h->cell_w / 2;
    int iy = THEME_PAD_Y;

    /* selection plate */
    if (sel) {
        /* Clearly larger than the artwork. At only 3px of margin the plate
         * showed as two stray corner slivers either side of the icon, which
         * read as artefacts rather than as a selection. */
        int pw = box + 14, ph = box + 12;
        set_rgba(cr, h->c_pink, 0.20 * a);
        round_rect(cr, cx - pw / 2, iy - 6, pw, ph, 14);
        cairo_fill(cr);
        cairo_set_line_width(cr, 1.0);
        set_rgba(cr, h->c_pink, 0.55 * a);
        round_rect(cr, cx - pw / 2, iy - 6, pw, ph, 14);
        cairo_stroke(cr);
    }

    int ix = cx - isz / 2;   /* the artwork may be smaller than the box */
    if (e->icon) {
        cairo_save(cr);
        cairo_set_operator(cr, CAIRO_OPERATOR_OVER);
        cairo_translate(cr, ix, iy);
        cairo_scale(cr, (double)isz / THEME_ICON_PX, (double)isz / THEME_ICON_PX);
        cairo_set_source_surface(cr, e->icon, 0, 0);
        cairo_pattern_set_filter(cairo_get_source(cr), CAIRO_FILTER_GOOD);
        cairo_paint_with_alpha(cr, a * dim);
        cairo_restore(cr);
    } else {
        /* No icon published: a drawn tile with the app's initial, so a row
         * never has a hole in it. */
        /* No icon published: a flat plate with the app's initial, so a row
         * never has a hole. Kept plain on purpose — a gradient or a tinted
         * blob competed with the real icons next to it. */
        /* A circle, not a rounded square. round_rect() draws the panel and the
         * selection plate correctly, but on this square it produced a
         * malformed path — concave bites out of the right and bottom edges and
         * two stray quarter-arcs at the opposite corners. I could not
         * account for it by reading the code and did not want to keep guessing,
         * so the fallback uses the one primitive that cannot come out wrong.
         * A monogram in a disc reads perfectly well in a row of app icons. */
        int px0 = cx - box / 2, psz = box;
        double ccx = px0 + psz / 2.0, ccy = iy + psz / 2.0, rad = psz / 2.0 - 1;
        set_rgba(cr, mix(h->c_panel, h->c_fg, 0.20), a);
        cairo_arc(cr, ccx, ccy, rad, 0, 2 * M_PI);
        cairo_fill(cr);
        cairo_set_line_width(cr, 1.0);
        set_rgba(cr, mix(h->c_panel, h->c_fg, 0.38), a);
        cairo_arc(cr, ccx, ccy, rad, 0, 2 * M_PI);
        cairo_stroke(cr);
        char ini[2] = { e->label[0] ? (char)toupper((unsigned char)e->label[0]) : '?', 0 };
        type_set(&h->label, ini, 0);
        int tw = type_w(&h->label);
        type_draw(&h->label, cr, sel ? h->c_fg : h->c_fg, a * (sel ? 1.0 : 0.8),
                  cx - tw / 2, iy + psz / 2 + h->label_h / 3);
    }

    /* label */
    rgb_t lc = sel ? h->c_fg : h->c_dim;
    type_set(&h->label, e->label, h->cell_w - 8);
    int tw = type_w(&h->label);
    type_draw(&h->label, cr, lc, a * (sel ? 1.0 : 0.75),
              cx - tw / 2, iy + box + THEME_LABEL_GAP + h->label_h * 0.8);

    /* window count, when the app owns more than one */
    if (e->count > 1) {
        char b[16];
        snprintf(b, sizeof b, "%d", e->count);
        type_set(&h->meta, b, 0);
        int bw = type_w(&h->meta), bh = type_h(&h->meta);
        double r = (bh * 0.5 > 8) ? bh * 0.5 : 8;
        double bx = cx + box / 2.0 - 2, by = iy + box - 2;
        set_rgba(cr, h->c_panel, a);
        cairo_arc(cr, bx, by, r + 2, 0, 2 * M_PI);
        cairo_fill(cr);
        set_rgba(cr, h->c_pink, a);
        cairo_arc(cr, bx, by, r, 0, 2 * M_PI);
        cairo_fill(cr);
        type_draw(&h->meta, cr, h->c_void, a, bx - bw / 2.0, by - bh / 2.0);
    }
}

static void paint_all(hud_t *h, double a)
{
    cairo_t *cr = h->cr;
    cairo_set_operator(cr, CAIRO_OPERATOR_SOURCE);
    set_rgba(cr, h->c_void, h->have_cx ? 0.0 : 1.0);
    cairo_paint(cr);
    cairo_set_operator(cr, CAIRO_OPERATOR_OVER);

    /* Opaque. A see-through strip over a light wallpaper let terminal text
     * bleed through and the whole thing turned to mush; a switcher has to be
     * the one solid thing on screen. Translucency is still available via
     * --opaque being absent, but the default is now readable. */
    set_rgba(cr, h->c_panel, h->have_cx ? a : 1.0);   /* crisp edge, no halo */
    round_rect(cr, 0, 0, h->want_w, h->want_h, THEME_RADIUS);
    cairo_fill(cr);
    cairo_set_line_width(cr, 1.0);
    set_rgba(cr, mix(h->c_panel, h->c_pink, 0.45), a * 0.9);
    round_rect(cr, 0.5, 0.5, h->want_w - 1, h->want_h - 1, THEME_RADIUS);
    cairo_stroke(cr);

    /* corner facets, kept clear of the text which starts at THEME_PAD_X */
    set_rgba(cr, h->c_lilac, a * 0.30);
    for (int c = 0; c < 4; c++) {
        double fx = (c & 1) ? h->want_w - THEME_FACET_INSET : THEME_FACET_INSET;
        double fy = (c & 2) ? h->want_h - THEME_FACET_INSET : THEME_FACET_INSET;
        cairo_move_to(cr, fx, fy - THEME_FACET_R);
        cairo_line_to(cr, fx + THEME_FACET_R, fy);
        cairo_line_to(cr, fx, fy + THEME_FACET_R);
        cairo_line_to(cr, fx - THEME_FACET_R, fy);
        cairo_close_path(cr);
        cairo_fill(cr);
    }

    if (h->apps->n == 0) {
        type_set(&h->label, h->message ? h->message : "nothing to switch to", 0);
        int tw = type_w(&h->label);
        type_draw(&h->label, cr, h->c_dim, a * 0.9,
                  h->want_w / 2 - tw / 2, h->want_h / 2 + h->label_h / 3);
    } else {
        for (int i = 0; i < h->apps->n; i++)
            paint_entry(h, i, a);
    }
    cairo_surface_flush(h->surf);
    XSync(h->dpy, False);
}

hud_t *hud_open(Display *dpy, int scr, elist_t *apps, int sel, int force_opaque)
{
    int screen_w = DisplayWidth(dpy, scr);
    int screen_h = DisplayHeight(dpy, scr);

    hud_t *h = calloc(1, sizeof *h);
    h->dpy = dpy;
    h->scr = scr;
    h->apps = apps;
    h->sel = (sel >= 0 && sel < apps->n) ? sel : 0;
    h->message = "no windows on this workspace";

    if (force_opaque)               h->have_cx = 0;
    else if (compositor_present(dpy)) h->have_cx = 1;
    else if (getenv("FAE_HUD_FORCE_OPAQUE")) h->have_cx = 0;

    XVisualInfo vinfo, *vi = NULL;
    int depth = CopyFromParent;
    Visual *visual = DefaultVisual(dpy, scr);
    if (h->have_cx && XMatchVisualInfo(dpy, scr, 32, TrueClass, &vinfo)) {
        vi = &vinfo;
        visual = vinfo.visual;
        depth = vinfo.depth;
    }

    h->ctx = pango_font_map_create_context(pango_cairo_font_map_get_default());
    type_open(&h->label, h->ctx, THEME_SIZE_LABEL);
    type_open(&h->meta,  h->ctx, THEME_SIZE_META);
    h->label_h = type_h(&h->label) > 0 ? type_h(&h->label) : THEME_SIZE_LABEL + 4;

    /* Fit: shrink the icons if there are many apps, and only scroll if even
     * the smallest icons would not fit. */
    int n = apps->n > 0 ? apps->n : 1;
    int max_icons = (screen_w * 80) / 100;
    int icon = THEME_ICON_PX;
    int cell = THEME_CELL_W;
    while (n * cell > max_icons && icon > THEME_MIN_ICON_PX) {
        icon = (int)(icon * 0.92);
        cell = (int)(icon * 1.5);
    }
    h->icon_px = icon;
    h->cell_w  = cell;
    h->count_h = h->label_h;

    h->want_w = THEME_PAD_X * 2 + n * cell;
    if (h->want_w > max_icons + THEME_PAD_X * 2)
        h->want_w = max_icons + THEME_PAD_X * 2;
    h->want_h = THEME_PAD_Y * 2 + (int)(icon * THEME_ICON_SEL_SCALE) + 12
              + THEME_LABEL_GAP + h->label_h;

    h->px = (screen_w - h->want_w) / 2;
    h->py = (int)(screen_h * THEME_ROW_TOP_FRACTION);
    if (h->px < 0) h->px = 0;
    if (h->py < 0) h->py = 0;
    ensure_visible(h);

    XSetWindowAttributes attr;
    memset(&attr, 0, sizeof attr);
    attr.override_redirect = True;
    attr.background_pixel  = 0;
    attr.border_pixel      = 0;
    attr.colormap = vi ? XCreateColormap(dpy, DefaultRootWindow(dpy), visual,
                                         AllocNone)
                       : DefaultColormap(dpy, scr);
    attr.event_mask = ExposureMask | StructureNotifyMask;

    h->win = XCreateWindow(dpy, DefaultRootWindow(dpy), h->px, h->py,
                           (unsigned)h->want_w, (unsigned)h->want_h, 0,
                           depth, InputOutput, visual,
                           CWOverrideRedirect | CWBackPixel | CWBorderPixel
                               | CWColormap | CWEventMask, &attr);
    if (!h->win) { type_free(&h->label); type_free(&h->meta);
                   g_object_unref(h->ctx); free(h); return NULL; }

    Atom wtype = XInternAtom(dpy, "_NET_WM_WINDOW_TYPE_DOCK", False);
    XChangeProperty(dpy, h->win, XInternAtom(dpy, "_NET_WM_WINDOW_TYPE", False),
                    XA_ATOM, 32, PropModeReplace, (unsigned char *)&wtype, 1);
    XChangeProperty(dpy, h->win, XInternAtom(dpy, "_NET_WM_NAME", False),
                    XInternAtom(dpy, "UTF8_STRING", False), 8,
                    PropModeReplace, (unsigned char *)"fae-hud", 7);
    XChangeProperty(dpy, h->win, XA_WM_NAME, XA_STRING, 8, PropModeReplace,
                    (unsigned char *)"fae-hud", 7);

    XMapRaised(dpy, h->win);
    XSync(dpy, False);
    h->surf = cairo_xlib_surface_create(dpy, h->win, visual, h->want_w, h->want_h);
    h->cr = cairo_create(h->surf);

    h->c_void  = hex_rgb(THEME_VOID);
    h->c_panel = hex_rgb(THEME_PANEL);
    h->c_pink  = hex_rgb(THEME_PINK);
    h->c_psoft = hex_rgb(THEME_PINK_SOFT);
    h->c_fg    = hex_rgb(THEME_FG);
    h->c_dim   = hex_rgb(THEME_FG_DIM);
    h->c_lilac = hex_rgb(THEME_LILAC);
    h->c_far   = hex_rgb(THEME_FAR);

    if (getenv("FAE_HUD_VERBOSE"))
        fprintf(stderr, "fae-hud: strip at (%d,%d) %dx%d apps=%d icon=%d "
                        "cell=%d sel=%d\n",
                h->px, h->py, h->want_w, h->want_h, apps->n, h->icon_px,
                h->cell_w, h->sel);

    paint_all(h, 1.0);
    return h;
}

int  hud_count(hud_t *h)      { return h ? h->apps->n : 0; }
int  hud_selection(hud_t *h) { return h ? h->sel : -1; }

void hud_select(hud_t *h, int sel)
{
    if (!h || h->apps->n <= 0) return;
    if (sel < 0) sel = 0;
    if (sel >= h->apps->n) sel = h->apps->n - 1;
    if (sel == h->sel) return;
    h->sel = sel;
    ensure_visible(h);
    paint_all(h, 1.0);
}

Window hud_target(hud_t *h)
{
    if (!h || h->apps->n <= 0) return None;
    if (h->sel < 0 || h->sel >= h->apps->n) return None;
    return h->apps->v[h->sel].xid;
}

const char *hud_label(hud_t *h)
{
    if (!h || h->apps->n <= 0) return "";
    if (h->sel < 0 || h->sel >= h->apps->n) return "";
    return h->apps->v[h->sel].label;
}

void hud_close(hud_t *h)
{
    if (!h) return;
    long t0 = now_ms();
    for (;;) {
        long el = now_ms() - t0;
        if (el >= THEME_OUT) break;
        paint_all(h, 1.0 - ease((double)el / THEME_OUT));
        struct timespec nap = { 0, 16L * 1000L * 1000L };
        nanosleep(&nap, NULL);
        while (XPending(h->dpy)) { XEvent ev; XNextEvent(h->dpy, &ev); }
    }
    cairo_destroy(h->cr);
    cairo_surface_destroy(h->surf);
    XDestroyWindow(h->dpy, h->win);
    XSync(h->dpy, False);
    type_free(&h->label);
    type_free(&h->meta);
    g_object_unref(h->ctx);
    free(h);
}

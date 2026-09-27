/* hud.c — the overlay panel.
 *
 * An override-redirect window, centred, never focused, so it floats above
 * everything the window manager manages without stealing the keyboard or the
 * pointer. It selects no button events, so clicks pass straight through.
 *
 * Drawn with cairo and pango. Xft has no arc primitive — only Rect, String,
 * Glyphs — so it cannot round a corner at all, and cairo also gives the
 * per-pixel alpha that plain X11 cannot.
 *
 * The panel does not focus, move or resize anything. It draws a list and
 * highlights a row; committing is someone else's job (hold.c, via the EWMH
 * _NET_ACTIVE_WINDOW message).
 */
#include "hud.h"
#include "theme.h"

#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <fcntl.h>
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
    rgb_t c;
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

static void glow_stroke(cairo_t *cr, rgb_t col, double alpha,
                        double x, double y, double w, double h, double r)
{
    for (int i = THEME_GLOW_STEPS; i >= 1; i--) {
        double f = 1.0 - (double)(i - 1) / THEME_GLOW_STEPS;
        cairo_set_line_width(cr, i * 2.0);
        set_rgba(cr, col, alpha * 0.10 * f);
        round_rect(cr, x, y, w, h, r);
        cairo_stroke(cr);
    }
}

static void diamond(cairo_t *cr, double cx, double cy, double r)
{
    cairo_move_to(cr, cx,     cy - r);
    cairo_line_to(cr, cx + r, cy);
    cairo_line_to(cr, cx,     cy + r);
    cairo_line_to(cr, cx - r, cy);
    cairo_close_path(cr);
}

/* ── type ────────────────────────────────────────────────────────────────── */

typedef struct {
    PangoLayout           *lay;
    PangoFontDescription *desc;
} type_t;

static void type_open(type_t *t, PangoContext *ctx, int size_px)
{
    t->desc = pango_font_description_new();
    pango_font_description_set_family(t->desc, THEME_FONT);
    pango_font_description_set_absolute_size(t->desc, size_px * PANGO_SCALE);
    t->lay = pango_layout_new(ctx);
    pango_layout_set_font_description(t->lay, t->desc);
    pango_layout_set_single_paragraph_mode(t->lay, TRUE);
}

static void type_close(type_t *t)
{
    /* PangoLayout is a GObject; PangoFontDescription is NOT — it is a boxed
     * type, and g_object_unref on it reads a GTypeInstance out of memory that
     * does not have one. It survived several runs by luck before ASan caught
     * it segfaulting inside g_type_check_instance_is_fundamentally_a. */
    if (t->lay)  g_object_unref(t->lay);
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
    int w = 0, hh = 0;
    pango_layout_get_pixel_size(t->lay, &w, &hh);
    return w;
}

static int type_h(type_t *t)
{
    int w = 0, hh = 0;
    pango_layout_get_pixel_size(t->lay, &w, &hh);
    return hh;
}

static void type_draw(type_t *t, cairo_t *cr, rgb_t col, double a,
                      double x, double baseline)
{
    set_rgba(cr, col, a);
    cairo_move_to(cr, x, baseline);
    pango_cairo_show_layout(cr, t->lay);
}

/* ── the panel ───────────────────────────────────────────────────────────── */

struct hud {
    Display   *dpy;
    int        scr;
    Window     win;
    Visual    *visual;
    cairo_surface_t *surf;
    cairo_t   *cr;
    Colormap   cmap;
    PangoContext *ctx;
    type_t     title, meta, head;
    wlist_t   *list;
    int        shown, hidden, sel;
    int        have_cx;
    /* layout */
    int        want_w, want_h, px, py;
    int        line_title, line_meta, line_head, row_h, text_x, text_max;
    int        body_top, body_h;
    /* palette */
    rgb_t c_void, c_panel, c_pink, c_psoft, c_fg, c_dim, c_lilac, c_far;
    /* the message shown instead of rows, when there is nothing to cycle */
    const char *message;
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

/* Plain X11 has no per-window alpha: without a compositor the transparent
 * pixels come out black. Ask before choosing a visual. */
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

/* ── painting ────────────────────────────────────────────────────────────── */

/* one row: optional band, glyph, hairline, title, meta */
static void paint_row(hud_t *h, int i, double alpha, double wipe)
{
    int sel = (i == h->sel);
    double x0 = h->px + THEME_PAD_X;
    double tx = x0 + h->text_x;
    double y = h->body_top + i * h->row_h;
    double base = y + h->line_title * 0.78;
    double rad = THEME_RADIUS * 0.6;
    cairo_t *cr = h->cr;

    if (sel && wipe > 0.001) {
        cairo_save(cr);
        cairo_rectangle(cr, h->px, y - 5, h->want_w * wipe,
                        h->line_title + THEME_LINE_GAP + h->line_meta);
        cairo_clip(cr);
        set_rgba(cr, h->c_pink, 0.20 * alpha);
        round_rect(cr, h->px + 1, y - 5, h->want_w - 2,
                   h->line_title + THEME_LINE_GAP + h->line_meta, rad);
        cairo_fill(cr);
        set_rgba(cr, h->c_pink, 0.34 * alpha);
        cairo_set_line_width(cr, 1.0);
        round_rect(cr, h->px + 1.5, y - 4.5, h->want_w - 3,
                   h->line_title + THEME_LINE_GAP + h->line_meta - 1, rad);
        cairo_stroke(cr);
        cairo_restore(cr);
    }

    rgb_t want_c = sel ? h->c_pink : h->c_fg;
    rgb_t rowc = mix(h->c_panel, want_c, alpha);

    type_set(&h->title, sel ? THEME_GLYPH_FOCUS : THEME_GLYPH_IDLE, 0);
    type_draw(&h->title, cr, rowc, alpha, x0, base);

    cairo_set_line_width(cr, 1.0);
    set_rgba(cr, h->c_lilac, alpha * 0.18);
    cairo_move_to(cr, x0 + h->text_x - THEME_GAP / 2.0, y + 2);
    cairo_line_to(cr, x0 + h->text_x - THEME_GAP / 2.0,
                  y + h->line_title + THEME_LINE_GAP + h->line_meta - 2);
    cairo_stroke(cr);

    type_set(&h->title, h->list->v[i].title, h->text_max);
    type_draw(&h->title, cr, rowc, alpha, tx, base);

    char b[512];
    snprintf(b, sizeof b, "%s%lu %s %s",
             h->list->v[i].desktop_known ? "" : "?",
             h->list->v[i].desktop, THEME_GLYPH_DOT, h->list->v[i].cls);
    type_set(&h->meta, b, h->text_max);
    rgb_t metac = sel ? h->c_psoft : h->c_dim;
    type_draw(&h->meta, cr, mix(h->c_panel, metac, alpha),
              alpha * (sel ? 1.0 : 0.85), tx,
              y + h->line_title + THEME_LINE_GAP + h->line_meta * 0.8);
}

/* the panel background, header, footer, corner facets */
static void paint_chrome(hud_t *h, double alpha)
{
    cairo_t *cr = h->cr;
    double x0 = h->px + THEME_PAD_X;
    double right = h->px + h->want_w - THEME_PAD_X;
    double y = h->py + THEME_PAD_Y;

    glow_stroke(cr, h->c_pink, alpha * 0.9, h->px, h->py, h->want_w,
                h->want_h, THEME_RADIUS);
    set_rgba(cr, h->c_panel, h->have_cx ? alpha : 1.0);
    round_rect(cr, h->px, h->py, h->want_w, h->want_h, THEME_RADIUS);
    cairo_fill(cr);
    cairo_set_line_width(cr, 1.0);
    set_rgba(cr, mix(h->c_panel, h->c_pink, 0.55), alpha);
    round_rect(cr, h->px + 0.5, h->py + 0.5, h->want_w - 1, h->want_h - 1,
               THEME_RADIUS);
    cairo_stroke(cr);

    set_rgba(cr, h->c_lilac, alpha * 0.34);
    diamond(cr, h->px + THEME_FACET_INSET, h->py + THEME_FACET_INSET,
            THEME_FACET_R); cairo_fill(cr);
    diamond(cr, h->px + h->want_w - THEME_FACET_INSET,
            h->py + THEME_FACET_INSET, THEME_FACET_R); cairo_fill(cr);
    diamond(cr, h->px + THEME_FACET_INSET,
            h->py + h->want_h - THEME_FACET_INSET, THEME_FACET_R);
    cairo_fill(cr);
    diamond(cr, h->px + h->want_w - THEME_FACET_INSET,
            h->py + h->want_h - THEME_FACET_INSET, THEME_FACET_R);
    cairo_fill(cr);

    if (h->shown > 0) {
        type_set(&h->head, THEME_GLYPH_FOCUS " windows", 0);
        type_draw(&h->head, cr, h->c_lilac, alpha, x0, y + h->line_head);
        char cnt[24];
        snprintf(cnt, sizeof cnt, "%d", h->shown);
        type_set(&h->meta, cnt, 0);
        type_draw(&h->meta, cr, h->c_lilac, alpha * 0.8,
                  right - type_w(&h->meta), y + h->line_head);
    } else {
        type_set(&h->head, THEME_GLYPH_FOCUS " windows", 0);
        type_draw(&h->head, cr, h->c_lilac, alpha, x0, y + h->line_head);
    }

    y += h->line_head + THEME_RULE_GAP;
    cairo_set_line_width(cr, 1.0);
    set_rgba(cr, h->c_lilac, alpha * 0.22);
    cairo_move_to(cr, x0, y + 0.5);
    cairo_line_to(cr, right, y + 0.5);
    cairo_stroke(cr);

    if (h->shown == 0) {
        type_set(&h->meta, h->message ? h->message : "nothing here", 0);
        type_draw(&h->meta, cr, h->c_dim, alpha * 0.9, x0,
                  h->body_top + h->line_meta * 0.8);
    }

    double fy = h->py + h->want_h - THEME_PAD_Y - h->line_meta * 0.5;
    cairo_set_line_width(cr, 1.0);
    set_rgba(cr, h->c_lilac, alpha * 0.18);
    cairo_move_to(cr, x0, fy - h->line_meta);
    cairo_line_to(cr, right, fy - h->line_meta);
    cairo_stroke(cr);
    type_set(&h->meta, "tab next " THEME_GLYPH_DOT " shift+tab back "
                        THEME_GLYPH_DOT " esc cancel", 0);
    type_draw(&h->meta, cr, h->c_dim, alpha * 0.85, x0, fy);
}

static void paint_all(hud_t *h, double alpha, double wipe)
{
    cairo_t *cr = h->cr;
    cairo_set_operator(cr, CAIRO_OPERATOR_SOURCE);
    set_rgba(cr, h->c_void, h->have_cx ? 0.0 : 1.0);
    cairo_paint(cr);
    cairo_set_operator(cr, CAIRO_OPERATOR_OVER);

    paint_chrome(h, alpha);
    for (int i = 0; i < h->shown; i++)
        paint_row(h, i, alpha, i == h->sel ? wipe : 0.0);
    cairo_surface_flush(h->surf);
    XSync(h->dpy, False);
}

/* Repaint only the rows in [lo,hi], background included, so the selection can
 * move without the whole panel flickering. This is the "no redraw" the
 * Alt+Tab gesture needs: one panel, two bands. */
static void repaint_rows(hud_t *h, int lo, int hi)
{
    if (h->shown <= 0) return;
    if (lo < 0) lo = 0;
    if (hi >= h->shown) hi = h->shown - 1;
    if (lo > hi) return;

    cairo_t *cr = h->cr;
    double y0 = h->body_top + lo * h->row_h - 6;
    double y1 = h->body_top + (hi + 1) * h->row_h;

    cairo_save(cr);
    cairo_rectangle(cr, h->px, y0, h->want_w, y1 - y0);
    cairo_clip(cr);
    /* repaint the panel background under the clip, then just those rows */
    set_rgba(cr, h->c_panel, 1.0);
    round_rect(cr, h->px, h->py, h->want_w, h->want_h, THEME_RADIUS);
    cairo_fill(cr);
    for (int i = lo; i <= hi; i++)
        paint_row(h, i, 1.0, i == h->sel ? 1.0 : 0.0);
    cairo_restore(cr);

    cairo_surface_flush(h->surf);
    XSync(h->dpy, False);
}

/* ── construction ────────────────────────────────────────────────────────── */

hud_t *hud_open(Display *dpy, int scr, wlist_t *list, int sel, int force_opaque)
{
    int screen_w = DisplayWidth(dpy, scr);
    int screen_h = DisplayHeight(dpy, scr);

    hud_t *h = calloc(1, sizeof *h);
    h->dpy = dpy;
    h->scr = scr;
    h->list = list;

    if (force_opaque)          h->have_cx = 0;
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
    h->visual = visual;

    h->ctx = pango_font_map_create_context(pango_cairo_font_map_get_default());
    type_open(&h->title, h->ctx, THEME_SIZE_TITLE);
    type_open(&h->meta,  h->ctx, THEME_SIZE_META);
    type_open(&h->head,  h->ctx, THEME_SIZE_META);

    h->shown = list->n;
    h->hidden = 0;
    if (h->shown > THEME_MAX_ROWS) {
        h->hidden = h->shown - THEME_MAX_ROWS;
        h->shown = THEME_MAX_ROWS;
    }
    if (h->shown == 0)
        h->message = "no windows on this workspace";
    h->sel = (sel >= 0 && sel < h->shown) ? sel : 0;

    /* measure */
    int glyph_w = 0, title_max = 0, meta_max = 0;
    type_set(&h->head, THEME_GLYPH_FOCUS " windows", 0);
    type_set(&h->title, THEME_GLYPH_FOCUS, 0);
    glyph_w = type_w(&h->title);
    for (int i = 0; i < list->n; i++) {
        type_set(&h->title, list->v[i].title, 0);
        if (type_w(&h->title) > title_max) title_max = type_w(&h->title);
        char b[512];
        snprintf(b, sizeof b, "%s%lu %s %s",
                 list->v[i].desktop_known ? "" : "?", list->v[i].desktop,
                 THEME_GLYPH_DOT, list->v[i].cls);
        type_set(&h->meta, b, 0);
        if (type_w(&h->meta) > meta_max) meta_max = type_w(&h->meta);
    }

    h->line_title = type_h(&h->title) > 0 ? type_h(&h->title) : THEME_SIZE_TITLE + 4;
    h->line_meta  = type_h(&h->meta)  > 0 ? type_h(&h->meta)  : THEME_SIZE_META + 4;
    h->line_head  = type_h(&h->head)  > 0 ? type_h(&h->head)  : THEME_SIZE_META + 4;

    h->text_x = THEME_GLYPH_COL * (glyph_w > 0 ? glyph_w : 8) + THEME_GAP;
    h->want_w = THEME_PAD_X * 2 + h->text_x
              + (title_max > meta_max ? title_max : meta_max);
    int cap = (int)(screen_w * THEME_W_FRACTION);
    if (cap > THEME_MAX_W) cap = THEME_MAX_W;
    if (h->want_w > cap) h->want_w = cap;
    if (h->want_w < THEME_MIN_W) h->want_w = THEME_MIN_W;
    h->text_max = h->want_w - THEME_PAD_X * 2 - h->text_x;

    int rows_for_height = h->shown > 0 ? h->shown : 1;
    h->row_h = h->line_title + THEME_LINE_GAP + h->line_meta + THEME_ROW_GAP;
    h->body_h = rows_for_height * h->row_h;
    h->want_h = THEME_PAD_Y * 2 + h->line_head + THEME_RULE_GAP + h->body_h
              + THEME_RULE_GAP + h->line_meta + THEME_PAD_Y / 2;

    h->px = (screen_w - h->want_w) / 2;
    h->py = (screen_h - h->want_h) / 3;
    if (h->px < 0) h->px = 0;
    if (h->py < 0) h->py = 0;

    XSetWindowAttributes attr;
    memset(&attr, 0, sizeof attr);
    attr.override_redirect = True;
    attr.background_pixel  = 0;
    attr.border_pixel      = 0;
    attr.colormap = vi ? XCreateColormap(dpy, DefaultRootWindow(dpy), visual,
                                         AllocNone)
                       : DefaultColormap(dpy, scr);
    attr.event_mask = ExposureMask | StructureNotifyMask;
    h->cmap = attr.colormap;

    h->win = XCreateWindow(dpy, DefaultRootWindow(dpy), h->px, h->py,
                           (unsigned)h->want_w, (unsigned)h->want_h, 0,
                           depth, InputOutput, visual,
                           CWOverrideRedirect | CWBackPixel | CWBorderPixel
                               | CWColormap | CWEventMask, &attr);
    if (!h->win) {
        type_close(&h->title); type_close(&h->meta); type_close(&h->head);
        g_object_unref(h->ctx);
        free(h);
        return NULL;
    }

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

    h->surf = cairo_xlib_surface_create(dpy, h->win, visual, h->want_w,
                                        h->want_h);
    h->cr = cairo_create(h->surf);

    h->c_void   = hex_rgb(THEME_VOID);
    h->c_panel  = hex_rgb(THEME_PANEL);
    h->c_pink   = hex_rgb(THEME_PINK);
    h->c_psoft  = hex_rgb(THEME_PINK_SOFT);
    h->c_fg     = hex_rgb(THEME_FG);
    h->c_dim    = hex_rgb(THEME_FG_DIM);
    h->c_lilac  = hex_rgb(THEME_LILAC);
    h->c_far    = hex_rgb(THEME_FAR);

    h->body_top = h->py + THEME_PAD_Y + h->line_head + THEME_RULE_GAP
                + THEME_RULE_GAP;

    if (getenv("FAE_HUD_VERBOSE"))
        fprintf(stderr, "fae-hud: win=0x%lx at (%d,%d) %dx%d rows=%d shown=%d "
                        "sel=%d text_max=%d\n",
                (unsigned long)h->win, h->px, h->py, h->want_w, h->want_h,
                list->n, h->shown, h->sel, h->text_max);

    paint_all(h, 1.0, 1.0);
    return h;
}

int hud_rows(hud_t *h)      { return h ? h->shown : 0; }
int hud_selection(hud_t *h) { return h ? h->sel : -1; }

void hud_select(hud_t *h, int sel)
{
    if (!h || h->shown <= 0) return;
    if (sel < 0) sel = 0;
    if (sel >= h->shown) sel = h->shown - 1;
    if (sel == h->sel) return;
    int old = h->sel;
    h->sel = sel;
    int lo = old < sel ? old : sel;
    int hi = old > sel ? old : sel;
    repaint_rows(h, lo, hi);
}

void hud_close(hud_t *h)
{
    if (!h) return;
    cairo_t *cr = h->cr;
    long t0 = now_ms();
    for (;;) {
        long el = now_ms() - t0;
        if (el >= THEME_FADE_OUT) break;
        double a = 1.0 - ease((double)el / THEME_FADE_OUT);
        cairo_set_operator(cr, CAIRO_OPERATOR_SOURCE);
        set_rgba(cr, h->c_void, h->have_cx ? 0.0 : 1.0);
        cairo_paint(cr);
        cairo_set_operator(cr, CAIRO_OPERATOR_OVER);
        paint_chrome(h, a);
        for (int i = 0; i < h->shown; i++)
            paint_row(h, i, a, i == h->sel ? 1.0 : 0.0);
        cairo_surface_flush(h->surf);
        XSync(h->dpy, False);
        struct timespec nap = { 0, 16L * 1000L * 1000L };
        nanosleep(&nap, NULL);
        while (XPending(h->dpy)) { XEvent ev; XNextEvent(h->dpy, &ev); }
    }

    cairo_destroy(h->cr);
    cairo_surface_destroy(h->surf);
    XDestroyWindow(h->dpy, h->win);
    XSync(h->dpy, False);
    type_close(&h->title);
    type_close(&h->meta);
    type_close(&h->head);
    g_object_unref(h->ctx);
    free(h);
}

int hud_run(Display *dpy, int scr, wlist_t *list, int force_opaque)
{
    hud_t *h = hud_open(dpy, scr, list, list->n > 1 ? 1 : 0, force_opaque);
    if (!h) return 1;
    long hold = list->n > 0 ? THEME_HOLD : 700;
    long t0 = now_ms();
    for (;;) {
        if (now_ms() - t0 >= hold) break;
        struct timespec nap = { 0, 16L * 1000L * 1000L };
        nanosleep(&nap, NULL);
        while (XPending(dpy)) { XEvent ev; XNextEvent(dpy, &ev); }
    }
    hud_close(h);
    return 0;
}

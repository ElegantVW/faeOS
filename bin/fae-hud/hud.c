/* hud.c — the overlay panel.
 *
 * An override-redirect window, centred, never focused, so it floats above
 * everything i3 manages without stealing the keyboard or the pointer. It
 * selects no button events, so clicks pass straight through to whatever is
 * underneath.
 *
 * Drawn with cairo and pango. The first version used Xft, which cannot round a
 * corner (it has no arc primitive — only Rect, String, Glyphs), so the panel
 * was a hard rectangle and any softness you saw was picom's shadow. Cairo
 * gives real anti-aliased round corners, genuine per-pixel alpha for the
 * translucency, and Pango for text shaping, which is why the hand-rolled
 * UTF-8 truncation in the old version is gone.
 *
 * It is a viewer, never a mutator: nothing here focuses, kills, moves or
 * resizes a window. fae-cycle owns state changes; this only draws them.
 *
 * Not a resident process: paint, hold, fade, exit. Spawned per Alt+Tab, it
 * lives about 1.6s. The rule came from the i3bar incident, where a status
 * script needed a daemon and a dying one printed errors across the screen.
 */
#include "hud.h"
#include "theme.h"

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

/* This X11's headers name StaticGray but not TrueClass; the value is 4 in the
 * protocol and has been since X11R4. */
#ifndef TrueClass
#define TrueClass 4
#endif

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

/* ── colour ──────────────────────────────────────────────────────────────── */

typedef struct { double r, g, b; } rgb_t;

/* "#rrggbb" -> normalised rgb */
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

/* A soft outer glow, drawn as concentric strokes of decreasing alpha. Cheaper
 * and far more predictable than a cairo shadow, and — unlike a shadow — it
 * still looks right when there is no compositor to blur it. */
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
    PangoLayout *lay;
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
    if (t->lay) g_object_unref(t->lay);
    if (t->desc) g_object_unref(t->desc);
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

static void type_draw(type_t *t, cairo_t *cr, rgb_t col, double a,
                      double x, double baseline)
{
    set_rgba(cr, col, a);
    cairo_move_to(cr, x, baseline);
    pango_cairo_show_layout(cr, t->lay);
}

/* ── timing ──────────────────────────────────────────────────────────────── */

static long now_ms(void)
{
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return ts.tv_sec * 1000L + ts.tv_nsec / 1000000L;
}

/* smoothstep, so motion eases instead of ramping linearly */
static double ease(double t)
{
    if (t < 0) t = 0;
    if (t > 1) t = 1;
    return t * t * (3.0 - 2.0 * t);
}

/* ── compositor ──────────────────────────────────────────────────────────── */

/* Plain X11 has no per-window alpha: without a compositor the transparent
 * pixels come out black. Ask before choosing a visual, and fall back to an
 * opaque panel rather than shipping something that looks like a rendering bug
 * on a bare X server. */
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

static int on_x_error(Display *dpy, XErrorEvent *e)
{
    /* the panel was destroyed under us (i3 restart, logout). Nothing to
     * recover and nowhere visible to complain: i3's stderr is /dev/tty1. */
    (void)dpy; (void)e;
    return 0;
}

/* ── the panel ───────────────────────────────────────────────────────────── */

int hud_run(Display *dpy, int scr, wlist_t *list, int force_opaque)
{
    int screen_w = DisplayWidth(dpy, scr);
    int screen_h = DisplayHeight(dpy, scr);

    int have_cx = 0;
    if (force_opaque) have_cx = 0;
    else if (compositor_present(dpy)) have_cx = 1;
    else if (getenv("FAE_HUD_FORCE_OPAQUE")) have_cx = 0;

    /* ── pick a visual: ARGB32 when a compositor can blend it ───────────── */
    XVisualInfo vinfo, *vi = NULL;
    int depth = CopyFromParent;
    Visual *visual = DefaultVisual(dpy, scr);
    if (have_cx && XMatchVisualInfo(dpy, scr, 32, TrueClass, &vinfo)) {
        vi = &vinfo;
        visual = vinfo.visual;
        depth = vinfo.depth;
    }

    if (getenv("FAE_HUD_VERBOSE"))
        fprintf(stderr, "fae-hud: compositor=%s visual=%s depth=%d\n",
                have_cx ? "yes" : "no", vi ? "ARGB32" : "default", depth);

    /* ── type, and therefore measurements ───────────────────────────────── */
    type_t title, meta, head;
    PangoContext *ctx =
        pango_font_map_create_context(pango_cairo_font_map_get_default());
    type_open(&title, ctx, THEME_SIZE_TITLE);
    type_open(&meta,  ctx, THEME_SIZE_META);
    type_open(&head,  ctx, THEME_SIZE_META);

    int shown = list->n;
    int hidden = 0;
    if (shown > THEME_MAX_ROWS) {
        hidden = shown - THEME_MAX_ROWS;
        shown = THEME_MAX_ROWS;
    }

    /* ── measure ────────────────────────────────────────────────────────── */
    int glyph_w = 0, dot_w = 0, title_max = 0, meta_max = 0, head_w = 0;
    type_set(&head, THEME_GLYPH_FOCUS " windows", 0);
    head_w = type_w(&head);
    type_set(&title, THEME_GLYPH_FOCUS, 0);
    glyph_w = type_w(&title);
    type_set(&meta, THEME_GLYPH_DOT, 0);
    dot_w = type_w(&meta);

    for (int i = 0; i < list->n; i++) {
        type_set(&title, list->v[i].title, 0);
        if (type_w(&title) > title_max) title_max = type_w(&title);

        char b[512];
        snprintf(b, sizeof b, "%s%lu %s %s",
                 list->v[i].desktop_known ? "" : "?",
                 list->v[i].desktop,
                 THEME_GLYPH_DOT, list->v[i].cls);
        type_set(&meta, b, 0);
        if (type_w(&meta) > meta_max) meta_max = type_w(&meta);
    }

    int line_title = type_h(&title) > 0 ? type_h(&title) : THEME_SIZE_TITLE + 4;
    int line_meta  = type_h(&meta)  > 0 ? type_h(&meta)  : THEME_SIZE_META + 4;
    int line_head  = type_h(&head)  > 0 ? type_h(&head)  : THEME_SIZE_META + 4;

    int text_x = THEME_GLYPH_COL * (glyph_w > 0 ? glyph_w : 8) + THEME_GAP;
    int want_w = THEME_PAD_X * 2 + text_x
               + (title_max > meta_max ? title_max : meta_max);
    int cap = (int)(screen_w * THEME_W_FRACTION);
    if (cap > THEME_MAX_W) cap = THEME_MAX_W;
    if (want_w > cap) want_w = cap;
    if (want_w < THEME_MIN_W) want_w = THEME_MIN_W;
    int text_max = want_w - THEME_PAD_X * 2 - text_x;

    int row_h = line_title + THEME_LINE_GAP + line_meta + THEME_ROW_GAP;
    int body_h = shown * row_h;
    int want_h = THEME_PAD_Y * 2 + line_head + THEME_RULE_GAP
               + body_h + THEME_RULE_GAP + line_meta + THEME_PAD_Y / 2;

    long total_for_log = THEME_ROW_START
                       + (long)(shown > 0 ? shown - 1 : 0) * THEME_ROW_LAG
                       + THEME_ROW_FADE + THEME_HOLD + THEME_FADE_OUT;

    /* ── create ─────────────────────────────────────────────────────────── */
    XSetWindowAttributes attr;
    memset(&attr, 0, sizeof attr);
    attr.override_redirect = True;
    attr.background_pixel  = 0;
    attr.border_pixel      = 0;
    attr.colormap          = (vi && vi) ? XCreateColormap(dpy, DefaultRootWindow(dpy), visual, AllocNone)
                                       : DefaultColormap(dpy, scr);
    attr.event_mask        = ExposureMask | StructureNotifyMask;

    Window win = XCreateWindow(dpy, DefaultRootWindow(dpy),
                               (screen_w - want_w) / 2,
                               (screen_h - want_h) / 3,
                               (unsigned)want_w, (unsigned)want_h, 0,
                               depth, InputOutput, visual,
                               CWOverrideRedirect | CWBackPixel | CWBorderPixel
                                   | CWColormap | CWEventMask,
                               &attr);
    if (!win) {
        type_close(&title); type_close(&meta); type_close(&head);
        g_object_unref(ctx);
        return 1;
    }

    /* Claim to be a panel so nothing tries to frame, tile or focus it. */
    Atom wtype = XInternAtom(dpy, "_NET_WM_WINDOW_TYPE_DOCK", False);
    XChangeProperty(dpy, win, XInternAtom(dpy, "_NET_WM_WINDOW_TYPE", False),
                    XA_ATOM, 32, PropModeReplace, (unsigned char *)&wtype, 1);
    XChangeProperty(dpy, win, XInternAtom(dpy, "_NET_WM_NAME", False),
                    XInternAtom(dpy, "UTF8_STRING", False), 8,
                    PropModeReplace, (unsigned char *)"fae-hud", 7);
    /* WM_NAME too: _NET_WM_NAME alone leaves the window invisible to
     * xdotool search and wmctrl, which is annoying when debugging. */
    XChangeProperty(dpy, win, XA_WM_NAME, XA_STRING, 8,
                    PropModeReplace, (unsigned char *)"fae-hud", 7);

    XErrorHandler prev = XSetErrorHandler(on_x_error);
    XMapRaised(dpy, win);
    XSync(dpy, False);

    cairo_surface_t *surf = cairo_xlib_surface_create(dpy, win, visual,
                                                      want_w, want_h);
    cairo_t *cr = cairo_create(surf);

    if (getenv("FAE_HUD_VERBOSE"))
        fprintf(stderr, "fae-hud: win=0x%lx at (%d,%d) %dx%d rows=%d shown=%d "
                        "text_max=%d row_h=%d total=%ldms\n",
                (unsigned long)win, (screen_w - want_w) / 2,
                (screen_h - want_h) / 3, want_w, want_h, list->n, shown,
                text_max, row_h, total_for_log);

    /* ── palette ────────────────────────────────────────────────────────── */
    rgb_t c_void   = hex_rgb(THEME_VOID);
    rgb_t c_panel  = hex_rgb(THEME_PANEL);
    rgb_t c_pink   = hex_rgb(THEME_PINK);
    rgb_t c_psoft  = hex_rgb(THEME_PINK_SOFT);
    rgb_t c_fg     = hex_rgb(THEME_FG);
    rgb_t c_dim    = hex_rgb(THEME_FG_DIM);
    rgb_t c_lilac  = hex_rgb(THEME_LILAC);
    rgb_t c_far    = hex_rgb(THEME_FAR);

    /* ── run ────────────────────────────────────────────────────────────── */
    long last_row = THEME_ROW_START + (long)(shown > 0 ? shown - 1 : 0) * THEME_ROW_LAG
                                  + THEME_ROW_FADE;
    long total = last_row + THEME_HOLD + THEME_FADE_OUT;
    long t0 = now_ms();

    for (;;) {
        long el = now_ms() - t0;
        if (el >= total) break;

        /* the bloom, and the fade at the end, share one envelope */
        double env;
        if (el < THEME_BLOOM_IN)
            env = ease((double)el / THEME_BLOOM_IN);
        else if (el < last_row + THEME_HOLD)
            env = 1.0;
        else
            env = 1.0 - ease((double)(el - last_row - THEME_HOLD) / THEME_FADE_OUT);

        /* The panel body blooms as one piece, but the type assembles top to
         * bottom with the rows. Before this, the header and footer rode the
         * global envelope, so at 80ms you got a fully-lit footer sitting
         * under an empty body — which reads as a bug, not as motion. */
        double a_head = ease((double)(el - (THEME_ROW_START - 45)) / THEME_ROW_FADE);
        double a_foot = ease((double)(el - (last_row - THEME_ROW_FADE)) / THEME_ROW_FADE);

        /* an opaque panel has no alpha to fade, so it fades its colour */
        rgb_t bg   = have_cx ? c_panel : mix(c_void, c_panel, env);
        double bg_a = have_cx ? env : 1.0;

        cairo_set_operator(cr, CAIRO_OPERATOR_SOURCE);
        set_rgba(cr, c_void, have_cx ? 0.0 : 1.0);
        cairo_paint(cr);
        cairo_set_operator(cr, CAIRO_OPERATOR_OVER);

        /* panel, blooming outward from a small inset */
        double inset = (1.0 - ease((double)el / THEME_BLOOM_IN)) * 14.0;
        double px = inset, py = inset;
        double pw = want_w - inset * 2, ph = want_h - inset * 2;
        double rad = THEME_RADIUS * (0.6 + 0.4 * (1.0 - inset / 14.0));

        if (!have_cx) { px = 0; py = 0; pw = want_w; ph = want_h; rad = 0; }

        glow_stroke(cr, c_pink, env * 0.9, px, py, pw, ph, rad);

        set_rgba(cr, bg, bg_a);
        round_rect(cr, px, py, pw, ph, rad);
        cairo_fill(cr);

        /* the crisp edge on top of the glow */
        cairo_set_line_width(cr, 1.0);
        set_rgba(cr, mix(bg, c_pink, 0.55), env);
        round_rect(cr, px + 0.5, py + 0.5, pw - 1, ph - 1, rad);
        cairo_stroke(cr);

        /* four corner facets — the cut-gem tell. Drawn rather than typed, so
         * they cannot collide with the corner radius or fall back to tofu. */
        set_rgba(cr, c_lilac, env * 0.34 * a_head);
        diamond(cr, px + THEME_FACET_INSET,        py + THEME_FACET_INSET,        THEME_FACET_R); cairo_fill(cr);
        diamond(cr, px + pw - THEME_FACET_INSET,   py + THEME_FACET_INSET,        THEME_FACET_R); cairo_fill(cr);
        diamond(cr, px + THEME_FACET_INSET,        py + ph - THEME_FACET_INSET,  THEME_FACET_R); cairo_fill(cr);
        diamond(cr, px + pw - THEME_FACET_INSET,   py + ph - THEME_FACET_INSET, THEME_FACET_R); cairo_fill(cr);

        double x0 = px + THEME_PAD_X;
        double right = px + pw - THEME_PAD_X;
        double y = py + THEME_PAD_Y;

        /* ── header ─────────────────────────────────────────────────────── */
        type_set(&head, THEME_GLYPH_FOCUS " windows", 0);
        type_draw(&head, cr, c_lilac, a_head, x0, y + line_head);

        char cnt[24];
        snprintf(cnt, sizeof cnt, "%d", list->n);
        type_set(&meta, cnt, 0);
        type_draw(&meta, cr, c_lilac, a_head * 0.8, right - type_w(&meta),
                  y + line_head);

        y += line_head + THEME_RULE_GAP;
        cairo_set_line_width(cr, 1.0);
        set_rgba(cr, c_lilac, a_head * 0.22);
        cairo_move_to(cr, x0, y + 0.5);
        cairo_line_to(cr, right, y + 0.5);
        cairo_stroke(cr);
        y += THEME_RULE_GAP;

        /* ── rows, cascading in ─────────────────────────────────────────── */
        for (int i = 0; i < shown; i++) {
            double a_row = ease((double)(el - (THEME_ROW_START + (long)i * THEME_ROW_LAG))
                                / THEME_ROW_FADE);
            double rtop = y;
            int sel = list->has_explicit_focus ? list->v[i].is_focus_target
                                               : list->v[i].is_active;

            if (sel) {
                /* the band wipes in from the left, so you see where you landed */
                double w = ease((double)(el - THEME_WIPE_START) / THEME_WIPE);
                /* hug the row's two lines, not the whole row cell: at row_h
                 * the band reached up over the title and touched the header
                 * rule, which read as a layout mistake rather than a band. */
                double bh = line_title + THEME_LINE_GAP + line_meta;
                double by = rtop - 5;
                if (w > 0.001) {
                    cairo_save(cr);
                    cairo_rectangle(cr, px, by, pw * w, bh);
                    cairo_clip(cr);
                    set_rgba(cr, c_pink, 0.20 * a_row);
                    round_rect(cr, px + 1, by, pw - 2, bh, rad * 0.6);
                    cairo_fill(cr);
                    set_rgba(cr, c_pink, 0.34 * a_row);
                    cairo_set_line_width(cr, 1.0);
                    round_rect(cr, px + 1.5, by + 0.5, pw - 3, bh - 1,
                               rad * 0.6);
                    cairo_stroke(cr);
                    cairo_restore(cr);
                }
            }

            double tx = x0 + text_x;
            rgb_t want_c = sel ? c_pink
                               : (list->v[i].on_current_workspace ? c_fg : c_far);
            rgb_t rowc = mix(bg, want_c, a_row);

            type_set(&title, sel ? THEME_GLYPH_FOCUS : THEME_GLYPH_IDLE, 0);
            type_draw(&title, cr, rowc, a_row, x0, y + line_title * 0.78);

            /* the hairline that separates the glyph column from the text */
            cairo_set_line_width(cr, 1.0);
            set_rgba(cr, c_lilac, a_row * 0.18);
            cairo_move_to(cr, x0 + text_x - THEME_GAP / 2.0, y + 2);
            cairo_line_to(cr, x0 + text_x - THEME_GAP / 2.0, y + line_title + THEME_LINE_GAP + line_meta - 2);
            cairo_stroke(cr);

            type_set(&title, list->v[i].title, text_max);
            type_draw(&title, cr, rowc, a_row, tx, y + line_title * 0.78);

            char b[512];
            snprintf(b, sizeof b, "%s%lu %s %s",
                     list->v[i].desktop_known ? "" : "?",
                     list->v[i].desktop,
                     THEME_GLYPH_DOT, list->v[i].cls);
            type_set(&meta, b, text_max);
            rgb_t metac = sel ? c_psoft : c_dim;
            type_draw(&meta, cr, mix(bg, metac, a_row), a_row * (sel ? 1.0 : 0.85),
                      tx, y + line_title + THEME_LINE_GAP + line_meta * 0.8);

            y += row_h;
        }

        if (hidden > 0) {
            char b[64];
            snprintf(b, sizeof b, "+%d more", hidden);
            type_set(&meta, b, 0);
            type_draw(&meta, cr, c_dim, a_foot * 0.7, x0, y + line_meta * 0.8);
        }

        /* ── footer ─────────────────────────────────────────────────────── */
        double fy = py + ph - THEME_PAD_Y - line_meta * 0.5;
        cairo_set_line_width(cr, 1.0);
        set_rgba(cr, c_lilac, a_foot * 0.18);
        cairo_move_to(cr, x0, fy - line_meta);
        cairo_line_to(cr, right, fy - line_meta);
        cairo_stroke(cr);

        type_set(&meta, "alt+tab next " THEME_GLYPH_DOT " alt+shift+tab back", 0);
        type_draw(&meta, cr, c_dim, a_foot * 0.85, x0, fy);

        cairo_surface_flush(surf);
        XSync(dpy, False);

        struct timespec nap = { 0, 16L * 1000L * 1000L };
        nanosleep(&nap, NULL);
        while (XPending(dpy)) {
            XEvent ev;
            XNextEvent(dpy, &ev);
        }
    }

    XSetErrorHandler(prev);
    cairo_destroy(cr);
    cairo_surface_destroy(surf);
    XDestroyWindow(dpy, win);
    XSync(dpy, False);
    type_close(&title); type_close(&meta); type_close(&head);
    g_object_unref(ctx);
    (void)dot_w; (void)head_w;
    return 0;
}

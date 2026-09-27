/* hud.c — the overlay window.
 *
 * An override-redirect window, centred, never focused, so it floats above
 * everything i3 manages without stealing the keyboard or the pointer. It
 * selects no button events, so clicks pass straight through to whatever is
 * underneath.
 *
 * The fade is done by interpolating every colour between the void and its
 * target, rather than by asking for window opacity. That matters: opacity
 * needs a compositor to honour it, and while picom is running today it may
 * not be tomorrow. Interpolating colours works on a bare X server.
 *
 * All text goes through the Utf8 entry points. The plain XftDrawString8 on
 * this box decodes Latin-1, which turned a typographic ellipsis into "â€¦"
 * and a middle dot into "Â·" — embarrassing in a house that has a rule about
 * typography. Positions are computed from measured advance widths, not from
 * an assumed character cell, because an assumed cell drifts across a long
 * title and eventually collides with the column on the right.
 */
#include "hud.h"
#include "theme.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#include <X11/Xlib.h>
#include <X11/Xatom.h>
#include <X11/Xft/Xft.h>

/* ── colour helpers ──────────────────────────────────────────────────────── */

/* XftColor wraps XRenderColor, which has no `pixel` field — so anything that
 * needs a raw pixel (a window background) goes through XAllocNamedColor. */
static void colour_of(Display *dpy, int scr, const char *hex, XftColor *out)
{
    XColor c, exact;
    memset(&c, 0, sizeof c);
    if (!XAllocNamedColor(dpy, DefaultColormap(dpy, scr), hex, &c, &exact))
        c.red = c.green = c.blue = 0;
    memset(out, 0, sizeof *out);
    out->color.red   = c.red;
    out->color.green = c.green;
    out->color.blue  = c.blue;
    out->color.alpha = 0xffff;
}

static unsigned long pixel_of(Display *dpy, int scr, const char *hex)
{
    XColor c, exact;
    if (!XAllocNamedColor(dpy, DefaultColormap(dpy, scr), hex, &c, &exact))
        return BlackPixel(dpy, scr);
    return c.pixel;
}

/* out = from + (to - from) * t, with t clamped to 0..1 */
static void mix(const XftColor *from, const XftColor *to, double t, XftColor *out)
{
    if (t < 0) t = 0;
    if (t > 1) t = 1;
    XftColor f = *from, g = *to;
    out->color.red   = (unsigned short)(f.color.red   + (g.color.red   - f.color.red)   * t);
    out->color.green = (unsigned short)(f.color.green + (g.color.green - f.color.green) * t);
    out->color.blue  = (unsigned short)(f.color.blue  + (g.color.blue  - f.color.blue)  * t);
    out->color.alpha = 0xffff;
}

/* ── utf-8 helpers ───────────────────────────────────────────────────────── */

/* Length in codepoints, not bytes — titles are UTF8_STRING. */
static int uc_len(const char *s)
{
    int n = 0;
    for (const unsigned char *p = (const unsigned char *)s; *p; p++)
        if ((*p & 0xc0) != 0x80) n++;
    return n;
}

/* Truncate to `cols` codepoints, appending a real ellipsis. Caller frees. */
static char *fit(const char *s, int cols)
{
    if (uc_len(s) <= cols) return strdup(s);
    int keep = cols > 1 ? cols - 1 : 0;
    size_t room = strlen(s) + 4;
    char *out = malloc(room);
    size_t i = 0;
    int n = 0;
    for (const unsigned char *p = (const unsigned char *)s; *p && n < keep; p++, i++) {
        if ((*p & 0xc0) != 0x80) n++;
        out[i] = (char)*p;
    }
    out[i] = '\0';
    strcat(out, "\xe2\x80\xa6"); /* U+2026 */
    return out;
}

/* ── the pen ─────────────────────────────────────────────────────────────── */

typedef struct {
    XftDraw  *draw;
    XftFont  *font;
    Display  *dpy;
    int       cell;     /* width of one "M" — the monospace unit */
    int       ascent;
    int       line_h;
} pen_t;

/* XGlyphInfo comes from Xrender: x, y, width, height, xOff, yOff. The advance
 * of a run is xOff + width. This Xft's XftTextExtentsUtf8 returns void. */
static int measure(pen_t *p, const char *s)
{
    XGlyphInfo ext;
    memset(&ext, 0, sizeof ext);
    XftTextExtentsUtf8(p->dpy, p->font, (const FcChar8 *)s,
                       (int)strlen(s), &ext);
    return (int)ext.xOff + (int)ext.width;
}

static void hline(XftColor *col, pen_t *p, int x, int y, unsigned w)
{
    XftDrawRect(p->draw, col, x, y, w, 1);
}

static void fill_rect(pen_t *p, XftColor *col, int x, int y, unsigned w, unsigned h)
{
    for (unsigned i = 0; i < h; i++)
        hline(col, p, x, (int)(y + i), w);
}

static void outline(XftColor *col, pen_t *p, int x, int y, unsigned w, unsigned h)
{
    XftDrawRect(p->draw, col, x, y, w, h);
}

static void text(XftColor *col, pen_t *p, int x, int baseline, const char *s)
{
    XftDrawStringUtf8(p->draw, col, p->font, x, baseline,
                      (const FcChar8 *)s, (int)strlen(s));
}

/* right-align a string ending at `right` */
static void text_right(XftColor *col, pen_t *p, int right, int baseline,
                       const char *s)
{
    text(col, p, right - measure(p, s), baseline, s);
}

/* ── timing ──────────────────────────────────────────────────────────────── */

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

static int on_x_error(Display *dpy, XErrorEvent *e)
{
    /* the panel was destroyed under us (i3 restart, logout). Nothing to
     * recover and nowhere visible to complain: i3's stderr is /dev/tty1. */
    (void)dpy; (void)e;
    return 0;
}

/* ── draw ────────────────────────────────────────────────────────────────── */

int hud_run(Display *dpy, int scr, wlist_t *list)
{
    int screen_w = DisplayWidth(dpy, scr);
    int screen_h = DisplayHeight(dpy, scr);
    int rows = list->n;

    XftFont *font = XftFontOpenName(dpy, scr, THEME_FONT_PATTERN);
    if (!font) {
        fprintf(stderr, "fae-hud: cannot open font %s\n", THEME_FONT);
        return 1;
    }

    pen_t pen;
    pen.dpy    = dpy;
    pen.font   = font;
    pen.cell   = font->max_advance_width > 0 ? font->max_advance_width
                                             : (font->height * 2) / 3;
    pen.ascent = font->ascent;
    pen.line_h = font->ascent + font->descent + THEME_LINE_GAP;

    /* ── measure, then decide the column budget ───────────────────────────── */
    const int CLS_MAX = 18, TITLE_MAX = 64;
    char **titles = calloc((size_t)(rows > 0 ? rows : 1), sizeof(char *));
    char **clss   = calloc((size_t)(rows > 0 ? rows : 1), sizeof(char *));
    int title_w = 0, cls_w = 0;
    for (int i = 0; i < rows; i++) {
        titles[i] = fit(list->v[i].title, TITLE_MAX);
        clss[i]   = fit(list->v[i].cls, CLS_MAX);
        int a = measure(&pen, titles[i]), b = measure(&pen, clss[i]);
        if (a > title_w) title_w = a;
        if (b > cls_w)   cls_w = b;
    }

    int gap = pen.cell;
    int mark_w = measure(&pen, ">");
    int idx_w  = measure(&pen, "88");
    int ws_w   = measure(&pen, "88");

    int fixed = THEME_PAD_X * 2 + mark_w + gap + idx_w + gap + ws_w + gap
              + gap * 2 + cls_w;
    int max_w = (screen_w * 3) / 4;
    int want_w = fixed + title_w;
    if (want_w > max_w) {
        title_w = max_w - fixed;
        if (title_w < pen.cell * 8) title_w = pen.cell * 8;
        want_w = fixed + title_w;
    }
    if (want_w < 360) want_w = 360;

    /* Re-fit the titles to the width we actually ended up with. DejaVu Sans
     * Mono is monospace, so pixels map to columns exactly. */
    int title_cols = title_w / (pen.cell > 0 ? pen.cell : 1);
    if (title_cols < 4) title_cols = 4;
    for (int i = 0; i < rows; i++) {
        char *t = fit(list->v[i].title, title_cols);
        free(titles[i]);
        titles[i] = t;
    }

    int head_h = pen.line_h;
    int foot_h = pen.line_h;
    int want_h = head_h + (rows > 0 ? rows : 1) * pen.line_h + foot_h
               + THEME_PAD_Y * 2;

    int px = (screen_w - want_w) / 2;
    int py = (screen_h - want_h) / 3;   /* a third down: above the middle */
    if (px < 0) px = 0;
    if (py < 0) py = 0;

    /* ── create ──────────────────────────────────────────────────────────── */
    XSetWindowAttributes attr;
    memset(&attr, 0, sizeof attr);
    attr.override_redirect = True;
    attr.background_pixel  = pixel_of(dpy, scr, THEME_VOID);
    attr.border_pixel      = 0;
    attr.event_mask        = ExposureMask | StructureNotifyMask;

    Window win = XCreateWindow(dpy, DefaultRootWindow(dpy), px, py,
                               (unsigned)want_w, (unsigned)want_h, 0,
                               CopyFromParent, InputOutput, CopyFromParent,
                               CWOverrideRedirect | CWBackPixel | CWBorderPixel
                                   | CWEventMask,
                               &attr);
    if (!win) {
        XftFontClose(dpy, font);
        return 1;
    }

    /* Claim to be a dock/panel so nothing tries to frame, tile or focus it. */
    Atom type = XInternAtom(dpy, "_NET_WM_WINDOW_TYPE_DOCK", False);
    XChangeProperty(dpy, win, XInternAtom(dpy, "_NET_WM_WINDOW_TYPE", False),
                    XA_ATOM, 32, PropModeReplace, (unsigned char *)&type, 1);
    XChangeProperty(dpy, win, XInternAtom(dpy, "_NET_WM_NAME", False),
                    XInternAtom(dpy, "UTF8_STRING", False), 8,
                    PropModeReplace, (unsigned char *)"fae-hud", 7);

    XMapRaised(dpy, win);
    XSync(dpy, False);

    pen.draw = XftDrawCreate(dpy, win, DefaultVisual(dpy, scr),
                             DefaultColormap(dpy, scr));

    XErrorHandler prev = XSetErrorHandler(on_x_error);

    /* ── palette ─────────────────────────────────────────────────────────── */
    XftColor void_c, panel_c, pink, pink_soft, fg, fg_dim, lilac, far;
    colour_of(dpy, scr, THEME_VOID,      &void_c);
    colour_of(dpy, scr, THEME_PANEL,     &panel_c);
    colour_of(dpy, scr, THEME_PINK,      &pink);
    colour_of(dpy, scr, THEME_PINK_SOFT, &pink_soft);
    colour_of(dpy, scr, THEME_FG,         &fg);
    colour_of(dpy, scr, THEME_FG_DIM,     &fg_dim);
    colour_of(dpy, scr, THEME_LILAC,      &lilac);
    colour_of(dpy, scr, THEME_FAR,        &far);

    /* ── run ─────────────────────────────────────────────────────────────── */
    const long total = THEME_FADE_IN + THEME_HOLD + THEME_FADE_OUT;
    long t0 = now_ms();
    for (;;) {
        long el = now_ms() - t0;
        if (el >= total) break;

        double a;
        if (el < THEME_FADE_IN)
            a = ease((double)el / THEME_FADE_IN);
        else if (el < THEME_FADE_IN + THEME_HOLD)
            a = 1.0;
        else
            a = 1.0 - ease((double)(el - THEME_FADE_IN - THEME_HOLD)
                          / THEME_FADE_OUT);

        XftColor bg, edge;
        mix(&void_c, &panel_c, a, &bg);
        mix(&bg, &pink, 0.35 * a, &edge);

        XClearWindow(dpy, win);
        fill_rect(&pen, &bg, 0, 0, (unsigned)want_w, (unsigned)want_h);
        outline(&edge, &pen, 0, 0, (unsigned)want_w - 1, (unsigned)want_h - 1);

        int x = THEME_PAD_X;
        int y = THEME_PAD_Y;
        int right = want_w - THEME_PAD_X;

        /* header */
        XftColor h_fg;
        mix(&bg, &lilac, a, &h_fg);
        text(&h_fg, &pen, x, y + pen.ascent, "windows");
        char cnt[24];
        snprintf(cnt, sizeof cnt, "%d", rows);
        text_right(&h_fg, &pen, right, y + pen.ascent, cnt);
        y += head_h;

        /* rows */
        for (int i = 0; i < rows; i++) {
            int base = y + pen.ascent;
            /* When fae-cycle named a window, that is the answer. Falling back
             * to _NET_ACTIVE_WINDOW as well would let a stale active window
             * highlight a second row, which reads as "two windows focused". */
            int sel = list->has_explicit_focus ? list->v[i].is_focus_target
                                              : list->v[i].is_active;

            if (sel) {
                XftColor hb;
                mix(&bg, &pink, 0.22 * a, &hb);
                fill_rect(&pen, &hb, THEME_PAD_X / 2, y - 3,
                          (unsigned)(want_w - THEME_PAD_X), (unsigned)pen.line_h);
            }

            XftColor want_c = fg;
            if (sel)                                want_c = pink;
            else if (!list->v[i].on_current_workspace) want_c = far;
            XftColor c;
            mix(&bg, &want_c, a, &c);

            text(&c, &pen, x, base, sel ? ">" : " ");
            x += mark_w + gap;

            char idx[24];
            snprintf(idx, sizeof idx, "%d", i + 1);
            text_right(&c, &pen, x + idx_w, base, idx);
            x += idx_w + gap;

            char ws[24];
            if (list->v[i].desktop_known)
                snprintf(ws, sizeof ws, "%lu", list->v[i].desktop);
            else
                snprintf(ws, sizeof ws, "?");
            XftColor wc;
            mix(&bg, &lilac,
                a * (list->v[i].on_current_workspace ? 1.0 : 0.45), &wc);
            text_right(&wc, &pen, x + ws_w, base, ws);
            x += ws_w + gap;

            text(&c, &pen, x, base, titles[i]);

            XftColor cc;
            mix(&bg, sel ? &pink_soft : &fg_dim, a, &cc);
            text_right(&cc, &pen, right, base, clss[i]);

            y += pen.line_h;
        }

        /* footer */
        XftColor fc;
        mix(&bg, &fg_dim, a * 0.9, &fc);
        text(&fc, &pen, THEME_PAD_X, y + pen.ascent,
             "alt+tab next \xc2\xb7 alt+shift+tab back");

        XSync(dpy, False);

        struct timespec nap = { 0, 16L * 1000L * 1000L };
        nanosleep(&nap, NULL);
        while (XPending(dpy)) {
            XEvent ev;
            XNextEvent(dpy, &ev);
        }
    }

    XSetErrorHandler(prev);
    XftDrawDestroy(pen.draw);
    XDestroyWindow(dpy, win);
    XSync(dpy, False);
    XftFontClose(dpy, font);
    for (int i = 0; i < rows; i++) { free(titles[i]); free(clss[i]); }
    free(titles);
    free(clss);
    return 0;
}

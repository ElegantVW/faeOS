/* frame.c — titlebar frames with – ▢ ×.
 *
 * The client is reparented into a frame window: titlebar on top (title +
 * three drawn glyphs), client below. The frame selects button masks on
 * itself, so chrome presses and releases pair natively; the client fills
 * the rest and gets its own events untouched. Frame clicks never forward
 * to clients.
 */
#include "frame.h"
#include "client.h"
#include "theme.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include <X11/Xlib.h>
#include <X11/Xatom.h>
#include <X11/Xutil.h>
#include <cairo/cairo-xlib.h>
#include <pango/pangocairo.h>

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

void frame_outer(client_t *c, int bw, int th, int *x, int *y, int *w, int *h)
{
    *x = c->x - bw;
    *y = c->y - (th + bw);
    *w = c->w + bw * 2;
    *h = c->h + th + bw * 2;
}

/* Button rects, frame-relative. Order from the right: × Max Min. */
static void btn_rect(client_t *c, int bw, int th, int fw, btn_t b,
                     int *x, int *y, int *w, int *h)
{
    int idx = (b == BTN_CLOSE) ? 0 : (b == BTN_MAX) ? 1 : 2;
    *w = WM_BTN_W;
    *h = th;
    *x = fw - bw - (idx + 1) * WM_BTN_W;
    *y = 0;
    (void)c;
}

btn_t frame_hit(client_t *c, int bw, int th, int fx, int fy)
{
    int fw = c->w + bw * 2;
    if (fy < 0 || fy >= th) return BTN_NONE;
    for (btn_t b = BTN_MIN; b <= BTN_CLOSE; b = (btn_t)(b + 1)) {
        int x, y, w, h;
        btn_rect(c, bw, th, fw, b, &x, &y, &w, &h);
        if (fx >= x && fx < x + w) return b;
    }
    return BTN_NONE;
}

client_t *frame_client(wm_t *wm, Window xid)
{
    for (client_t *c = wm->clients; c; c = c->next)
        if (c->frame == xid) return c;
    return NULL;
}

int frame_create(wm_t *wm, client_t *c)
{
    int bw = wm->border_w, th = WM_TITLE_H;
    int fx, fy, fw, fh;
    frame_outer(c, bw, th, &fx, &fy, &fw, &fh);

    XSetWindowAttributes attr;
    memset(&attr, 0, sizeof attr);
    attr.override_redirect = False;
    attr.background_pixel = BlackPixel(wm->dpy, wm->scr);
    attr.event_mask = ExposureMask | PointerMotionMask |
                       ButtonPressMask | ButtonReleaseMask;
    c->frame = XCreateWindow(wm->dpy, wm->root, fx, fy, (unsigned)fw, (unsigned)fh,
                             0, CopyFromParent, InputOutput, CopyFromParent,
                             CWOverrideRedirect | CWBackPixel | CWEventMask, &attr);
    if (!c->frame) return 0;
    XSetWindowBorderWidth(wm->dpy, c->frame, (unsigned)bw);
    XReparentWindow(wm->dpy, c->xid, c->frame, bw, th + bw);
    XSetWindowBorderWidth(wm->dpy, c->xid, 0);
    XMapWindow(wm->dpy, c->xid);
    XMapWindow(wm->dpy, c->frame);
    c->pressed_btn = BTN_NONE;
    c->hover_btn = BTN_NONE;
    return 1;
}

void frame_destroy(wm_t *wm, client_t *c)
{
    if (!c->frame) return;
    /* Hand the client back to the root before the frame goes away. */
    XReparentWindow(wm->dpy, c->xid, wm->root, c->x, c->y);
    XDestroyWindow(wm->dpy, c->frame);
    c->frame = None;
}

/* Re-fit the frame after any move/resize/state change. */
void frame_layout(wm_t *wm, client_t *c)
{
    if (!c->frame) return;
    int bw = c->fullscreen ? 0 : wm->border_w;
    int th = c->fullscreen ? 0 : WM_TITLE_H;
    int fx, fy, fw, fh;
    frame_outer(c, bw, th, &fx, &fy, &fw, &fh);
    XSetWindowBorderWidth(wm->dpy, c->frame, (unsigned)bw);
    XMoveResizeWindow(wm->dpy, c->frame, fx, fy, (unsigned)fw, (unsigned)fh);
    XMoveResizeWindow(wm->dpy, c->xid, bw, th + bw,
                      (unsigned)c->w, (unsigned)c->h);
    frame_paint(wm, c);
}

static void glyph(cairo_t *cr, btn_t b, double cx, double cy, double s)
{
    cairo_set_line_width(cr, 1.6);
    cairo_set_line_cap(cr, CAIRO_LINE_CAP_ROUND);
    if (b == BTN_MIN) {
        cairo_move_to(cr, cx - s, cy);
        cairo_line_to(cr, cx + s, cy);
        cairo_stroke(cr);
    } else if (b == BTN_MAX) {
        cairo_rectangle(cr, cx - s, cy - s * 0.8, s * 2, s * 1.6);
        cairo_stroke(cr);
    } else if (b == BTN_CLOSE) {
        cairo_move_to(cr, cx - s, cy - s);
        cairo_line_to(cr, cx + s, cy + s);
        cairo_move_to(cr, cx + s, cy - s);
        cairo_line_to(cr, cx - s, cy + s);
        cairo_stroke(cr);
    }
}

void frame_paint(wm_t *wm, client_t *c)
{
    if (!c->frame) return;
    int bw = c->fullscreen ? 0 : wm->border_w;
    int th = c->fullscreen ? 0 : WM_TITLE_H;
    if (th <= 0) return;
    int fw = c->w + bw * 2;
    int fh = c->h + th + bw * 2;
    int focused = (wm->focus == c);

    Display *dpy = wm->dpy;
    cairo_surface_t *surf =
        cairo_xlib_surface_create(dpy, c->frame, DefaultVisual(dpy, wm->scr),
                                  fw, fh);
    cairo_t *cr = cairo_create(surf);
    PangoContext *ctx =
        pango_font_map_create_context(pango_cairo_font_map_get_default());
    PangoLayout *lay = pango_layout_new(ctx);
    PangoFontDescription *desc =
        pango_font_description_from_string(THEME_FONT_ROW);
    pango_layout_set_font_description(lay, desc);
    pango_layout_set_single_paragraph_mode(lay, TRUE);

    rgb_t bg = hex_rgb(THEME_BG);
    rgb_t pink = hex_rgb(THEME_PINK);
    rgb_t fg = hex_rgb(THEME_FG);
    rgb_t silver = hex_rgb(THEME_SILVER);
    rgb_t muted = hex_rgb(THEME_MUTED);

    /* Titlebar slab. */
    if (th > 0) {
        cairo_set_source_rgb(cr, bg.r, bg.g, bg.b);
        cairo_rectangle(cr, 0, 0, fw, th);
        cairo_fill(cr);

        /* Title, ellipsised before the buttons. */
        int text_w = fw - bw * 2 - 3 * WM_BTN_W - 8;
        if (text_w < 40) text_w = 40;
        pango_layout_set_text(lay, c->title ? c->title : "window", -1);
        pango_layout_set_ellipsize(lay, PANGO_ELLIPSIZE_END);
        pango_layout_set_width(lay, text_w * PANGO_SCALE);
        int tw = 0, tht = 0;
        pango_layout_get_pixel_size(lay, &tw, &tht);
        rgb_t tc = focused ? fg : silver;
        cairo_set_source_rgb(cr, tc.r, tc.g, tc.b);
        cairo_move_to(cr, bw + 6, (th - tht) / 2);
        pango_cairo_show_layout(cr, lay);

        /* Buttons. */
        for (btn_t b = BTN_MIN; b <= BTN_CLOSE; b = (btn_t)(b + 1)) {
            int x, y, w, h;
            btn_rect(c, bw, th, fw, b, &x, &y, &w, &h);
            rgb_t bc = muted;
            if (b == (btn_t)c->pressed_btn) bc = fg;
            else if (b == (btn_t)c->hover_btn) bc = pink;
            cairo_set_source_rgb(cr, bc.r, bc.g, bc.b);
            glyph(cr, b, x + w / 2.0, th / 2.0, 4.5);
        }

        /* Hairline under the bar. */
        cairo_set_source_rgb(cr, pink.r, pink.g, pink.b);
        cairo_set_line_width(cr, 1.0);
        cairo_move_to(cr, 0.5, th + 0.5);
        cairo_line_to(cr, fw - 0.5, th + 0.5);
        cairo_stroke(cr);
    }

    cairo_destroy(cr);
    cairo_surface_destroy(surf);
    pango_font_description_free(desc);
    g_object_unref(ctx);
    XFlush(dpy);
}

void frame_press(wm_t *wm, client_t *c, int fx, int fy)
{
    if (c->fullscreen) { c->pressed_btn = BTN_NONE; return; }
    c->pressed_btn = (int)frame_hit(c, wm->border_w, WM_TITLE_H, fx, fy);
    frame_paint(wm, c);
}

void frame_release(wm_t *wm, client_t *c, int fx, int fy)
{
    btn_t b = BTN_NONE;
    if (!c->fullscreen)
        b = frame_hit(c, wm->border_w, WM_TITLE_H, fx, fy);
    btn_t armed = (btn_t)c->pressed_btn;
    c->pressed_btn = BTN_NONE;
    frame_paint(wm, c);
    if (b != BTN_NONE && b == armed) {
        if (b == BTN_CLOSE) client_close(wm, c);
        else if (b == BTN_MAX) client_toggle_max(wm, c);
        else if (b == BTN_MIN) client_minimize(wm, c);
    }
}

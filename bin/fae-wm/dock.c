/* dock.c — the macOS-type dock.
 *
 * Bottom-center pill, autohiding: hidden below the screen edge, slides up
 * when the pointer nears the bottom, slides away after it leaves. Tiles are app
 * sigils — the ASCII art apps publish under assets/sigils — with big-initial
 * fallback, labels beneath, pink dots for running. Hover pills + shimmer sweeps
 * across the glyph chars; minimized dim. Click toggles focus/minimize; click an
 * idle pin to launch it.
 *
 * Single surface: one background rounded rect, no inner boxes. Override
 * redirect, above everything, never takes focus; clicks arrive via the root
 * grabs and motion directly.
 *
 * Auto-hide note: motion events over client windows never reach this WM, so the
 * hide decision is made by polling the pointer in dock_tick instead of relying
 * on MotionNotify.
 */
#include "dock.h"
#include "dock_geom.h"
#include "client.h"
#include "config.h"
#include "theme.h"
#include "wm.h"
#include "ewmh.h"

#include <ctype.h>
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

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

#define DOCK_PAD_X     10
#define DOCK_PAD_Y     8
#define DOCK_GAP       8
#define DOCK_TILE_W    52
#define DOCK_ART_H     32
#define DOCK_LBL_GAP   4
#define DOCK_HIDE_MS   400
#define DOCK_HOVER_MS  120
#define DOCK_FLASH_MS  1500
#define DOCK_SHIM_MS   240
#define DOCK_SLIDE_MS  240
#define DOCK_MAX_TILES 12
#define DOCK_TILES_MAX 64

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

static long now_ms(void)
{
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return ts.tv_sec * 1000L + ts.tv_nsec / 1000000L;
}

/* ── sigils ──────────────────────────────────────────────────────────────── */

#define SIG_MAX 32
#define SIG_LINES 16

typedef struct {
    char  key[64];
    char *lines[SIG_LINES];
    int   nlines;
} sigil_t;

static sigil_t sigils[SIG_MAX];
static int nsigils = 0;

static const sigil_t *sigil_for(const char *key)
{
    if (!key || !*key) return NULL;
    char norm[64];
    size_t i = 0;
    for (; key[i] && i < sizeof norm - 1; i++) {
        char ch = key[i];
        norm[i] = (ch >= 'A' && ch <= 'Z') ? ch + 32 : ch;
    }
    norm[i] = 0;
    for (int s = 0; s < nsigils; s++)
        if (!strcmp(sigils[s].key, norm)) return &sigils[s];
    if (nsigils >= SIG_MAX) return NULL;
    const char *home = getenv("HOME");
    if (!home) return NULL;
    char path[512];
    snprintf(path, sizeof path, "%s/%s/assets/sigils/%s.txt",
             home, norm, norm);
    FILE *f = fopen(path, "r");
    if (!f) return NULL;
    sigil_t *s = &sigils[nsigils];
    snprintf(s->key, sizeof s->key, "%s", norm);
    s->nlines = 0;
    char line[256];
    while (s->nlines < SIG_LINES && fgets(line, sizeof line, f)) {
        size_t n = strlen(line);
        while (n > 0 && (line[n - 1] == '\n' || line[n - 1] == '\r'))
            line[--n] = 0;
        s->lines[s->nlines] = strdup(line);
        s->nlines++;
    }
    fclose(f);
    if (s->nlines == 0) return NULL;
    nsigils++;
    return s;
}

/* ── tiles ───────────────────────────────────────────────────────────────── */

typedef struct {
    int       is_pin;
    pin_t    *pin;
    client_t *client;
} tile_t;

static Window dock_w = None;
static int dock_x, dock_y, dock_ww, dock_hh;
static int dock_hover_idx = -1;
static int dock_shown = 0;
static long dock_hide_at = 0;
static int dock_cur_y = -1;
static int dock_target_y = -1;      /* last slide destination */
static int dock_slide_from = 0;     /* y the current slide started at */
static long dock_slide_t0 = 0;
static int shim_idx = -1;           /* -2 = sweep all */
static long shim_t0 = 0;
static long dock_band_t0 = 0;       /* dwell clock for the hotspot */
static long hover_t0 = 0;

static int contains_ci(const char *hay, const char *needle)
{
    if (!hay || !needle || !*needle) return 0;
    size_t nl = strlen(needle);
    for (const char *p = hay; *p; p++) {
        size_t i = 0;
        for (; i < nl && p[i]; i++) {
            char a = p[i], b = needle[i];
            if (a >= 'A' && a <= 'Z') a += 32;
            if (b >= 'A' && b <= 'Z') b += 32;
            if (a != b) break;
        }
        if (i == nl) return 1;
    }
    return 0;
}

extern config_t *fae_cfg(void);

static client_t *pin_match(wm_t *wm, pin_t *pin)
{
    if (pin->pid > 0) {
        for (client_t *c = wm->clients; c; c = c->next)
            if (ewmh_pid(wm->dpy, c->xid) == (long)pin->pid) return c;
    }
    if (pin->match && *pin->match) {
        for (client_t *c = wm->clients; c; c = c->next) {
            if (contains_ci(c->title, pin->match)) return c;
            char *cls = ewmh_class(wm->dpy, c->xid);
            int hit = contains_ci(cls, pin->match);
            free(cls);
            if (hit) return c;
        }
    }
    return NULL;
}

static const sigil_t *tile_sigil(wm_t *wm, tile_t *t)
{
    static char keybuf[64];
    const sigil_t *s = NULL;
    if (t->is_pin && t->pin->match && *t->pin->match)
        s = sigil_for(t->pin->match);
    if (!s && t->client) {
        char *cls = ewmh_class(wm->dpy, t->client->xid);
        snprintf(keybuf, sizeof keybuf, "%s", cls ? cls : "");
        free(cls);
        s = sigil_for(keybuf);
    }
    if (!s) {
        const char *nm = t->is_pin ? t->pin->label :
                         (t->client ? t->client->title : "?");
        snprintf(keybuf, sizeof keybuf, "%s", nm);
        s = sigil_for(keybuf);
    }
    return s;
}

static int build_tiles(wm_t *wm, tile_t *out, int max)
{
    config_t *cfg = fae_cfg();
    int n = 0;
    if (cfg)
        for (int i = 0; i < cfg->npins && n < max; i++) {
            out[n].is_pin = 1;
            out[n].pin = &cfg->pins[i];
            out[n].client = pin_match(wm, &cfg->pins[i]);
            n++;
        }
    for (client_t *c = wm->clients; c && n < max; c = c->next) {
        int matched = 0;
        if (cfg)
            for (int i = 0; i < cfg->npins; i++)
                if (pin_match(wm, &cfg->pins[i]) == c) { matched = 1; break; }
        if (!matched) {
            out[n].is_pin = 0;
            out[n].pin = NULL;
            out[n].client = c;
            n++;
        }
    }
    return n;
}

static const char *tile_label(wm_t *wm, tile_t *t, char *buf, size_t n)
{
    if (t->is_pin && t->pin && t->pin->label) {
        dock_short_label(buf, n, t->pin->label);
        return buf;
    }
    if (t->client) {
        char *cls = ewmh_class(wm->dpy, t->client->xid);
        if (cls && *cls) {
            dock_short_label(buf, n, cls);
            free(cls);
            return buf;
        }
        free(cls);
        dock_short_label(buf, n, t->client->title);
        return buf;
    }
    snprintf(buf, n, "?");
    return buf;
}

/* Row start (window-relative): single formula for paint/click/hover. */
static int dock_start(int want_w, int n)
{
    int x = DOCK_PAD_X + (want_w - DOCK_PAD_X * 2 -
                          (n * DOCK_TILE_W + (n > 0 ? (n - 1) * DOCK_GAP : 0))) / 2;
    if (x < DOCK_PAD_X) x = DOCK_PAD_X;
    return x;
}

Window dock_win(wm_t *wm)
{
    (void)wm;
    return dock_w;
}

int dock_reserve(wm_t *wm)
{
    (void)wm;
    return 0;   /* overlaying autohide reserves nothing */
}

/* ── paint ───────────────────────────────────────────────────────────────── */

static void shimmer_span(char *dst, size_t n, const char *line, double sweep,
                         rgb_t base)
{
    size_t len = strlen(line);
    size_t at = 0;
    for (size_t i = 0; i < len && at + 64 < n; i++) {
        double d = (double)(int)i - sweep;
        if (d < 0) d = -d;
        double glow = d < 3.0 ? 1.0 - d / 3.0 : 0.0;
        int r = (int)(base.r * 255 + (0xe8 - base.r * 255) * glow + 0.5);
        int g = (int)(base.g * 255 + (0x79 - base.g * 255) * glow + 0.5);
        int b = (int)(base.b * 255 + (0xa0 - base.b * 255) * glow + 0.5);
        if (r < 0) r = 0; if (r > 255) r = 255;
        if (g < 0) g = 0; if (g > 255) g = 255;
        if (b < 0) b = 0; if (b > 255) b = 255;
        char ch = line[i];
        if (ch == ' ') {
            at += snprintf(dst + at, n - at, " ");
        } else {
            char esc[8];
            if (ch == '&') snprintf(esc, sizeof esc, "&amp;");
            else if (ch == '<') snprintf(esc, sizeof esc, "&lt;");
            else if (ch == '>') snprintf(esc, sizeof esc, "&gt;");
            else { esc[0] = ch; esc[1] = 0; }
            at += snprintf(dst + at, n - at,
                           "<span fgcolor=\"#%02x%02x%02x\">%s</span>",
                           r, g, b, esc);
        }
    }
    dst[at < n ? at : n - 1] = 0;
}

static void dock_paint(wm_t *wm)
{
    tile_t tiles[DOCK_TILES_MAX];
    int n = build_tiles(wm, tiles, DOCK_TILES_MAX);
    if (dock_hover_idx >= n) dock_hover_idx = -1;

    /* Cap the visible tiles; the last slot becomes an overflow indicator. */
    int shown = n, overflow = 0;
    if (n > DOCK_MAX_TILES) {
        shown = DOCK_MAX_TILES - 1;
        overflow = n - shown;
    }

    Display *dpy = wm->dpy;
    int scr = wm->scr;
    int n_slots = shown + (overflow > 0 ? 1 : 0);
    int want_w = DOCK_PAD_X * 2 + n_slots * DOCK_TILE_W +
                 (n_slots > 0 ? (n_slots - 1) * DOCK_GAP : 0);
    int max_w = DisplayWidth(dpy, scr) - 40;
    if (want_w > max_w) want_w = max_w;
    if (want_w < 120) want_w = 120;
    int want_h = DOCK_PAD_Y + DOCK_ART_H + DOCK_LBL_GAP + 12 + DOCK_PAD_Y;
    int px = (DisplayWidth(dpy, scr) - want_w) / 2;
    int target_y = DisplayHeight(dpy, scr) - want_h - 12;
    if (px < 0) px = 0;

    if (dock_w == None) {
        XSetWindowAttributes attr;
        memset(&attr, 0, sizeof attr);
        attr.override_redirect = True;
        attr.background_pixel = 0;
        attr.colormap = DefaultColormap(dpy, scr);
        attr.event_mask = ExposureMask | PointerMotionMask |
                       ButtonPressMask | ButtonReleaseMask;
        dock_w = XCreateWindow(dpy, DefaultRootWindow(dpy), px, target_y,
                               (unsigned)want_w, (unsigned)want_h, 0,
                               CopyFromParent, InputOutput, CopyFromParent,
                               CWOverrideRedirect | CWBackPixel | CWColormap |
                               CWEventMask, &attr);
        Atom wtype = XInternAtom(dpy, "_NET_WM_WINDOW_TYPE_DOCK", False);
        XChangeProperty(dpy, dock_w, XInternAtom(dpy, "_NET_WM_WINDOW_TYPE",
                                                False), XA_ATOM, 32,
                        PropModeReplace, (unsigned char *)&wtype, 1);
        dock_cur_y = DisplayHeight(dpy, scr);
        dock_target_y = dock_cur_y;
        XMoveWindow(dpy, dock_w, px, dock_cur_y);
        XMapWindow(dpy, dock_w);
    } else {
        XMoveResizeWindow(dpy, dock_w, px, dock_cur_y, (unsigned)want_w,
                          (unsigned)want_h);
    }
    dock_x = px;
    dock_y = target_y;
    dock_ww = want_w;
    dock_hh = want_h;

    cairo_surface_t *surf =
        cairo_xlib_surface_create(dpy, dock_w, DefaultVisual(dpy, scr),
                                  want_w, want_h);
    cairo_t *cr = cairo_create(surf);
    PangoContext *ctx =
        pango_font_map_create_context(pango_cairo_font_map_get_default());
    PangoLayout *lay = pango_layout_new(ctx);
    PangoFontDescription *desc_art =
        pango_font_description_from_string(THEME_FONT ":size=7");
    PangoFontDescription *desc_lbl =
        pango_font_description_from_string(THEME_FONT ":size=9");
    pango_layout_set_font_description(lay, desc_art);
    pango_layout_set_single_paragraph_mode(lay, TRUE);

    rgb_t bg = hex_rgb(THEME_BG);
    rgb_t silver = hex_rgb(THEME_SILVER);
    rgb_t muted = hex_rgb(THEME_MUTED);
    rgb_t pink = hex_rgb(THEME_PINK);

    /* Single surface: background rounded rect, no inner boxes. */
    double r = 12;
    cairo_new_sub_path(cr);
    cairo_arc(cr, want_w - r, want_h - r, r, 0.0, M_PI / 2);
    cairo_arc(cr, want_w - r, r,         r, M_PI / 2, M_PI);
    cairo_arc(cr, r,         r,         r, M_PI, 3 * M_PI / 2);
    cairo_arc(cr, r,         want_h - r, r, 3 * M_PI / 2, 2 * M_PI);
    cairo_close_path(cr);
    cairo_set_operator(cr, CAIRO_OPERATOR_SOURCE);
    cairo_set_source_rgba(cr, 0, 0, 0, 0);
    cairo_paint(cr);
    cairo_set_operator(cr, CAIRO_OPERATOR_OVER);
    cairo_set_source_rgb(cr, bg.r, bg.g, bg.b);
    cairo_fill(cr);

    long now = now_ms();
    double shim_pos = -1;
    int sweeping = 0;
    if (shim_idx == -2 || shim_idx >= 0) {
        long el = now - shim_t0;
        if (el >= DOCK_SHIM_MS) shim_idx = -1;
        else { sweeping = 1; shim_pos = (double)el / DOCK_SHIM_MS * 12.0 - 2.0; }
    }

    int x = dock_start(want_w, n_slots);
    for (int i = 0; i < shown; i++) {
        int cx = x + DOCK_TILE_W / 2;
        client_t *c = tiles[i].client;
        int running = (c != NULL);
        int dimmed = (c && c->minimized) || !running;
        int focused = (c && wm->focus == c);
        int hov = (i == dock_hover_idx);
        rgb_t base = focused ? pink : (dimmed ? muted : silver);

        /* Light blush behind the glyph only. */
        if (hov) {
            long hel = now - hover_t0;
            double ht = hel >= DOCK_HOVER_MS ? 1.0 : (double)hel / DOCK_HOVER_MS;
            ht = 1.0 - (1.0 - ht) * (1.0 - ht);
            double pr = 6;
            double pxx = x + 2, pyy = DOCK_PAD_Y;
            double pww = DOCK_TILE_W - 4, phh = DOCK_ART_H;
            cairo_set_source_rgba(cr, 0xf0 / 255.0, 0xb4 / 255.0, 0xc8 / 255.0,
                                  0.18 + 0.22 * ht);
            cairo_new_sub_path(cr);
            cairo_arc(cr, pxx + pww - pr, pyy + phh - pr, pr, 0.0, M_PI / 2);
            cairo_arc(cr, pxx + pww - pr, pyy + pr, pr, M_PI / 2, M_PI);
            cairo_arc(cr, pxx + pr, pyy + pr, pr, M_PI, 3 * M_PI / 2);
            cairo_arc(cr, pxx + pr, pyy + phh - pr, pr, 3 * M_PI / 2, 2 * M_PI);
            cairo_close_path(cr);
            cairo_fill(cr);
        }

        /* Glyph art, clipped to this tile and scaled to the art box. */
        const sigil_t *sig = tile_sigil(wm, &tiles[i]);
        pango_layout_set_font_description(lay, desc_art);
        cairo_save(cr);
        cairo_rectangle(cr, x, DOCK_PAD_Y, DOCK_TILE_W, DOCK_ART_H);
        cairo_clip(cr);
        if (sig) {
            int shimmering = (sweeping && (shim_idx == -2 || i == shim_idx));
            int total = 0;
            int lhs[SIG_LINES];
            for (int li = 0; li < sig->nlines; li++) {
                pango_layout_set_text(lay, sig->lines[li], -1);
                int tw = 0, th = 0;
                pango_layout_get_pixel_size(lay, &tw, &th);
                lhs[li] = th;
                total += th + 1;
            }
            double scale = 1.0;
            if (total > DOCK_ART_H && total > 0)
                scale = (double)DOCK_ART_H / (double)total;
            cairo_translate(cr, cx, DOCK_PAD_Y);
            cairo_scale(cr, scale, scale);
            cairo_translate(cr, -cx, -DOCK_PAD_Y);
            int ay = DOCK_PAD_Y;
            for (int li = 0; li < sig->nlines; li++) {
                char markup[1024];
                if (shimmering)
                    shimmer_span(markup, sizeof markup, sig->lines[li],
                                 shim_pos, base);
                else {
                    char esc[512];
                    size_t a2 = 0;
                    for (const char *p = sig->lines[li];
                         *p && a2 + 8 < sizeof esc; p++) {
                        if (*p == '&') { memcpy(esc + a2, "&amp;", 5); a2 += 5; }
                        else if (*p == '<') { memcpy(esc + a2, "&lt;", 4); a2 += 4; }
                        else if (*p == '>') { memcpy(esc + a2, "&gt;", 4); a2 += 4; }
                        else esc[a2++] = *p;
                    }
                    esc[a2] = 0;
                    snprintf(markup, sizeof markup,
                             "<span fgcolor=\"#%02x%02x%02x\">%s</span>",
                             (int)(base.r * 255), (int)(base.g * 255),
                             (int)(base.b * 255), esc);
                }
                pango_layout_set_markup(lay, markup, -1);
                int tw = 0, th = 0;
                pango_layout_get_pixel_size(lay, &tw, &th);
                cairo_move_to(cr, cx - tw / 2, ay);
                pango_cairo_show_layout(cr, lay);
                ay += lhs[li] + 1;
            }
        } else {
            char ini[8];
            const char *nm = tiles[i].is_pin ? tiles[i].pin->label :
                             (c && c->title ? c->title : "?");
            snprintf(ini, sizeof ini, "%c", nm[0] ? nm[0] : '?');
            pango_layout_set_text(lay, ini, -1);
            int tw = 0, th = 0;
            pango_layout_get_pixel_size(lay, &tw, &th);
            cairo_set_source_rgb(cr, base.r, base.g, base.b);
            cairo_move_to(cr, cx - tw / 2, DOCK_PAD_Y + (DOCK_ART_H - th) / 2);
            pango_cairo_show_layout(cr, lay);
        }
        cairo_restore(cr);

        /* Label under the art, short name, this tile only. */
        char label[128];
        tile_label(wm, &tiles[i], label, sizeof label);
        pango_layout_set_font_description(lay, desc_lbl);
        pango_layout_set_text(lay, label, -1);
        pango_layout_set_ellipsize(lay, PANGO_ELLIPSIZE_END);
        pango_layout_set_width(lay, (DOCK_TILE_W - 4) * PANGO_SCALE);
        int tw = 0, th = 0;
        pango_layout_get_pixel_size(lay, &tw, &th);
        cairo_set_source_rgb(cr, base.r, base.g, base.b);
        cairo_move_to(cr, cx - tw / 2, DOCK_PAD_Y + DOCK_ART_H + DOCK_LBL_GAP);
        pango_cairo_show_layout(cr, lay);

        /* Running dot. */
        if (running && !c->minimized) {
            cairo_set_source_rgb(cr, pink.r, pink.g, pink.b);
            cairo_arc(cr, cx, want_h - 6, 1.8, 0, 2 * M_PI);
            cairo_fill(cr);
        }
        x += DOCK_TILE_W + DOCK_GAP;
    }

    /* Overflow indicator. */
    if (overflow > 0) {
        int cx = x + DOCK_TILE_W / 2;
        rgb_t muted = hex_rgb(THEME_MUTED);
        char buf[16];
        snprintf(buf, sizeof buf, "+%d", overflow);
        pango_layout_set_text(lay, buf, -1);
        PangoFontDescription *big =
            pango_font_description_from_string(THEME_FONT_ROW);
        pango_layout_set_font_description(lay, big);
        pango_font_description_free(big);
        int tw = 0, th = 0;
        pango_layout_get_pixel_size(lay, &tw, &th);
        cairo_set_source_rgb(cr, muted.r, muted.g, muted.b);
        cairo_move_to(cr, cx - tw / 2, DOCK_PAD_Y + (DOCK_ART_H - th) / 2);
        pango_cairo_show_layout(cr, lay);
        pango_layout_set_font_description(lay, desc_lbl);

        pango_layout_set_text(lay, "more", -1);
        pango_layout_set_ellipsize(lay, PANGO_ELLIPSIZE_END);
        pango_layout_set_width(lay, (DOCK_TILE_W - 4) * PANGO_SCALE);
        pango_layout_get_pixel_size(lay, &tw, &th);
        cairo_move_to(cr, cx - tw / 2, DOCK_PAD_Y + DOCK_ART_H + DOCK_LBL_GAP);
        pango_cairo_show_layout(cr, lay);
    }

    cairo_destroy(cr);
    cairo_surface_destroy(surf);
    pango_font_description_free(desc_art);
    pango_font_description_free(desc_lbl);
    g_object_unref(ctx);
    XRaiseWindow(dpy, dock_w);
    XSync(dpy, False);
}

/* ── show / hide ─────────────────────────────────────────────────────────── */

static void dock_place(wm_t *wm)
{
    if (dock_w == None) return;
    Display *dpy = wm->dpy;
    XMoveWindow(dpy, dock_w, dock_x, dock_cur_y);
    XFlush(dpy);          /* async: no round-trip in the animation hot path */
}

void dock_refresh(wm_t *wm)
{
    if (dock_w == None) {
        dock_paint(wm);
        if (!dock_shown) {
            Display *dpy = wm->dpy;
            dock_cur_y = DisplayHeight(dpy, wm->scr);
            dock_target_y = dock_cur_y;
            XMoveWindow(dpy, dock_w, dock_x, dock_cur_y);
            XSync(dpy, False);
        }
        return;
    }
    dock_paint(wm);
}

void dock_flash(wm_t *wm)
{
    dock_shown = 1;
    dock_hide_at = now_ms() + DOCK_FLASH_MS;
    shim_idx = -2;
    shim_t0 = now_ms();
    dock_refresh(wm);
}

/* Summon / schedule-hide from a root y. Called from both the motion handler and
 * the pointer poller, so it must be idempotent. */
void dock_edge(wm_t *wm, int x_root, int y_root)
{
    int sw = DisplayWidth(wm->dpy, wm->scr);
    int sh = DisplayHeight(wm->dpy, wm->scr);
    config_t *cfg = fae_cfg();
    int center = cfg ? cfg->dock_hotspot_center : 1;
    int dwell = cfg ? cfg->dock_dwell : 280;
    long now = now_ms();
    int in_hot = dock_in_hotspot(x_root, y_root, sw, sh,
                                 dock_x, dock_ww, DOCK_EDGE_PX, center);
    int over = 0;
    if (dock_w != None && dock_shown)
        over = x_root >= dock_x && x_root < dock_x + dock_ww
            && y_root >= dock_cur_y && y_root < dock_cur_y + dock_hh;
    int ready = over || dock_dwell_ready(in_hot, now, &dock_band_t0, dwell);
    if (ready) {
        if (!dock_shown) {
            dock_shown = 1;
            dock_hide_at = 0;
            shim_idx = -2;
            shim_t0 = now;
            dock_refresh(wm);
        } else {
            dock_hide_at = 0;
        }
        return;
    }
    if (!dock_shown) return;
    if (!dock_hide_at)
        dock_hide_at = now + DOCK_HIDE_MS;
}

/* Main-loop driver: slide, hide timer, shimmer frames, and the pointer poll that
 * actually decides auto-hide. */
void dock_tick(wm_t *wm)
{
    if (dock_w == None) return;
    long now = now_ms();

    /* Auto-hide from polling — motion over clients never reaches us. */
    Window rr, cr;
    int rx, ry, wx, wy;
    unsigned mask = 0;
    XQueryPointer(wm->dpy, wm->root, &rr, &cr, &rx, &ry, &wx, &wy, &mask);
    dock_edge(wm, rx, ry);

    int target = dock_y;
    if (!dock_shown)
        target = DisplayHeight(wm->dpy, wm->scr);

    if (target != dock_target_y) {
        dock_target_y = target;
        dock_slide_from = dock_cur_y;
        dock_slide_t0 = now;
    }
    if (dock_cur_y != target) {
        long el = now - dock_slide_t0;
        double t = el >= DOCK_SLIDE_MS ? 1.0 : (double)el / DOCK_SLIDE_MS;
        double e = 1.0 - (1.0 - t) * (1.0 - t) * (1.0 - t);   /* ease-out cubic */
        int ny = dock_slide_from + (int)((target - dock_slide_from) * e);
        if (ny == dock_cur_y && t < 1.0)
            ny = dock_cur_y + (target > dock_cur_y ? 1 : -1);
        dock_cur_y = ny;
        if (t >= 1.0) dock_cur_y = target;
        dock_place(wm);
    }
    if (dock_hide_at && now >= dock_hide_at) {
        dock_hide_at = 0;
        dock_shown = 0;
    }
    if (shim_idx != -1) dock_paint(wm);
    else if (hover_t0 && now - hover_t0 < DOCK_HOVER_MS) dock_paint(wm);
}

void dock_click(wm_t *wm, int x_root, int y_root)
{
    if (dock_w == None) return;
    if (y_root < dock_y || y_root >= dock_y + dock_hh) return;

    tile_t tiles[DOCK_TILES_MAX];
    int n = build_tiles(wm, tiles, DOCK_TILES_MAX);
    int shown = n, overflow = 0;
    if (n > DOCK_MAX_TILES) {
        shown = DOCK_MAX_TILES - 1;
        overflow = n - shown;
    }
    int x = dock_x + dock_start(dock_ww, shown);
    for (int i = 0; i < shown; i++) {
        if (x_root >= x && x_root < x + DOCK_TILE_W) {
            tile_t *t = &tiles[i];
            if (t->is_pin && !t->client) {
                config_t *cfg = fae_cfg();
                pid_t pid = spawn_cmd(t->pin->cmd);
                if (pid > 0 && cfg) {
                    for (int k = 0; k < cfg->npins; k++)
                        if (&cfg->pins[k] == t->pin)
                            cfg->pins[k].pid = (int)pid;
                }
                wmlog("dock launch %s", t->pin->label);
                return;
            }
            client_t *c = t->client;
            if (!c) return;
            if (c->minimized) { client_unminimize(wm, c); return; }
            if (wm->focus == c) client_minimize(wm, c);
            else client_focus(wm, c);
            return;
        }
        x += DOCK_TILE_W + DOCK_GAP;
    }
    if (overflow > 0 && x_root >= x && x_root < x + DOCK_TILE_W) {
        dock_refresh(wm);   /* overflow tile: repaint only */
    }
}

void dock_hover(wm_t *wm, int x_root, int y_root)
{
    int hit = -1;
    if (dock_w != None && y_root >= dock_y && y_root < dock_y + dock_hh) {
        tile_t tiles[DOCK_TILES_MAX];
        int n = build_tiles(wm, tiles, DOCK_TILES_MAX);
        int shown = n, overflow = 0;
        if (n > DOCK_MAX_TILES) {
            shown = DOCK_MAX_TILES - 1;
            overflow = n - shown;
        }
        int x = dock_x + dock_start(dock_ww, shown);
        for (int i = 0; i < shown; i++) {
            if (x_root >= x && x_root < x + DOCK_TILE_W) { hit = i; break; }
            x += DOCK_TILE_W + DOCK_GAP;
        }
        if (hit < 0 && overflow > 0 && x_root >= x && x_root < x + DOCK_TILE_W)
            hit = -2;   /* overflow slot: no per-tile hover */
    }
    if (hit != dock_hover_idx) {
        dock_hover_idx = hit;
        hover_t0 = now_ms();
        if (hit >= 0) {
            shim_idx = hit;
            shim_t0 = now_ms();
        }
        dock_paint(wm);
    }
}

void dock_teardown(wm_t *wm)
{
    if (dock_w == None) return;
    XDestroyWindow(wm->dpy, dock_w);
    dock_w = None;
    XSync(wm->dpy, False);
}
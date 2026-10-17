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
#include "tile.h"

#include <ctype.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <sys/statvfs.h>

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
#define DOCK_CELL_W    56
#define DOCK_CELL_H    36
#define DOCK_GAP       8
#define DOCK_HIDE_MS   400
#define DOCK_HOVER_MS  120
#define DOCK_FLASH_MS  1500
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
static Pixmap dock_pix = None;
static cairo_surface_t *dock_surf = NULL;
static GC dock_gc = None;
static int pix_w, pix_h;
static Visual *dock_vis;
static int dock_depth;
static Colormap dock_cmap;
static int dock_x, dock_y, dock_ww, dock_hh;
static int dock_hover_idx = -1;
static int dock_shown = 0;
static long dock_hide_at = 0;
static int dock_cur_y = -1;
static int dock_target_y = -1;      /* last slide destination */
static int dock_slide_from = 0;     /* y the current slide started at */
static long dock_slide_t0 = 0;
static long dock_band_t0 = 0;       /* dwell clock for the hotspot */
static long hover_t0 = 0;
static struct { int x, w; } dock_cells[DOCK_MAX_TILES];
static int dock_ncells;
static int dock_row_y, dock_row_h;

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

static const char *SPARK = "▁▂▃▄▅▆▇█";
static int spark_i(int pct)
{
    if (pct < 0) pct = 0;
    if (pct > 100) pct = 100;
    return pct * 7 / 100;
}

static void spark_utf8(int pct, char *out, size_t n)
{
    int i = spark_i(pct);
    const unsigned char *p = (const unsigned char *)SPARK;
    /* each bar is 3-byte utf-8 */
    if (n < 4) { if (n) out[0] = 0; return; }
    memcpy(out, p + i * 3, 3);
    out[3] = 0;
}

static int ram_pct(void)
{
    FILE *f = fopen("/proc/meminfo", "r");
    if (!f) return -1;
    long total = 0, avail = 0;
    char k[64];
    long v;
    char rest[64];
    while (fscanf(f, "%63s %ld %63s\n", k, &v, rest) >= 2) {
        if (!strcmp(k, "MemTotal:")) total = v;
        else if (!strcmp(k, "MemAvailable:")) avail = v;
    }
    fclose(f);
    if (total <= 0) return -1;
    return (int)((100L * (total - avail)) / total);
}

static int cpu_pct(void)
{
    static unsigned long pidle, ptotal;
    static int last = -1;
    FILE *f = fopen("/proc/stat", "r");
    if (!f) return last;
    unsigned long u = 0, n = 0, s = 0, id = 0;
    if (fscanf(f, "cpu %lu %lu %lu %lu", &u, &n, &s, &id) < 4) {
        fclose(f);
        return last;
    }
    fclose(f);
    unsigned long tot = u + n + s + id;
    if (ptotal > 0 && tot > ptotal) {
        unsigned long dt = tot - ptotal, di = id - pidle;
        last = (int)((100 * (dt - di)) / dt);
        if (last < 0) last = 0;
        if (last > 100) last = 100;
    }
    pidle = id;
    ptotal = tot;
    return last;
}

static int disk_pct(void)
{
    struct statvfs v;
    if (statvfs("/", &v) != 0) return -1;
    unsigned long blocks = v.f_blocks;
    unsigned long freeb = v.f_bavail;
    if (!blocks) return -1;
    return (int)((100UL * (blocks - freeb)) / blocks);
}

static int cpu_temp_c(void)
{
    FILE *f = fopen("/sys/class/thermal/thermal_zone0/temp", "r");
    if (!f) return -1;
    int t = 0;
    if (fscanf(f, "%d", &t) != 1) { fclose(f); return -1; }
    fclose(f);
    t /= 1000;
    if (t < 10 || t > 110) return -1;
    return t;
}

static void music_label(char *dst, size_t n)
{
    dst[0] = 0;
    const char *home = getenv("HOME");
    if (!home) return;
    char path[256];
    snprintf(path, sizeof path, "%s/.cache/siren/now.json", home);
    FILE *f = fopen(path, "r");
    if (!f) return;
    char buf[512];
    size_t r = fread(buf, 1, sizeof buf - 1, f);
    fclose(f);
    buf[r] = 0;
    if (!strstr(buf, "\"state\":\"play\"")) return;
    char *p = strstr(buf, "\"label\":\"");
    if (!p) return;
    p += 9;
    char *e = strchr(p, '"');
    if (!e) return;
    size_t L = (size_t)(e - p);
    if (L > 40) L = 40;
    if (L == 0) return;
    snprintf(dst, n, "♪ %.*s", (int)L, p);
}

static int hit_cell(int lx, int ly)
{
    if (ly < dock_row_y || ly >= dock_row_y + dock_row_h) return -1;
    for (int i = 0; i < dock_ncells; i++)
        if (lx >= dock_cells[i].x && lx < dock_cells[i].x + dock_cells[i].w)
            return i;
    return -1;
}

static void dock_buffer_free(Display *dpy)
{
    if (dock_surf) {
        cairo_surface_destroy(dock_surf);
        dock_surf = NULL;
    }
    if (dock_pix != None) {
        XFreePixmap(dpy, dock_pix);
        dock_pix = None;
    }
    pix_w = pix_h = 0;
}

static int dock_buffer_ok(Display *dpy, int w, int h)
{
    if (w < 1) w = 1;
    if (h < 1) h = 1;
    if (dock_pix != None && pix_w == w && pix_h == h && dock_surf)
        return 1;
    dock_buffer_free(dpy);
    int depth = dock_depth ? dock_depth : DefaultDepth(dpy, DefaultScreen(dpy));
    Visual *vis = dock_vis ? dock_vis : DefaultVisual(dpy, DefaultScreen(dpy));
    dock_pix = XCreatePixmap(dpy, dock_w, (unsigned)w, (unsigned)h, (unsigned)depth);
    dock_surf = cairo_xlib_surface_create(dpy, dock_pix, vis, w, h);
    pix_w = w;
    pix_h = h;
    if (dock_gc == None)
        dock_gc = XCreateGC(dpy, dock_w, 0, NULL);
    return dock_pix != None && dock_surf != NULL;
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

static void dock_paint(wm_t *wm)
{
    tile_t tiles[DOCK_TILES_MAX];
    int n = build_tiles(wm, tiles, DOCK_TILES_MAX);
    if (dock_hover_idx >= n) dock_hover_idx = -1;

    int shown = n, overflow = 0;
    if (n > DOCK_MAX_TILES) {
        shown = DOCK_MAX_TILES - 1;
        overflow = n - shown;
    }

    Display *dpy = wm->dpy;
    int scr = wm->scr;

    char user[32];
    snprintf(user, sizeof user, "%s", getenv("USER") ? getenv("USER") : "you");
    char app[64] = "";
    if (dock_hover_idx >= 0 && dock_hover_idx < shown)
        tile_label(wm, &tiles[dock_hover_idx], app, sizeof app);

    char when[64], ram[32], cpu[32], hdd[32], tmpc[16], mus[96];
    time_t nowt = time(NULL);
    struct tm *tm = localtime(&nowt);
    if (tm)
        strftime(when, sizeof when, "%a %d %b · %H:%M", tm);
    else
        snprintf(when, sizeof when, "?");
    int rp = ram_pct(), cp = cpu_pct(), dp = disk_pct(), tp = cpu_temp_c();
    char sb[8];
    spark_utf8(rp < 0 ? 0 : rp, sb, sizeof sb);
    if (rp >= 0) snprintf(ram, sizeof ram, "RAM %s %d%%", sb, rp);
    else snprintf(ram, sizeof ram, "RAM ?");
    spark_utf8(cp < 0 ? 0 : cp, sb, sizeof sb);
    if (cp >= 0) snprintf(cpu, sizeof cpu, "CPU %s %d%%", sb, cp);
    else snprintf(cpu, sizeof cpu, "CPU ?");
    spark_utf8(dp < 0 ? 0 : dp, sb, sizeof sb);
    if (dp >= 0) snprintf(hdd, sizeof hdd, "HDD %s %d%%", sb, dp);
    else snprintf(hdd, sizeof hdd, "HDD ?");
    if (tp >= 0) snprintf(tmpc, sizeof tmpc, "%d°C", tp);
    else tmpc[0] = 0;
    music_label(mus, sizeof mus);

    char title[256];
    const char *who = app[0] ? app : user;
    snprintf(title, sizeof title, " ✦ %s ✦ · %s · %s · %s · %s%s%s ",
             who, when, ram, cpu, hdd,
             tmpc[0] ? " · " : "", tmpc);

    int n_slots = shown + (overflow > 0 ? 1 : 0);
    int inner_w = n_slots * DOCK_CELL_W + (n_slots > 1 ? (n_slots - 1) * DOCK_GAP : 0);
    int title_est = (int)strlen(title) + 4;
    int want_w = inner_w + DOCK_PAD_X * 2 + 8;
    if (want_w < title_est * 8) want_w = title_est * 8; /* rough; pango corrects */
    int max_w = DisplayWidth(dpy, scr) - 40;
    if (want_w > max_w) want_w = max_w;
    if (want_w < 280) want_w = 280;
    int want_h = 8 + 16 + DOCK_CELL_H + 16 + 8;
    int px = (DisplayWidth(dpy, scr) - want_w) / 2;
    int target_y = DisplayHeight(dpy, scr) - want_h - 8;
    if (px < 0) px = 0;

    if (dock_w == None) {
        XSetWindowAttributes attr;
        memset(&attr, 0, sizeof attr);
        attr.override_redirect = True;
        attr.background_pixel = 0;
        attr.border_pixel = 0;
        attr.backing_store = WhenMapped;
        attr.event_mask = ExposureMask | PointerMotionMask |
                       ButtonPressMask | ButtonReleaseMask;
        int depth = DefaultDepth(dpy, scr);
        Visual *vis = DefaultVisual(dpy, scr);
        unsigned vmask = CWOverrideRedirect | CWBackPixel | CWBorderPixel |
                         CWEventMask | CWBackingStore;
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
            dock_vis = vis;
            dock_depth = 32;
            dock_cmap = XCreateColormap(dpy, DefaultRootWindow(dpy), vis, AllocNone);
            attr.colormap = dock_cmap;
            vmask |= CWColormap;
            XFree(vi);
        } else {
            attr.colormap = DefaultColormap(dpy, scr);
            vmask |= CWColormap;
            if (vi) XFree(vi);
        }
        dock_w = XCreateWindow(dpy, DefaultRootWindow(dpy), px, target_y,
                               (unsigned)want_w, (unsigned)want_h, 0,
                               depth, InputOutput, vis, vmask, &attr);
        Atom wtype = XInternAtom(dpy, "_NET_WM_WINDOW_TYPE_DOCK", False);
        XChangeProperty(dpy, dock_w, XInternAtom(dpy, "_NET_WM_WINDOW_TYPE",
                                                False), XA_ATOM, 32,
                        PropModeReplace, (unsigned char *)&wtype, 1);
        dock_cur_y = DisplayHeight(dpy, scr);
        dock_target_y = dock_cur_y;
        XMoveWindow(dpy, dock_w, px, dock_cur_y);
        XMapWindow(dpy, dock_w);
        XRaiseWindow(dpy, dock_w);
    } else if (want_w != dock_ww || want_h != dock_hh) {
        XMoveResizeWindow(dpy, dock_w, px, dock_cur_y, (unsigned)want_w,
                          (unsigned)want_h);
    }
    dock_x = px;
    dock_y = target_y;
    dock_ww = want_w;
    dock_hh = want_h;

    if (!dock_buffer_ok(dpy, want_w, want_h)) return;
    cairo_t *cr = cairo_create(dock_surf);
    PangoContext *ctx =
        pango_font_map_create_context(pango_cairo_font_map_get_default());
    PangoLayout *lay = pango_layout_new(ctx);
    PangoFontDescription *desc =
        pango_font_description_from_string(THEME_FONT ":size=11");
    PangoFontDescription *desc_g =
        pango_font_description_from_string(THEME_FONT ":size=7");
    pango_layout_set_font_description(lay, desc);
    pango_layout_set_single_paragraph_mode(lay, TRUE);

    rgb_t bg = hex_rgb(THEME_BG);
    rgb_t pink = hex_rgb(THEME_PINK);
    rgb_t dim = hex_rgb(THEME_MUTED);
    rgb_t silver = hex_rgb(THEME_SILVER);

    cairo_set_operator(cr, CAIRO_OPERATOR_SOURCE);
    cairo_set_source_rgba(cr, 0, 0, 0, 0);
    cairo_paint(cr);
    cairo_set_operator(cr, CAIRO_OPERATOR_OVER);

    pango_layout_set_text(lay, "M", -1);
    int ch_w = 8, ch_h = 14;
    pango_layout_get_pixel_size(lay, &ch_w, &ch_h);

    pango_layout_set_text(lay, title, -1);
    int tw = 0, th = 0;
    pango_layout_get_pixel_size(lay, &tw, &th);
    int inner = want_w - 2 * ch_w - 4;
    if (inner < 20) inner = 20;

    /* fill inside the box */
    double a_fill = dock_depth == 32 ? 0.82 : 1.0;
    cairo_set_source_rgba(cr, bg.r, bg.g, bg.b, a_fill);
    cairo_rectangle(cr, 1, 1, want_w - 2, want_h - 2);
    cairo_fill(cr);

    cairo_set_source_rgb(cr, dim.r, dim.g, dim.b);
    pango_layout_set_text(lay, "╭─", -1);
    int x0 = 2, y0 = 4;
    cairo_move_to(cr, x0, y0);
    pango_cairo_show_layout(cr, lay);
    int px1 = 0, py1 = 0;
    pango_layout_get_pixel_size(lay, &px1, &py1);
    cairo_set_source_rgb(cr, pink.r, pink.g, pink.b);
    cairo_move_to(cr, x0 + px1, y0);
    pango_layout_set_text(lay, title, -1);
    pango_cairo_show_layout(cr, lay);
    int tt = 0, thh = 0;
    pango_layout_get_pixel_size(lay, &tt, &thh);
    cairo_set_source_rgb(cr, dim.r, dim.g, dim.b);
    int dx = x0 + px1 + tt;
    while (dx + ch_w < want_w - ch_w - 2) {
        pango_layout_set_text(lay, "─", -1);
        cairo_move_to(cr, dx, y0);
        pango_cairo_show_layout(cr, lay);
        int dw = 0, dh = 0;
        pango_layout_get_pixel_size(lay, &dw, &dh);
        if (dw < 1) dw = ch_w;
        dx += dw;
    }
    pango_layout_set_text(lay, "╮", -1);
    cairo_move_to(cr, want_w - ch_w - 2, y0);
    pango_cairo_show_layout(cr, lay);

    dock_row_y = y0 + thh + 2;
    dock_row_h = DOCK_CELL_H;
    int gx = DOCK_PAD_X + 4;
    dock_ncells = shown;
    long now = now_ms();
    double ht = 1.0;
    if (hover_t0)
        ht = (double)(now - hover_t0) / (double)DOCK_HOVER_MS;
    if (ht > 1) ht = 1;
    ht = 1.0 - (1.0 - ht) * (1.0 - ht);

    pango_layout_set_font_description(lay, desc_g);
    for (int i = 0; i < shown; i++) {
        dock_cells[i].x = gx;
        dock_cells[i].w = DOCK_CELL_W;
        int hov = (i == dock_hover_idx);
        client_t *c = tiles[i].client;
        int running = c && !c->minimized;
        int focused = c && wm->focus == c;
        rgb_t ink = focused ? pink : (running ? silver : dim);
        if (hov) {
            cairo_set_source_rgba(cr, pink.r, pink.g, pink.b, 0.22 + 0.25 * ht);
            cairo_rectangle(cr, gx, dock_row_y, DOCK_CELL_W, DOCK_CELL_H);
            cairo_fill(cr);
            ink = pink;
        }
        cairo_save(cr);
        cairo_rectangle(cr, gx, dock_row_y, DOCK_CELL_W, DOCK_CELL_H);
        cairo_clip(cr);
        cairo_set_source_rgb(cr, ink.r, ink.g, ink.b);
        const sigil_t *sig = tile_sigil(wm, &tiles[i]);
        if (sig && sig->nlines > 0) {
            int start = sig->nlines > 3 ? (sig->nlines - 3) / 2 : 0;
            int use = sig->nlines > 3 ? 3 : sig->nlines;
            int ay = dock_row_y + 2;
            for (int li = 0; li < use; li++) {
                pango_layout_set_text(lay, sig->lines[start + li], -1);
                int gw = 0, gh = 0;
                pango_layout_get_pixel_size(lay, &gw, &gh);
                cairo_move_to(cr, gx + (DOCK_CELL_W - gw) / 2, ay);
                pango_cairo_show_layout(cr, lay);
                ay += gh;
            }
        } else {
            char ini[8];
            const char *nm = tiles[i].is_pin && tiles[i].pin ? tiles[i].pin->label : "?";
            snprintf(ini, sizeof ini, "%c", nm[0] ? nm[0] : '?');
            pango_layout_set_font_description(lay, desc);
            pango_layout_set_text(lay, ini, -1);
            int gw = 0, gh = 0;
            pango_layout_get_pixel_size(lay, &gw, &gh);
            cairo_move_to(cr, gx + (DOCK_CELL_W - gw) / 2,
                          dock_row_y + (DOCK_CELL_H - gh) / 2);
            pango_cairo_show_layout(cr, lay);
            pango_layout_set_font_description(lay, desc_g);
        }
        cairo_restore(cr);
        if (running) {
            cairo_set_source_rgb(cr, pink.r, pink.g, pink.b);
            pango_layout_set_font_description(lay, desc);
            pango_layout_set_text(lay, "*", -1);
            cairo_move_to(cr, gx + DOCK_CELL_W - 10, dock_row_y + DOCK_CELL_H - 14);
            pango_cairo_show_layout(cr, lay);
            pango_layout_set_font_description(lay, desc_g);
        }
        gx += DOCK_CELL_W + DOCK_GAP;
    }
    if (overflow > 0) {
        pango_layout_set_font_description(lay, desc);
        char more[16];
        snprintf(more, sizeof more, "+%d", overflow);
        cairo_set_source_rgb(cr, dim.r, dim.g, dim.b);
        pango_layout_set_text(lay, more, -1);
        cairo_move_to(cr, gx, dock_row_y + 8);
        pango_cairo_show_layout(cr, lay);
    }
    if (mus[0] && gx + 80 < want_w - 12) {
        pango_layout_set_font_description(lay, desc);
        cairo_set_source_rgb(cr, pink.r, pink.g, pink.b);
        pango_layout_set_text(lay, mus, -1);
        cairo_move_to(cr, gx + 8, dock_row_y + (DOCK_CELL_H - ch_h) / 2);
        pango_cairo_show_layout(cr, lay);
    }

    pango_layout_set_font_description(lay, desc);
    cairo_set_source_rgb(cr, dim.r, dim.g, dim.b);
    pango_layout_set_text(lay, "│", -1);
    cairo_move_to(cr, 2, dock_row_y);
    pango_cairo_show_layout(cr, lay);
    cairo_move_to(cr, want_w - ch_w - 2, dock_row_y);
    pango_cairo_show_layout(cr, lay);

    int by = dock_row_y + DOCK_CELL_H + 2;
    pango_layout_set_text(lay, "╰", -1);
    cairo_move_to(cr, 2, by);
    pango_cairo_show_layout(cr, lay);
    int bx = 2 + ch_w;
    pango_layout_set_text(lay, "─", -1);
    int dw = ch_w, dh = ch_h;
    pango_layout_get_pixel_size(lay, &dw, &dh);
    if (dw < 1) dw = ch_w;
    while (bx + dw < want_w - ch_w - 2) {
        cairo_move_to(cr, bx, by);
        pango_cairo_show_layout(cr, lay);
        bx += dw;
    }
    pango_layout_set_text(lay, "╯", -1);
    cairo_move_to(cr, want_w - ch_w - 2, by);
    pango_cairo_show_layout(cr, lay);

    cairo_surface_flush(dock_surf);
    cairo_destroy(cr);
    pango_font_description_free(desc);
    pango_font_description_free(desc_g);
    g_object_unref(lay);
    g_object_unref(ctx);
    XCopyArea(dpy, dock_pix, dock_w, dock_gc, 0, 0,
              (unsigned)want_w, (unsigned)want_h, 0, 0);
    XFlush(dpy);
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
            XFlush(dpy);
        }
        return;
    }
    dock_paint(wm);
}

void dock_flash(wm_t *wm)
{
    dock_shown = 1;
    dock_hide_at = now_ms() + DOCK_FLASH_MS;
    XRaiseWindow(wm->dpy, dock_w);
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
            XRaiseWindow(wm->dpy, dock_w);
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
    if (tile_desk_fullscreen(wm)) {
        if (dock_shown) {
            dock_shown = 0;
            dock_hide_at = 0;
        }
    } else {
        dock_edge(wm, rx, ry);
    }

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
    if (hover_t0 && now - hover_t0 < DOCK_HOVER_MS) dock_paint(wm);
    else if (dock_shown && (now / 1000) != ((now - 16) / 1000))
        dock_paint(wm); /* clock / RAM once a second */
}

void dock_click(wm_t *wm, int x_root, int y_root)
{
    if (dock_w == None) return;
    int lx = x_root - dock_x;
    int ly = y_root - dock_cur_y;
    int i = hit_cell(lx, ly);
    if (i < 0) return;

    tile_t tiles[DOCK_TILES_MAX];
    int n = build_tiles(wm, tiles, DOCK_TILES_MAX);
    int shown = n;
    if (n > DOCK_MAX_TILES) shown = DOCK_MAX_TILES - 1;
    if (i >= shown) return;
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
}

void dock_hover(wm_t *wm, int x_root, int y_root)
{
    int hit = -1;
    if (dock_w != None) {
        int lx = x_root - dock_x;
        int ly = y_root - dock_cur_y;
        hit = hit_cell(lx, ly);
    }
    if (hit != dock_hover_idx) {
        dock_hover_idx = hit;
        hover_t0 = now_ms();
        dock_paint(wm);
    }
}

void dock_teardown(wm_t *wm)
{
    if (dock_w == None) return;
    dock_buffer_free(wm->dpy);
    if (dock_gc != None) {
        XFreeGC(wm->dpy, dock_gc);
        dock_gc = None;
    }
    XDestroyWindow(wm->dpy, dock_w);
    dock_w = None;
    XFlush(wm->dpy);
}
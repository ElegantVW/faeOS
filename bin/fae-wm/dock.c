/* dock.c — starship capsule.
 *
 * Pink glass stadium (radius = half height) with circular wells. Each well
 * holds the whole house sigil, scaled to fit. Hover lifts the well out of
 * the capsule. Top band is clock/RAM/CPU/HDD/temp; footer is music, mail
 * count, focused client. Width follows the icon row; status ellipsizes.
 *
 * 32-bit ARGB, named fae-dock, picom leaves it unrounded/unshadowed.
 * Slide is XMoveWindow. Paint on show, hover ease, tile/scale change, or
 * a 1 s stats cache change while shown.
 */
#include "dock.h"
#include "dock_geom.h"
#include "client.h"
#include "config.h"
#include "theme.h"
#include "wm.h"
#include "ewmh.h"
#include "tile.h"

#include <dirent.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/statvfs.h>
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
static int dock_target_y = -1;
static int dock_slide_from = 0;
static long dock_slide_t0 = 0;
static long dock_band_t0 = 0;
static long hover_t0 = 0;
static dock_m_t M;
static int M_ready = 0;
static long stats_t0 = 0;
static char stats_top[192];
static char stats_foot[192];

static double live_scale(void)
{
    config_t *cfg = fae_cfg();
    return dock_scale_snap(cfg ? cfg->dock_scale : 1.0);
}

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

static int ram_pct(void)
{
    FILE *f = fopen("/proc/meminfo", "r");
    if (!f) return -1;
    long total = 0, avail = 0, v;
    char k[64], rest[64];
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
    if (!v.f_blocks) return -1;
    return (int)((100UL * (v.f_blocks - v.f_bavail)) / v.f_blocks);
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

static int goblin_unread(void)
{
    const char *home = getenv("HOME");
    if (!home) return 0;
    char path[512];
    snprintf(path, sizeof path, "%s/.cache/goblin/mail/unread", home);
    DIR *d = opendir(path);
    if (!d) return 0;
    int n = 0;
    struct dirent *e;
    while ((e = readdir(d))) {
        size_t L = strlen(e->d_name);
        if (L > 4 && !strcmp(e->d_name + L - 4, ".txt")) n++;
    }
    closedir(d);
    return n;
}

/* Returns 1 if the cached strings changed. */
static int stats_refresh(wm_t *wm, int force)
{
    long now = now_ms();
    if (!force && stats_t0 && now - stats_t0 < 1000) return 0;
    stats_t0 = now;

    const char *user = getenv("USER");
    if (!user || !*user) user = "you";
    char when[16];
    time_t nowt = time(NULL);
    struct tm *tm = localtime(&nowt);
    if (tm) strftime(when, sizeof when, "%H:%M", tm);
    else snprintf(when, sizeof when, "??:??");
    int rp = ram_pct(), cp = cpu_pct(), dp = disk_pct(), tp = cpu_temp_c();
    char top[192];
    if (tp >= 0)
        snprintf(top, sizeof top, "✦ %s ✦ · %s · RAM %02d%% · CPU %02d%% · HDD %02d%% · %d°C",
                 user, when, rp < 0 ? 0 : rp, cp < 0 ? 0 : cp, dp < 0 ? 0 : dp, tp);
    else
        snprintf(top, sizeof top, "✦ %s ✦ · %s · RAM %02d%% · CPU %02d%% · HDD %02d%%",
                 user, when, rp < 0 ? 0 : rp, cp < 0 ? 0 : cp, dp < 0 ? 0 : dp);

    char mus[96];
    music_label(mus, sizeof mus);
    char focus[32] = "";
    if (wm && wm->focus)
        dock_short_label(focus, sizeof focus, wm->focus->title);
    int mail = goblin_unread();
    char foot[192];
    foot[0] = 0;
    if (mus[0]) snprintf(foot, sizeof foot, "%s", mus);
    if (mail > 0) {
        char chip[24];
        snprintf(chip, sizeof chip, "✉ %d", mail);
        if (foot[0]) {
            size_t n = strlen(foot);
            snprintf(foot + n, sizeof foot - n, " · %s", chip);
        } else snprintf(foot, sizeof foot, "%s", chip);
    }
    if (focus[0]) {
        if (foot[0]) {
            size_t n = strlen(foot);
            snprintf(foot + n, sizeof foot - n, " · %s", focus);
        } else snprintf(foot, sizeof foot, "%s", focus);
    }

    int changed = strcmp(top, stats_top) || strcmp(foot, stats_foot);
    snprintf(stats_top, sizeof stats_top, "%s", top);
    snprintf(stats_foot, sizeof stats_foot, "%s", foot);
    return changed;
}

static void dock_install_cmap(Display *dpy)
{
    if (dock_cmap) XInstallColormap(dpy, dock_cmap);
}

static void round_rect(cairo_t *cr, double x, double y, double w, double h, double rad)
{
    if (rad > w / 2) rad = w / 2;
    if (rad > h / 2) rad = h / 2;
    cairo_new_sub_path(cr);
    cairo_arc(cr, x + w - rad, y + rad, rad, -M_PI / 2, 0.0);
    cairo_arc(cr, x + w - rad, y + h - rad, rad, 0.0, M_PI / 2);
    cairo_arc(cr, x + rad, y + h - rad, rad, M_PI / 2, M_PI);
    cairo_arc(cr, x + rad, y + rad, rad, M_PI, 3 * M_PI / 2);
    cairo_close_path(cr);
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

static void dock_name_window(Display *dpy, Window w)
{
    XStoreName(dpy, w, "fae-dock");
    XClassHint ch;
    ch.res_name = "fae-dock";
    ch.res_class = "fae-dock";
    XSetClassHint(dpy, w, &ch);
    XWMHints hints;
    memset(&hints, 0, sizeof hints);
    hints.flags = InputHint;
    hints.input = False;
    XSetWMHints(dpy, w, &hints);
}

Window dock_win(wm_t *wm)
{
    (void)wm;
    return dock_w;
}

int dock_reserve(wm_t *wm)
{
    (void)wm;
    return 0;
}

static int hit_tile(int x_root, int y_root, int shown)
{
    if (!M_ready || dock_w == None) return -1;
    int y0 = dock_cur_y >= 0 ? dock_cur_y : dock_y;
    if (y_root < y0 || y_root >= y0 + dock_hh) return -1;
    int x = dock_x + dock_row_start(dock_ww, shown, &M);
    for (int i = 0; i < shown; i++) {
        if (x_root >= x && x_root < x + M.tile_w) return i;
        x += M.tile_w + M.gap;
    }
    return -1;
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
    M = dock_metrics(live_scale());
    M_ready = 1;
    int n_slots = shown + (overflow > 0 ? 1 : 0);
    int want_w = dock_want_w(n_slots, &M);
    int max_w = DisplayWidth(dpy, scr) - 40;
    if (want_w > max_w) want_w = max_w;
    if (want_w < 120) want_w = 120;
    int want_h = dock_want_h(&M);
    int px = (DisplayWidth(dpy, scr) - want_w) / 2;
    int target_y = DisplayHeight(dpy, scr) - want_h - 8;
    if (px < 0) px = 0;
    int stadium_h = dock_stadium_h(&M);
    int shelf_y = M.head + M.lift;
    int status_y = shelf_y + M.pad_y;
    int well_y = status_y + M.status_h + M.band_gap;
    int foot_y = well_y + M.well + M.band_gap;
    double stadium_r = stadium_h / 2.0;
    int first = 0;
    stats_refresh(wm, 1);

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
        dock_name_window(dpy, dock_w);
        dock_install_cmap(dpy);
        dock_cur_y = DisplayHeight(dpy, scr);
        dock_target_y = dock_cur_y;
        first = 1;
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
    char f_art[64], f_mark[64], f_lbl[64], f_stat[64], f_foot[64];
    snprintf(f_art, sizeof f_art, "%s:size=%d", THEME_FONT, M.art_pt);
    snprintf(f_mark, sizeof f_mark, "%s:size=%d", THEME_FONT, M.mark_pt);
    snprintf(f_lbl, sizeof f_lbl, "%s:size=%d", THEME_FONT, M.lbl_pt);
    snprintf(f_stat, sizeof f_stat, "%s:size=%d", THEME_FONT, M.status_pt);
    snprintf(f_foot, sizeof f_foot, "%s:size=%d", THEME_FONT, M.foot_pt);
    PangoFontDescription *desc_art = pango_font_description_from_string(f_art);
    PangoFontDescription *desc_mark = pango_font_description_from_string(f_mark);
    PangoFontDescription *desc_lbl = pango_font_description_from_string(f_lbl);
    PangoFontDescription *desc_stat = pango_font_description_from_string(f_stat);
    PangoFontDescription *desc_foot = pango_font_description_from_string(f_foot);
    pango_layout_set_single_paragraph_mode(lay, TRUE);

    rgb_t bg = hex_rgb(THEME_BG);
    rgb_t pink = hex_rgb(THEME_PINK);
    rgb_t muted = hex_rgb(THEME_MUTED);
    rgb_t silver = hex_rgb(THEME_SILVER);
    rgb_t wellc = hex_rgb("#3a1824");

    cairo_set_operator(cr, CAIRO_OPERATOR_SOURCE);
    cairo_set_source_rgba(cr, 0, 0, 0, 0);
    cairo_paint(cr);
    cairo_set_operator(cr, CAIRO_OPERATOR_OVER);

    /* Stadium: pink glass, hairline on the same path, radius = half height. */
    {
        cairo_pattern_t *g = cairo_pattern_create_linear(0, shelf_y, 0, want_h);
        cairo_pattern_add_color_stop_rgb(g, 0.0, 0x3a / 255.0, 0x18 / 255.0, 0x24 / 255.0);
        cairo_pattern_add_color_stop_rgb(g, 1.0, bg.r, bg.g, bg.b);
        round_rect(cr, 0.5, shelf_y + 0.5, want_w - 1.0, stadium_h - 1.0, stadium_r);
        cairo_set_source(cr, g);
        cairo_fill_preserve(cr);
        cairo_pattern_destroy(g);
        cairo_set_source_rgba(cr, pink.r, pink.g, pink.b, 0.70);
        cairo_set_line_width(cr, 1.2);
        cairo_stroke(cr);
        cairo_save(cr);
        round_rect(cr, 0.5, shelf_y + 0.5, want_w - 1.0, stadium_h - 1.0, stadium_r);
        cairo_clip(cr);
        cairo_set_source_rgba(cr, 1.0, 0.92, 0.95, 0.14);
        cairo_set_line_width(cr, 1.2);
        cairo_move_to(cr, stadium_r, shelf_y + 1.4);
        cairo_line_to(cr, want_w - stadium_r, shelf_y + 1.4);
        cairo_stroke(cr);
        cairo_restore(cr);
    }

    int inner_text = want_w - 2 * M.pad_x;
    if (inner_text < 40) inner_text = 40;
    pango_layout_set_ellipsize(lay, PANGO_ELLIPSIZE_END);
    pango_layout_set_width(lay, inner_text * PANGO_SCALE);
    pango_layout_set_font_description(lay, desc_stat);
    cairo_set_source_rgba(cr, pink.r, pink.g, pink.b, 0.92);
    pango_layout_set_text(lay, stats_top, -1);
    int stw = 0, sth = 0;
    pango_layout_get_pixel_size(lay, &stw, &sth);
    cairo_move_to(cr, M.pad_x, status_y + (M.status_h - sth) / 2);
    pango_cairo_show_layout(cr, lay);

    pango_layout_set_font_description(lay, desc_foot);
    cairo_set_source_rgba(cr, pink.r, pink.g, pink.b, 0.75);
    pango_layout_set_text(lay, stats_foot[0] ? stats_foot : "", -1);
    int ftw = 0, fth = 0;
    pango_layout_get_pixel_size(lay, &ftw, &fth);
    cairo_move_to(cr, M.pad_x, foot_y + (M.foot_h - fth) / 2);
    pango_cairo_show_layout(cr, lay);
    pango_layout_set_width(lay, -1);
    pango_layout_set_ellipsize(lay, PANGO_ELLIPSIZE_NONE);

    long now = now_ms();
    double dot_y = well_y + M.well + M.dot_r * 2.0 + 1.0;

    int x = dock_row_start(want_w, n_slots, &M);
    for (int i = 0; i < shown; i++) {
        int cx = x + M.tile_w / 2;
        client_t *c = tiles[i].client;
        int running = (c != NULL);
        int dimmed = (c && c->minimized) || !running;
        int focused = (c && wm->focus == c);
        int hov = (i == dock_hover_idx);
        rgb_t ink = focused ? pink : (dimmed ? muted : silver);
        double sc = 1.0, lift = 0.0;
        if (hov) {
            double t = hover_t0 ? (double)(now - hover_t0) / (double)DOCK_HOVER_MS : 1.0;
            sc = dock_hover_scale(t);
            lift = dock_hover_lift_px(t, (double)M.lift);
        }
        double ww = M.well;
        double cy = well_y + ww / 2.0 + lift;
        double crd = ww / 2.0;

        cairo_save(cr);
        cairo_translate(cr, cx, cy);
        cairo_scale(cr, sc, sc);
        cairo_translate(cr, -cx, -cy);

        cairo_arc(cr, cx, cy, crd, 0, 2 * M_PI);
        cairo_set_source_rgb(cr, wellc.r, wellc.g, wellc.b);
        cairo_fill_preserve(cr);
        if (focused || hov) {
            cairo_set_source_rgba(cr, pink.r, pink.g, pink.b, hov ? 0.95 : 0.55);
            cairo_set_line_width(cr, 1.4);
            cairo_stroke_preserve(cr);
        } else {
            cairo_set_source_rgba(cr, pink.r, pink.g, pink.b, 0.45);
            cairo_set_line_width(cr, 1.1);
            cairo_stroke_preserve(cr);
        }
        cairo_clip(cr);

        const sigil_t *sig = tile_sigil(wm, &tiles[i]);
        cairo_set_source_rgb(cr, ink.r, ink.g, ink.b);
        pango_layout_set_font_description(lay, desc_art);
        if (sig && sig->nlines > 0) {
            int maxw = 0, total = 0, hs[SIG_LINES];
            for (int li = 0; li < sig->nlines; li++) {
                pango_layout_set_text(lay, sig->lines[li], -1);
                int tw = 0, th = 0;
                pango_layout_get_pixel_size(lay, &tw, &th);
                hs[li] = th;
                if (tw > maxw) maxw = tw;
                total += th;
            }
            double fit = dock_sigil_fit(ww, (double)maxw, (double)total, 4.0);
            cairo_save(cr);
            cairo_translate(cr, cx, cy);
            cairo_scale(cr, fit, fit);
            cairo_translate(cr, -maxw / 2.0, -total / 2.0);
            int ay = 0;
            for (int li = 0; li < sig->nlines; li++) {
                pango_layout_set_text(lay, sig->lines[li], -1);
                cairo_move_to(cr, 0, ay);
                pango_cairo_show_layout(cr, lay);
                ay += hs[li];
            }
            cairo_restore(cr);
        } else {
            char ini[8];
            const char *nm = tiles[i].is_pin && tiles[i].pin ? tiles[i].pin->label :
                             (c && c->title ? c->title : "?");
            snprintf(ini, sizeof ini, "%c", nm[0] ? nm[0] : '?');
            pango_layout_set_font_description(lay, desc_mark);
            pango_layout_set_text(lay, ini, -1);
            int tw = 0, th = 0;
            pango_layout_get_pixel_size(lay, &tw, &th);
            cairo_move_to(cr, cx - tw / 2.0, cy - th / 2.0);
            pango_cairo_show_layout(cr, lay);
        }
        cairo_restore(cr);

        if (running && c && !c->minimized) {
            cairo_set_source_rgb(cr, pink.r, pink.g, pink.b);
            cairo_arc(cr, cx, dot_y, M.dot_r, 0, 2 * M_PI);
            cairo_fill(cr);
        }

        if (hov) {
            char label[128];
            tile_label(wm, &tiles[i], label, sizeof label);
            pango_layout_set_font_description(lay, desc_lbl);
            pango_layout_set_ellipsize(lay, PANGO_ELLIPSIZE_END);
            pango_layout_set_width(lay, (M.tile_w + 24) * PANGO_SCALE);
            pango_layout_set_text(lay, label, -1);
            int tw = 0, th = 0;
            pango_layout_get_pixel_size(lay, &tw, &th);
            double lx = cx - tw / 2.0;
            if (lx < 2) lx = 2;
            if (lx + tw > want_w - 2) lx = want_w - 2 - tw;
            round_rect(cr, lx - 4, 2, tw + 8, th + 4, 6);
            cairo_set_source_rgb(cr, bg.r, bg.g, bg.b);
            cairo_fill_preserve(cr);
            cairo_set_source_rgba(cr, pink.r, pink.g, pink.b, 0.5);
            cairo_set_line_width(cr, 1.0);
            cairo_stroke(cr);
            cairo_set_source_rgb(cr, pink.r, pink.g, pink.b);
            cairo_move_to(cr, lx, 4);
            pango_cairo_show_layout(cr, lay);
            pango_layout_set_width(lay, -1);
            pango_layout_set_ellipsize(lay, PANGO_ELLIPSIZE_NONE);
        }
        x += M.tile_w + M.gap;
    }

    if (overflow > 0) {
        int cx = x + M.tile_w / 2;
        char buf[16];
        snprintf(buf, sizeof buf, "+%d", overflow);
        pango_layout_set_font_description(lay, desc_mark);
        pango_layout_set_text(lay, buf, -1);
        int tw = 0, th = 0;
        pango_layout_get_pixel_size(lay, &tw, &th);
        cairo_set_source_rgb(cr, muted.r, muted.g, muted.b);
        cairo_move_to(cr, cx - tw / 2, well_y + (M.well - th) / 2);
        pango_cairo_show_layout(cr, lay);
    }

    cairo_surface_flush(dock_surf);
    cairo_destroy(cr);
    pango_font_description_free(desc_art);
    pango_font_description_free(desc_mark);
    pango_font_description_free(desc_lbl);
    pango_font_description_free(desc_stat);
    pango_font_description_free(desc_foot);
    g_object_unref(lay);
    g_object_unref(ctx);
    XCopyArea(dpy, dock_pix, dock_w, dock_gc, 0, 0,
              (unsigned)want_w, (unsigned)want_h, 0, 0);
    if (first) {
        XMoveWindow(dpy, dock_w, px, dock_cur_y);
        XMapWindow(dpy, dock_w);
    }
    XFlush(dpy);
}

/* ── show / hide ─────────────────────────────────────────────────────────── */

static void dock_place(wm_t *wm)
{
    if (dock_w == None) return;
    Display *dpy = wm->dpy;
    XMoveWindow(dpy, dock_w, dock_x, dock_cur_y);
    XFlush(dpy);
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
    if (dock_w != None) XRaiseWindow(wm->dpy, dock_w);
    dock_refresh(wm);
}

void dock_scale_nudge(wm_t *wm, int dir)
{
    config_t *cfg = fae_cfg();
    double cur = cfg ? cfg->dock_scale : 1.0;
    double next = dock_scale_next(cur, dir);
    if (cfg) {
        cfg->dock_scale = next;
        config_save_dock_scale(next);
    }
    wmlog("dock scale %.2f", next);
    int was = dock_shown;
    dock_paint(wm);
    if (!was) dock_flash(wm);
}

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
            dock_install_cmap(wm->dpy);
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

void dock_tick(wm_t *wm)
{
    if (dock_w == None) return;
    long now = now_ms();

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
        double e = 1.0 - (1.0 - t) * (1.0 - t) * (1.0 - t);
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
    else if (dock_shown && stats_refresh(wm, 0)) dock_paint(wm);
}

void dock_click(wm_t *wm, int x_root, int y_root)
{
    if (dock_w == None) return;

    tile_t tiles[DOCK_TILES_MAX];
    int n = build_tiles(wm, tiles, DOCK_TILES_MAX);
    int shown = n;
    if (n > DOCK_MAX_TILES) shown = DOCK_MAX_TILES - 1;
    int i = hit_tile(x_root, y_root, shown);
    if (i < 0) return;

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
    tile_t tiles[DOCK_TILES_MAX];
    int n = build_tiles(wm, tiles, DOCK_TILES_MAX);
    int shown = n;
    if (n > DOCK_MAX_TILES) shown = DOCK_MAX_TILES - 1;
    int hit = hit_tile(x_root, y_root, shown);
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

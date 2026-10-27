/* dock_geom.h — hotspot / dwell / label clip. No X. */
#ifndef FAE_WM_DOCK_GEOM_H
#define FAE_WM_DOCK_GEOM_H

#include <stddef.h>
#include <string.h>

#define DOCK_EDGE_PX     8
#define DOCK_HOT_PAD     24
#define DOCK_HOT_FALLBACK 400
#define DOCK_LABEL_MAX   9

#define DOCK_SCALE_N 5
static const double DOCK_SCALES[DOCK_SCALE_N] = { 0.80, 1.00, 1.25, 1.50, 2.00 };

static int dock_scale_idx(double s)
{
    int best = 1; /* 1.00 */
    double bd = 1e9;
    for (int i = 0; i < DOCK_SCALE_N; i++) {
        double d = s - DOCK_SCALES[i];
        if (d < 0) d = -d;
        if (d < bd) { bd = d; best = i; }
    }
    return best;
}

static double dock_scale_snap(double s)
{
    return DOCK_SCALES[dock_scale_idx(s)];
}

/* dir > 0 bigger, dir < 0 smaller. dir == 0 snaps in place. */
static double dock_scale_next(double s, int dir)
{
    int i = dock_scale_idx(s);
    if (dir > 0) i++;
    else if (dir < 0) i--;
    if (i < 0) i = 0;
    if (i >= DOCK_SCALE_N) i = DOCK_SCALE_N - 1;
    return DOCK_SCALES[i];
}

typedef struct {
    int pad_x, pad_y, gap, tile_w, well, head, mag, lift;
    int art_pt, mark_pt, lbl_pt, status_pt, foot_pt;
    int status_h, foot_h, band_gap, dot_band;
    double well_rad, dot_r;
} dock_m_t;

static dock_m_t dock_metrics(double s)
{
    if (s < 0.5) s = 0.5;
    if (s > 2.5) s = 2.5;
    dock_m_t m;
    m.pad_x = (int)(14 * s + 0.5);
    m.pad_y = (int)(8 * s + 0.5);
    m.gap = (int)(6 * s + 0.5);
    m.tile_w = (int)(52 * s + 0.5);
    m.well = (int)(40 * s + 0.5);
    m.head = (int)(20 * s + 0.5);
    m.mag = (int)(10 * s + 0.5);
    m.lift = (int)(14 * s + 0.5);
    m.art_pt = (int)(8 * s + 0.5);
    m.mark_pt = (int)(16 * s + 0.5);
    m.lbl_pt = (int)(9 * s + 0.5);
    m.status_pt = (int)(9 * s + 0.5);
    m.foot_pt = (int)(8 * s + 0.5);
    m.status_h = (int)(14 * s + 0.5);
    m.foot_h = (int)(12 * s + 0.5);
    m.band_gap = (int)(6 * s + 0.5);
    m.dot_band = (int)(8 * s + 0.5);
    if (m.pad_x < 8) m.pad_x = 8;
    if (m.pad_y < 5) m.pad_y = 5;
    if (m.gap < 4) m.gap = 4;
    if (m.well < 24) m.well = 24;
    if (m.tile_w < m.well + 8) m.tile_w = m.well + 8;
    if (m.head < 14) m.head = 14;
    if (m.mag < 6) m.mag = 6;
    if (m.lift < 10) m.lift = 10;
    if (m.art_pt < 6) m.art_pt = 6;
    if (m.mark_pt < 8) m.mark_pt = 8;
    if (m.lbl_pt < 7) m.lbl_pt = 7;
    if (m.status_pt < 7) m.status_pt = 7;
    if (m.foot_pt < 6) m.foot_pt = 6;
    if (m.status_h < 12) m.status_h = 12;
    if (m.foot_h < 10) m.foot_h = 10;
    if (m.band_gap < 4) m.band_gap = 4;
    if (m.dot_band < 6) m.dot_band = 6;
    m.well_rad = m.well / 2.0; /* circle */
    m.dot_r = 1.7 * s;
    if (m.dot_r < 1.4) m.dot_r = 1.4;
    return m;
}

static int dock_row_start(int want_w, int n, const dock_m_t *m)
{
    int inner = n * m->tile_w + (n > 1 ? (n - 1) * m->gap : 0);
    int x = m->pad_x + (want_w - m->pad_x * 2 - inner) / 2;
    if (x < m->pad_x) x = m->pad_x;
    return x;
}

static int dock_want_w(int n_slots, const dock_m_t *m)
{
    if (n_slots < 1) n_slots = 1;
    return m->pad_x * 2 + n_slots * m->tile_w +
           (n_slots > 1 ? (n_slots - 1) * m->gap : 0);
}

static int dock_stadium_h(const dock_m_t *m)
{
    return m->pad_y + m->status_h + m->band_gap + m->well + m->band_gap
         + m->foot_h + m->dot_band + m->pad_y;
}

static int dock_want_h(const dock_m_t *m)
{
    return m->head + m->lift + dock_stadium_h(m);
}

/* Uniform scale so a w×h mark sits in the well with `pad` on each side. */
static double dock_sigil_fit(double well, double text_w, double text_h, double pad)
{
    double inner = well - 2.0 * pad;
    if (inner < 4.0) inner = 4.0;
    if (text_w < 1.0) text_w = 1.0;
    if (text_h < 1.0) text_h = 1.0;
    double sx = inner / text_w;
    double sy = inner / text_h;
    return sx < sy ? sx : sy;
}

static int dock_in_hotspot(int x, int y, int sw, int sh,
                           int dock_x, int dock_w, int edge_px, int center)
{
    if (sh <= 0 || y < sh - edge_px) return 0;
    if (!center) return 1;
    int x0, x1;
    if (dock_w > 0) {
        x0 = dock_x - DOCK_HOT_PAD;
        x1 = dock_x + dock_w + DOCK_HOT_PAD;
    } else {
        int band = DOCK_HOT_FALLBACK;
        if (band > sw) band = sw;
        x0 = sw / 2 - band / 2;
        x1 = x0 + band;
    }
    if (x0 < 0) x0 = 0;
    if (x1 > sw) x1 = sw;
    return x >= x0 && x < x1;
}

/* in_hot: pointer in the summon band. *entered is 0 when out.
 * Returns 1 once dwell_ms have passed while staying in. */
static int dock_dwell_ready(int in_hot, long now, long *entered, int dwell_ms)
{
    if (!in_hot) {
        *entered = 0;
        return 0;
    }
    if (*entered == 0) *entered = now;
    if (dwell_ms <= 0) return 1;
    return now - *entered >= dwell_ms;
}

/* t in [0,1] → scale 1.0 .. 1.18, ease-out quad. */
static double dock_hover_scale(double t)
{
    if (t < 0) t = 0;
    if (t > 1) t = 1;
    t = 1.0 - (1.0 - t) * (1.0 - t);
    return 1.0 + 0.18 * t;
}

static double dock_hover_lift_px(double t, double mag)
{
    if (t < 0) t = 0;
    if (t > 1) t = 1;
    t = 1.0 - (1.0 - t) * (1.0 - t);
    return -mag * t;
}

static void dock_short_label(char *dst, size_t n, const char *src)
{
    if (!dst || n == 0) return;
    dst[0] = 0;
    if (!src) return;
    while (*src == ' ' || *src == '\t') src++;
    size_t i = 0;
    for (; src[i] && src[i] != '\n' && src[i] != '\r' && i + 1 < n; i++) {
        if (i >= DOCK_LABEL_MAX) break;
        dst[i] = src[i];
    }
    if (src[i] && src[i] != '\n' && src[i] != '\r' && i >= DOCK_LABEL_MAX && n > 4) {
        dst[DOCK_LABEL_MAX - 1] = '.';
        dst[DOCK_LABEL_MAX - 2] = '.';
        dst[DOCK_LABEL_MAX - 3] = '.';
        i = DOCK_LABEL_MAX;
    }
    dst[i] = 0;
}

#endif /* FAE_WM_DOCK_GEOM_H */

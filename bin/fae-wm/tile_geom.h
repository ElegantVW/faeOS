/* tile_geom.h — split a work rect; lerp for tile animation. No X. */
#ifndef FAE_WM_TILE_GEOM_H
#define FAE_WM_TILE_GEOM_H

#define TILE_KEEP 0.62
#define TILE_MIN_W 420
#define TILE_MIN_H 280

static int tile_too_small(int w, int h)
{
    return w < TILE_MIN_W || h < TILE_MIN_H;
}

static double tile_ratio_clamp(double r)
{
    if (r < 0.15) return 0.15;
    if (r > 0.85) return 0.85;
    return r;
}

/* 0 = side by side, 1 = stacked. Wide cells split left/right. */
static int tile_auto_split(int w, int h)
{
    return (h > w) ? 1 : 0;
}

/* Last focus step: left/up → new leaf is a; else b (right/below/default). */
static int tile_new_is_b(int dx, int dy)
{
    if (dx < 0 || dy < 0) return 0;
    return 1;
}

static void tile_split_rect(int x, int y, int w, int h, int gap, int vert,
                            double ratio,
                            int *ax, int *ay, int *aw, int *ah,
                            int *bx, int *by, int *bw, int *bh)
{
    if (ratio < 0.15) ratio = 0.15;
    if (ratio > 0.85) ratio = 0.85;
    if (vert) {
        int ha = (int)((h - gap) * ratio);
        int hb = h - gap - ha;
        if (ha < 32) { ha = 32; hb = h - gap - ha; }
        if (hb < 32) { hb = 32; ha = h - gap - hb; }
        *ax = x; *ay = y; *aw = w; *ah = ha;
        *bx = x; *by = y + ha + gap; *bw = w; *bh = hb;
    } else {
        int wa = (int)((w - gap) * ratio);
        int wb = w - gap - wa;
        if (wa < 64) { wa = 64; wb = w - gap - wa; }
        if (wb < 64) { wb = 64; wa = w - gap - wb; }
        *ax = x; *ay = y; *aw = wa; *ah = h;
        *bx = x + wa + gap; *by = y; *bw = wb; *bh = h;
    }
}

static double tile_ease(double t)
{
    if (t < 0) t = 0;
    if (t > 1) t = 1;
    return 1.0 - (1.0 - t) * (1.0 - t) * (1.0 - t);
}

static int tile_lerp(int a, int b, double t)
{
    return a + (int)((b - a) * tile_ease(t) + (b >= a ? 0.5 : -0.5));
}

#endif

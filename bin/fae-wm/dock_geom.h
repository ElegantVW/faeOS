/* dock_geom.h — hotspot / dwell / label clip. No X. */
#ifndef FAE_WM_DOCK_GEOM_H
#define FAE_WM_DOCK_GEOM_H

#include <stddef.h>
#include <string.h>

#define DOCK_EDGE_PX     8
#define DOCK_HOT_PAD     24
#define DOCK_HOT_FALLBACK 400
#define DOCK_LABEL_MAX   9

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

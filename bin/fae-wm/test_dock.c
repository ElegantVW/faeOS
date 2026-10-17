/* test_dock.c — hotspot / dwell / labels. No X. */
#include "dock_geom.h"
#include "tile_geom.h"
#include <stdio.h>
#include <string.h>

static int fails;

static void ok(int cond, const char *msg)
{
    if (!cond) {
        fprintf(stderr, "FAIL %s\n", msg);
        fails++;
    }
}

int main(void)
{
    /* 1920×1080, dock 600 wide at x=660. Center hotspot misses the sides. */
    ok(!dock_in_hotspot(8, 1075, 1920, 1080, 660, 600, 8, 1),
       "center: left edge is not a summon");
    ok(!dock_in_hotspot(1910, 1075, 1920, 1080, 660, 600, 8, 1),
       "center: right edge is not a summon");
    ok(dock_in_hotspot(960, 1075, 1920, 1080, 660, 600, 8, 1),
       "center: middle of the dock band summons");
    ok(dock_in_hotspot(8, 1075, 1920, 1080, 660, 600, 8, 0),
       "full: left edge summons");
    ok(!dock_in_hotspot(960, 1000, 1920, 1080, 660, 600, 8, 1),
       "above the edge does not summon");

    long entered = 0;
    ok(!dock_dwell_ready(1, 100, &entered, 280), "100ms is not enough dwell");
    ok(entered == 100, "dwell start latched");
    ok(!dock_dwell_ready(1, 200, &entered, 280), "200ms still waiting");
    ok(dock_dwell_ready(1, 380, &entered, 280), "280ms in-band shows");
    ok(!dock_dwell_ready(0, 400, &entered, 280), "leaving resets");
    ok(entered == 0, "entered cleared on leave");

    char buf[32];
    dock_short_label(buf, sizeof buf, "Grok Build — a very long title\nmore");
    ok(strchr(buf, '\n') == NULL, "label has no newline");
    ok(strlen(buf) <= DOCK_LABEL_MAX, "label is clipped");
    ok(buf[0] == 'G', "label keeps the start");

    dock_short_label(buf, sizeof buf, "  Pixie");
    ok(!strcmp(buf, "Pixie"), "label strips and fits");

    ok(dock_hover_scale(0) > 0.99 && dock_hover_scale(0) < 1.01, "scale at rest is 1");
    ok(dock_hover_scale(1) > 1.21 && dock_hover_scale(1) < 1.23, "scale at 1 is 1.22");
    ok(dock_hover_scale(0.5) > 1.0 && dock_hover_scale(0.5) < 1.22, "scale eases in between");

    int ax, ay, aw, ah, bx, by, bw, bh;
    tile_split_rect(0, 0, 200, 100, 4, 0, 0.5, &ax, &ay, &aw, &ah, &bx, &by, &bw, &bh);
    ok(ax == 0 && ay == 0, "h-split a origin");
    ok(aw + 4 + bw == 200, "h-split widths plus gap");
    ok(ah == 100 && bh == 100, "h-split full height");
    tile_split_rect(0, 0, 100, 200, 4, 1, 0.5, &ax, &ay, &aw, &ah, &bx, &by, &bw, &bh);
    ok(ah + 4 + bh == 200, "v-split heights plus gap");
    ok(tile_lerp(0, 100, 0) == 0 && tile_lerp(0, 100, 1) == 100, "lerp ends");
    ok(tile_auto_split(800, 400) == 0, "wide cell splits side by side");
    ok(tile_auto_split(400, 800) == 1, "tall cell splits stacked");
    ok(tile_new_is_b(1, 0) == 1, "walked right → new is b");
    ok(tile_new_is_b(-1, 0) == 0, "walked left → new is a");
    ok(tile_new_is_b(0, -1) == 0, "walked up → new is a");
    ok(TILE_KEEP > 0.5 && TILE_KEEP < 0.7, "focus keeps the larger share");
    ok(tile_too_small(200, 800) == 1, "narrow cell is too small to slice");
    ok(tile_too_small(800, 200) == 1, "short cell is too small to slice");
    ok(tile_too_small(800, 600) == 0, "roomy cell may split");
    ok(tile_ratio_clamp(0.01) >= 0.15 && tile_ratio_clamp(0.99) <= 0.85,
       "ratio stays in bounds");

    if (fails) {
        fprintf(stderr, "%d fail(s)\n", fails);
        return 1;
    }
    puts("test_dock ok");
    return 0;
}

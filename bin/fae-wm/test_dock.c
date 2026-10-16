/* test_dock.c — hotspot / dwell / labels. No X. */
#include "dock_geom.h"
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

    if (fails) {
        fprintf(stderr, "%d fail(s)\n", fails);
        return 1;
    }
    puts("test_dock ok");
    return 0;
}

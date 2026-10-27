/* test_dock.c — hotspot / dwell / labels. No X. */
#include "dock_geom.h"
#include "tile_geom.h"
#include "takeover.h"
#include "launch_geom.h"
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
    ok(dock_hover_scale(1) > 1.17 && dock_hover_scale(1) < 1.19, "scale at 1 is 1.18");
    ok(dock_hover_scale(0.5) > 1.0 && dock_hover_scale(0.5) < 1.18, "scale eases in between");
    ok(dock_hover_lift_px(0, 14) > -0.01 && dock_hover_lift_px(0, 14) < 0.01, "lift at rest is 0");
    ok(dock_hover_lift_px(1, 14) < -13.9 && dock_hover_lift_px(1, 14) > -14.1, "lift at 1 is -14");

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

    ok(dock_scale_snap(1.0) > 0.99 && dock_scale_snap(1.0) < 1.01, "scale 1 snaps to 1");
    ok(dock_scale_next(1.0, 1) > 1.24 && dock_scale_next(1.0, 1) < 1.26, "up from 1 is 1.25");
    ok(dock_scale_next(1.0, -1) > 0.79 && dock_scale_next(1.0, -1) < 0.81, "down from 1 is 0.80");
    ok(dock_scale_next(0.80, -1) > 0.79 && dock_scale_next(0.80, -1) < 0.81, "scale floor is 0.80");
    ok(dock_scale_next(2.00, 1) > 1.99 && dock_scale_next(2.00, 1) < 2.01, "scale ceiling is 2.00");
    ok(dock_scale_snap(1.1) > 0.99 && dock_scale_snap(1.1) < 1.01, "1.1 snaps to 1.00");
    dock_m_t m1 = dock_metrics(1.0);
    dock_m_t m2 = dock_metrics(2.0);
    ok(m1.tile_w == 52 && m1.well == 40, "scale 1 tile is 52, well 40");
    ok(m2.tile_w == 104 && m2.well == 80, "scale 2 doubles the tile");
    ok(m1.well_rad > 19.9 && m1.well_rad < 20.1, "well is a circle");
    ok(dock_want_w(7, &m1) == 14 * 2 + 7 * 52 + 6 * 6, "width follows icons, not a title");
    ok(dock_want_w(3, &m1) < dock_want_w(7, &m1), "fewer tiles, narrower shelf");
    ok(dock_row_start(dock_want_w(3, &m1), 3, &m1) == m1.pad_x, "three tiles fill the shelf");
    ok(dock_want_h(&m1) > m1.well + m1.head + m1.status_h, "height includes well, head, status");
    ok(dock_stadium_h(&m1) > m1.well + m1.status_h + m1.foot_h, "stadium holds status+wells+footer");
    {
        double fit = dock_sigil_fit(40, 35, 63, 4);
        ok(fit > 0.40 && fit < 0.55, "7-line star fits in a 40px well");
    }

    ok(size_is_takeover(1920, 1080, 1920, 1080), "exact monitor is takeover");
    ok(size_is_takeover(1920, 1080, 1912, 1080), "32px slack is takeover");
    ok(!size_is_takeover(1920, 1080, 1280, 720), "720p on 1080p is not takeover");
    ok(size_is_large(1920, 1080, 1280, 720), "720p is large on 1080p");
    ok(size_is_large(1920, 1080, 1280, 800), "Steam Big Picture 1280x800 is large");
    ok(!size_is_takeover(1920, 1080, 1280, 800), "BP is not monitor-sized");
    ok(!size_is_large(1920, 1080, 800, 600), "kitty default is not large");
    ok(class_is_takeover("steam"), "steam class is takeover host");
    ok(class_is_takeover("Steam"), "steam class is case-insensitive");
    ok(class_is_takeover("steam_app_637650"), "steam_app is takeover");
    ok(class_is_game("steam_app_637650"), "steam_app is a game");
    ok(!class_is_game("steam"), "steam client is not a game class");
    ok(class_is_takeover("wine"), "wine is takeover host");
    ok(class_is_takeover("explorer.exe"), "explorer.exe is takeover host");
    ok(!class_is_takeover("kitty"), "kitty is not takeover");
    ok(!class_is_takeover("zen-browser"), "zen is not takeover");
    ok(!class_is_takeover(""), "empty class is not takeover");

    {
        char name[LAUNCH_NAME_MAX], exec[LAUNCH_EXEC_MAX];
        int term = 0;
        const char *desk =
            "[Desktop Entry]\n"
            "Type=Application\n"
            "Name=Kitty\n"
            "Exec=kitty %u\n";
        ok(launch_parse_desktop(desk, name, sizeof name, exec, sizeof exec, &term),
           "parses a desktop file");
        ok(!strcmp(name, "Kitty"), "desktop Name");
        ok(!strcmp(exec, "kitty"), "field codes stripped");
        ok(!term, "Terminal unset");
    }
    {
        char name[LAUNCH_NAME_MAX], exec[LAUNCH_EXEC_MAX];
        int term = 0;
        const char *rev =
            "[Desktop Entry]\nExec=revapp %F\nName=Rev\nType=Application\n";
        ok(launch_parse_desktop(rev, name, sizeof name, exec, sizeof exec, &term),
           "Exec before Name still parses");
        ok(!strcmp(name, "Rev") && !strcmp(exec, "revapp"), "order-independent keys");
    }
    {
        char name[LAUNCH_NAME_MAX], exec[LAUNCH_EXEC_MAX];
        int term = 0;
        const char *hid =
            "[Desktop Entry]\nName=Hidden\nExec=x\nHidden=true\n";
        ok(!launch_parse_desktop(hid, name, sizeof name, exec, sizeof exec, &term),
           "Hidden=true is skipped");
    }
    {
        char name[LAUNCH_NAME_MAX], exec[LAUNCH_EXEC_MAX];
        int term = 0;
        const char *nd =
            "[Desktop Entry]\nName=Quiet\nExec=x\nNoDisplay=true\n";
        ok(!launch_parse_desktop(nd, name, sizeof name, exec, sizeof exec, &term),
           "NoDisplay=true is skipped");
    }
    {
        char name[LAUNCH_NAME_MAX], exec[LAUNCH_EXEC_MAX];
        int term = 0;
        const char *termdesk =
            "[Desktop Entry]\nName=Top\nExec=htop\nTerminal=true\n";
        ok(launch_parse_desktop(termdesk, name, sizeof name, exec, sizeof exec, &term),
           "terminal app parses");
        ok(term, "Terminal=true");
        ok(!strcmp(exec, "htop"), "terminal Exec kept");
    }
    {
        char e[64];
        snprintf(e, sizeof e, "steam %%U");
        /* strip on a copy that still has the percent — parser already stripped.
         * Direct strip: */
        strcpy(e, "foo %f %u bar");
        launch_strip_field_codes(e);
        ok(!strcmp(e, "foo bar"), "field codes drop and spaces collapse");
    }
    ok(launch_match("Kitty", "kitty", ""), "empty query matches");
    ok(launch_match("Steam", "/usr/bin/steam", "ste"), "fuzzy name");
    ok(launch_match("Kitty", "kitty", "KIT"), "fuzzy is case-insensitive");
    ok(!launch_match("Kitty", "kitty", "steam"), "miss does not match");

    if (fails) {
        fprintf(stderr, "%d fail(s)\n", fails);
        return 1;
    }
    puts("test_dock ok");
    return 0;
}

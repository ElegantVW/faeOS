/* takeover.h — who owns the glass. No X. */
#ifndef FAE_WM_TAKEOVER_H
#define FAE_WM_TAKEOVER_H

#include <stddef.h>

#define TAKEOVER_SLACK 32
#define TAKEOVER_LARGE_PCT 65

static int takeover_abs(int v)
{
    return v < 0 ? -v : v;
}

/* Monitor-sized: Big Picture, a game that already asked for the screen. */
static int size_is_takeover(int sw, int sh, int w, int h)
{
    if (sw <= 0 || sh <= 0 || w <= 0 || h <= 0) return 0;
    return takeover_abs(w - sw) <= TAKEOVER_SLACK &&
           takeover_abs(h - sh) <= TAKEOVER_SLACK;
}

/* Steam Big Picture maps at 1280×800, not 1920×1080. 65% catches that
 * without swallowing a kitty or a friends-list popup. */
static int size_is_large(int sw, int sh, int w, int h)
{
    if (sw <= 0 || sh <= 0 || w <= 0 || h <= 0) return 0;
    return w * 100 >= sw * TAKEOVER_LARGE_PCT &&
           h * 100 >= sh * TAKEOVER_LARGE_PCT;
}

static int takeover_eq(const char *a, const char *b)
{
    if (!a || !b) return 0;
    while (*a && *b) {
        char ca = *a, cb = *b;
        if (ca >= 'A' && ca <= 'Z') ca = (char)(ca - 'A' + 'a');
        if (cb >= 'A' && cb <= 'Z') cb = (char)(cb - 'A' + 'a');
        if (ca != cb) return 0;
        a++;
        b++;
    }
    return *a == 0 && *b == 0;
}

static int takeover_pref(const char *s, const char *p)
{
    if (!s || !p) return 0;
    while (*p) {
        char cs = *s, cp = *p;
        if (!cs) return 0;
        if (cs >= 'A' && cs <= 'Z') cs = (char)(cs - 'A' + 'a');
        if (cp >= 'A' && cp <= 'Z') cp = (char)(cp - 'A' + 'a');
        if (cs != cp) return 0;
        s++;
        p++;
    }
    return 1;
}

/* One WM_CLASS token: steam_app_* always; steam/wine hosts for size/desk rules. */
static int class_is_game(const char *cls)
{
    return takeover_pref(cls, "steam_app_");
}

static int class_is_takeover(const char *cls)
{
    if (!cls || !*cls) return 0;
    if (class_is_game(cls)) return 1;
    if (takeover_eq(cls, "steam")) return 1;
    if (takeover_eq(cls, "steamwebhelper")) return 1;
    if (takeover_eq(cls, "wine")) return 1;
    if (takeover_eq(cls, "explorer.exe")) return 1;
    return 0;
}

#endif

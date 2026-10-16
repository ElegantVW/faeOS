/* config.c — tiny line config. `key value`, `bind Mod+Shift+x action arg...`,
 * `exec <command>`, `# comments`. Unknown lines are ignored, not fatal. */
#include "config.h"
#include "theme.h"

#include <ctype.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include <X11/Xlib.h>
#include <X11/keysym.h>

static unsigned parse_mod(const char *s)
{
    unsigned m = 0;
    char tmp[128];
    snprintf(tmp, sizeof tmp, "%s", s);
    for (char *tok = strtok(tmp, "+"); tok; tok = strtok(NULL, "+")) {
        if (!strcasecmp(tok, "Mod1") || !strcasecmp(tok, "Alt")) m |= Mod1Mask;
        else if (!strcasecmp(tok, "Mod4") || !strcasecmp(tok, "Super")) m |= Mod4Mask;
        else if (!strcasecmp(tok, "Shift")) m |= ShiftMask;
        else if (!strcasecmp(tok, "Ctrl") || !strcasecmp(tok, "Control")) m |= ControlMask;
        else return 0; /* not a modifier: must be the key */
    }
    return m;
}

/* Split "Mod4+Shift+q" into mask + keysym name. Returns keysym or NoSymbol. */
static unsigned split_bind(const char *s, unsigned *mod)
{
    /* key is after the last '+' unless the key itself is named with one
     * (none are), so: everything up to the last '+' is modifiers. */
    const char *plus = strrchr(s, '+');
    char mods[128] = { 0 }, key[64] = { 0 };
    if (plus) {
        size_t n = (size_t)(plus - s);
        if (n >= sizeof mods) n = sizeof mods - 1;
        memcpy(mods, s, n);
        snprintf(key, sizeof key, "%s", plus + 1);
    } else {
        snprintf(key, sizeof key, "%s", s);
    }
    *mod = parse_mod(mods);
    if (plus && *mod == 0) return NoSymbol;
    return XStringToKeysym(key);
}

static void add_bind(config_t *c, unsigned mod, unsigned ks, action_t act,
                     const char *arg)
{
    bind_t *nb = realloc(c->binds, (size_t)(c->nbinds + 1) * sizeof(bind_t));
    if (!nb) return;
    c->binds = nb;
    bind_t *b = &c->binds[c->nbinds++];
    b->mod = mod;
    b->keysym = ks;
    b->act = act;
    b->arg = arg && *arg ? strdup(arg) : NULL;
}

static void add_pin(config_t *c, const char *label, const char *cmd,
                    const char *match)
{
    pin_t *np = realloc(c->pins, (size_t)(c->npins + 1) * sizeof(pin_t));
    if (!np) return;
    c->pins = np;
    pin_t *p = &c->pins[c->npins++];
    p->label = strdup(label ? label : "?");
    p->cmd = strdup(cmd ? cmd : "");
    p->match = strdup(match ? match : "");
    for (char *s = p->match; *s; s++)
        if (*s >= 'A' && *s <= 'Z') *s += 32;
    p->pid = 0;
}

/* Starter pins: everyday apps. Config `pin` lines append. kur is a stub
 * until it grows its own TUI (separate project). */
static void default_pins(config_t *c)
{
    struct { const char *label, *cmd, *match; } d[] = {
        { "Opencode", "kitty opencode", "opencode" },
        { "Grok", "kitty grok", "grok" },
        { "Zen", "zen-browser", "navigator" },
        { "Magpie", "kitty magpie", "magpie" },
        { "Pixie", "kitty pixie", "pixie" },
        { "Kur", "kitty kur", "kur" },
        { "Imp", "imp", "imp" },
    };
    for (unsigned i = 0; i < sizeof d / sizeof d[0]; i++)
        add_pin(c, d[i].label, d[i].cmd, d[i].match);
}

static void add_auto(config_t *c, const char *cmd)
{
    char **na = realloc(c->autostart,
                        (size_t)(c->nauto + 1) * sizeof(char *));
    if (!na) return;
    c->autostart = na;
    c->autostart[c->nauto++] = strdup(cmd);
}

static action_t action_of(const char *s)
{
    static const struct { const char *name; action_t act; } tab[] = {
        { "exec", ACT_EXEC }, { "close", ACT_CLOSE },
        { "fullscreen", ACT_FULLSCREEN }, { "maximize", ACT_MAXIMIZE },
        { "minimize", ACT_MINIMIZE }, { "focus", ACT_FOCUS },
        { "move", ACT_NUDGE }, { "workspace", ACT_WORKSPACE },
        { "toworkspace", ACT_TOWORKSPACE }, { "resize-mode", ACT_RESIZE_MODE },
        { "preset", ACT_PRESET }, { "reload", ACT_RELOAD },
        { "quit", ACT_QUIT },
    };
    for (unsigned i = 0; i < sizeof tab / sizeof tab[0]; i++)
        if (!strcmp(s, tab[i].name)) return tab[i].act;
    return ACT_EXEC; /* unknown action word: never happens (checked first) */
}

static int is_action(const char *s)
{
    static const char *names[] = { "exec", "close", "fullscreen", "maximize",
        "minimize", "focus",
        "move", "workspace", "toworkspace", "resize-mode", "preset",
        "reload", "quit", NULL };
    for (int i = 0; names[i]; i++) if (!strcmp(s, names[i])) return 1;
    return 0;
}

/* Built-in defaults: the house i3 bindings, translated. */
static void defaults(config_t *c)
{
    struct { const char *keys, *act, *arg; } d[] = {
        { "Mod4+Return", "exec", "kitty" },
        { "Mod4+d", "exec", "rofi -show drun" },
        { "Mod4+z", "exec", "rofi -show run" },
        { "Mod4+Shift+q", "close", "" },
        { "Mod4+f", "fullscreen", "" },
        { "Mod4+Shift+f", "maximize", "" },
        { "Mod4+m", "minimize", "" },
        { "Mod4+j", "focus", "left" },
        { "Mod4+k", "focus", "down" },
        { "Mod4+l", "focus", "up" },
        { "Mod4+semicolon", "focus", "right" },
        { "Mod4+Left", "focus", "left" },
        { "Mod4+Down", "focus", "down" },
        { "Mod4+Up", "focus", "up" },
        { "Mod4+Right", "focus", "right" },
        { "Mod4+Shift+j", "move", "left" },
        { "Mod4+Shift+k", "move", "down" },
        { "Mod4+Shift+l", "move", "up" },
        { "Mod4+Shift+semicolon", "move", "right" },
        { "Mod4+r", "resize-mode", "" },
        { "Mod4+Ctrl+Left", "preset", "left" },
        { "Mod4+Ctrl+Right", "preset", "right" },
        { "Mod4+Ctrl+Up", "preset", "top" },
        { "Mod4+Ctrl+Down", "preset", "center" },
        { "Mod4+1", "workspace", "1" },
        { "Mod4+2", "workspace", "2" },
        { "Mod4+3", "workspace", "3" },
        { "Mod4+4", "workspace", "4" },
        { "Mod4+5", "workspace", "5" },
        { "Mod4+6", "workspace", "6" },
        { "Mod4+7", "workspace", "7" },
        { "Mod4+8", "workspace", "8" },
        { "Mod4+9", "workspace", "9" },
        { "Mod4+0", "workspace", "10" },
        { "Mod4+Shift+1", "toworkspace", "1" },
        { "Mod4+Shift+2", "toworkspace", "2" },
        { "Mod4+Shift+3", "toworkspace", "3" },
        { "Mod4+Shift+4", "toworkspace", "4" },
        { "Mod4+Shift+5", "toworkspace", "5" },
        { "Mod4+Shift+6", "toworkspace", "6" },
        { "Mod4+Shift+7", "toworkspace", "7" },
        { "Mod4+Shift+8", "toworkspace", "8" },
        { "Mod4+Shift+9", "toworkspace", "9" },
        { "Mod4+Shift+0", "toworkspace", "10" },
        { "Mod4+Shift+c", "reload", "" },
        { "Mod4+Shift+e", "quit", "" },
    };
    for (unsigned i = 0; i < sizeof d / sizeof d[0]; i++) {
        unsigned mod = 0;
        unsigned ks = split_bind(d[i].keys, &mod);
        if (ks != NoSymbol) add_bind(c, mod, ks, action_of(d[i].act), d[i].arg);
    }
    add_auto(c, "picom --config ~/.config/picom/picom.conf");
    add_auto(c, "feh --bg-fill ~/Pictures/wall.png");
    default_pins(c);
}

int config_load(config_t *c, const char **errpath)
{
    memset(c, 0, sizeof *c);
    c->gap_outer = WM_GAP_OUTER;
    c->border_w = WM_BORDER_W;
    c->focus_follows_mouse = 1;
    c->dock_dwell = 280;
    c->dock_hotspot_center = 1;
    snprintf(c->color_focus, sizeof c->color_focus, "#e879a0");
    snprintf(c->color_unfocus, sizeof c->color_unfocus, "#9d5c75");
    defaults(c);

    const char *env = getenv("FAE_WM_CONFIG");
    char home_path[1024] = { 0 };
    const char *path = env;
    if (!path || !*path) {
        const char *home = getenv("HOME");
        if (!home) return 0;
        snprintf(home_path, sizeof home_path, "%s/.config/fae-wm/config", home);
        path = home_path;
    }
    FILE *f = fopen(path, "r");
    if (!f) return 0;   /* missing file is fine: defaults stand */
    if (errpath) *errpath = path;

    char line[1024];
    while (fgets(line, sizeof line, f)) {
        char *s = line;
        while (*s && isspace((unsigned char)*s)) s++;
        if (!*s || *s == '#') continue;
        char *nl = strchr(s, '\n');
        if (nl) *nl = 0;
        char *key = strtok(s, " \t");
        if (!key) continue;
        if (!strcmp(key, "bind")) {
            char *keys = strtok(NULL, " \t");
            char *act = strtok(NULL, " \t");
            char *arg = strtok(NULL, "");
            if (!keys || !act || !is_action(act)) continue;
            unsigned mod = 0;
            unsigned ks = split_bind(keys, &mod);
            if (ks == NoSymbol) continue;
            if (arg) { while (*arg && isspace((unsigned char)*arg)) arg++; }
            add_bind(c, mod, ks, action_of(act), arg ? arg : "");
        } else if (!strcmp(key, "exec")) {
            char *cmd = strtok(NULL, "");
            if (cmd) {
                while (*cmd && isspace((unsigned char)*cmd)) cmd++;
                if (*cmd) add_auto(c, cmd);
            }
        } else if (!strcmp(key, "pin")) {
            /* pin Label command... [match=substr] */
            char *label = strtok(NULL, " \t");
            char *rest = strtok(NULL, "");
            if (label && rest) {
                while (*rest && isspace((unsigned char)*rest)) rest++;
                char match[128] = { 0 };
                char *mp = strstr(rest, "match=");
                char cmd[768] = { 0 };
                if (mp) {
                    size_t n = (size_t)(mp - rest);
                    if (n >= sizeof cmd) n = sizeof cmd - 1;
                    memcpy(cmd, rest, n);
                    while (n > 0 && isspace((unsigned char)cmd[n - 1])) n--;
                    cmd[n] = 0;
                    snprintf(match, sizeof match, "%s", mp + 6);
                } else {
                    snprintf(cmd, sizeof cmd, "%s", rest);
                    snprintf(match, sizeof match, "%s", label);
                }
                if (*cmd) add_pin(c, label, cmd, match);
            }
        } else if (!strcmp(key, "gap")) {
            char *v = strtok(NULL, " \t");
            if (v) c->gap_outer = atoi(v);
        } else if (!strcmp(key, "border")) {
            char *v = strtok(NULL, " \t");
            if (v) c->border_w = atoi(v);
        } else if (!strcmp(key, "focus_follows_mouse")) {
            char *v = strtok(NULL, " \t");
            if (v) c->focus_follows_mouse =
                (!strcasecmp(v, "yes") || !strcmp(v, "1"));
        } else if (!strcmp(key, "color_focus")) {
            char *v = strtok(NULL, " \t");
            if (v) snprintf(c->color_focus, sizeof c->color_focus, "%s", v);
        } else if (!strcmp(key, "color_unfocus")) {
            char *v = strtok(NULL, " \t");
            if (v) snprintf(c->color_unfocus, sizeof c->color_unfocus, "%s", v);
        } else if (!strcmp(key, "dock_dwell")) {
            char *v = strtok(NULL, " \t");
            if (v) c->dock_dwell = atoi(v);
        } else if (!strcmp(key, "dock_hotspot")) {
            char *v = strtok(NULL, " \t");
            if (v)
                c->dock_hotspot_center = strcasecmp(v, "full") != 0;
        }
    }
    fclose(f);
    return 0;
}

void config_free(config_t *c)
{
    for (int i = 0; i < c->nbinds; i++) free(c->binds[i].arg);
    free(c->binds);
    for (int i = 0; i < c->nauto; i++) free(c->autostart[i]);
    free(c->autostart);
    for (int i = 0; i < c->npins; i++) {
        free(c->pins[i].label);
        free(c->pins[i].cmd);
        free(c->pins[i].match);
    }
    free(c->pins);
    memset(c, 0, sizeof *c);
}

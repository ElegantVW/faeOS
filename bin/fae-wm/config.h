/* config.h — one small config file. Values first, binds after. */
#ifndef FAE_WM_CONFIG_H
#define FAE_WM_CONFIG_H

typedef enum {
    ACT_EXEC, ACT_CLOSE, ACT_FULLSCREEN, ACT_MAXIMIZE, ACT_MINIMIZE,
    ACT_FOCUS, ACT_NUDGE,
    ACT_WORKSPACE, ACT_TOWORKSPACE, ACT_RESIZE_MODE, ACT_PRESET,
    ACT_RELOAD, ACT_QUIT, ACT_HELP, ACT_SPLIT, ACT_FLOAT
} action_t;

typedef struct {
    unsigned mod;     /* X modifier mask */
    unsigned keysym;  /* XK_* */
    action_t act;
    char    *arg;     /* exec command / focus dir / preset name / ws number */
} bind_t;

typedef struct {
    char *label;
    char *cmd;
    char *match;    /* substring match vs title/class (lowercased both) */
    int   pid;      /* last launched pid, 0 when unknown */
} pin_t;

typedef struct {
    int   gap_outer;
    int   border_w;
    int   focus_follows_mouse; /* i3 default was yes; hover focuses */
    int   dock_dwell;          /* ms in the hotspot before the dock rises */
    int   dock_hotspot_center; /* 1 = bottom-center band, 0 = full bottom edge */
    char  color_focus[16];
    char  color_unfocus[16];
    pin_t *pins;
    int    npins;
    bind_t *binds;
    int     nbinds;
    char  **autostart;
    int     nauto;
} config_t;

/* Path searched: $FAE_WM_CONFIG, else ~/.config/fae-wm/config. Missing file
 * is fine — defaults mirror the house i3 setup. Returns 0 on ok. */
int  config_load(config_t *c, const char **errpath);
void config_free(config_t *c);

#endif /* FAE_WM_CONFIG_H */

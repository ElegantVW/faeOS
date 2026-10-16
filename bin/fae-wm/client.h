/* client.h — managed windows. Border-only frames: no frame windows, the
 * border is drawn on the client itself. Floating everywhere. */
#ifndef FAE_WM_CLIENT_H
#define FAE_WM_CLIENT_H

#include <X11/Xlib.h>
#include "ewmh.h"

#define WM_NDESKS 10
#define WM_STACK_MAX 256

typedef struct client {
    Window xid;
    Window frame;        /* titlebar frame (ours); None when bare */
    char  *title;
    int    x, y, w, h;       /* client area geometry */
    int    desk;             /* 0-based workspace */
    int    fullscreen;
    int    maximized;
    int    minimized;
    int    floated;          /* out of the tile tree */
    int    above;            /* docks/panels: never lowered */
    int    tx, ty, tw, th;   /* tile goal */
    int    ax, ay, aw, ah;   /* tile anim from */
    long   anim_t0;
    int    ignore_unmap;     /* set when WE unmap (workspace switch) */
    int    pressed_btn;      /* armed titlebar button (frame.h btn_t) */
    int    hover_btn;
    int    sx, sy, sw, sh;   /* saved geometry for fullscreen/max exit */
    struct client *next;     /* focus order, most-recent-first */
} client_t;

typedef struct {
    Display *dpy;
    int      scr;
    Window   root;
    int      sw, sh;         /* screen size */
    client_t *clients;       /* focus order, most-recent-first */
    client_t *focus;         /* focused client, may be NULL */
    int      cur_desk;
    int      border_w, gap;
    unsigned long col_focus, col_unfocus;
    atoms_t  atoms;
    Window   stack[WM_STACK_MAX]; /* bottom-to-top for EWMH */
    int      nstack;
    int      cascade_n;
} wm_t;

void client_manage(wm_t *wm, Window xid);   /* adopt + place + focus */
void client_unmanage(wm_t *wm, Window xid); /* forget (window already gone) */
client_t *client_find(wm_t *wm, Window xid);
void client_colors(wm_t *wm, const char *focus, const char *unfocus);
/* Resolve any descendant to its managed client: walks up to the root's
 * direct child, then matches frames and clients. Real toolkits (Zen!)
 * nest widgets deep; the event subwindow is rarely the frame itself. */
client_t *client_resolve(wm_t *wm, Window xid);

void client_focus(wm_t *wm, client_t *c);    /* focus + raise + borders + EWMH */
void client_hover(wm_t *wm, client_t *c);    /* focus only: no raise, no reorder */
void client_show_desk(wm_t *wm, int desk);  /* switch workspace */
void client_to_desk(wm_t *wm, client_t *c, int desk);
void client_toggle_full(wm_t *wm, client_t *c);
void client_toggle_max(wm_t *wm, client_t *c);   /* gaps-aware maximize */
void client_minimize(wm_t *wm, client_t *c);
void client_unminimize(wm_t *wm, client_t *c);   /* map + focus */
void client_close(wm_t *wm, client_t *c);   /* WM_DELETE or kill */
void client_nudge(wm_t *wm, client_t *c, int dx, int dy);
void client_focus_dir(wm_t *wm, int dx, int dy); /* nearest in direction */
void client_preset(wm_t *wm, client_t *c, const char *which);
client_t *client_at(wm_t *wm, int desk, int idx); /* visible list order */

/* stacking bottom-to-top for _NET_CLIENT_LIST_STACKING */
int  client_stack(wm_t *wm, Window *out, int max);

#endif /* FAE_WM_CLIENT_H */

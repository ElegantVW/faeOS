/* list.h — the window list. Read-only EWMH; owns the MRU ring file. */
#ifndef FAE_HUD_LIST_H
#define FAE_HUD_LIST_H

#include <X11/Xlib.h>

#ifndef MRU_MAX
#define MRU_MAX 128
#endif

typedef struct {
    Window xid;
    char  *title;
} win_t;

typedef struct {
    win_t *v;
    int    n;
} winlist_t;

/* Windows on the current workspace (or all), rotated so the focused window
 * is index 0. Titles only — no icons, no classes. Caller frees with
 * list_free(). Empty (n==0) when X has nothing to say. */
winlist_t *list_windows(Display *dpy, Window root, Window focus, int all_ws);
void       list_free(winlist_t *l);
Window     list_active(Display *dpy, Window root);

/* MRU ring file: most-recent-first hex xids. Prunes dead ids, keeps every
 * survivor in its slot, appends the new. Never move-to-front: that toggles
 * between two windows instead of walking. */
const char *mru_path(void);
int         mru_load(Window *out, int max);
void        mru_note(const Window *live, int nlive);

#endif /* FAE_HUD_LIST_H */

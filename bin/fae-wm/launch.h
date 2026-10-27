#ifndef FAE_WM_LAUNCH_H
#define FAE_WM_LAUNCH_H

#include "client.h"

void launch_toggle(wm_t *wm);
void launch_hide(wm_t *wm);
int  launch_visible(void);
int  launch_is_win(Window w);
void launch_expose(wm_t *wm);
void launch_tick(wm_t *wm);
void launch_on_key(wm_t *wm, XKeyEvent *ev);

#endif

#ifndef FAE_WM_HELP_H
#define FAE_WM_HELP_H

#include "client.h"

void help_toggle(wm_t *wm);
void help_hide(wm_t *wm);
int  help_visible(void);
int  help_is_win(Window w);
void help_expose(wm_t *wm);

#endif

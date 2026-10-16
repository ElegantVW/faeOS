/* wm.h — the event loop: grabs, dispatch, drag, resize mode, Alt+Tab. */
#ifndef FAE_WM_H
#define FAE_WM_H

#include "client.h"
#include "config.h"

/* Run the window manager. Only returns on quit (or fatal X loss). */
int wm_run(Display *dpy, int scr, config_t *cfg);

/* Live config for dock pins. */
config_t *fae_cfg(void);
/* Spawn a command, returning the child pid (or -1). */
pid_t spawn_cmd(const char *cmd);

/* Always-on audit log (XDG_RUNTIME_DIR/fae-wm.log, fae-cycle style). */
void wmlog_open(void);
void wmlog(const char *fmt, ...);

#endif /* FAE_WM_H */

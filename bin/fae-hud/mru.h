/* mru.h — our own recency list.
 *
 * Why this exists: `_NET_CLIENT_LIST_STACKING` is NOT most-recently-used. It
 * was measured on this machine by focusing the bottom-most window in the
 * stack and reading the property again — the order came back byte-for-byte
 * identical. So cycling off it walks a fixed ring, which is why the switcher
 * felt broken even when it had something to switch to.
 *
 * We keep our own list: one hex X window id per line, most-recent-first.
 * `mru_note()` rewrites it on every commit, dropping ids that no longer
 * exist, so it cannot accumulate garbage.
 *
 * The honest limit: this only records focus changes *we* make. If you click
 * into a terminal with the mouse, the currently focused window is still right
 * — that is read fresh from _NET_ACTIVE_WINDOW every time — but the tail of
 * the list does not learn about it. Only i3's own tree order would fix that,
 * and asking i3 is exactly the coupling this program does not have.
 */
#ifndef FAE_HUD_MRU_H
#define FAE_HUD_MRU_H

#include <X11/Xlib.h>

#ifndef MRU_MAX
#define MRU_MAX 128
#endif

const char *mru_path(void);

/* Most-recent-first, into out[]. Returns how many. */
int  mru_load(Window *out, int max);

/* Prune dead ids, keep the order of the rest, append anything live that is new.
 * Maintains a stable ring so Alt+Tab walks instead of toggling. */
void mru_note(const Window *live, int nlive);

#endif /* FAE_HUD_MRU_H */

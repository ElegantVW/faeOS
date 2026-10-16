/* tile.h — per-workspace binary split tree. */
#ifndef FAE_WM_TILE_H
#define FAE_WM_TILE_H

#include "client.h"

void tile_insert(wm_t *wm, client_t *c);
void tile_remove(wm_t *wm, client_t *c);
void tile_retile(wm_t *wm);
void tile_tick(wm_t *wm);
void tile_set_split(int vert);          /* one-shot: 0 side by side, 1 stacked */
void tile_note_focus_dir(int dx, int dy);
void tile_toggle_float(wm_t *wm, client_t *c);
void tile_swap_dir(wm_t *wm, client_t *c, int dx, int dy);
int  tile_desk_fullscreen(wm_t *wm);

#endif

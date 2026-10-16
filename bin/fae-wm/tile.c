/* tile.c — binary split tree per workspace. */
#include "tile.h"
#include "tile_geom.h"
#include "frame.h"
#include "theme.h"
#include "wm.h"

#include <stdlib.h>
#include <string.h>
#include <X11/Xlib.h>
#include <X11/Xutil.h>

#define TILE_MS 180

typedef struct tnode tnode_t;
struct tnode {
    tnode_t *parent, *a, *b;
    client_t *c;
    int vert;
    double ratio;
};

static tnode_t *roots[WM_NDESKS];
static int force_split = -1; /* -1 auto, 0 side, 1 stacked (one shot) */
static int last_dx, last_dy;
static void leaf_box(tnode_t *n, int x, int y, int w, int h, int gap,
                     client_t *want, int *ox, int *oy, int *ow, int *oh);

static tnode_t *mkleaf(client_t *c)
{
    tnode_t *n = calloc(1, sizeof *n);
    if (n) {
        n->c = c;
        n->ratio = 0.5;
    }
    return n;
}

static tnode_t *find_leaf(tnode_t *n, client_t *c)
{
    if (!n) return NULL;
    if (n->c == c) return n;
    tnode_t *p = find_leaf(n->a, c);
    return p ? p : find_leaf(n->b, c);
}

static tnode_t *first_leaf(tnode_t *n)
{
    if (!n) return NULL;
    if (n->c) return n;
    tnode_t *p = first_leaf(n->a);
    return p ? p : first_leaf(n->b);
}

static void replace_child(tnode_t *p, tnode_t *old, tnode_t *neu)
{
    if (!p) return;
    if (p->a == old) p->a = neu;
    else if (p->b == old) p->b = neu;
    if (neu) neu->parent = p;
}

void tile_set_split(int vert)
{
    force_split = vert ? 1 : 0;
}

void tile_note_focus_dir(int dx, int dy)
{
    last_dx = dx;
    last_dy = dy;
}

static int is_tiled(client_t *c)
{
    return c && !c->floated && !c->fullscreen && !c->minimized && !c->maximized && !c->above;
}

#include <time.h>
static long now_ms(void)
{
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return ts.tv_sec * 1000L + ts.tv_nsec / 1000000L;
}

static void goal_anim(client_t *c, int x, int y, int w, int h)
{
    if (w < 32) w = 32;
    if (h < 32) h = 32;
    int first = (c->tw == 0 && c->th == 0);
    c->tx = x; c->ty = y; c->tw = w; c->th = h;
    if (first) {
        c->x = x; c->y = y; c->w = w; c->h = h;
        c->anim_t0 = 0;
        return;
    }
    c->ax = c->x; c->ay = c->y; c->aw = c->w; c->ah = c->h;
    c->anim_t0 = now_ms();
}

static void lay(tnode_t *n, int x, int y, int w, int h, int gap)
{
    if (!n) return;
    if (n->c) {
        if (is_tiled(n->c))
            goal_anim(n->c, x, y, w, h);
        return;
    }
    int ax, ay, aw, ah, bx, by, bw, bh;
    tile_split_rect(x, y, w, h, gap, n->vert, n->ratio,
                    &ax, &ay, &aw, &ah, &bx, &by, &bw, &bh);
    lay(n->a, ax, ay, aw, ah, gap);
    lay(n->b, bx, by, bw, bh, gap);
}

void tile_retile(wm_t *wm)
{
    int g = wm->gap;
    int x = g, y = g;
    int w = wm->sw - g * 2;
    int h = wm->sh - g * 2;
    if (w < 64) w = 64;
    if (h < 64) h = 64;
    int d = wm->cur_desk;
    if (d < 0 || d >= WM_NDESKS) return;
    lay(roots[d], x, y, w, h, g);
    for (client_t *c = wm->clients; c; c = c->next) {
        if (c->desk != d) continue;
        if (c->fullscreen || c->minimized) continue;
        frame_layout(wm, c);
    }
}

void tile_tick(wm_t *wm)
{
    long now = now_ms();
    int dirty = 0;
    for (client_t *c = wm->clients; c; c = c->next) {
        if (!c->anim_t0) continue;
        double t = (double)(now - c->anim_t0) / (double)TILE_MS;
        if (t >= 1.0) {
            c->x = c->tx; c->y = c->ty; c->w = c->tw; c->h = c->th;
            c->anim_t0 = 0;
        } else {
            c->x = tile_lerp(c->ax, c->tx, t);
            c->y = tile_lerp(c->ay, c->ty, t);
            c->w = tile_lerp(c->aw, c->tw, t);
            c->h = tile_lerp(c->ah, c->th, t);
        }
        frame_layout(wm, c);
        dirty = 1;
    }
    (void)dirty;
}

void tile_insert(wm_t *wm, client_t *c)
{
    if (!c || c->floated || c->above) return;
    int d = c->desk;
    if (d < 0 || d >= WM_NDESKS) return;
    if (!roots[d]) {
        roots[d] = mkleaf(c);
        tile_retile(wm);
        return;
    }
    tnode_t *at = NULL;
    if (wm->focus && wm->focus != c && wm->focus->desk == d && is_tiled(wm->focus))
        at = find_leaf(roots[d], wm->focus);
    if (!at) at = first_leaf(roots[d]);
    if (!at) {
        roots[d] = mkleaf(c);
        tile_retile(wm);
        return;
    }
    tnode_t *leaf = mkleaf(c);
    tnode_t *sp = calloc(1, sizeof *sp);
    if (!sp || !leaf) return;

    int cw = at->c ? at->c->w : 800;
    int ch = at->c ? at->c->h : 600;
    int ox = 0, oy = 0, ow = 0, oh = 0;
    leaf_box(roots[d], wm->gap, wm->gap, wm->sw - 2 * wm->gap, wm->sh - 2 * wm->gap,
             wm->gap, at->c, &ox, &oy, &ow, &oh);
    if (ow > 0 && oh > 0) { cw = ow; ch = oh; }

    int vert;
    if (force_split >= 0) {
        vert = force_split;
        force_split = -1;
    } else {
        vert = tile_auto_split(cw, ch);
    }
    if (at->c) {
        XSizeHints hints;
        long supplied = 0;
        memset(&hints, 0, sizeof hints);
        if (XGetWMNormalHints(wm->dpy, c->xid, &hints, &supplied) &&
            (hints.flags & PMinSize) && hints.min_width > (cw - wm->gap) / 2)
            vert = 1;
    }

    int new_b = tile_new_is_b(last_dx, last_dy);
    sp->vert = vert;
    sp->parent = at->parent;
    if (new_b) {
        sp->a = at;
        sp->b = leaf;
        sp->ratio = TILE_KEEP;
    } else {
        sp->a = leaf;
        sp->b = at;
        sp->ratio = 1.0 - TILE_KEEP;
    }
    at->parent = sp;
    leaf->parent = sp;
    if (sp->parent) replace_child(sp->parent, at, sp);
    else roots[d] = sp;
    tile_retile(wm);
}

void tile_remove(wm_t *wm, client_t *c)
{
    if (!c) return;
    int d = c->desk;
    if (d < 0 || d >= WM_NDESKS) return;
    tnode_t *leaf = find_leaf(roots[d], c);
    if (!leaf) return;
    tnode_t *p = leaf->parent;
    if (!p) {
        free(leaf);
        roots[d] = NULL;
        return;
    }
    tnode_t *sib = (p->a == leaf) ? p->b : p->a;
    tnode_t *gp = p->parent;
    if (sib) sib->parent = gp;
    if (gp) replace_child(gp, p, sib);
    else roots[d] = sib;
    leaf->a = leaf->b = NULL;
    p->a = p->b = NULL;
    free(leaf);
    free(p);
    tile_retile(wm);
}

void tile_toggle_float(wm_t *wm, client_t *c)
{
    if (!c || c->fullscreen) return;
    if (c->floated) {
        c->floated = 0;
        tile_insert(wm, c);
    } else {
        tile_remove(wm, c);
        c->floated = 1;
        tile_retile(wm);
    }
}

static void leaf_box(tnode_t *n, int x, int y, int w, int h, int gap,
                     client_t *want, int *ox, int *oy, int *ow, int *oh)
{
    if (!n) return;
    if (n->c) {
        if (n->c == want) {
            *ox = x + w / 2;
            *oy = y + h / 2;
            if (ow) *ow = w;
            if (oh) *oh = h;
        }
        return;
    }
    int ax, ay, aw, ah, bx, by, bw, bh;
    tile_split_rect(x, y, w, h, gap, n->vert, n->ratio,
                    &ax, &ay, &aw, &ah, &bx, &by, &bw, &bh);
    leaf_box(n->a, ax, ay, aw, ah, gap, want, ox, oy, ow, oh);
    leaf_box(n->b, bx, by, bw, bh, gap, want, ox, oy, ow, oh);
}

void tile_swap_dir(wm_t *wm, client_t *c, int dx, int dy)
{
    if (!c || !is_tiled(c)) return;
    int d = c->desk;
    tnode_t *root = roots[d];
    if (!root) return;
    int g = wm->gap;
    int fx = 0, fy = 0;
    leaf_box(root, g, g, wm->sw - 2 * g, wm->sh - 2 * g, g, c, &fx, &fy, NULL, NULL);
    client_t *best = NULL;
    long best_s = 0;
    for (client_t *o = wm->clients; o; o = o->next) {
        if (o == c || o->desk != d || !is_tiled(o)) continue;
        int ox = 0, oy = 0;
        leaf_box(root, g, g, wm->sw - 2 * g, wm->sh - 2 * g, g, o, &ox, &oy, NULL, NULL);
        int cx = ox - fx, cy = oy - fy;
        long prim = (long)cx * dx + (long)cy * dy;
        if (prim <= 0) continue;
        long perp = labs((long)cx * dy - (long)cy * dx);
        long s = prim + perp * 3;
        if (!best || s < best_s) { best = o; best_s = s; }
    }
    if (!best) return;
    tnode_t *la = find_leaf(root, c);
    tnode_t *lb = find_leaf(root, best);
    if (!la || !lb) return;
    client_t *tmp = la->c;
    la->c = lb->c;
    lb->c = tmp;
    tile_retile(wm);
}

int tile_desk_fullscreen(wm_t *wm)
{
    for (client_t *c = wm->clients; c; c = c->next)
        if (c->desk == wm->cur_desk && c->fullscreen && !c->minimized)
            return 1;
    return 0;
}

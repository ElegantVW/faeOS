/* client.c — managed windows, focus stack, workspaces, geometry.
 *
 * Every client lives reparented inside a titlebar frame (frame.c). Borders,
 * raises, maps and paints all address the frame; the client area geometry
 * in c->x/y/w/h is the source of truth and the frame derives from it.
 */
#include "client.h"
#include "tile.h"
#include "frame.h"
#include "dock.h"
#include "theme.h"
#include "wm.h"

#include <stdlib.h>
#include <string.h>

#include <X11/Xlib.h>
#include <X11/Xatom.h>
#include <X11/Xutil.h>

static unsigned long get_pixel(Display *dpy, int scr, const char *hex)
{
    XColor c;
    Colormap cm = DefaultColormap(dpy, scr);
    if (!XParseColor(dpy, cm, hex, &c)) return BlackPixel(dpy, scr);
    if (!XAllocColor(dpy, cm, &c)) return BlackPixel(dpy, scr);
    return c.pixel;
}

void client_colors(wm_t *wm, const char *focus, const char *unfocus)
{
    wm->col_focus = get_pixel(wm->dpy, wm->scr, focus);
    wm->col_unfocus = get_pixel(wm->dpy, wm->scr, unfocus);
}

static void stack_add(wm_t *wm, Window xid)
{
    for (int i = 0; i < wm->nstack; i++)
        if (wm->stack[i] == xid) return;
    if (wm->nstack < WM_STACK_MAX) wm->stack[wm->nstack++] = xid;
}

static void stack_del(wm_t *wm, Window xid)
{
    for (int i = 0; i < wm->nstack; i++)
        if (wm->stack[i] == xid) {
            memmove(&wm->stack[i], &wm->stack[i + 1],
                    (size_t)(wm->nstack - i - 1) * sizeof(Window));
            wm->nstack--;
            return;
        }
}

/* Raise the frame, keeping above-layer windows on top. */
static void stack_raise(wm_t *wm, client_t *c)
{
    stack_del(wm, c->xid);
    int at = wm->nstack;
    for (int i = 0; i < wm->nstack; i++) {
        client_t *o = client_find(wm, wm->stack[i]);
        if (o && o->above) { at = i; break; }
    }
    if (wm->nstack < WM_STACK_MAX) {
        memmove(&wm->stack[at + 1], &wm->stack[at],
                (size_t)(wm->nstack - at) * sizeof(Window));
        wm->stack[at] = c->xid;
        wm->nstack++;
    }
    if (c->frame) XRaiseWindow(wm->dpy, c->frame);
    else XRaiseWindow(wm->dpy, c->xid);
    for (int i = 0; i < wm->nstack; i++) {
        client_t *o = client_find(wm, wm->stack[i]);
        if (o && o->above && o != c && o->frame)
            XRaiseWindow(wm->dpy, o->frame);
    }
}

static void ewmh_sync(wm_t *wm)
{
    ewmh_update_clients(wm->dpy, wm->root, &wm->atoms, wm->stack, wm->nstack);
    ewmh_update_active(wm->dpy, wm->root, &wm->atoms,
                       wm->focus ? wm->focus->xid : None);
}

static int win_type_is(Display *dpy, atoms_t *a, Window w, Atom t)
{
    Atom actual_type;
    int actual_format;
    unsigned long nitems, bytes_after;
    unsigned char *data = NULL;
    if (XGetWindowProperty(dpy, w, a->wm_window_type, 0, 8, False, XA_ATOM,
                           &actual_type, &actual_format, &nitems,
                           &bytes_after, &data) != Success)
        return 0;
    int hit = 0;
    if (data && actual_format == 32)
        for (unsigned long i = 0; i < nitems; i++)
            if (((Atom *)data)[i] == t) hit = 1;
    if (data) XFree(data);
    return hit;
}

static void front(wm_t *wm, client_t *c)
{
    client_t **pp = &wm->clients;
    while (*pp && *pp != c) pp = &(*pp)->next;
    if (*pp) {
        *pp = c->next;
        c->next = wm->clients;
        wm->clients = c;
    }
}

static void constrain(wm_t *wm, int *x, int *y, int w, int h)
{
    int g = wm->gap;
    int work_h = wm->sh - dock_reserve(wm);
    if (*x < g) *x = g;
    if (*y < g) *y = g;
    if (*x + w > wm->sw - g) *x = wm->sw - g - w;
    if (*y + h > work_h - g) *y = work_h - g - h;
    if (*x < g) *x = g;
    if (*y < g) *y = g;
}

static void paint_borders(wm_t *wm)
{
    for (client_t *o = wm->clients; o; o = o->next) {
        Window w = o->frame ? o->frame : o->xid;
        if (o->fullscreen) {
            XSetWindowBorderWidth(wm->dpy, w, 0);
            continue;
        }
        XSetWindowBorderWidth(wm->dpy, w, (unsigned)wm->border_w);
        XSetWindowBorder(wm->dpy, w,
                         o == wm->focus ? wm->col_focus : wm->col_unfocus);
        if (o->frame) frame_paint(wm, o);
    }
}

/* Honor _NET_WM_STATE the client mapped with (kiosk browsers demand
 * fullscreen from the first frame; session restore demands maximized). */
static void apply_initial_state(wm_t *wm, client_t *c)
{
    Atom actual_type;
    int actual_format;
    unsigned long nitems, bytes_after;
    unsigned char *data = NULL;
    if (XGetWindowProperty(wm->dpy, c->xid, wm->atoms.wm_state, 0, 8, False,
                           XA_ATOM, &actual_type, &actual_format, &nitems,
                           &bytes_after, &data) != Success)
        return;
    int full = 0, maxv = 0, maxh = 0;
    if (data && actual_format == 32)
        for (unsigned long i = 0; i < nitems; i++) {
            Atom s = ((Atom *)data)[i];
            if (s == wm->atoms.wm_state_fullscreen) full = 1;
            else if (s == wm->atoms.wm_state_maxv) maxv = 1;
            else if (s == wm->atoms.wm_state_maxh) maxh = 1;
        }
    if (data) XFree(data);
    if (full) {
        c->sx = c->x; c->sy = c->y; c->sw = c->w; c->sh = c->h;
        c->fullscreen = 1;
        c->x = 0; c->y = 0; c->w = wm->sw; c->h = wm->sh;
        wmlog("initial fullscreen %s", c->title);
    } else if (maxv && maxh) {
        c->sx = c->x; c->sy = c->y; c->sw = c->w; c->sh = c->h;
        c->maximized = 1;
        int g = wm->gap;
        c->x = g; c->y = g;
        c->w = wm->sw - g * 2;
        c->h = wm->sh - g * 2;
        wmlog("initial maximized %s", c->title);
    }
}

void client_manage(wm_t *wm, Window xid)
{
    if (client_find(wm, xid)) return;
    XWindowAttributes at;
    if (!XGetWindowAttributes(wm->dpy, xid, &at)) return;
    if (at.override_redirect) return;

    client_t *c = calloc(1, sizeof *c);
    if (!c) return;
    c->xid = xid;
    c->title = ewmh_title(wm->dpy, &wm->atoms, xid);
    c->x = at.x; c->y = at.y;
    c->w = at.width; c->h = at.height;
    c->desk = wm->cur_desk;
    c->above = win_type_is(wm->dpy, &wm->atoms, xid, wm->atoms.wm_window_type_dock) ||
               win_type_is(wm->dpy, &wm->atoms, xid, wm->atoms.wm_window_type_desktop);
    c->floated = win_type_is(wm->dpy, &wm->atoms, xid, wm->atoms.wm_window_type_dialog) ||
                 win_type_is(wm->dpy, &wm->atoms, xid, wm->atoms.wm_window_type_utility);

    if (c->x == 0 && c->y == 0) {
        int k = wm->cascade_n++ % 12;
        c->x = wm->gap + 40 + k * WM_CASCADE_STEP;
        c->y = wm->gap + 40 + k * WM_CASCADE_STEP;
    }
    if (c->w <= 0) c->w = 800;
    if (c->h <= 0) c->h = 600;
    constrain(wm, &c->x, &c->y, c->w, c->h);
    apply_initial_state(wm, c);

    XSelectInput(wm->dpy, xid,
                 StructureNotifyMask | PropertyChangeMask |
                 FocusChangeMask | EnterWindowMask);

    c->next = wm->clients;
    wm->clients = c;
    if (!frame_create(wm, c)) {
        wm->clients = c->next;
        free(c->title);
        free(c);
        return;
    }
    stack_add(wm, xid);
    if (!c->floated && !c->fullscreen && !c->above)
        tile_insert(wm, c);
    client_focus(wm, c);
    dock_refresh(wm);
    ewmh_sync(wm);
}

void client_unmanage(wm_t *wm, Window xid)
{
    client_t **pp = &wm->clients;
    while (*pp && (*pp)->xid != xid) pp = &(*pp)->next;
    if (!*pp) return;
    client_t *c = *pp;
    *pp = c->next;
    stack_del(wm, xid);
    tile_remove(wm, c);
    frame_destroy(wm, c);
    int was_focus = (wm->focus == c);
    int was_min = c->minimized;
    free(c->title);
    free(c);
    if (was_focus) {
        wm->focus = NULL;
        for (client_t *o = wm->clients; o; o = o->next)
            if (o->desk == wm->cur_desk && !o->minimized) {
                client_focus(wm, o);
                break;
            }
        if (!wm->focus) ewmh_sync(wm);
    } else {
        ewmh_sync(wm);
    }
    if (was_min) dock_refresh(wm);
}

client_t *client_find(wm_t *wm, Window xid)
{
    for (client_t *c = wm->clients; c; c = c->next)
        if (c->xid == xid) return c;
    return NULL;
}

client_t *client_resolve(wm_t *wm, Window xid)
{
    if (xid == None || xid == wm->root) return NULL;
    Window w = xid;
    for (int i = 0; i < 16; i++) {
        client_t *c = client_find(wm, w);
        if (c) return c;
        for (client_t *f = wm->clients; f; f = f->next)
            if (f->frame == w) return f;
        Window rret, pret, *kids = NULL;
        unsigned nkids = 0;
        if (!XQueryTree(wm->dpy, w, &rret, &pret, &kids, &nkids)) return NULL;
        if (kids) XFree(kids);
        if (pret == None || pret == wm->root) {
            /* w is (or was) a direct child: one last match attempt. */
            client_t *c2 = client_find(wm, w);
            if (c2) return c2;
            for (client_t *f = wm->clients; f; f = f->next)
                if (f->frame == w) return f;
            return NULL;
        }
        w = pret;
    }
    return NULL;
}

void client_focus(wm_t *wm, client_t *c)
{
    if (!c) {
        wm->focus = NULL;
        XSetInputFocus(wm->dpy, PointerRoot, RevertToPointerRoot, CurrentTime);
        ewmh_sync(wm);
        return;
    }
    if (c->minimized) client_unminimize(wm, c);
    front(wm, c);
    wm->focus = c;
    if (c->desk != wm->cur_desk) client_show_desk(wm, c->desk);
    stack_raise(wm, c);
    paint_borders(wm);
    XSetInputFocus(wm->dpy, c->xid, RevertToPointerRoot, CurrentTime);
    ewmh_sync(wm);
}

void client_hover(wm_t *wm, client_t *c)
{
    if (!c || c == wm->focus || c->minimized) return;
    wm->focus = c;
    paint_borders(wm);
    XSetInputFocus(wm->dpy, c->xid, RevertToPointerRoot, CurrentTime);
    ewmh_sync(wm);
}

void client_show_desk(wm_t *wm, int desk)
{
    if (desk < 0) desk = 0;
    if (desk >= WM_NDESKS) desk = WM_NDESKS - 1;
    wm->cur_desk = desk;
    for (client_t *c = wm->clients; c; c = c->next) {
        Window w = c->frame ? c->frame : c->xid;
        if (c->desk == desk && !c->minimized) XMapWindow(wm->dpy, w);
        else {
            c->ignore_unmap = 1;
            XUnmapWindow(wm->dpy, w);
        }
    }
    XSync(wm->dpy, False);
    wm->focus = NULL;
    for (client_t *c = wm->clients; c; c = c->next)
        if (c->desk == desk && !c->minimized) { client_focus(wm, c); break; }
    if (!wm->focus) {
        XSetInputFocus(wm->dpy, PointerRoot, RevertToPointerRoot, CurrentTime);
        ewmh_sync(wm);
    }
    ewmh_update_desktop(wm->dpy, wm->root, &wm->atoms, desk);
    tile_retile(wm);
}

void client_to_desk(wm_t *wm, client_t *c, int desk)
{
    if (!c) return;
    if (desk < 0) desk = 0;
    if (desk >= WM_NDESKS) desk = WM_NDESKS - 1;
    tile_remove(wm, c);
    c->desk = desk;
    unsigned long d = (unsigned long)desk;
    XChangeProperty(wm->dpy, c->xid, wm->atoms.wm_desktop, XA_CARDINAL, 32,
                    PropModeReplace, (unsigned char *)&d, 1);
    Window w = c->frame ? c->frame : c->xid;
    if (desk == wm->cur_desk && !c->minimized) {
        XMapWindow(wm->dpy, w);
        client_focus(wm, c);
    } else {
        c->ignore_unmap = 1;
        XUnmapWindow(wm->dpy, w);
        if (wm->focus == c) {
            wm->focus = NULL;
            for (client_t *o = wm->clients; o; o = o->next)
                if (o->desk == wm->cur_desk && !o->minimized) {
                    client_focus(wm, o);
                    break;
                }
            if (!wm->focus) ewmh_sync(wm);
        }
    }
    if (!c->floated && !c->fullscreen && !c->above)
        tile_insert(wm, c);
    tile_retile(wm);
}

void client_toggle_full(wm_t *wm, client_t *c)
{
    if (!c) return;
    if (c->maximized) {
        c->maximized = 0;
        c->x = c->sx; c->y = c->sy; c->w = c->sw; c->h = c->sh;
    }
    if (!c->fullscreen) {
        c->sx = c->x; c->sy = c->y; c->sw = c->w; c->sh = c->h;
        c->fullscreen = 1;
        c->x = 0; c->y = 0; c->w = wm->sw; c->h = wm->sh;
        Atom state[1] = { wm->atoms.wm_state_fullscreen };
        XChangeProperty(wm->dpy, c->xid, wm->atoms.wm_state, XA_ATOM, 32,
                        PropModeReplace, (unsigned char *)state, 1);
    } else {
        c->fullscreen = 0;
        XDeleteProperty(wm->dpy, c->xid, wm->atoms.wm_state);
        c->x = c->sx; c->y = c->sy; c->w = c->sw; c->h = c->sh;
        constrain(wm, &c->x, &c->y, c->w, c->h);
    }
    frame_layout(wm, c);
    if (c->fullscreen)
        XSetWindowBorderWidth(wm->dpy, c->frame ? c->frame : c->xid, 0);
    stack_raise(wm, c);
    tile_retile(wm);
}

void client_toggle_max(wm_t *wm, client_t *c)
{
    if (!c) return;
    if (c->fullscreen) client_toggle_full(wm, c);  /* un-fullscreen first */
    if (!c->maximized) {
        c->sx = c->x; c->sy = c->y; c->sw = c->w; c->sh = c->h;
        c->maximized = 1;
        int g = wm->gap;
        int H = wm->sh - dock_reserve(wm);
        c->x = g; c->y = g;
        c->w = wm->sw - g * 2;
        c->h = H - g * 2;
        Atom state[2] = { wm->atoms.wm_state_maxv, wm->atoms.wm_state_maxh };
        XChangeProperty(wm->dpy, c->xid, wm->atoms.wm_state, XA_ATOM, 32,
                        PropModeReplace, (unsigned char *)state, 2);
    } else {
        c->maximized = 0;
        XDeleteProperty(wm->dpy, c->xid, wm->atoms.wm_state);
        c->x = c->sx; c->y = c->sy; c->w = c->sw; c->h = c->sh;
        constrain(wm, &c->x, &c->y, c->w, c->h);
    }
    frame_layout(wm, c);
    stack_raise(wm, c);
}

void client_minimize(wm_t *wm, client_t *c)
{
    if (!c || c->minimized) return;
    wmlog("minimize %s", c->title);
    c->minimized = 1;
    if (c->frame) {
        c->ignore_unmap = 1;
        XUnmapWindow(wm->dpy, c->frame);
    }
    Atom state[1] = { XInternAtom(wm->dpy, "_NET_WM_STATE_HIDDEN", False) };
    XChangeProperty(wm->dpy, c->xid, wm->atoms.wm_state, XA_ATOM, 32,
                    PropModeReplace, (unsigned char *)state, 1);
    long wmstate[2] = { 3 /* IconicState */, None };
    XChangeProperty(wm->dpy, c->xid,
                    XInternAtom(wm->dpy, "WM_STATE", False),
                    XInternAtom(wm->dpy, "WM_STATE", False),
                    32, PropModeReplace, (unsigned char *)wmstate, 2);
    if (wm->focus == c) {
        wm->focus = NULL;
        for (client_t *o = wm->clients; o; o = o->next)
            if (o->desk == c->desk && !o->minimized) {
                client_focus(wm, o);
                break;
            }
        if (!wm->focus) {
            XSetInputFocus(wm->dpy, PointerRoot, RevertToPointerRoot,
                           CurrentTime);
            ewmh_sync(wm);
        }
    }
    dock_flash(wm);
}

void client_unminimize(wm_t *wm, client_t *c)
{
    if (!c || !c->minimized) return;
    wmlog("unminimize %s", c->title);
    c->minimized = 0;
    XDeleteProperty(wm->dpy, c->xid, wm->atoms.wm_state);
    long wmstate[2] = { 1 /* NormalState */, None };
    XChangeProperty(wm->dpy, c->xid,
                    XInternAtom(wm->dpy, "WM_STATE", False),
                    XInternAtom(wm->dpy, "WM_STATE", False),
                    32, PropModeReplace, (unsigned char *)wmstate, 2);
    if (c->desk != wm->cur_desk) client_show_desk(wm, c->desk);
    else if (c->frame) XMapWindow(wm->dpy, c->frame);
    client_focus(wm, c);
    dock_refresh(wm);
}

void client_close(wm_t *wm, client_t *c)
{
    if (!c) return;
    Atom *protos = NULL;
    int n = 0;
    int can_delete = 0;
    if (XGetWMProtocols(wm->dpy, c->xid, &protos, &n)) {
        for (int i = 0; i < n; i++)
            if (protos[i] == wm->atoms.wm_delete_window) can_delete = 1;
        XFree(protos);
    }
    if (can_delete) {
        XEvent e;
        memset(&e, 0, sizeof e);
        e.xclient.type = ClientMessage;
        e.xclient.window = c->xid;
        e.xclient.message_type = wm->atoms.wm_protocols;
        e.xclient.format = 32;
        e.xclient.data.l[0] = (long)wm->atoms.wm_delete_window;
        e.xclient.data.l[1] = CurrentTime;
        XSendEvent(wm->dpy, c->xid, False, NoEventMask, &e);
        XFlush(wm->dpy);
    } else {
        XKillClient(wm->dpy, c->xid);
    }
}

void client_nudge(wm_t *wm, client_t *c, int dx, int dy)
{
    if (!c || c->fullscreen || c->maximized) return;
    c->x += dx; c->y += dy;
    constrain(wm, &c->x, &c->y, c->w, c->h);
    frame_layout(wm, c);
}

void client_focus_dir(wm_t *wm, int dx, int dy)
{
    client_t *from = wm->focus;
    if (!from) {
        for (client_t *c = wm->clients; c; c = c->next)
            if (c->desk == wm->cur_desk && !c->minimized) {
                client_focus(wm, c);
                return;
            }
        return;
    }
    int fx = from->x + from->w / 2;
    int fy = from->y + from->h / 2;
    client_t *best = NULL;
    long best_score = 0;
    for (client_t *c = wm->clients; c; c = c->next) {
        if (c == from || c->desk != wm->cur_desk || c->minimized) continue;
        int cx = c->x + c->w / 2 - fx;
        int cy = c->y + c->h / 2 - fy;
        long primary = (long)cx * dx + (long)cy * dy;
        if (primary <= 0) continue;
        long perp = labs((long)cx * dy - (long)cy * dx);
        long score = primary + perp * 3;
        if (!best || score < best_score) { best = c; best_score = score; }
    }
    if (best) client_focus(wm, best);
}

void client_preset(wm_t *wm, client_t *c, const char *which)
{
    if (!c || c->fullscreen || c->maximized) return;
    int g = wm->gap;
    int W = wm->sw, H = wm->sh - dock_reserve(wm);
    if (!strcmp(which, "left")) {
        c->x = g; c->y = g; c->w = W / 2 - g * 2; c->h = H - g * 2;
    } else if (!strcmp(which, "right")) {
        c->w = W / 2 - g * 2; c->h = H - g * 2;
        c->x = W / 2 + g; c->y = g;
    } else if (!strcmp(which, "top")) {
        c->x = g; c->y = g; c->w = W - g * 2; c->h = H / 2 - g * 2;
    } else {
        c->w = 1200; c->h = 700;
        if (c->w > W - g * 2) c->w = W - g * 2;
        if (c->h > H - g * 2) c->h = H - g * 2;
        c->x = (W - c->w) / 2; c->y = (H - c->h) / 2;
    }
    constrain(wm, &c->x, &c->y, c->w, c->h);
    frame_layout(wm, c);
    stack_raise(wm, c);
}

client_t *client_at(wm_t *wm, int desk, int idx)
{
    int i = 0;
    for (client_t *c = wm->clients; c; c = c->next) {
        if (c->desk != desk || c->minimized) continue;
        if (i++ == idx) return c;
    }
    return NULL;
}

int client_stack(wm_t *wm, Window *out, int max)
{
    int n = wm->nstack < max ? wm->nstack : max;
    for (int i = 0; i < n; i++) out[i] = wm->stack[i];
    return n;
}

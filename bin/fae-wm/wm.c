/* wm.c — the event loop.
 *
 * Floating windows, ten workspaces, click-to-focus, directional keys,
 * Super+drag move/resize, fullscreen, cascade-on-open, and the built-in
 * Alt+Tab switcher (which reads the focus stack directly — exact recency,
 * including mouse clicks, with no ring file and no polling).
 *
 * Border-only frames: the border is drawn on the client itself, so there
 * are no frame windows to keep in sync.
 */
#include "wm.h"
#include "client.h"
#include "config.h"
#include "ewmh.h"
#include "frame.h"
#include "panel.h"
#include "dock.h"
#include "help.h"
#include "tile.h"
#include "theme.h"

#include <errno.h>
#include <fcntl.h>
#include <signal.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/select.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

#include <X11/Xlib.h>
#include <X11/Xatom.h>
#include <X11/Xutil.h>
#include <X11/keysym.h>

static wm_t W;
static config_t *CFG;
static int resize_mode = 0;
static int wake_pipe[2] = { -1, -1 };
/* ── audit log ─────────────────────────────────────────────────────────────
 * Always on, fae-cycle style: one line per interesting moment. stderr goes
 * who-knows-where under startx; this file is how we tell "never fired"
 * apart from "fired and misbehaved". */
static FILE *wmlog_fp = NULL;

void wmlog_open(void)
{
    if (wmlog_fp) return;
    const char *r = getenv("XDG_RUNTIME_DIR");
    char path[1024];
    if (r && *r) snprintf(path, sizeof path, "%s/fae-wm.log", r);
    else snprintf(path, sizeof path, "/tmp/fae-wm.log");
    wmlog_fp = fopen(path, "a");
}

void wmlog(const char *fmt, ...)
{
    if (!wmlog_fp) return;
    time_t now = time(NULL);
    struct tm tm;
    localtime_r(&now, &tm);
    fprintf(wmlog_fp, "%02d:%02d:%02d pid=%d ",
            tm.tm_hour, tm.tm_min, tm.tm_sec, (int)getpid());
    va_list ap;
    va_start(ap, fmt);
    vfprintf(wmlog_fp, fmt, ap);
    va_end(ap);
    fputc('\n', wmlog_fp);
    fflush(wmlog_fp);
}

static void on_signal(int sig)
{
    unsigned char b = (unsigned char)sig;
    ssize_t n = write(wake_pipe[1], &b, 1);
    (void)n;
}

static long now_ms(void)
{
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return ts.tv_sec * 1000L + ts.tv_nsec / 1000000L;
}

static int key_down(Display *dpy, KeyCode kc)
{
    char keys[32];
    if (!kc) return 0;
    XQueryKeymap(dpy, keys);
    return (keys[kc / 8] >> (kc % 8)) & 1;
}

/* ── actions ─────────────────────────────────────────────────────────────── */

/* Returns the child pid, or -1. */
pid_t spawn_cmd(const char *cmd)
{
    if (!cmd || !*cmd) return -1;
    pid_t pid = fork();
    if (pid < 0) return -1;
    if (pid == 0) {
        setsid();
        /* Expand a leading ~ the way a shell would for these two. */
        char buf[1024];
        const char *home = getenv("HOME");
        if (home && !strncmp(cmd, "~/", 2))
            snprintf(buf, sizeof buf, "%s%s", home, cmd + 1);
        else
            snprintf(buf, sizeof buf, "%s", cmd);
        execl("/bin/sh", "sh", "-c", buf, (char *)NULL);
        _exit(127);
    }
    return pid;
}

config_t *fae_cfg(void)
{
    return CFG;
}

static void do_preset(client_t *c, const char *which)
{
    client_preset(&W, c, which ? which : "center");
}

static void do_focus_arg(const char *arg)
{
    int dx = 0, dy = 0;
    if (!strcmp(arg, "left")) dx = -1;
    else if (!strcmp(arg, "right")) dx = 1;
    else if (!strcmp(arg, "up")) dy = -1;
    else if (!strcmp(arg, "down")) dy = 1;
    else return;
    client_focus_dir(&W, dx, dy);
}

static void do_nudge_arg(client_t *c, const char *arg)
{
    int dx = 0, dy = 0;
    if (!strcmp(arg, "left")) dx = -1;
    else if (!strcmp(arg, "right")) dx = 1;
    else if (!strcmp(arg, "up")) dy = -1;
    else if (!strcmp(arg, "down")) dy = 1;
    else return;
    if (c && !c->floated && !c->fullscreen)
        tile_swap_dir(&W, c, dx, dy);
    else
        client_nudge(&W, c, dx * WM_NUDGE, dy * WM_NUDGE);
}

static void run_bind(const bind_t *b)
{
    client_t *c = W.focus;
    switch (b->act) {
    case ACT_EXEC:       spawn_cmd(b->arg); break;
    case ACT_CLOSE:      client_close(&W, c); break;
    case ACT_FULLSCREEN: client_toggle_full(&W, c); break;
    case ACT_MAXIMIZE:  client_toggle_max(&W, c); break;
    case ACT_MINIMIZE:  client_minimize(&W, c); break;
    case ACT_FOCUS:      do_focus_arg(b->arg ? b->arg : ""); break;
    case ACT_NUDGE:      do_nudge_arg(c, b->arg ? b->arg : ""); break;
    case ACT_WORKSPACE:  client_show_desk(&W, atoi(b->arg ? b->arg : "1") - 1); break;
    case ACT_TOWORKSPACE:
        client_to_desk(&W, c, atoi(b->arg ? b->arg : "1") - 1);
        break;
    case ACT_RESIZE_MODE:
        resize_mode = 1;
        if (getenv("FAE_WM_VERBOSE")) fprintf(stderr, "fae-wm: resize mode\n");
        break;
    case ACT_PRESET:     do_preset(c, b->arg); break;
    case ACT_HELP:       help_toggle(&W); break;
    case ACT_SPLIT:
        tile_set_split(b->arg && !strcmp(b->arg, "vertical"));
        break;
    case ACT_FLOAT:      tile_toggle_float(&W, c); break;
    case ACT_EVEN:       tile_even(&W, c); break;
    case ACT_LAYOUT:     tile_toggle_layout(&W); break;
    case ACT_RELOAD:     /* handled by main loop: re-exec ourselves */ break;
    case ACT_QUIT:       break;
    }
}

/* Resize mode: hjkl/arrows grow/shrink, Return/Esc/Mod+r exits. */
static int resize_key(KeySym ks)
{
    client_t *c = W.focus;
    if (!c || c->fullscreen) return 0;
    int dx = 0, dy = 0, dw = 0, dh = 0;
    switch (ks) {
    case XK_j: case XK_Left:  dx = -1; dw = -WM_RESIZE_STEP; break;
    case XK_k: case XK_Down:  dy = 1;  dh = WM_RESIZE_STEP; break;
    case XK_l: case XK_Up:    dy = -1; dh = -WM_RESIZE_STEP; break;
    case XK_semicolon: case XK_Right: dx = 1; dw = WM_RESIZE_STEP; break;
    default: return 0;
    }
    if (!c->floated) {
        tile_grow(&W, c, dx, dy);
        return 1;
    }
    c->w += dw; c->h += dh;
    if (c->w < 80) c->w = 80;
    if (c->h < 60) c->h = 60;
    frame_layout(&W, c);
    return 1;
}

/* ── grabs ───────────────────────────────────────────────────────────────── */

static int grab_failed_code = 0;

static int grab_trap(Display *dpy, XErrorEvent *e)
{
    (void)dpy;
    grab_failed_code = e->error_code;
    return 0;
}

/* A failed grab is silent death for a binding: log it loudly when asked. */
static void grab_key(KeyCode kc, unsigned mod)
{
    /* Plus Lock and NumLock variants, or the binding dies with Caps on. */
    unsigned mods[] = { mod, mod | LockMask, mod | Mod2Mask,
                        mod | LockMask | Mod2Mask };
    for (unsigned i = 0; i < 4; i++) {
        grab_failed_code = 0;
        XErrorHandler prev = XSetErrorHandler(grab_trap);
        XGrabKey(W.dpy, kc, mods[i], W.root, False,
                 GrabModeAsync, GrabModeAsync);
        XSync(W.dpy, False);
        XSetErrorHandler(prev);
        if (grab_failed_code)
            wmlog("grab FAILED kc=%d mod=0x%x", (int)kc, mods[i]);
    }
}

static void grab_keys(void)
{
    XUngrabKey(W.dpy, AnyKey, AnyModifier, W.root);
    for (int i = 0; i < CFG->nbinds; i++) {
        KeyCode kc = XKeysymToKeycode(W.dpy, CFG->binds[i].keysym);
        if (kc) grab_key(kc, CFG->binds[i].mod);
    }
    /* The switcher lives here now: Alt+Tab / Alt+Shift+Tab. */
    KeyCode tab = XKeysymToKeycode(W.dpy, XK_Tab);
    if (tab) {
        grab_key(tab, Mod1Mask);
        grab_key(tab, Mod1Mask | ShiftMask);
    }
    /* Root passive grabs, owner_events=False: only the Mod4 gestures the WM
     * actually owns. An unmodified Button1 grab is deliberately absent —
     * it would swallow every click in every app (and divert their XI2
     * events to the root), forcing a synthetic re-injection that apps
     * either mis-pair or ignore outright. Unmodified presses are none of
     * our business: the frame and dock select their own masks. */
    unsigned bmods[] = { Mod4Mask, Mod4Mask | LockMask,
                         Mod4Mask | Mod2Mask,
                         Mod4Mask | LockMask | Mod2Mask };
    for (unsigned i = 0; i < sizeof bmods / sizeof bmods[0]; i++) {
        XGrabButton(W.dpy, Button1, bmods[i], W.root, False,
                    ButtonPressMask | ButtonReleaseMask,
                    GrabModeAsync, GrabModeAsync, None, None);
        XGrabButton(W.dpy, Button3, bmods[i], W.root, False,
                    ButtonPressMask | ButtonReleaseMask,
                    GrabModeAsync, GrabModeAsync, None, None);
    }
}

static const bind_t *match_bind(unsigned state, KeySym ks)
{
    unsigned mod = state & (ShiftMask | ControlMask | Mod1Mask | Mod4Mask);
    for (int i = 0; i < CFG->nbinds; i++)
        if (CFG->binds[i].keysym == (unsigned)ks && CFG->binds[i].mod == mod)
            return &CFG->binds[i];
    return NULL;
}

/* ── pointer drag ────────────────────────────────────────────────────────── */

static void drag(client_t *c, int resize, int button, int press_x, int press_y)
{
    if (!c || c->fullscreen) return;
    int gr = XGrabPointer(W.dpy, W.root, False,
                          PointerMotionMask | ButtonReleaseMask,
                          GrabModeAsync, GrabModeAsync,
                          None, None, CurrentTime);
    if (gr != GrabSuccess) {
        if (getenv("FAE_WM_VERBOSE"))
            fprintf(stderr, "fae-wm: drag grab failed (%d)\n", gr);
        return;
    }
    /* Poll the pointer, don't block on events: the physical button state
     * wins, so a lost ButtonRelease can never wedge the main loop. */
    unsigned want = button == Button3 ? Button3Mask : Button1Mask;
    /* Origin is the press itself: by the first poll the pointer may already
     * sit at its final spot, which would collapse every delta to zero. */
    int sx = press_x, sy = press_y, ox = c->x, oy = c->y, ow = c->w, oh = c->h;
    Window rr, cr;
    int rx, ry, wx, wy;
    unsigned mask = 0;
    wmlog("drag %s button=%d from=%d,%d", resize ? "resize" : "move",
          button, press_x, press_y);
    /* Drain-then-confirm: queued MotionNotify carries fast drags (the whole
     * press+release can land before the first poll), while the physical
     * button state wins against a lost release — neither alone wedges or
     * misses. */
    for (;;) {
        int done = 0;
        while (XPending(W.dpy)) {
            XEvent ev;
            XNextEvent(W.dpy, &ev);
            if (ev.type == ButtonRelease) done = 1;
        }
        XQueryPointer(W.dpy, W.root, &rr, &cr, &rx, &ry, &wx, &wy, &mask);
        if (getenv("FAE_WM_VERBOSE")) {
            static int n = 0;
            fprintf(stderr, "fae-wm: drag iter=%d done=%d mask=0x%x want=0x%x pos=%d,%d\n",
                    n++, done, mask, want, rx, ry);
        }
        if (resize) {
            c->w = ow + (rx - sx); c->h = oh + (ry - sy);
            if (c->w < 80) c->w = 80;
            if (c->h < 60) c->h = 60;
        } else {
            c->x = ox + (rx - sx); c->y = oy + (ry - sy);
            int g = W.gap;
            if (c->x < g) c->x = g;
            if (c->y < g) c->y = g;
        }
        frame_layout(&W, c);
        XFlush(W.dpy);
        if (done || !(mask & want)) break;
        struct timespec nap = { 0, 8 * 1000 * 1000 };
        nanosleep(&nap, NULL);
    }
    /* Drain the press/release pair so it never leaks to clients. */
    while (XPending(W.dpy)) { XEvent ev; XNextEvent(W.dpy, &ev); }
    XUngrabPointer(W.dpy, CurrentTime);
    XSync(W.dpy, False);
}

/* ── the Alt+Tab gesture, in-house ─────────────────────────────────────────
 * The panel reads the focus stack directly: exact recency, mouse clicks
 * included. No ring file, no polling for Tab (events carry it), Alt release
 * polled like the classic — a spurious release arrives on grab, so the poll
 * wins. Tap (Alt already up) commits immediately. */

static void switcher(void)
{
    int n = 0;
    for (client_t *c = W.clients; c; c = c->next)
        if (c->desk == W.cur_desk) n++;
    if (n <= 1) return;   /* nothing to switch to; change nothing */

    KeyCode kc_tab = XKeysymToKeycode(W.dpy, XK_Tab);
    KeyCode kc_esc = XKeysymToKeycode(W.dpy, XK_Escape);
    KeyCode kc_alt_l = XKeysymToKeycode(W.dpy, XK_Alt_L);
    KeyCode kc_alt_r = XKeysymToKeycode(W.dpy, XK_Alt_R);
    KeyCode kc_sl = XKeysymToKeycode(W.dpy, XK_Shift_L);
    KeyCode kc_sr = XKeysymToKeycode(W.dpy, XK_Shift_R);
    int reverse = key_down(W.dpy, kc_sl) || key_down(W.dpy, kc_sr);
    int sel = reverse ? n - 1 : 1;

    panel_t *p = panel_open(&W, sel, 0);
    if (!p) return;

    if (XGrabKeyboard(W.dpy, W.root, True,
                      GrabModeAsync, GrabModeAsync, CurrentTime) != GrabSuccess) {
        panel_close(p);
        return;
    }

    int cancelled = 0, tab_was = 0;
    long last_step = 0;
    for (;;) {
        fd_set fds;
        FD_ZERO(&fds);
        int xfd = ConnectionNumber(W.dpy);
        FD_SET(xfd, &fds);
        FD_SET(wake_pipe[0], &fds);
        int mx = xfd > wake_pipe[0] ? xfd : wake_pipe[0];
        struct timeval tv = { 0, 30 * 1000 };
        if (select(mx + 1, &fds, NULL, NULL, &tv) < 0) {
            if (errno == EINTR) continue;
            break;
        }
        if (FD_ISSET(wake_pipe[0], &fds)) break;
        while (XPending(W.dpy) && !cancelled) {
            XEvent ev;
            XNextEvent(W.dpy, &ev);
            if (ev.type == KeyPress && ev.xkey.keycode == kc_esc)
                cancelled = 1;
        }
        if (cancelled) break;
        /* Reap stragglers the grab caught so they never leak to clients. */
        while (XPending(W.dpy)) { XEvent ev; XNextEvent(W.dpy, &ev); }

        int tab_down = key_down(W.dpy, kc_tab);
        int shift = key_down(W.dpy, kc_sl) || key_down(W.dpy, kc_sr);
        if (tab_down && (!tab_was || (now_ms() - last_step >= TAB_REPEAT_MS))) {
            sel = shift ? (sel - 1 + n) % n : (sel + 1) % n;
            panel_select(p, sel);
            last_step = now_ms();
        }
        tab_was = tab_down;
        if (!key_down(W.dpy, kc_alt_l) && !key_down(W.dpy, kc_alt_r)) break;
    }

    XUngrabKeyboard(W.dpy, CurrentTime);
    XSync(W.dpy, False);
    /* Tap path included: if Alt is already up we never looped, and sel is
     * the pre-step — exactly one step, committed at once. */
    if (!cancelled) {
        client_t *t = NULL;
        int i = 0;
        for (client_t *c = W.clients; c; c = c->next) {
            if (c->desk != W.cur_desk) continue;
            if (i++ == sel) { t = c; break; }
        }
        if (t) client_focus(&W, t);
    }
    panel_close(p);
}

/* ── events ──────────────────────────────────────────────────────────────── */

static void on_keypress(XKeyEvent *ev)
{
    KeySym ks = XLookupKeysym(ev, 0);
    unsigned state = ev->state;

    if (help_visible()) {
        const bind_t *hb = match_bind(state, ks);
        if (ks == XK_Escape || (hb && hb->act == ACT_HELP)) {
            help_hide(&W);
            return;
        }
        if (ks == XK_Escape) return;
    }

    /* Alt+Tab belongs to the switcher, always. */
    if (ev->keycode == XKeysymToKeycode(W.dpy, XK_Tab) &&
        (state & Mod1Mask) && !(state & (Mod4Mask | ControlMask))) {
        switcher();
        return;
    }
    if (resize_mode) {
        if (ks == XK_Return || ks == XK_Escape ||
            (ks == XK_r && (state & Mod4Mask))) {
            resize_mode = 0;
            return;
        }
        resize_key(ks);
        return;
    }
    const bind_t *b = match_bind(state, ks);
    if (!b) return;
    if (b->act == ACT_RELOAD) {
        /* Re-exec: config + binds + autostart re-applied fresh. */
        char exe[1024];
        ssize_t r = readlink("/proc/self/exe", exe, sizeof exe - 1);
        if (r > 0) {
            exe[r] = 0;
            XCloseDisplay(W.dpy);
            execl(exe, exe, (char *)NULL);
        }
        return;
    }
    if (b->act == ACT_QUIT) {
        /* Graceful: hand every client back to the root before leaving, so
         * nothing is lost to a dead frame. The dock goes too. */
        dock_teardown(&W);
        while (W.clients) {
            client_t *c = W.clients;
            W.clients = c->next;
            frame_destroy(&W, c);
            XMapWindow(W.dpy, c->xid);
            free(c->title);
            free(c);
        }
        XSync(W.dpy, False);
        XCloseDisplay(W.dpy);
        _exit(0);
    }
    run_bind(b);
}

/* No button forwarding lives here any more. We used to grab every
 * unmodified press on the root and re-inject it with XSendEvent, pairing
 * presses and releases by hand. That is what killed right-click (and
 * middle-click) outright, and it handed apps synthetic events that their
 * XI2 paths ignore, so plain clicks did nothing either. Now that the root
 * no longer selects ButtonPressMask, presses reach the owning client
 * natively and there is nothing to forward. */

static void on_button(XButtonEvent *ev)
{
    Window target = ev->subwindow != None ? ev->subwindow : ev->window;
    /* Presses only ever reach us two ways: one of our own windows asks for
     * them (frame, dock), or a Mod4 passive grab activated on the root. In
     * the grab case the event window is the root and subwindow names the
     * child underneath — the frame. Anything else belongs to the client. */
    if (target == dock_win(&W)) {
        if (ev->button == Button1) dock_click(&W, ev->x_root, ev->y_root);
        return;
    }
    client_t *fc = frame_client(&W, target);
    if (!fc) return;
    client_focus(&W, fc);
    if (getenv("FAE_WM_VERBOSE"))
        fprintf(stderr, "fae-wm: press button=%d state=0x%x frame=0x%lx\n",
                ev->button, ev->state, (unsigned long)target);
    if (ev->state & Mod4Mask) {
        if (ev->button == Button1) drag(fc, 0, Button1, ev->x_root, ev->y_root);
        else if (ev->button == Button3) drag(fc, 1, Button3, ev->x_root, ev->y_root);
        return;
    }
    /* Only chrome: the client fills the rest of the frame, so a press that
     * lands on the frame at all is either a button or titlebar to drag. */
    if (ev->button != Button1 || fc->fullscreen) return;
    int bw = fc->fullscreen ? 0 : W.border_w;
    int th = fc->fullscreen ? 0 : WM_TITLE_H;
    int fx, fy, fw, fh;
    frame_outer(fc, bw, th, &fx, &fy, &fw, &fh);
    int lx = ev->x_root - fx, ly = ev->y_root - fy;
    if (frame_hit(fc, bw, th, lx, ly) != BTN_NONE)
        frame_press(&W, fc, lx, ly);
    else if (ly < th)
        drag(fc, 0, Button1, ev->x_root, ev->y_root);
}

/* The frame owns its own press/release pairing now (it selects both masks),
 * so the armed frame resolves the release by root coords and everything
 * else is a drag gesture's release, which has no client waiting on it. */
static void on_release(XButtonEvent *ev)
{
    for (client_t *c = W.clients; c; c = c->next) {
        if (c->pressed_btn != BTN_NONE && c->frame) {
            int bw = c->fullscreen ? 0 : W.border_w;
            int th = c->fullscreen ? 0 : WM_TITLE_H;
            int fx, fy, fw, fh;
            frame_outer(c, bw, th, &fx, &fy, &fw, &fh);
            frame_release(&W, c, ev->x_root - fx, ev->y_root - fy);
            return;
        }
    }
    /* Unarmed: the press became a drag or a Mod4 gesture and was consumed
     * by this window. Drop it — clients never saw the press. */
}

/* Sloppy focus: hover focuses, click raises. Matches the old i3 default.
 * Hover never reorders or raises: mouse sweeps must not scramble Alt+Tab. */
static void on_enter(XCrossingEvent *ev)
{
    if (!CFG->focus_follows_mouse) return;
    if (ev->mode != NotifyNormal || ev->detail == NotifyInferior) return;
    client_t *c = NULL;
    if (ev->window != W.root) c = client_resolve(&W, ev->window);
    if (!c && ev->subwindow != None) c = client_resolve(&W, ev->subwindow);
    if (c && c != W.focus && c->desk == W.cur_desk) client_hover(&W, c);
}

/* Button hover on titlebars; the motion is ours (no grab on motion). */
static void on_motion(XMotionEvent *ev)
{
    if (ev->window == dock_win(&W)) {
        dock_hover(&W, ev->x_root, ev->y_root);
        return;
    }
    if (ev->window == W.root) {
        /* Bottom edge summons the dock even with no dock window yet. */
        dock_edge(&W, ev->x_root, ev->y_root);
        return;
    }
    client_t *c = frame_client(&W, ev->window);
    if (!c || c->fullscreen) return;
    /* Direct delivery (motion is never grabbed): coords are frame-relative. */
    btn_t hov = frame_hit(c, W.border_w, WM_TITLE_H, ev->x, ev->y);
    if (hov != (btn_t)c->hover_btn) {
        c->hover_btn = (int)hov;
        frame_paint(&W, c);
    }
}

static void on_expose(XExposeEvent *ev)
{
    if (ev->count != 0) return;
    client_t *c = frame_client(&W, ev->window);
    if (c) { frame_paint(&W, c); return; }
    if (ev->window == dock_win(&W)) dock_refresh(&W);
    if (help_is_win(ev->window)) help_expose(&W);
}

static void on_map_request(XMapRequestEvent *ev)
{
    client_t *c = client_find(&W, ev->window);
    if (c) {
        /* The app un-iconified itself: honor it. */
        if (c->minimized) client_unminimize(&W, c);
        return;
    }
    client_manage(&W, ev->window);
}

static void on_unmap(XUnmapEvent *ev)
{
    /* Reparenting unmaps fire too; only forget truly withdrawn windows.
     * Workspace switches unmap explicitly and say so on the client. */
    if (ev->event != W.root) return;
    client_t *c = client_find(&W, ev->window);
    if (!c) return;
    if (c->ignore_unmap) { c->ignore_unmap = 0; return; }
    client_unmanage(&W, ev->window);
}

static void on_destroy(XDestroyWindowEvent *ev)
{
    client_unmanage(&W, ev->window);
}

static void on_configure(XConfigureRequestEvent *ev)
{
    client_t *c = client_find(&W, ev->window);
    XWindowChanges wc;
    memset(&wc, 0, sizeof wc);
    unsigned mask = 0;
    if (ev->value_mask & CWX) { wc.x = ev->x; mask |= CWX; }
    if (ev->value_mask & CWY) { wc.y = ev->y; mask |= CWY; }
    if (ev->value_mask & CWWidth) { wc.width = ev->width; mask |= CWWidth; }
    if (ev->value_mask & CWHeight) { wc.height = ev->height; mask |= CWHeight; }
    if (ev->value_mask & CWBorderWidth) {
        wc.border_width = 0;
        mask |= CWBorderWidth;
    }
    if (ev->value_mask & CWStackMode) {
        wc.stack_mode = ev->detail;
        mask |= CWStackMode;
    }
    if (c) {
        /* Client coords are frame-relative now; placement is ours alone. */
        if (mask & CWWidth) c->w = wc.width;
        if (mask & CWHeight) c->h = wc.height;
        mask &= ~(CWX | CWY);
        if (c->fullscreen) mask &= ~(CWWidth | CWHeight);
        if (mask & (CWWidth | CWHeight)) {
            frame_layout(&W, c);
            mask &= ~(CWWidth | CWHeight);
        }
        if (mask) XConfigureWindow(W.dpy, ev->window, mask, &wc);
    } else if (mask) {
        XConfigureWindow(W.dpy, ev->window, mask, &wc);
    }
    XSync(W.dpy, False);
}

static void on_property(XPropertyEvent *ev)
{
    if (ev->atom != W.atoms.wm_name) return;
    client_t *c = client_find(&W, ev->window);
    if (!c) return;
    free(c->title);
    c->title = ewmh_title(W.dpy, &W.atoms, ev->window);
    frame_paint(&W, c);
}

static void on_client_message(XClientMessageEvent *ev)
{
    if (ev->message_type == W.atoms.active_window) {
        client_t *c = client_find(&W, ev->window);
        if (c) client_focus(&W, c);
    } else if (ev->message_type == W.atoms.close_window) {
        client_t *c = client_find(&W, ev->window);
        if (c) client_close(&W, c);
    } else if (ev->message_type == W.atoms.current_desktop) {
        client_show_desk(&W, (int)ev->data.l[0]);
    } else if (ev->message_type == W.atoms.wm_desktop) {
        client_t *c = client_find(&W, ev->window);
        if (c) client_to_desk(&W, c, (int)ev->data.l[0]);
    } else if (ev->message_type == W.atoms.wm_state) {
        client_t *c = client_find(&W, ev->window);
        if (c) {
            /* data.l[0]: 0 remove, 1 add, 2 toggle. data.l[1..2]: props. */
            long act = ev->data.l[0];
            for (int k = 1; k <= 2; k++) {
                Atom prop = (Atom)ev->data.l[k];
                if (prop == W.atoms.wm_state_fullscreen) {
                    if ((act == 1 && !c->fullscreen) ||
                        (act == 0 && c->fullscreen) || act == 2)
                        client_toggle_full(&W, c);
                } else if (prop == W.atoms.wm_state_maxv ||
                           prop == W.atoms.wm_state_maxh) {
                    if ((act == 1 && !c->maximized) ||
                        (act == 0 && c->maximized) || act == 2)
                        client_toggle_max(&W, c);
                }
            }
        }
    }
}

/* ── run ─────────────────────────────────────────────────────────────────── */

static int on_x_error(Display *dpy, XErrorEvent *e)
{
    (void)dpy;
    if (getenv("FAE_WM_VERBOSE"))
        fprintf(stderr, "fae-wm: X error code=%d request=%d resource=0x%lx\n",
                e->error_code, e->request_code, e->resourceid);
    return 0;
}

/* If another WM already owns SubstructureRedirect, selecting it raises
 * BadAccess asynchronously — trap it with a sync to know for sure. */
static int trapped_badaccess = 0;

static int access_trap(Display *dpy, XErrorEvent *e)
{
    (void)dpy;
    if (e->error_code == BadAccess) trapped_badaccess = 1;
    return on_x_error(dpy, e);
}

static int another_wm(Display *dpy, Window root)
{
    trapped_badaccess = 0;
    XErrorHandler prev = XSetErrorHandler(access_trap);
    /* Also the root's real event selection, and it sticks. Deliberately NO
     * ButtonPressMask here: SubstructureRedirectMask redirects every press
     * on every descendant that the selecting client also selects, so adding
     * it would divert each app's clicks to us. Clients get native presses
     * (and their own XI2 events) instead; we only ever claim our own
     * windows and the explicit Mod4 grabs. */
    XSelectInput(dpy, root,
                 SubstructureNotifyMask | SubstructureRedirectMask |
                 PointerMotionMask | PropertyChangeMask);
    XSync(dpy, False);
    XSetErrorHandler(prev);
    return trapped_badaccess;
}

int wm_run(Display *dpy, int scr, config_t *cfg)
{
    memset(&W, 0, sizeof W);
    W.dpy = dpy;
    W.scr = scr;
    W.root = RootWindow(dpy, scr);
    W.sw = DisplayWidth(dpy, scr);
    W.sh = DisplayHeight(dpy, scr);
    wmlog_open();
    wmlog("start %dx%d binds=%d", W.sw, W.sh, cfg->nbinds);
    W.border_w = cfg->border_w > 0 ? cfg->border_w : 0;
    W.gap = cfg->gap_outer >= 0 ? cfg->gap_outer : 0;
    CFG = cfg;
    atoms_init(dpy, &W.atoms);
    client_colors(&W, cfg->color_focus, cfg->color_unfocus);

    XSetErrorHandler(on_x_error);
    if (another_wm(dpy, W.root)) {
        fprintf(stderr, "fae-wm: another window manager is running\n");
        return 1;
    }

    ewmh_publish(dpy, W.root, &W.atoms, WM_NDESKS);

    /* Adopt what's already mapped. */
    Window rret, pret, *kids = NULL;
    unsigned nkids = 0;
    if (XQueryTree(dpy, W.root, &rret, &pret, &kids, &nkids)) {
        for (unsigned i = 0; i < nkids; i++) {
            XWindowAttributes at;
            if (XGetWindowAttributes(dpy, kids[i], &at) &&
                !at.override_redirect && at.map_state == IsViewable)
                client_manage(&W, kids[i]);
        }
        if (kids) XFree(kids);
    }

    if (pipe(wake_pipe) != 0) return 1;
    struct sigaction sa;
    memset(&sa, 0, sizeof sa);
    sa.sa_handler = on_signal;
    sa.sa_flags = SA_RESTART;
    sigaction(SIGTERM, &sa, NULL);
    sigaction(SIGINT, &sa, NULL);
    sigaction(SIGHUP, &sa, NULL);

    grab_keys();
    for (int i = 0; i < cfg->nauto; i++) spawn_cmd(cfg->autostart[i]);
    dock_refresh(&W);

    for (;;) {
        fd_set fds;
        FD_ZERO(&fds);
        int xfd = ConnectionNumber(dpy);
        FD_SET(xfd, &fds);
        FD_SET(wake_pipe[0], &fds);
        int mx = xfd > wake_pipe[0] ? xfd : wake_pipe[0];
        /* ~60Hz tick, not forever: dock slides/shimmers and pending press/release
         * pairs complete on physical state even when the release never arrives. */
        struct timeval tv = { 0, 16 * 1000 };
        if (select(mx + 1, &fds, NULL, NULL, &tv) < 0) {
            if (errno == EINTR) continue;
            break;
        }
        if (FD_ISSET(wake_pipe[0], &fds)) break;
        dock_tick(&W);
        tile_tick(&W);
        help_tick(&W);
        while (XPending(dpy)) {
            XEvent ev;
            XNextEvent(dpy, &ev);
            if (getenv("FAE_WM_VERBOSE") &&
                (ev.type == ButtonPress || ev.type == ButtonRelease ||
                 ev.type == MotionNotify)) {
                int btn = -1;
                if (ev.type == ButtonPress || ev.type == ButtonRelease)
                    btn = ev.xbutton.button;
                fprintf(stderr, "fae-wm: ev type=%d button=%d\n",
                        ev.type, btn);
            }
            switch (ev.type) {
            case MapRequest:      on_map_request(&ev.xmaprequest); break;
            case UnmapNotify:      on_unmap(&ev.xunmap); break;
            case DestroyNotify:    on_destroy(&ev.xdestroywindow); break;
            case ConfigureRequest: on_configure(&ev.xconfigurerequest); break;
            case ButtonPress:      on_button(&ev.xbutton); break;
            case ButtonRelease:    on_release(&ev.xbutton); break;
            case MotionNotify:     on_motion(&ev.xmotion); break;
            case Expose:           on_expose(&ev.xexpose); break;
            case EnterNotify:      on_enter(&ev.xcrossing); break;
            case KeyPress:         on_keypress(&ev.xkey); break;
            case PropertyNotify:   on_property(&ev.xproperty); break;
            case ClientMessage:    on_client_message(&ev.xclient); break;
            default: break;
            }
        }
        while (waitpid(-1, NULL, WNOHANG) > 0) { }
    }
    return 0;
}

/* hold.c — the Alt+Tab gesture.
 *
 * One strip for the whole gesture. Alt+Tab opens it, Tab moves the highlight,
 * Shift+Tab reverses, Esc cancels, and releasing Alt commits.
 *
 * The order matters and used to be wrong: focus moves FIRST, then the strip
 * fades. That is what every modern switcher does, and it is why they feel
 * instant. The previous version waited ~850ms on screen before committing,
 * which read as lag and stacked a panel on every tap.
 *
 * ── on grabbing the keyboard ──────────────────────────────────────────────
 * While Alt is held we need Tab, and Tab belongs to your shell. The only
 * reliable way to see it is an active XGrabKeyboard, which takes everything.
 * The failure that would actually hurt is this process dying while grabbed,
 * leaving the keyboard dead until you log out — so:
 *
 *   - a self-pipe carries signals into the main loop, so ungrabbing always
 *     happens in normal context and never from a signal handler
 *   - alarm(THEME_MAX_HOLD) is a failsafe: a stuck Alt cannot hold the
 *     keyboard longer than that whatever else goes wrong
 *   - every exit path calls XUngrabKeyboard, and there is only one
 */
#include "hold.h"
#include "hud.h"
#include "theme.h"

#include <errno.h>
#include <fcntl.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/select.h>
#include <time.h>
#include <unistd.h>

#include <X11/Xlib.h>
#include <X11/keysym.h>
#include <X11/Xatom.h>

#ifndef TrueClass
#define TrueClass 4
#endif

static int wake_pipe[2] = { -1, -1 };
static int grab_code = 0;

static int grab_failed(Display *d, XErrorEvent *e)
{
    (void)d;
    grab_code = e->error_code;
    return 0;
}

static void on_signal(int sig)
{
    unsigned char b = (unsigned char)sig;
    ssize_t n = write(wake_pipe[1], &b, 1);
    (void)n;
}

static int install_pipe(void)
{
    if (pipe(wake_pipe) != 0) return 0;
    for (int i = 0; i < 2; i++) {
        int fl = fcntl(wake_pipe[i], F_GETFL, 0);
        if (fl >= 0) fcntl(wake_pipe[i], F_SETFL, fl | O_NONBLOCK);
    }
    return 1;
}

/* the standard, WM-agnostic way to ask for focus. Not i3-msg: this program
 * does not know i3 exists. */
static void request_focus(Display *dpy, Window xid)
{
    XEvent e;
    memset(&e, 0, sizeof e);
    e.xclient.type = ClientMessage;
    e.xclient.window = xid;
    e.xclient.message_type = XInternAtom(dpy, "_NET_ACTIVE_WINDOW", False);
    e.xclient.format = 32;
    e.xclient.data.l[0] = 2;              /* source: pager, i.e. a switcher */
    e.xclient.data.l[1] = CurrentTime;
    e.xclient.data.l[2] = 0;
    XSendEvent(dpy, DefaultRootWindow(dpy), False,
               SubstructureNotifyMask | SubstructureRedirectMask, &e);
    XFlush(dpy);
}

static int key_down(Display *dpy, KeyCode kc)
{
    char keys[32];
    if (!kc) return 0;
    XQueryKeymap(dpy, keys);
    return (keys[kc / 8] >> (kc % 8)) & 1;
}

static void commit(Display *dpy, hud_t *h, const char *how)
{
    Window t = hud_target(h);
    if (t != None) request_focus(dpy, t);
    if (getenv("FAE_HUD_VERBOSE"))
        fprintf(stderr, "fae-hud: %s -> %s\n", how, t == None ? "none" : hud_label(h));
}

int hold_cycle(Display *dpy, int scr, elist_t *apps)
{
    int n = apps->n;
    if (n == 0) {
        hud_t *empty = hud_open(dpy, scr, apps, 0, 0);
        if (empty) {
            struct timespec nap = { 0, 700L * 1000L * 1000L };
            nanosleep(&nap, NULL);
            while (XPending(dpy)) { XEvent ev; XNextEvent(dpy, &ev); }
            hud_close(empty);
        }
        return 0;
    }

    /* Windows/macOS semantics: the first Alt+Tab has ALREADY moved you one
     * step, so a single tap lands on the next app without any further input. */
    int sel = n > 1 ? 1 : 0;
    hud_t *h = hud_open(dpy, scr, apps, sel, 0);
    if (!h) return 1;

    KeyCode kc_tab    = XKeysymToKeycode(dpy, XK_Tab);
    KeyCode kc_esc    = XKeysymToKeycode(dpy, XK_Escape);
    KeyCode kc_alt_l  = XKeysymToKeycode(dpy, XK_Alt_L);
    KeyCode kc_alt_r  = XKeysymToKeycode(dpy, XK_Alt_R);
    KeyCode kc_lshift = XKeysymToKeycode(dpy, XK_Shift_L);

    int cancelled = 0, tab_was = 0;

    /* A tap: i3 consumed the Alt+Tab that started us and the user has already
     * let go. Commit immediately — no wait — and let the strip fade as the
     * confirmation. Waiting here was what made it feel slow. */
    if (!key_down(dpy, kc_alt_l) && !key_down(dpy, kc_alt_r)) {
        commit(dpy, h, "tap");
        hud_close(h);
        return 0;
    }

    if (!install_pipe()) { hud_close(h); return 1; }
    struct sigaction sa;
    memset(&sa, 0, sizeof sa);
    sa.sa_handler = on_signal;
    sa.sa_flags = SA_RESTART;
    sigaction(SIGALRM, &sa, NULL);
    sigaction(SIGTERM, &sa, NULL);
    sigaction(SIGINT,  &sa, NULL);
    sigaction(SIGHUP,  &sa, NULL);

    {
        grab_code = 0;
        XErrorHandler prev = XSetErrorHandler(grab_failed);
        XGrabKeyboard(dpy, DefaultRootWindow(dpy), True,
                      GrabModeAsync, GrabModeAsync, CurrentTime);
        XSync(dpy, False);
        XSetErrorHandler(prev);
        if (getenv("FAE_HUD_VERBOSE"))
            fprintf(stderr, "fae-hud: XGrabKeyboard %s\n",
                    grab_code == 0 ? "OK" : "REFUSED");
    }
    alarm(THEME_MAX_HOLD);

    /* The event stream is not trustworthy for "is Alt still down": a spurious
     * KeyRelease for the Alt keycode arrives the moment the grab takes, and
     * acting on it ended the whole gesture before the user pressed anything.
     * So events carry Tab and Escape, and a 30ms poll of the real key state
     * decides when the gesture is over. The poll wins, always. */
    for (;;) {
        fd_set fds;
        FD_ZERO(&fds);
        int xfd = ConnectionNumber(dpy);
        FD_SET(xfd, &fds);
        FD_SET(wake_pipe[0], &fds);
        int mx = xfd > wake_pipe[0] ? xfd : wake_pipe[0];
        struct timeval tv = { 0, 30 * 1000 };

        if (select(mx + 1, &fds, NULL, NULL, &tv) < 0) {
            if (errno == EINTR) continue;
            break;
        }
        if (FD_ISSET(wake_pipe[0], &fds)) {
            if (getenv("FAE_HUD_VERBOSE"))
                fprintf(stderr, "fae-hud: exit on signal/failsafe\n");
            break;
        }

        while (XPending(dpy) && !cancelled) {
            XEvent ev;
            XNextEvent(dpy, &ev);
            if (ev.type == KeyPress && ev.xkey.keycode == kc_esc) {
                cancelled = 1;
                commit(dpy, h, "cancelled");
            }
        }
        if (cancelled) break;

        int tab_down = key_down(dpy, kc_tab);
        if (tab_down && !tab_was && n > 1) {
            int shift = key_down(dpy, kc_lshift);
            sel = shift ? (sel - 1 + n) % n : (sel + 1) % n;
            hud_select(h, sel);
            if (getenv("FAE_HUD_VERBOSE"))
                fprintf(stderr, "fae-hud: selection -> %d\n", sel);
        }
        tab_was = tab_down;

        if (!key_down(dpy, kc_alt_l) && !key_down(dpy, kc_alt_r)) {
            if (getenv("FAE_HUD_VERBOSE"))
                fprintf(stderr, "fae-hud: alt up\n");
            break;
        }
    }

    alarm(0);
    XUngrabKeyboard(dpy, CurrentTime);
    XSync(dpy, False);

    if (!cancelled) commit(dpy, h, "release");
    hud_close(h);
    return 0;
}

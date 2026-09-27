/* hold.c — the Alt+Tab gesture.
 *
 * One panel for the whole gesture. Alt+Tab opens it, Tab moves the highlight,
 * Shift+Tab reverses, Esc cancels, and releasing Alt focuses the selection.
 * Focus does not move while you browse, which is the whole point: i3 follows
 * focus across workspaces, so a switcher that focuses on every press drags you
 * around your own machine and hides everything you started from.
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
 *     keyboard for longer than that no matter what
 *   - every exit path calls XUngrabKeyboard, and there is only one exit path
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
#include <time.h>
#include <sys/select.h>
#include <unistd.h>

#include <X11/Xlib.h>
#include <X11/keysym.h>
#include <X11/Xatom.h>

#ifndef TrueClass
#define TrueClass 4
#endif

static int wake_pipe[2] = { -1, -1 };

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

/* the standard, WM-agnostic way to ask for focus. Deliberately not i3-msg:
 * this program does not know i3 exists. */
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

static int grab_code = 0;
static int grab_failed(Display *d, XErrorEvent *e)
{
    (void)d;
    grab_code = e->error_code;
    return 0;
}

static int key_down(Display *dpy, KeyCode kc)
{
    char keys[32];
    if (!kc) return 0;
    XQueryKeymap(dpy, keys);
    return (keys[kc / 8] >> (kc % 8)) & 1;
}

int hold_cycle(Display *dpy, int scr, wlist_t *list)
{
    if (list->n == 0) {
        /* Nothing on this workspace. Show the panel saying so rather than
         * exiting 1 in silence: the old behaviour was invisible because i3
         * sends a script's stderr to /dev/tty1. */
        hud_t *empty = hud_open(dpy, scr, list, 0, 0);
        if (empty) {
            struct timespec nap = { 0, 700L * 1000L * 1000L };
            nanosleep(&nap, NULL);
            while (XPending(dpy)) { XEvent ev; XNextEvent(dpy, &ev); }
            hud_close(empty);
        }
        return 0;
    }

    /* Windows semantics: the first Alt+Tab already selects the *next* window,
     * so a quick tap steps one window and a hold lets you keep going. */
    int sel = list->n > 1 ? 1 : 0;
    hud_t *h = hud_open(dpy, scr, list, sel, 0);
    if (!h) return 1;

    int n = hud_rows(h);
    int chosen = sel;
    int cancelled = 0;

    KeyCode kc_tab    = XKeysymToKeycode(dpy, XK_Tab);
    KeyCode kc_esc    = XKeysymToKeycode(dpy, XK_Escape);
    KeyCode kc_alt_l  = XKeysymToKeycode(dpy, XK_Alt_L);
    KeyCode kc_alt_r  = XKeysymToKeycode(dpy, XK_Alt_R);
    KeyCode kc_lshift = XKeysymToKeycode(dpy, XK_Shift_L);

    if (getenv("FAE_HUD_VERBOSE"))
        fprintf(stderr, "fae-hud: keycodes tab=%d esc=%d alt_l=%d alt_r=%d "
                        "shift_l=%d\n", kc_tab, kc_esc, kc_alt_l, kc_alt_r,
                kc_lshift);

    int grabbed = 0;

    /* A quick tap: i3 consumed the Alt+Tab that started us, and by the time
     * we get here the user has already let go. Nothing to browse — commit the
     * single step and get out of the way. */
    if (!key_down(dpy, kc_alt_l) && !key_down(dpy, kc_alt_r)) {
        int target = (sel < list->n) ? list->v[sel].xid : None;
        hud_close(h);
        if (target != None) request_focus(dpy, target);
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

    /* Find out whether the grab actually took. A failed XGrabKeyboard raises
     * BadAccess, which the global handler in main.c quietly absorbs — so
     * without this check we would carry on believing we own the keyboard while
     * Tab is in fact going to the shell and triggering completion. */
    {
        static int code = 0;
        code = 0;
        XErrorHandler prev = XSetErrorHandler(grab_failed);
        XGrabKeyboard(dpy, DefaultRootWindow(dpy), True,
                      GrabModeAsync, GrabModeAsync, CurrentTime);
        XSync(dpy, False);
        XSetErrorHandler(prev);
        grabbed = (code == 0);
        if (getenv("FAE_HUD_VERBOSE"))
            fprintf(stderr, "fae-hud: XGrabKeyboard %s (error=%d)\n",
                    grabbed ? "OK" : "REFUSED", code);
    }
    alarm(THEME_MAX_HOLD);

    /* The event stream is not trustworthy for "is Alt still down": a spurious
     * KeyRelease for the Alt keycode arrives the moment the grab takes, and
     * the real release is not guaranteed to follow in a form we can rely on.
     * So: events tell us about Tab and Escape, and a 30ms poll of the actual
     * key state tells us when the gesture is over. Polling wins, always. */
    int done = 0, tab_was_down = 0;
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

        while (XPending(dpy) && !done && !cancelled) {
            XEvent ev;
            XNextEvent(dpy, &ev);
            if (ev.type == KeyPress && ev.xkey.keycode == kc_esc) {
                cancelled = 1;
                done = 1;
            }
        }
        if (done) break;

        /* Tab edges, read from the key state so a press that arrives between
         * two select() wakeups is still counted exactly once. */
        int tab_down = key_down(dpy, kc_tab);
        if (tab_down && !tab_was_down && n > 1) {
            int shift = key_down(dpy, kc_lshift);
            chosen = shift ? (chosen - 1 + n) % n : (chosen + 1) % n;
            hud_select(h, chosen);
            if (getenv("FAE_HUD_VERBOSE"))
                fprintf(stderr, "fae-hud: selection -> %d\n", chosen);
        }
        tab_was_down = tab_down;

        if (!key_down(dpy, kc_alt_l) && !key_down(dpy, kc_alt_r)) {
            if (getenv("FAE_HUD_VERBOSE"))
                fprintf(stderr, "fae-hud: alt up, ending gesture\n");
            break;
        }
    }

    if (grabbed) {
        alarm(0);
        XUngrabKeyboard(dpy, CurrentTime);
        XSync(dpy, False);
    }

    Window target = None;
    if (!cancelled && chosen >= 0 && chosen < list->n)
        target = list->v[chosen].xid;

    hud_close(h);

    if (target != None) request_focus(dpy, target);
    if (getenv("FAE_HUD_VERBOSE"))
        fprintf(stderr, "fae-hud: cycle %s -> %s\n",
                cancelled ? "cancelled" : "committed",
                target == None ? "none" : "focused");
    return 0;
}

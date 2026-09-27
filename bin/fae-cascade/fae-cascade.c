/* fae-cascade — stop new windows from landing exactly on top of each other.
 *
 * Why this exists: `for_window [class=".*"] floating enable` floats every new
 * window at the container's rect, and i3 uses the same rect each time. Open
 * three terminals and all three sit at (610,315 700x450) — literally stacked,
 * so from outside you see one window and the other two look minimized. We
 * caught three of them sharing one position while auditing fae-hud.
 *
 * The offset only applies when a new window's position *exactly* matches a
 * window that is already there, so this never moves anything on purpose.
 *
 * Unlike fae-hud, which is EWMH-only and does not know i3 exists, this one
 * moves windows through i3's IPC. XMoveWindow on a managed window is fighting
 * the window manager and losing; i3-msg is the supported path here, and a
 * tool whose whole job is "fix up how the WM places things" is not the place
 * to pretend otherwise.
 *
 * This is the one resident process in the house, and it is deliberate: it
 * reacts to a window appearing, and there is no trigger to spawn it from.
 * It holds nothing, draws nothing, and prints nothing to the screen.
 */
#include <X11/Xlib.h>
#include <X11/Xatom.h>
#include <X11/Xutil.h>

#include <fcntl.h>
#include <signal.h>
#include <sys/file.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

#define TICK_MS      350
#define STEP_PX      30    /* how far each stacked window is nudged */
#define MAX_SEEN     512
#define MIN_W        120
#define MIN_H        80

static volatile sig_atomic_t stop = 0;
static const char *LOGP;

static void on_term(int s) { (void)s; stop = 1; }

static int swallow(Display *d, XErrorEvent *e) { (void)d; (void)e; return 0; }

static void logline(const char *fmt, ...)
{
    va_list ap;
    FILE *f = fopen(LOGP, "a");
    if (!f) return;
    va_start(ap, fmt);
    vfprintf(f, fmt, ap);
    va_end(ap);
    fputc('\n', f);
    fclose(f);
}

int main(int argc, char **argv)
{
    int force = 0;
    for (int i = 1; i < argc; i++) {
        if (strcmp(argv[i], "--force") == 0) force = 1;
        else if (strncmp(argv[i], "--log=", 6) == 0) LOGP = argv[i] + 6;
    }
    if (!LOGP) LOGP = "/tmp/fae-cascade.log";

    /* Single instance.
     *
     * This is started from the i3 config, and `exec` lines do not re-run on
     * reload — only `exec_always` does. Using exec_always means a reload would
     * otherwise leave you with three copies all nudging the same windows, so
     * the second and third must exit at once. flock is released by the kernel
     * when the process dies, so a crash cannot leave a stale lock. */
    {
        const char *lp = getenv("FAE_CASCADE_LOCK");
        char lbuf[512];
        if (!lp) {
            snprintf(lbuf, sizeof lbuf, "%s/.fae-cascade.lock",
                     getenv("XDG_RUNTIME_DIR") ? getenv("XDG_RUNTIME_DIR")
                                               : "/tmp");
            lp = lbuf;
        }
        int lfd = open(lp, O_CREAT | O_RDWR, 0644);
        if (lfd >= 0 && flock(lfd, LOCK_EX | LOCK_NB) != 0) {
            if (getenv("FAE_HUD_VERBOSE") || 1)
                fprintf(stderr, "fae-cascade: already running\n");
            return 0;
        }
        if (lfd >= 0) {
            char pid[32];
            int n = snprintf(pid, sizeof pid, "%d\n", (int)getpid());
            if (write(lfd, pid, (size_t)n) != n) { /* not fatal */ }
        }
    }

    Display *dpy = XOpenDisplay(NULL);
    if (!dpy) { fprintf(stderr, "fae-cascade: no display\n"); return 1; }
    int scr = DefaultScreen(dpy);
    Window root = RootWindow(dpy, scr);

    signal(SIGTERM, on_term);
    signal(SIGINT,  on_term);
    signal(SIGHUP,  on_term);

    /* A destroyed window must not take this down either. Same reason as
     * fae-hud: we read a list of windows and then read attributes off each
     * one, and a client can exit in between. Xlib's default handler would
     * exit() on BadWindow. */
    XSetErrorHandler(swallow);

    Window seen[MAX_SEEN];
    int nseen = 0;
    /* The first tick ADOPTS the windows already on screen and does nothing.
     * Without this, starting fae-cascade treats every window you already had
     * as brand new and tries to cascade all of them — the first run did
     * exactly that, and its log shows it going after six real windows. */
    int primed = 0;

    logline("fae-cascade: up (pid %d, step %dpx)", (int)getpid(), STEP_PX);

    while (!stop) {
        /* Read the managed list. */
        Atom a = XInternAtom(dpy, "_NET_CLIENT_LIST", False);
        Atom actual_type; int actual_format;
        unsigned long nitems, bytes_after;
        unsigned char *data = NULL;
        Window list[MAX_SEEN];
        int n = 0;

        if (a != None &&
            XGetWindowProperty(dpy, root, a, 0, MAX_SEEN, False, AnyPropertyType,
                               &actual_type, &actual_format, &nitems,
                               &bytes_after, &data) == Success && data) {
            if (actual_format == 32) {
                n = (int)(nitems > MAX_SEEN ? MAX_SEEN : nitems);
                memcpy(list, data, (size_t)n * sizeof(Window));
            }
            XFree(data);
        }

        for (int k = 0; k < n; k++) {
            Window w = list[k];

            int already = 0;
            for (int s = 0; s < nseen; s++)
                if (seen[s] == w) { already = 1; break; }
            if (already) continue;
            if (nseen < MAX_SEEN) seen[nseen++] = w;
            if (!primed) continue;   /* first pass: record only */

            /* skip anything that is not a real app window */
            XWindowAttributes wa;
            if (!XGetWindowAttributes(dpy, w, &wa)) continue;
            if (wa.map_state != IsViewable) continue;
            if (wa.override_redirect) continue;
            if (wa.width < MIN_W || wa.height < MIN_H) continue;

            /* how many other windows sit at exactly this position? */
            int twins = 0;
            for (int j = 0; j < n; j++) {
                if (j == k) continue;
                XWindowAttributes oa;
                if (!XGetWindowAttributes(dpy, list[j], &oa)) continue;
                if (oa.override_redirect) continue;
                if (oa.x == wa.x && oa.y == wa.y) twins++;
            }
            if (twins == 0) continue;

            /* Cascade position AND size together.
             *
             * Moving alone cannot work: i3 floats every new window at the
             * full container rect, so a new terminal is 1879px wide on a
             * 1920px screen and there is no room to shift it right — the first
             * two attempts logged a "move" and left all three windows stacked
             * at the same point. Shaving STEP_PX off each edge per twin makes
             * room and produces a proper staircase. */
            int step = STEP_PX * (twins + 1);
            int nw = wa.width  - step;
            int nh = wa.height - step;
            if (nw < MIN_W || nh < MIN_H) {
                logline("fae-cascade: 0x%lx too small to cascade",
                        (unsigned long)w);
                continue;
            }
            int nx = wa.x + step;
            int ny = wa.y + step;
            if (nx + nw > DisplayWidth(dpy, scr)  - 4) nx = DisplayWidth(dpy, scr)  - 4 - nw;
            if (ny + nh > DisplayHeight(dpy, scr) - 4) ny = DisplayHeight(dpy, scr) - 4 - nh;
            if (nx < 4) nx = 4;
            if (ny < 4) ny = 4;
            if (nx == wa.x && ny == wa.y && nw == wa.width && nh == wa.height)
                continue;   /* nowhere to go */

            char cmd[320];
            snprintf(cmd, sizeof cmd,
                     "i3-msg [id=%lu] resize set %d px %d px, move position %d %d",
                     (unsigned long)w, nw, nh, nx, ny);
            if (system(cmd) != 0)
                logline("fae-cascade: nudge failed for 0x%lx", (unsigned long)w);
            else
                logline("fae-cascade: 0x%lx had %d twin(s) at (%d,%d %dx%d) "
                        "-> (%d,%d %dx%d)",
                        (unsigned long)w, twins, wa.x, wa.y, wa.width,
                        wa.height, nx, ny, nw, nh);

            /* Re-read next tick from a clean base. */
            (void)force;
        }

        if (!primed) {
            primed = 1;
            logline("fae-cascade: adopted %d existing window(s)", nseen);
        }

        struct timespec nap = { 0, TICK_MS * 1000L * 1000L };
        nanosleep(&nap, NULL);
    }

    logline("fae-cascade: down");
    XCloseDisplay(dpy);
    return 0;
}

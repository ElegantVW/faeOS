/* mru.c — the recency file. See mru.h for why it has to exist. */
#include "mru.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

const char *mru_path(void)
{
    static char buf[512];
    const char *d = getenv("XDG_RUNTIME_DIR");
    if (!d || !*d) d = "/tmp";
    snprintf(buf, sizeof buf, "%s/fae-hud.mru", d);
    return buf;
}

int mru_load(Window *out, int max)
{
    const char *p = mru_path();
    FILE *f = fopen(p, "r");
    int n = 0;
    if (!f) return 0;
    while (n < max && n < MRU_MAX) {
        unsigned long v;
        if (fscanf(f, "%lx", &v) != 1) break;
        if (v) out[n++] = (Window)v;
    }
    fclose(f);
    return n;
}

static int in_list(const Window *v, int n, Window w)
{
    for (int i = 0; i < n; i++) if (v[i] == w) return 1;
    return 0;
}

void mru_note(const Window *live, int nlive)
{
    /* This maintains a STABLE RING, not a recency list. Both of the obvious
     * alternatives were built and measured, and both toggle instead of walk:
     *
     *   move-to-front (textbook MRU): ring [A,B,C,D], A current, one Alt+Tab
     *     lands on B. Rewriting the ring as [B,A,C,D] means the next gesture
     *     computes "the one after B" — which is A, the window you just left.
     *     Measured: 1a->18->1a->18, a two-window toggle.
     *
     *   record-only-the-committed-window: the ring stays length one, so
     *     entry.c fills the rest of the list from stacking order — which is
     *     static, so it puts the topmost window immediately after the current
     *     one. Measured: the same toggle, and the ring grew 1, 2, 1, 2, ...
     *
     * So: prune what is dead, keep every survivor in its existing slot, and
     * APPEND anything live we have not seen. Appending is what grows the ring
     * to the full window set on the first commit; inserting at the front
     * would reverse the cyclic order and reintroduce the first bug.
     */
    Window prev[MRU_MAX];
    int nprev = mru_load(prev, MRU_MAX);

    Window next[MRU_MAX + 4];
    int n = 0;

    for (int i = 0; i < nprev && n < MRU_MAX; i++)
        if (in_list(live, nlive, prev[i]) && !in_list(next, n, prev[i]))
            next[n++] = prev[i];

    for (int i = 0; i < nlive && n < MRU_MAX; i++)
        if (!in_list(next, n, live[i]))
            next[n++] = live[i];

    const char *p = mru_path();
    char tmp[600];
    snprintf(tmp, sizeof tmp, "%s.tmp%ld", p, (long)getpid());
    FILE *f = fopen(tmp, "w");
    if (!f) return;
    for (int i = 0; i < n; i++) fprintf(f, "%lx\n", (unsigned long)next[i]);
    fclose(f);
    /* Atomic replace, so a crash mid-write cannot leave a half-written list
     * that would scramble the order on the next run. */
    if (rename(tmp, p) != 0) remove(tmp);
}

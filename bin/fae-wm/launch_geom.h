/* launch_geom.h — .desktop parse + fuzzy match. No X. */
#ifndef FAE_WM_LAUNCH_GEOM_H
#define FAE_WM_LAUNCH_GEOM_H

#include <stddef.h>
#include <string.h>

#define LAUNCH_NAME_MAX 128
#define LAUNCH_EXEC_MAX 512

static void launch_strip_field_codes(char *exec)
{
    char *d, *s;
    int sp;
    if (!exec) return;
    d = exec;
    s = exec;
    sp = 1;
    while (*s) {
        if (*s == '%' && s[1]) {
            if (s[1] == '%') {
                *d++ = '%';
                s += 2;
                sp = 0;
                continue;
            }
            s += 2;
            while (*s == ' ' || *s == '\t') s++;
            continue;
        }
        if (*s == ' ' || *s == '\t') {
            if (!sp) {
                *d++ = ' ';
                sp = 1;
            }
            s++;
            continue;
        }
        *d++ = *s++;
        sp = 0;
    }
    while (d > exec && d[-1] == ' ') d--;
    *d = 0;
}

static int launch_truthy(const char *v)
{
    return v && (v[0] == '1' || v[0] == 't' || v[0] == 'T' || v[0] == 'y' ||
                 v[0] == 'Y');
}

static int launch_key(const char *line, size_t n, const char *key, char *out,
                      size_t cap)
{
    size_t k = strlen(key);
    size_t i;
    if (n < k + 1) return 0;
    if (strncmp(line, key, k) != 0) return 0;
    if (line[k] != '=') return 0;
    i = k + 1;
    while (i < n && (line[i] == ' ' || line[i] == '\t')) i++;
    if (n > 0 && line[n - 1] == '\r') n--;
    if (n - i >= cap) n = i + cap - 1;
    memcpy(out, line + i, n - i);
    out[n - i] = 0;
    return 1;
}

static int launch_match(const char *name, const char *exec, const char *q)
{
    const char *hay[2];
    int h;
    size_t nq;
    if (!q || !*q) return 1;
    nq = strlen(q);
    hay[0] = name ? name : "";
    hay[1] = exec ? exec : "";
    for (h = 0; h < 2; h++) {
        const char *p = hay[h];
        for (; *p; p++) {
            size_t i;
            for (i = 0; i < nq; i++) {
                char a = p[i], b = q[i];
                if (!a) break;
                if (a >= 'A' && a <= 'Z') a = (char)(a - 'A' + 'a');
                if (b >= 'A' && b <= 'Z') b = (char)(b - 'A' + 'a');
                if (a != b) break;
            }
            if (i == nq) return 1;
        }
    }
    return 0;
}

/* 1 = usable Application. Hidden/NoDisplay/Link skipped. */
static int launch_parse_desktop(const char *body, char *name, size_t nlen,
                                char *exec, size_t elen, int *terminal)
{
    int in = 0, hidden = 0, nodisp = 0, is_app = 1;
    const char *p;
    if (!body || !name || !exec || nlen == 0 || elen == 0) return 0;
    name[0] = 0;
    exec[0] = 0;
    if (terminal) *terminal = 0;
    p = body;
    while (*p) {
        const char *nl = strchr(p, '\n');
        size_t n = nl ? (size_t)(nl - p) : strlen(p);
        char buf[LAUNCH_EXEC_MAX];
        if (n > 0 && p[n - 1] == '\r') n--;
        if (n > 0 && p[0] == '[') {
            in = (n >= 15 && strncmp(p, "[Desktop Entry]", 15) == 0);
        } else if (in && n > 0 && p[0] != '#' ) {
            if (launch_key(p, n, "Hidden", buf, sizeof buf) && launch_truthy(buf))
                hidden = 1;
            if (launch_key(p, n, "NoDisplay", buf, sizeof buf) &&
                launch_truthy(buf))
                nodisp = 1;
            if (launch_key(p, n, "Terminal", buf, sizeof buf) &&
                launch_truthy(buf) && terminal)
                *terminal = 1;
            if (launch_key(p, n, "Type", buf, sizeof buf))
                is_app = (strcmp(buf, "Application") == 0);
            if (!name[0])
                launch_key(p, n, "Name", name, nlen);
            if (!exec[0])
                launch_key(p, n, "Exec", exec, elen);
        }
        p = nl ? nl + 1 : p + n;
        if (!nl) break;
    }
    if (hidden || nodisp || !is_app || !name[0] || !exec[0]) return 0;
    launch_strip_field_codes(exec);
    return exec[0] != 0;
}

#endif

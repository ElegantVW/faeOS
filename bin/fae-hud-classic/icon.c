/* icon.c — _NET_WM_ICON -> a cairo surface.
 *
 * The property is a list of images; each is two CARD32s (w, h) followed by
 * w*h 32-bit pixels in 0xAARRGGBB. Cairo wants premultiplied ARGB32, and on a
 * little-endian machine that is B,G,R,A in memory, so the word has to be
 * re-ordered AND the colour multiplied by alpha — otherwise icons with
 * transparency come out with black fringes, which is the classic way this
 * looks worse than having no icons at all.
 */
#include "icon.h"
#include "theme.h"

#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#include <X11/Xatom.h>

/* one icon, straight from the property, before scaling */
typedef struct {
    unsigned long *px;   /* w*h, 0xAARRGGBB */
    int            w, h;
} raw_t;

static int pick_best(const unsigned long *data, long n, raw_t *out)
{
    long i = 0;
    int found = 0;
    while (i + 1 < n) {
        long w = (long)data[i], h = (long)data[i + 1];
        i += 2;
        if (w <= 0 || h <= 0 || w > 4096 || h > 4096) break;
        if (i + w * h > n) break;
        /* prefer the largest image that is still at least as big as we need;
         * fall back to the largest available */
        if (!found || (w <= THEME_ICON_PX && out->w < w) ||
            (w <= THEME_ICON_PX && out->w == 0)) {
            out->px = (unsigned long *)(data + i);
            out->w = (int)w;
            out->h = (int)h;
            found = 1;
        }
        i += w * h;
    }
    return found;
}

cairo_surface_t *icon_load(Display *dpy, Window xid, int target_px)
{
    Atom a = XInternAtom(dpy, "_NET_WM_ICON", False);
    Atom actual_type;
    int actual_format;
    unsigned long nitems, bytes_after;
    unsigned char *data = NULL;

    if (a == None) return NULL;
    if (XGetWindowProperty(dpy, xid, a, 0, 1024 * 1024, False, AnyPropertyType,
                           &actual_type, &actual_format, &nitems,
                           &bytes_after, &data) != Success)
        return NULL;
    if (!data) return NULL;
    if (actual_format != 32) { XFree(data); return NULL; }

    raw_t best = { NULL, 0, 0 };
    int ok = pick_best((const unsigned long *)data, (long)nitems, &best);
    if (!ok || !best.px) { XFree(data); return NULL; }

    /* cairo ARGB32 is premultiplied */
    cairo_surface_t *s = cairo_image_surface_create(CAIRO_FORMAT_ARGB32,
                                                     best.w, best.h);
    unsigned char *dst = cairo_image_surface_get_data(s);
    int stride = cairo_image_surface_get_stride(s);

    for (int y = 0; y < best.h; y++) {
        uint32_t *row = (uint32_t *)(dst + (size_t)y * stride);
        for (int x = 0; x < best.w; x++) {
            unsigned long v = best.px[(size_t)y * best.w + x];
            unsigned a = (v >> 24) & 0xff;
            unsigned r = (v >> 16) & 0xff;
            unsigned g = (v >> 8) & 0xff;
            unsigned b = v & 0xff;
            if (a == 0) { row[x] = 0; continue; }
            if (a != 0xff) {
                r = (r * a + 127) / 255;
                g = (g * a + 127) / 255;
                b = (b * a + 127) / 255;
            }
            row[x] = (a << 24) | (r << 16) | (g << 8) | b;
        }
    }
    cairo_surface_mark_dirty(s);
    cairo_surface_flush(s);

    /* ── crop to the visible content, then scale ────────────────────────────
     * Icons from _NET_WM_ICON are rarely edge-to-edge: kitty's cat occupies
     * maybe 60% of its 128x128 box with transparent margins, so every icon
     * appeared to float inside its cell at a different size and the row looked
     * misaligned. Cropping to the alpha bounding box first, then scaling to fit
     * a square and centring, makes them line up — the single biggest thing
     * separating this from a real switcher. */
    int x0 = best.w, y0 = best.h, x1 = -1, y1 = -1;
    for (int y = 0; y < best.h; y++) {
        uint32_t *row = (uint32_t *)(dst + (size_t)y * stride);
        for (int x = 0; x < best.w; x++) {
            if ((row[x] >> 24) > 8) {
                if (x < x0) x0 = x;
                if (x > x1) x1 = x;
                if (y < y0) y0 = y;
                if (y > y1) y1 = y;
            }
        }
    }
    if (x1 < x0 || y1 < y0) {           /* fully transparent: no icon */
        cairo_surface_destroy(s);
        XFree(data);
        return NULL;
    }
    int cw = x1 - x0 + 1, ch = y1 - y0 + 1;

    double sc = (double)target_px / (cw > ch ? cw : ch);
    if (sc > 1.0) sc = 1.0;              /* never upscale a tiny icon */
    int tw = (int)(cw * sc + 0.5), th = (int)(ch * sc + 0.5);
    if (tw < 1) tw = 1;
    if (th < 1) th = 1;

    cairo_surface_t *out = cairo_image_surface_create(CAIRO_FORMAT_ARGB32,
                                                      target_px, target_px);
    cairo_t *cr = cairo_create(out);
    cairo_translate(cr, (target_px - tw) / 2.0, (target_px - th) / 2.0);
    cairo_scale(cr, sc, sc);
    /* clip away the transparent margin, then paint the icon at the crop origin */
    cairo_rectangle(cr, x0, y0, cw, ch);
    cairo_clip(cr);
    cairo_pattern_t *p = cairo_pattern_create_for_surface(s);
    cairo_pattern_set_filter(p, CAIRO_FILTER_GOOD);
    cairo_set_source(cr, p);
    cairo_paint(cr);
    cairo_pattern_destroy(p);
    cairo_destroy(cr);
    cairo_surface_destroy(s);
    cairo_surface_mark_dirty(out);
    XFree(data);
    return out;
}

/* icon.h — window icons for the switcher.
 *
 * Source is _NET_WM_ICON: a CARDINAL array holding one or more images, each
 * as width, height, then width*height 32-bit 0xAARRGGBB pixels.
 *
 * Measured on this machine: kitty publishes a 128x128 image plus three small
 * ones. (Do not try to check this with xprop — this system's xprop renders
 * CARDINAL icon data as coloured blocks, which reads as an empty property.)
 */
#ifndef FAE_HUD_ICON_H
#define FAE_HUD_ICON_H

#include <X11/Xlib.h>
#include <cairo/cairo.h>

/* A cairo ARGB32 image surface holding the window's icon scaled to fit
 * target_px, or NULL when the client publishes nothing usable. Caller frees
 * with cairo_surface_destroy(). */
cairo_surface_t *icon_load(Display *dpy, Window xid, int target_px);

#endif /* FAE_HUD_ICON_H */

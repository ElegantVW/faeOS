/* help.c — Super+h overlay. */
#include "help.h"
#include "theme.h"

#include <string.h>
#include <X11/Xlib.h>
#include <X11/Xatom.h>
#include <cairo/cairo-xlib.h>
#include <pango/pangocairo.h>

static Window help_w = None;
static int help_on = 0;

static const char *HELP =
    "fae-wm\n"
    "\n"
    "Super+Shift+q    close\n"
    "Super+m          minimize\n"
    "Super+Shift+f    maximize\n"
    "Super+f          fullscreen\n"
    "Super+v          next split stacked\n"
    "Super+s          next split side-by-side\n"
    "Super+Shift+Space  float / tile\n"
    "Super+j k l ;    focus\n"
    "Super+Shift+jkl; swap (tiled) or nudge\n"
    "Super+1..0       workspace\n"
    "Super+Return     terminal\n"
    "\n"
    "Super+h or Esc   close this";

int help_visible(void)
{
    return help_on;
}

static void help_paint(wm_t *wm)
{
    if (help_w == None) return;
    int W = 420, H = 340;
    cairo_surface_t *surf = cairo_xlib_surface_create(
        wm->dpy, help_w, DefaultVisual(wm->dpy, wm->scr), W, H);
    cairo_t *cr = cairo_create(surf);
    PangoContext *ctx =
        pango_font_map_create_context(pango_cairo_font_map_get_default());
    PangoLayout *lay = pango_layout_new(ctx);
    PangoFontDescription *desc =
        pango_font_description_from_string(THEME_FONT ":size=11");
    pango_layout_set_font_description(lay, desc);
    pango_layout_set_text(lay, HELP, -1);

    cairo_set_source_rgb(cr, 0x1a / 255.0, 0x0a / 255.0, 0x12 / 255.0);
    cairo_paint(cr);
    cairo_set_source_rgb(cr, 0xe8 / 255.0, 0x79 / 255.0, 0xa0 / 255.0);
    cairo_set_line_width(cr, 2);
    cairo_rectangle(cr, 1, 1, W - 2, H - 2);
    cairo_stroke(cr);
    cairo_move_to(cr, 18, 16);
    pango_cairo_show_layout(cr, lay);

    cairo_destroy(cr);
    cairo_surface_destroy(surf);
    pango_font_description_free(desc);
    g_object_unref(lay);
    g_object_unref(ctx);
    XFlush(wm->dpy);
}

void help_hide(wm_t *wm)
{
    if (help_w == None) return;
    XDestroyWindow(wm->dpy, help_w);
    help_w = None;
    help_on = 0;
}

void help_toggle(wm_t *wm)
{
    if (help_on) {
        help_hide(wm);
        return;
    }
    int W = 420, H = 340;
    int x = (wm->sw - W) / 2, y = (wm->sh - H) / 2;
    XSetWindowAttributes attr;
    memset(&attr, 0, sizeof attr);
    attr.override_redirect = True;
    attr.background_pixel = BlackPixel(wm->dpy, wm->scr);
    attr.event_mask = ExposureMask | KeyPressMask;
    help_w = XCreateWindow(wm->dpy, wm->root, x, y, (unsigned)W, (unsigned)H, 0,
                           CopyFromParent, InputOutput, CopyFromParent,
                           CWOverrideRedirect | CWBackPixel | CWEventMask, &attr);
    XMapRaised(wm->dpy, help_w);
    help_on = 1;
    help_paint(wm);
}

int help_is_win(Window w)
{
    return help_w != None && w == help_w;
}

void help_expose(wm_t *wm)
{
    if (help_on) help_paint(wm);
}

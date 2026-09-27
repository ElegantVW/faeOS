# fae-hud — themed window cycler panel.
#
# Zero runtime dependencies beyond X11 itself: Xlib for the window, Xft for
# antialiased DejaVu Sans Mono (core X bitmap fonts would break the house
# all-mono rule), fontconfig to find the face.
#
#   make            build ./fae-hud
#   make install    copy to ~/bin
#   make clean

CC      ?= gcc
CFLAGS  ?= -O2 -Wall -Wextra -Wno-unused-parameter
PKGS     = x11 xft fontconfig
CFLAGS  += $(shell pkg-config --cflags $(PKGS))
LDLIBS   = $(shell pkg-config --libs $(PKGS))

PREFIX  ?= $(HOME)/bin
BIN      = fae-hud
SRC      = main.c wm.c hud.c
HDR      = wm.h hud.h theme.h

all: $(BIN)

$(BIN): $(SRC) $(HDR)
	$(CC) $(CFLAGS) -o $@ $(SRC) $(LDLIBS)

install: $(BIN)
	install -Dm755 $(BIN) $(PREFIX)/$(BIN)

clean:
	rm -f $(BIN)

.PHONY: all install clean

# fae-wm — Jana, the house window manager.
#
# Tiling by default, EWMH-serving, X11. The Alt+Tab switcher from fae-hud is
# built in and reads the WM's own focus stack: exact recency, mouse clicks
# included, no ring file, no grab races.
#
#   make            build ./fae-wm
#   make install    copy to ~/bin
#   make clean

CC      ?= gcc
CFLAGS  ?= -O2 -Wall -Wextra -Wno-unused-parameter
PKGS     = x11 cairo pangocairo
CFLAGS  += $(shell pkg-config --cflags $(PKGS))
LDLIBS   = $(shell pkg-config --libs $(PKGS))

PREFIX  ?= $(HOME)/bin
BIN      = fae-wm
SRC      = main.c config.c ewmh.c client.c frame.c dock.c panel.c wm.c tile.c help.c launch.c
HDR      = config.h ewmh.h client.h frame.h dock.h panel.h wm.h theme.h dock_geom.h tile.h tile_geom.h help.h launch.h launch_geom.h takeover.h

all: $(BIN)

$(BIN): $(SRC) $(HDR)
	$(CC) $(CFLAGS) -o $@ $(SRC) $(LDLIBS)

test: test_dock
	./test_dock

test_dock: test_dock.c dock_geom.h tile_geom.h takeover.h launch_geom.h
	$(CC) $(CFLAGS) -o $@ test_dock.c

install: $(BIN)
	install -Dm755 $(BIN) $(PREFIX)/$(BIN)

clean:
	rm -f $(BIN) test_dock test_dock

.PHONY: all install clean test

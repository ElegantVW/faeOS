# fae-hud — themed window switcher panel.
#
# Minimal remake: EWMH window list, house pink-chrome panel, Alt+Tab gesture.
# No icons, no window-manager coupling, no daemon.
#
# Libraries: Xlib for the window and its properties, cairo for the drawing
# (round corners and per-pixel alpha both need it), pangocairo for shaped,
# ellipsised text.
#
#   make            build ./fae-hud
#   make install    copy to ~/bin
#   make clean

CC      ?= gcc
CFLAGS  ?= -O2 -Wall -Wextra -Wno-unused-parameter
PKGS     = x11 cairo pangocairo
CFLAGS  += $(shell pkg-config --cflags $(PKGS))
LDLIBS   = $(shell pkg-config --libs $(PKGS))

PREFIX  ?= $(HOME)/bin
BIN      = fae-hud
SRC      = main.c list.c panel.c gesture.c
HDR      = list.h panel.h gesture.h theme.h

all: $(BIN)

$(BIN): $(SRC) $(HDR)
	$(CC) $(CFLAGS) -o $@ $(SRC) $(LDLIBS)

install: $(BIN)
	install -Dm755 $(BIN) $(PREFIX)/$(BIN)

clean:
	rm -f $(BIN)

.PHONY: all install clean

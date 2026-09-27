# fae-hud — themed window cycler panel.
#
# Libraries: Xlib for the window and its properties, cairo for the drawing
# (round corners and per-pixel alpha both need it — Xft has no arc primitive),
# pangocairo for shaped, ellipsised text.
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
SRC      = main.c wm.c hud.c hold.c entry.c icon.c mru.c
HDR      = wm.h hud.h theme.h hold.h entry.h icon.h mru.h

all: $(BIN)

$(BIN): $(SRC) $(HDR)
	$(CC) $(CFLAGS) -o $@ $(SRC) $(LDLIBS)

install: $(BIN)
	install -Dm755 $(BIN) $(PREFIX)/$(BIN)

clean:
	rm -f $(BIN)

.PHONY: all install clean

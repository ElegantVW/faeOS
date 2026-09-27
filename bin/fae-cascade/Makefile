# fae-cascade — nudge new windows that land exactly on top of another.
# Xlib only: it reads window geometry, and the move itself goes through i3-msg
# (see the note at the top of the .c file for why).

CC     ?= gcc
CFLAGS ?= -O2 -Wall -Wextra
CFLAGS += $(shell pkg-config --cflags x11)
LDLIBS  = $(shell pkg-config --libs x11)

PREFIX ?= $(HOME)/bin
BIN     = fae-cascade

all: $(BIN)

$(BIN): fae-cascade.c
	$(CC) $(CFLAGS) -o $@ $< $(LDLIBS)

install: $(BIN)
	install -Dm755 $(BIN) $(PREFIX)/$(BIN)

clean:
	rm -f $(BIN)

.PHONY: all install clean

# Screen clear policy (`pixie-screen`)

## Problem we solved

Every new feature (scry, grace, pixie wait, art preview…) used to patch
`periodic` / `preexec` with another special case. That bit-rotted constantly.

## Rule

**Only one question:** *are there any active holds?*

- **No holds** → clear is allowed (preexec before a command, idle tick).
- **Any hold** → never clear / never tick-wipe.

## API

```bash
pixie-screen hold NAME [seconds]   # block clears (omit seconds = until release)
pixie-screen release NAME
pixie-screen release-all
pixie-screen allowed               # exit 0 if clear OK
pixie-screen clear                 # clear only if allowed
pixie-screen status
pixie-screen purge                 # drop expired TTLs
```

## How hooks use it

| Hook | Action |
|------|--------|
| `preexec` | `pixie-screen clear` before non-empty command |
| `precmd` | never clear; arm idle timer; purge expired holds |
| `periodic` | if tick on && allowed && timer/song → clear + redraw |

## How features use it

```bash
# scry UI
pixie-screen hold scry
# … UI …
pixie-screen release scry

# temporary art preview
pixie-screen hold art 15
pixie-art pixie
# auto-expires in 15s, or: pixie-screen release art

# read grace after a reply (also via pixie-session grace)
pixie-screen hold grace 45
```

Python (ask / wait display):

```python
# hold busy.<pid> while thinking — already wired in ask.py
```

## Adding something new (e.g. pixie-art on the prompt)

1. **Do not** edit `periodic` / `preexec` conditionals.
2. Around the feature:

   ```bash
   pixie-screen hold art 20
   # show art / run TUI
   pixie-screen release art   # if it ends early
   ```

3. Optional: document the hold name in `pixie-screen status` help.

That’s it.

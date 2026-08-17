# Seal — screen lock + greeter

**Role:** Lock the graphical session; optional graphical login face.  
**Status:** lock + PAM + greeter mode · startx integration via `seal-login`

## Surface
- `seal` — lock now (X11 animated face)
- `seal --greeter --session i3` — login face; on success **exec** the session
- `seal-login` — thin wrapper for `~/.xinitrc` (`exec seal-login`)
- `seald` / `seal --daemon` — idle auto-lock (user systemd unit)
- `seal-tui` — configure timeouts, messages, users (with hearth)
- `pixie-lock` — legacy binary name when installed

## Auth
1. hearth socket (multi-user, if daemon up)  
2. **PAM** service `seal` (then `login` / `system-auth`)  
3. `sudo -S -k -v` fallback for the current user only  

Install PAM: `sudo cp faeos/config/seal.pam /etc/pam.d/seal`  
(or run `fae-bootstrap.sh`).

## Greeter (startx path) — current default

Seal is an **X11 client** (`XOpenDisplay`). It cannot run *before* Xorg starts.
To make Seal feel like a normal greeter (first interactive face, only password):

1. **kmscon console autologin** (silent — no password at TTY)
2. `~/.zprofile` → `startx` when `DISPLAY` is empty
3. `~/.xinitrc` → `exec seal-login "…"` (Seal greeter)
4. On success → session (`dbus-run-session i3`)

```bash
# ~/.xinitrc (installed)
exec seal-login "dbus-run-session i3"
```

User-visible path: **boot → Seal “welcome” → desktop**.  
Console autologin is plumbing so X can start; it is *not* an unlocked session.

## Lock policy
- Failed attempts **never** unlock  
- Backoff after 3 / 5 / 8 fails (2s / 5s / 15s)  
- Password dots redraw immediately  

## User management (greeter polish)

- **List:** hearth socket `LIST` if up, else `/etc/passwd` (uid ≥ 1000) + hide/display from `~/.config/pixie/hearth.json`
- **Face:** username (`< name >` when multiple), password dots, Tab/↑↓ cycle users
- **Auth:** PAM for selected user; desktop still continues as console autologin uid (not true multi-user session)
- **seal-tui:** hide/display, add/remove via hearth, **p** / Set Pass → `sudo chpasswd`

## Boot splash (UKI)

Arch UKI used `--splash /usr/share/systemd/bootctl/splash-arch.bmp`.

faeOS:
```bash
python3 faeos/tools/make_boot_splash.py   # → assets/boot/splash-faeos.bmp
sudo install -m 644 faeos/assets/boot/splash-faeos.bmp /usr/share/faeos/
# /etc/mkinitcpio.d/linux.preset:
#   default_options="--splash /usr/share/faeos/splash-faeos.bmp"
sudo mkinitcpio -p linux
```

Revert: restore Arch splash path (backup `linux.preset.bak.arch-splash`) and rebuild.

**Note:** Plymouth is the Linux *boot splash* framework (named after the English city) — not the gin. This machine uses systemd-stub UKI splash instead of Plymouth.

## Later (plan more)
- True pre-session greeter without console autologin → greetd/ly *or* DRM/kms Seal
- Multi-user greeter session as *other* uids (needs root/greetd)
- seald reliably After=graphical-session / i3 exec hook
- Wayland session lock protocol  

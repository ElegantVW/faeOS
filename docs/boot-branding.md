# faeOS boot branding

Two layers work together:

1. **UKI BMP** — instant first frame in the EFI stub (blink-short).
2. **Plymouth** — stays for the rest of boot with spinner, **✦ Entering the Realm ✦**, and a pink progress bar (systemd boot progress when available).

Plymouth is the Linux *boot splash* framework (named after the English city; **not** the gin).

---

## UKI splash (early)

| | |
|--|--|
| Source art | `faeos/tools/make_boot_splash.py` |
| Asset | `faeos/assets/boot/splash-faeos.bmp` (566×167) |
| Install | `/usr/share/faeos/splash-faeos.bmp` |
| Hook | `linux.preset` → `--splash /usr/share/faeos/splash-faeos.bmp` |

```bash
python3 ~/faeos/tools/make_boot_splash.py
sudo install -m 644 ~/faeos/assets/boot/splash-faeos.bmp /usr/share/faeos/
sudo mkinitcpio -p linux
```

---

## Plymouth — “Entering the Realm”

| | |
|--|--|
| Theme sources | `faeos/assets/plymouth/faeos/` |
| Assets script | `faeos/tools/make_plymouth_assets.py` |
| Install | `/usr/share/plymouth/themes/faeos/` + `plymouth-set-default-theme faeos` |
| mkinitcpio | `plymouth` hook after `kms` |
| Cmdline | `/etc/kernel/cmdline`: `quiet splash … systemd.show_status=false` |
| Handoff | `~/.zprofile` runs `plymouth quit` then `startx` → Seal greeter |

Regenerate theme after art changes:

```bash
python3 ~/faeos/tools/make_plymouth_assets.py
sudo cp -a ~/faeos/assets/plymouth/faeos/. /usr/share/plymouth/themes/faeos/
sudo plymouth-set-default-theme -R faeos   # -R rebuilds initramfs on some setups; we use mkinitcpio
sudo mkinitcpio -p linux
```

### Recovery (splash stuck / black screen)

At GRUB, edit the entry and add:

```
plymouth.enable=0
```

or remove `splash`. Then:

```bash
sudo plymouth-set-default-theme text
sudo mkinitcpio -p linux
```

### Revert UKI BMP to Arch

```bash
sudo cp /etc/mkinitcpio.d/linux.preset.bak.arch-splash /etc/mkinitcpio.d/linux.preset
# or set --splash back to /usr/share/systemd/bootctl/splash-arch.bmp
sudo mkinitcpio -p linux
```

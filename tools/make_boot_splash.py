#!/usr/bin/env python3
"""Render faeOS crystal + title as a UKI/bootctl splash BMP.

Matches seal's FAE_SIGIL geometry and the stock Arch splash size (566×167)
so systemd-stub accepts it without fuss.

  python3 tools/make_boot_splash.py
  # → assets/boot/splash-faeos.bmp
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# Same mono grid as faeos/seal/src/render.rs FAE_SIGIL
FAE_SIGIL = [
    "       *       ",
    "      / \\      ",
    "     /   \\     ",
    "    /  +  \\    ",
    "   /       \\   ",
    "   \\       /   ",
    "    \\  |  /    ",
    "     \\ | /     ",
    "      \\|/      ",
    "       V       ",
]

W, H = 566, 167
BG = (0x12, 0x08, 0x0E, 255)  # kmscon-ish dark
PINK = (0xE8, 0x79, 0xA0, 255)
SILVER = (0xC0, 0xC0, 0xC8, 255)
DIM = (0x9D, 0x5C, 0x75, 255)

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets" / "boot" / "splash-faeos.bmp"


def font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in (
        "/usr/share/fonts/TTF/DejaVuSansMono.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        "/usr/share/fonts/noto/NotoSansMono-Regular.ttf",
        "/usr/share/fonts/TTF/DejaVuSans.ttf",
    ):
        p = Path(path)
        if p.is_file():
            return ImageFont.truetype(str(p), size=size)
    return ImageFont.load_default()


def main() -> None:
    img = Image.new("RGBA", (W, H), BG)
    draw = ImageDraw.Draw(img)

    # Soft pink vignette corners
    for y in range(H):
        for x in (0, 1, 2, W - 1, W - 2, W - 3):
            draw.point((x, y), fill=DIM)
    for x in range(W):
        for y in (0, 1, 2, H - 1, H - 2, H - 3):
            draw.point((x, y), fill=DIM)

    mono = font(11)
    title_f = font(28)
    sub_f = font(12)

    # Crystal block — left-of-center
    line_h = 12
    crystal_h = len(FAE_SIGIL) * line_h
    crystal_w = draw.textlength(FAE_SIGIL[0], font=mono)
    cx0 = 48
    cy0 = (H - crystal_h) // 2 - 2
    for i, line in enumerate(FAE_SIGIL):
        draw.text((cx0, cy0 + i * line_h), line, font=mono, fill=PINK)

    # Title block — right of crystal
    title = "faeOS"
    subtitle = "a fae light on bare metal"
    tx = int(cx0 + crystal_w + 36)
    ty = (H - 40) // 2
    draw.text((tx, ty), title, font=title_f, fill=PINK)
    draw.text((tx, ty + 36), subtitle, font=sub_f, fill=SILVER)

    # Small sigil sparkle far right
    draw.text((W - 40, H // 2 - 8), "✦", font=title_f, fill=PINK)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    # bootctl wants classic BMP; convert via RGB then save as BMP
    rgb = Image.new("RGB", (W, H), BG[:3])
    rgb.paste(img, mask=img.split()[3])
    rgb.save(OUT, format="BMP")
    print(f"wrote {OUT} ({W}x{H})")


if __name__ == "__main__":
    main()

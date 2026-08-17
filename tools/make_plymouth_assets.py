#!/usr/bin/env python3
"""Generate faeOS Plymouth theme images (crystal, spinner, progress bar)."""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

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

BG = (0x12, 0x08, 0x0E, 0)  # transparent for overlays; solid bg separate
PINK = (0xE8, 0x79, 0xA0, 255)
PINK_DIM = (0x9D, 0x5C, 0x75, 255)
SILVER = (0xC0, 0xC0, 0xC8, 255)
TRACK = (0x3A, 0x1A, 0x28, 255)
WHITE = (255, 255, 255, 255)

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets" / "plymouth" / "faeos"


def font(size: int):
    for path in (
        "/usr/share/fonts/TTF/DejaVuSansMono.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        "/usr/share/fonts/TTF/DejaVuSans.ttf",
    ):
        if Path(path).is_file():
            return ImageFont.truetype(path, size=size)
    return ImageFont.load_default()


def make_crystal(path: Path) -> None:
    f = font(22)
    # measure
    line_h = 24
    w = 320
    h = len(FAE_SIGIL) * line_h + 16
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    for i, line in enumerate(FAE_SIGIL):
        tw = draw.textlength(line, font=f)
        x = (w - tw) / 2
        y = 8 + i * line_h
        col = PINK if any(c in line for c in "*+V") else PINK_DIM
        draw.text((x, y), line, font=f, fill=col)
    img.save(path)


def make_spinner(path: Path, size: int = 96) -> None:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    m = 8
    # arc of a ring (not full circle) — rotation makes it spin
    bbox = [m, m, size - m - 1, size - m - 1]
    draw.arc(bbox, start=-40, end=220, fill=PINK, width=6)
    # small head sparkle
    draw.ellipse([size // 2 + 28, m + 4, size // 2 + 40, m + 16], fill=PINK)
    img.save(path)


def make_progress_box(path: Path, w: int = 420, h: int = 14) -> None:
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle([0, 0, w - 1, h - 1], radius=h // 2, outline=PINK_DIM, width=2)
    draw.rounded_rectangle([2, 2, w - 3, h - 3], radius=h // 2 - 2, fill=TRACK)
    img.save(path)


def make_progress_bar(path: Path, w: int = 416, h: int = 10) -> None:
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle([0, 0, w - 1, h - 1], radius=h // 2, fill=PINK)
    # soft highlight
    draw.rounded_rectangle([2, 1, w - 3, h // 2], radius=h // 4, fill=(255, 200, 220, 80))
    img.save(path)


def make_solid_bg(path: Path, w: int = 1920, h: int = 1080) -> None:
    img = Image.new("RGBA", (w, h), (0x12, 0x08, 0x0E, 255))
    # faint vignette
    draw = ImageDraw.Draw(img)
    for i in range(40):
        a = int(30 * (1 - i / 40))
        draw.rectangle([i, i, w - 1 - i, h - 1 - i], outline=(0xE8, 0x79, 0xA0, a))
    img.save(path)


def make_dialog_bits(out: Path) -> None:
    # minimal password dialog assets (recolor of script theme idea)
    box = Image.new("RGBA", (360, 72), (0, 0, 0, 0))
    d = ImageDraw.Draw(box)
    d.rounded_rectangle([0, 0, 359, 71], radius=12, fill=(0x1A, 0x0C, 0x14, 230), outline=PINK, width=2)
    box.save(out / "box.png")

    entry = Image.new("RGBA", (260, 36), (0, 0, 0, 0))
    d = ImageDraw.Draw(entry)
    d.rounded_rectangle([0, 0, 259, 35], radius=8, fill=TRACK, outline=PINK_DIM, width=1)
    entry.save(out / "entry.png")

    lock = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
    d = ImageDraw.Draw(lock)
    d.rounded_rectangle([8, 14, 24, 28], radius=3, outline=PINK, width=2)
    d.arc([10, 4, 22, 18], start=0, end=180, fill=PINK, width=2)
    lock.save(out / "lock.png")

    bullet = Image.new("RGBA", (12, 12), (0, 0, 0, 0))
    d = ImageDraw.Draw(bullet)
    d.ellipse([2, 2, 10, 10], fill=PINK)
    bullet.save(out / "bullet.png")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    make_crystal(OUT / "crystal.png")
    make_spinner(OUT / "spinner.png")
    make_progress_box(OUT / "progress_box.png")
    make_progress_bar(OUT / "progress_bar.png")
    make_solid_bg(OUT / "background.png")
    make_dialog_bits(OUT)
    print(f"wrote assets → {OUT}")


if __name__ == "__main__":
    main()

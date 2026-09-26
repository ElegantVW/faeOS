#!/usr/bin/env python3
"""storyify — landscape master + box-voice captions -> 1080x1920 story MP4.

Layout: video scaled to 1080 wide on Night, top prompt-style caption box,
bottom chapter line per segment (see storyify.yaml). DejaVu Sans Mono,
house palette only.

Usage: storyify.py ENTRY --src IN.MP4 --out OUT.MP4 [--yaml storyify.yaml]
Requires: PIL, numpy, pyyaml (or plain parse below), ffmpeg on PATH.
"""
import argparse
import os
import subprocess
import sys
import tempfile

from PIL import Image, ImageDraw, ImageFont

W, H = 1080, 1920
NIGHT = (26, 18, 24)
PARCH = (240, 228, 238)
ROSE = (232, 160, 180)
DUSK = (107, 111, 168)
MONO = "DejaVuSansMono"
MONO_B = "DejaVuSansMono-Bold"


def load_tracks(path):
    """Minimal YAML subset parser (entries -> title/what/flavor/chapters)."""
    entries, cur, chap = {}, None, None
    with open(path) as f:
        for raw in f:
            line = raw.rstrip("\n")
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            if s == "entries:":
                continue
            if s.endswith(":") and not s.startswith(("- ", '"')) and line.startswith("  ") and not line.startswith("    "):
                cur = s[:-1]
                entries[cur] = {"chapters": []}
                continue
            if cur and ":" in s and not s.startswith("-"):
                k, v = s.split(":", 1)
                if k.strip() == "chapters":
                    continue
                entries[cur][k.strip()] = v.strip().strip('"')
                continue
            if s.startswith("- ["):
                inner = s[3:].rstrip("]")
                a, b, c = [x.strip() for x in inner.split(",", 2)]
                entries[cur]["chapters"].append((float(a), float(b), c.strip().strip('"')))
    return entries


def text_box(entry, tracks):
    """Top prompt-style box PNG (1080x300)."""
    img = Image.new("RGB", (W, 300), NIGHT)
    d = ImageDraw.Draw(img)
    f_big = ImageFont.truetype(MONO_B, 40)
    f_mid = ImageFont.truetype(MONO, 30)
    f_sml = ImageFont.truetype(MONO, 26)
    d.rounded_rectangle([(24, 24), (W - 24, 276)], radius=28, outline=ROSE, width=3)
    t = tracks[entry]
    d.text((60, 52), f"* {t['title']} *", font=f_big, fill=PARCH)
    d.text((60, 122), t["what"], font=f_mid, fill=ROSE)
    d.text((60, 178), f"~ {t['flavor']}", font=f_sml, fill=DUSK)
    # footer shimmer line
    d.text((60, 228), "ElegantVW", font=f_sml, fill=DUSK)
    return img


def chapter_card(text):
    """Bottom chapter strip PNG (1080x110, transparent)."""
    img = Image.new("RGBA", (W, 110), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    f = ImageFont.truetype(MONO, 30)
    bb = d.textbbox((0, 0), text, font=f)
    tw = bb[2] - bb[0]
    d.rounded_rectangle([(W // 2 - tw // 2 - 24, 8), (W // 2 + tw // 2 + 24, 102)],
                        radius=20, fill=NIGHT + (235,))
    d.text((W // 2 - tw // 2, 30), text, font=f, fill=PARCH)
    return img


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("entry")
    ap.add_argument("--src", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--yaml", default=os.path.join(os.path.dirname(__file__), "storyify.yaml"))
    args = ap.parse_args()

    tracks = load_tracks(args.yaml)
    if args.entry not in tracks:
        print(f"unknown entry {args.entry}", file=sys.stderr)
        return 1
    t = tracks[args.entry]

    tmp = tempfile.mkdtemp(prefix="storyify-")
    box_path = os.path.join(tmp, "box.png")
    text_box(args.entry, tracks).save(box_path)

    # probe source size
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "csv=p=0", args.src],
        capture_output=True, text=True, check=True)
    sw, sh = (int(x) for x in probe.stdout.strip().split(","))
    portrait = sh > sw

    fc = ["ffmpeg", "-y", "-v", "error", "-i", args.src]
    filters = []
    if portrait:
        # contain narrow sources (e.g. window crops): scale to width, pad Night
        filters.append("[0:v]scale=1080:-2,format=yuv420p[vfit]")
        filters.append("[vfit]pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=#1A1218[vbase]")
        vy = "(1920-ih)/2"
    else:
        filters.append("[0:v]scale=1080:675,format=yuv420p[vvid]")
        filters.append("[vvid]pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=#1A1218[vbase]")
        vy = "(1920-675)/2"
    filters.append(f"movie={box_path}[box];[vbase][box]overlay=0:60[v1]")
    last = "[v1]"
    for i, (a, b, text) in enumerate(t["chapters"]):
        cp = os.path.join(tmp, f"ch{i}.png")
        chapter_card(text).save(cp)
        filters.append(f"movie={cp}[ch{i}];{last}[ch{i}]overlay=0:{H - 190}:enable='between(t,{a},{b})'[v{i + 2}]")
        last = f"[v{i + 2}]"
    filters.append(f"{last}format=yuv420p")
    cmd = fc + ["-filter_complex", ";".join(filters), "-c:v", "libx264",
                "-pix_fmt", "yuv420p", "-crf", "21", "-movflags", "+faststart", args.out]
    subprocess.run(cmd, check=True)
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

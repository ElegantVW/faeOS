#!/usr/bin/env python3
"""story2clip — 5s glitter-glitch story MP4 from a story PNG.

Motion: slow zoom + palette slice-glitch + twinkling glitter (accent +
Gold/Ice), fade in/out. Deterministic per --seed. House palette only.

Usage: story2clip.py IN.PNG --accent HEX --out OUT.MP4 [--secs 5 --fps 24]
Requires: PIL, numpy, ffmpeg on PATH.
"""
import argparse
import math
import random
import subprocess
import sys
import tempfile
import os

from PIL import Image, ImageDraw
import numpy as np

W, H = 1080, 1920
GLITTER = ["#F0D8A0", "#D4B4E8", "#C8E8EC"]  # Gold, Lilac, Ice


def hexrgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("--accent", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--secs", type=float, default=5.0)
    ap.add_argument("--fps", type=int, default=24)
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()

    rng = random.Random(args.seed)
    base = Image.open(args.src).convert("RGB")
    if base.size != (W, H):
        base = base.resize((W, H))
    arr0 = np.asarray(base).astype(np.int16)
    accent = np.array(hexrgb(args.accent), dtype=np.int16)

    n = int(args.secs * args.fps)
    # glitter stars: fixed positions, twinkle phases (more + bigger = whimsy)
    stars = [
        (rng.randrange(W), rng.randrange(H), rng.random() * math.tau, rng.choice(GLITTER))
        for _ in range(120)
    ]
    # sparkle-burst pops: expanding rings that fade over ~8 frames
    bursts = [
        (rng.randrange(n // 8, n - n // 8), rng.randrange(100, W - 100),
         rng.randrange(200, H - 300), rng.choice(GLITTER))
        for _ in range(max(2, int(args.secs * 0.8)))
    ]
    # glitch events: (frame, band_y, band_h, shift, tint_strength)
    glitches = []
    for _ in range(max(2, int(args.secs * 1.2))):
        f = rng.randrange(n // 8, n - n // 8)
        glitches.append(
            (f, rng.randrange(0, H - 60), rng.randrange(24, 90),
             rng.choice([-14, -8, 8, 14]), rng.uniform(0.25, 0.6))
        )

    tmp = tempfile.mkdtemp(prefix="storyclip-")
    for i in range(n):
        t = i / max(n - 1, 1)
        # slow zoom 1.00 -> 1.06 + gentle bob around the sigil
        z = 1.0 + 0.06 * t
        zw, zh = int(W * z), int(H * z)
        frame = base.resize((zw, zh), Image.BILINEAR)
        bob = int(10 * math.sin(t * math.tau * 1.2))
        cx = min(max(zw // 2, W // 2), zw - W // 2)
        cy = min(max(int(zh * 0.42) + bob, H // 2), zh - H // 2)
        frame = frame.crop((cx - W // 2, cy - H // 2, cx + W // 2, cy + H // 2))
        a = np.asarray(frame).astype(np.int16)

        # breathing shimmer: faint accent lift oscillating over the clip
        shimmer = 0.04 * (0.5 + 0.5 * math.sin(t * math.tau * 0.8))
        a = a + (accent - a) * shimmer * (a.mean(axis=2, keepdims=True) > 40)

        # slice glitch on event frames (+1 decay frame)
        for (f, by, bh, sh, k) in glitches:
            if i == f or i == f + 1:
                kk = k if i == f else k * 0.4
                band = a[by : by + bh].copy()
                band = np.roll(band, sh, axis=1)
                lift = (accent - band) * kk
                a[by : by + bh] = np.clip(band + lift, 0, 255)

        img = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
        d = ImageDraw.Draw(img)
        # glitter twinkle (slower, bigger)
        for (x, y, ph, col) in stars:
            b = 0.5 + 0.5 * math.sin(ph + t * 6.0)
            if b < 0.5:
                continue
            r = 1 + int(3 * b)
            c = tuple(int(v * (0.35 + 0.65 * b)) for v in hexrgb(col))
            d.line([(x - r * 2, y), (x + r * 2, y)], fill=c)
            d.line([(x, y - r * 2), (x, y + r * 2)], fill=c)
        # sparkle-burst pops
        for (f, x, y, col) in bursts:
            k = i - f
            if 0 <= k < 9:
                r = 6 + k * 9
                al = 1.0 - k / 9.0
                c = tuple(int(v * al) for v in hexrgb(col))
                for dx, dy in ((r, 0), (-r, 0), (0, r), (0, -r),
                               (int(r * 0.7), int(r * 0.7)), (int(-r * 0.7), int(r * 0.7)),
                               (int(r * 0.7), int(-r * 0.7)), (int(-r * 0.7), int(-r * 0.7))):
                    d.ellipse([(x + dx - 2, y + dy - 2), (x + dx + 2, y + dy + 2)], fill=c)
        # fade in/out
        if i < 12 or i >= n - 12:
            k = min(i, n - 1 - i) / 12.0
            img = Image.blend(Image.new("RGB", (W, H), (26, 18, 24)), img, max(k, 0.0))
        img.save(os.path.join(tmp, f"f{i:04d}.png"))

    cmd = [
        "ffmpeg", "-y", "-v", "error", "-framerate", str(args.fps),
        "-i", os.path.join(tmp, "f%04d.png"),
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "21",
        "-movflags", "+faststart", args.out,
    ]
    subprocess.run(cmd, check=True)
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

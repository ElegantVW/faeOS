#!/usr/bin/env python3
"""Compose *Glass Fog* — murmur theme (original GBA/PSG-style waltz).

Core idea (v3):
  A steady vampiresque piano (1–2–3) holds ONE looping progression through the piece.
  Section layers (lead, echo, pads, climax sparkle) ride *on top* of that piano —
  they never replace the waltz engine.

Form (3/4): intro 4 · waltz 24 · bridge 16 · climax 16 · comedown 8 · reintro 4
Default ~94 BPM. Whole piece circles for game-loop replay.
"""
from __future__ import annotations

import argparse
import math
import pathlib
import random
import struct
import wave
from shutil import copy2

SR = 44100
# Base D4=62; default piece is transposed down (see --transpose).
ROOT_D4 = 62
STEPS = {1: 0, 2: 2, 3: 4, 4: 5, 5: 7, 6: 9, 7: 11}

# Looping harmonic engine (vampiresque waltz in D-major color):
#   D → A → Bm → F#m   (I – V – vi – iii), 2 bars each → 8-bar cycle
# Degrees: 1, 5, 6, 3
PROG = [1, 1, 5, 5, 6, 6, 3, 3]

# Chord tones over each root (include maj7 / soft 9 for heavenly lift)
CHORDS = {
    1: (1, 3, 5, 7),   # D F# A C#
    5: (5, 7, 2, 4),   # A C# E G
    6: (6, 1, 3, 5),   # B D F# A
    3: (3, 5, 7, 2),   # F# A C# E
}


def hz(midi: float) -> float:
    return 440.0 * (2.0 ** ((midi - 69.0) / 12.0))


_TRANSPOSE = 0  # semitones; set in compose()


def deg(d: int, oct: int = 0) -> float:
    d = int(d)
    while d < 1:
        d += 7
        oct -= 1
    while d > 7:
        d -= 7
        oct += 1
    return ROOT_D4 + STEPS[d] + 12 * oct + _TRANSPOSE


def pulse(f: float, t: float, duty: float = 0.5) -> float:
    return 0.42 if (t * f) % 1.0 < duty else -0.42


def tri(f: float, t: float) -> float:
    x = 0.0
    for k, a in ((1, 1.0), (3, -1 / 9), (5, 1 / 25)):
        x += a * math.sin(2 * math.pi * f * k * t)
    return x * 0.65


def sine(f: float, t: float) -> float:
    return math.sin(2 * math.pi * f * t)


def env(t: float, t0: float, t1: float, a: float, d: float, s: float, r: float) -> float:
    if t < t0 or t > t1 + r:
        return 0.0
    if t > t1:
        return s * max(0.0, 1.0 - (t - t1) / max(r, 1e-6))
    u = t - t0
    if u < a:
        return u / max(a, 1e-6)
    if u < a + d:
        return 1.0 - (1.0 - s) * ((u - a) / max(d, 1e-6))
    return s


class Score:
    def __init__(self) -> None:
        self.ev: list[tuple] = []

    def add(
        self,
        start: float,
        dur: float,
        midi: float,
        amp: float,
        kind: str = "pulse",
        duty: float = 0.5,
        a: float = 0.01,
        d: float = 0.06,
        s: float = 0.7,
        r: float = 0.12,
    ) -> None:
        if dur <= 0 or amp <= 0:
            return
        self.ev.append((start, dur, float(midi), amp, kind, duty, a, d, s, r))


def root_at(bar: int) -> int:
    """Progression always cycles — same engine every section."""
    return PROG[bar % 8]


def piano_waltz(
    sc: Score,
    bar: int,
    *,
    dens: float = 1.0,
    bass_amp: float = 0.17,
    chord_amp: float = 0.10,
) -> None:
    """Steady waltz piano + lower-octave companion.

    Main piano: mid register 1–2–3 (bass root + dyads).
    Low piano: octave below — strong on **ONE**, lighter on two–three
    so the vampiresque lilt is anchored without muddying the mid hand.
    """
    bs = bar * 3.0
    root = root_at(bar)
    ct = CHORDS[root]
    ba = bass_amp * dens
    ca = chord_amp * dens
    # low companion levels (relative to dens)
    low1 = 0.14 * dens  # ONE — weight
    low23 = 0.055 * dens  # two / three — soft footprint

    # ── Lower-octave piano (accompaniment) ───────────────────────────
    # Beat 1 — deep ONE (root + soft fifth for body, not a full chord)
    sc.add(bs, 1.05, deg(root, -1), low1, "tri", a=0.015, d=0.1, s=0.5, r=0.22)
    sc.add(bs + 0.03, 0.9, deg(ct[2], -1), low1 * 0.4, "sine", a=0.03, d=0.12, s=0.4, r=0.2)
    # Beat 2 — light low dyad
    sc.add(bs + 1.0, 0.8, deg(ct[0], 0), low23, "tri", a=0.02, d=0.08, s=0.4, r=0.15)
    sc.add(bs + 1.06, 0.7, deg(ct[2], 0), low23 * 0.7, "sine", a=0.025, d=0.08, s=0.35, r=0.14)
    # Beat 3 — light low dyad
    sc.add(bs + 2.0, 0.8, deg(ct[1], 0), low23 * 0.9, "tri", a=0.02, d=0.08, s=0.4, r=0.15)
    sc.add(bs + 2.06, 0.7, deg(ct[3], 0), low23 * 0.55, "sine", a=0.025, d=0.08, s=0.35, r=0.14)

    # ── Main piano (mid hand) ────────────────────────────────────────
    # Beat 1 — root (sits above the deep ONE)
    sc.add(bs, 0.95, deg(root, 0), ba, "tri", a=0.012, d=0.08, s=0.55, r=0.18)

    # Beat 2 — two-note dyad
    sc.add(bs + 1.0, 0.85, deg(ct[0], 1), ca, "pulse", 0.45, a=0.01, d=0.06, s=0.45, r=0.14)
    sc.add(bs + 1.08, 0.78, deg(ct[2], 1), ca * 0.75, "pulse", 0.5, a=0.02, d=0.06, s=0.4, r=0.14)

    # Beat 3 — two-note dyad
    sc.add(bs + 2.0, 0.85, deg(ct[1], 1), ca * 0.9, "pulse", 0.4, a=0.01, d=0.06, s=0.45, r=0.14)
    sc.add(bs + 2.08, 0.78, deg(ct[3], 1), ca * 0.6, "sine", a=0.02, d=0.08, s=0.5, r=0.16)


def melody_ride(
    sc: Score,
    start_bar: int,
    notes: list[tuple[int, int, float, float]],
    amp: float = 0.12,
    *,
    echo: bool = True,
) -> None:
    """Lead above the piano; optional sparse echo (not every note)."""
    base = start_bar * 3.0
    for i, (d, o, off, dn) in enumerate(notes):
        sc.add(
            base + off,
            dn,
            deg(d, o),
            amp,
            "pulse",
            0.28,
            a=0.015,
            d=0.05,
            s=0.55,
            r=0.2,
        )
        # echo only every other note — less clutter
        if echo and i % 2 == 0:
            echo_midi = deg(d, o) - 5 if d >= 3 else deg(d + 2, max(0, o - 1))
            sc.add(
                base + off + 1.0,
                max(0.45, dn * 0.7),
                echo_midi,
                amp * 0.35,
                "pulse",
                0.4,
                a=0.04,
                d=0.08,
                s=0.35,
                r=0.22,
            )


def compose(bpm: float = 94.0, transpose: int = -4) -> tuple[list[int], float]:
    global _TRANSPOSE
    _TRANSPOSE = int(transpose)
    beat = 60.0 / bpm
    bars = 72
    dur = bars * 3 * beat
    n = int(SR * dur)
    sc = Score()

    # ═══════════════ INTRO / FOG (0–3): piano arrives ═══════════════
    for bar in range(0, 4):
        bs = bar * 3.0
        # thin fog: one pad tone, second only later
        sc.add(bs, 3.1, deg(1, 1), 0.08, "sine", a=0.25, d=0.2, s=0.85, r=0.5)
        if bar >= 2:
            sc.add(bs + 0.5, 2.6, deg(5, 1), 0.055, "sine", a=0.3, d=0.2, s=0.8, r=0.5)
        dens = 0.3 + 0.18 * bar
        piano_waltz(sc, bar, dens=dens, bass_amp=0.14, chord_amp=0.07)

    # ═══════════════ WALTZ BODY (4–27): piano + sparse lead ══════════
    for bar in range(4, 28):
        piano_waltz(sc, bar, dens=1.0)

    # fewer, longer melody notes (3–4 per 4-bar cell)
    waltz_phrases = [
        (4, [(5, 1, 0.5, 2.2), (3, 1, 3.5, 2.5), (5, 1, 6.5, 2.5)]),
        (8, [(3, 1, 0.0, 2.0), (5, 1, 2.5, 2.0), (1, 2, 5.0, 3.5)]),
        (12, [(1, 1, 0.5, 2.5), (5, 1, 3.5, 2.0), (6, 1, 6.0, 2.5)]),
        (16, [(5, 1, 0.0, 2.0), (1, 2, 2.5, 3.0), (5, 1, 6.5, 2.5)]),
        (20, [(6, 1, 0.5, 2.5), (5, 1, 3.5, 2.0), (3, 1, 6.0, 3.0)]),
        (24, [(1, 1, 0.0, 2.5), (3, 1, 3.0, 2.5), (5, 1, 6.0, 3.0)]),
    ]
    for sb, notes in waltz_phrases:
        melody_ride(sc, sb, notes, amp=0.105, echo=True)

    # occasional long color veil (every 4 bars only)
    for bar in range(4, 28, 4):
        bs = bar * 3.0
        ct = CHORDS[root_at(bar)]
        sc.add(bs + 0.3, 6.0, deg(ct[3], 1), 0.03, "sine", a=0.4, d=0.25, s=0.7, r=0.7)

    # ═══════════════ BRIDGE (28–43) ═══════════════════════════════════
    for bar in range(28, 44):
        local = bar - 28
        dens = 1.0 + 0.08 * (local / 15.0)
        piano_waltz(sc, bar, dens=min(1.1, dens), bass_amp=0.16, chord_amp=0.09)

    bridge_mel = [
        (28, [(1, 1, 0.0, 2.0), (5, 1, 2.5, 2.0), (6, 1, 5.0, 2.5), (5, 1, 8.0, 3.0)]),
        (32, [(5, 1, 0.5, 2.0), (1, 2, 3.0, 2.5), (6, 1, 6.0, 2.0), (5, 1, 8.5, 2.5)]),
        (36, [(6, 1, 0.0, 2.0), (3, 1, 2.5, 2.0), (5, 1, 5.0, 2.5), (1, 2, 8.0, 3.0)]),
        (40, [(1, 2, 0.0, 2.0), (5, 1, 2.5, 2.0), (3, 1, 5.0, 2.5), (1, 1, 8.0, 3.0)]),
    ]
    for sb, notes in bridge_mel:
        melody_ride(sc, sb, notes, amp=0.11, echo=True)

    for bar in range(28, 44):
        bs = bar * 3.0
        local = bar - 28
        # only one soft and-tone per bar, not three
        if local % 2 == 1:
            ct = CHORDS[root_at(bar)]
            sc.add(bs + 1.5, 0.7, deg(ct[2], 2), 0.04, "pulse", 0.35, a=0.03, d=0.06, s=0.4, r=0.12)
        if local % 4 == 2:
            ct = CHORDS[root_at(bar)]
            sc.add(bs + 0.4, 2.4, deg(ct[3], 1), 0.035, "sine", a=0.25, d=0.15, s=0.7, r=0.4)

    # ═══════════════ CLIMAX (44–59) ═══════════════════════════════════
    for bar in range(44, 60):
        piano_waltz(sc, bar, dens=1.15, bass_amp=0.17, chord_amp=0.10)

    climax_mel = [
        (44, [(1, 2, 0.0, 1.5), (5, 2, 2.0, 1.5), (6, 2, 4.0, 2.0), (5, 2, 6.5, 2.0), (1, 2, 9.0, 2.5)]),
        (48, [(5, 2, 0.0, 1.5), (1, 3, 2.0, 2.0), (5, 2, 4.5, 2.0), (3, 2, 7.0, 2.5)]),
        (52, [(6, 2, 0.5, 1.5), (5, 2, 2.5, 1.5), (7, 2, 4.5, 2.0), (1, 3, 7.0, 3.0)]),
        (56, [(1, 3, 0.0, 2.0), (5, 2, 2.5, 2.0), (3, 2, 5.0, 2.0), (1, 2, 7.5, 3.5)]),
    ]
    for sb, notes in climax_mel:
        melody_ride(sc, sb, notes, amp=0.12, echo=False)

    for bar in range(44, 60):
        bs = bar * 3.0
        local = bar - 44
        dens = 0.65 + 0.25 * (local / 15.0)
        ct = CHORDS[root_at(bar)]
        # sparse arp: 3 notes/bar, not 6
        for i, off in enumerate((0.5, 1.5, 2.5)):
            sc.add(
                bs + off,
                0.45,
                deg(ct[i % 3], 2),
                0.045 * dens,
                "pulse",
                0.25,
                a=0.015,
                d=0.05,
                s=0.35,
                r=0.1,
            )
        if local % 4 == 0:
            sc.add(bs + 0.2, 1.2, deg(1, 3), 0.035 * dens, "sine", a=0.08, d=0.1, s=0.4, r=0.25)

    # ═══════════════ COMEDOWN (60–67) ════════════════════════════════
    for bar in range(60, 68):
        local = bar - 60
        dens = 0.9 - 0.5 * (local / 7.0)
        piano_waltz(sc, bar, dens=dens, bass_amp=0.14, chord_amp=0.075)
        if local % 2 == 0:
            bs = bar * 3.0
            ct = CHORDS[root_at(bar)]
            sc.add(bs + 0.4, 2.4, deg(ct[3], 1), 0.035 * dens, "sine", a=0.3, d=0.2, s=0.7, r=0.5)

    # ═══════════════ REINTRO (68–71) ═════════════════════════════════
    for bar in range(68, 72):
        local = bar - 68
        dens = 0.5 - 0.1 * local
        piano_waltz(sc, bar, dens=max(0.18, dens), bass_amp=0.12, chord_amp=0.06)
        bs = bar * 3.0
        sc.add(bs, 3.0, deg(1, 1), 0.07 - local * 0.01, "sine", a=0.25, d=0.2, s=0.85, r=0.55)
        if local >= 2:
            sc.add(bs + 0.5, 2.5, deg(5, 1), 0.045, "sine", a=0.3, d=0.2, s=0.75, r=0.55)

    # ── Render ───────────────────────────────────────────────────────
    n = int(SR * dur)
    buf = [0.0] * n
    rng = random.Random(0xF06)
    beat = 60.0 / bpm

    for start_b, dur_b, midi, amp, kind, duty, ea, ed, es, er in sc.ev:
        t0 = start_b * beat
        t1 = (start_b + dur_b) * beat
        i0 = max(0, int(t0 * SR))
        i1 = min(n, int((t1 + er + 0.02) * SR))
        f = hz(midi) if kind != "noise" and midi > 0 else 0.0
        # High notes: less square "chip" — blend pulse toward sine / softer duty
        high = kind == "pulse" and midi >= 70
        for i in range(i0, i1):
            t = i / SR
            a = env(t, t0, t1, ea, ed, es, er)
            if a <= 0:
                continue
            if kind == "noise":
                s = rng.uniform(-1, 1) * 0.35
            elif kind == "tri":
                s = tri(f, t)
            elif kind == "sine":
                s = sine(f, t)
            elif high:
                # dreamy high: mostly sine, a little pulse for character
                s = sine(f, t) * 0.72 + pulse(f, t, duty=min(duty, 0.35)) * 0.28
            else:
                s = pulse(f, t, duty=duty)
            buf[i] += s * amp * a

    # Gentle high-pass (~110 Hz) — air/dream, less boxy low mud under the waltz
    # one-pole HP: y[n] = α (y[n-1] + x[n] - x[n-1])
    hp_hz = 110.0
    rc = 1.0 / (2.0 * math.pi * hp_hz)
    dt = 1.0 / SR
    alpha_hp = rc / (rc + dt)
    y = 0.0
    x_prev = 0.0
    for i in range(n):
        x = buf[i]
        y = alpha_hp * (y + x - x_prev)
        x_prev = x
        buf[i] = y

    # Very light low-pass on the top (~6.5 kHz) so residual chip fizz softens
    lp_hz = 6500.0
    alpha_lp = dt / (1.0 / (2.0 * math.pi * lp_hz) + dt)
    z = 0.0
    for i in range(n):
        z += alpha_lp * (buf[i] - z)
        buf[i] = z

    xf = int(0.05 * SR)
    for i in range(xf):
        w = i / xf
        buf[i] = buf[i] * w + buf[n - xf + i] * (1.0 - w)

    peak = max(abs(x) for x in buf) or 1.0
    gain = 0.56 / peak
    out: list[int] = []
    for i, x in enumerate(buf):
        t = i / SR
        edge = 1.0
        if t < 0.06:
            edge = t / 0.06
        if t > dur - 0.1:
            edge = max(0.0, (dur - t) / 0.1)
        out.append(int(max(-1.0, min(1.0, x * gain * edge)) * 32767))
    return out, dur


def main() -> None:
    ap = argparse.ArgumentParser(description="Compose Glass Fog for murmur")
    ap.add_argument("--bpm", type=float, default=94.0)
    ap.add_argument(
        "--transpose",
        type=int,
        default=-4,
        help="semitones from D (default -3)",
    )
    ap.add_argument(
        "--out",
        type=pathlib.Path,
        default=pathlib.Path.home() / "Music/faeos-chiptune/murmur_glass_fog.wav",
    )
    args = ap.parse_args()
    samples, dur = compose(args.bpm, transpose=args.transpose)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(args.out), "w") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(struct.pack("<" + "h" * len(samples), *samples))
    mirror = pathlib.Path.home() / "faeos/assets/sounds/music/murmur_glass_fog.wav"
    mirror.parent.mkdir(parents=True, exist_ok=True)
    copy2(args.out, mirror)
    mins = int(dur // 60)
    secs = dur % 60
    print(
        f"wrote {args.out}  {mins}:{secs:05.2f}  bpm={args.bpm}  "
        f"transpose={args.transpose}  3/4  piano 1-2-3  thinner riders"
    )


if __name__ == "__main__":
    main()

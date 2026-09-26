#!/usr/bin/env python3
"""magpie_image — Magpie's own raster, terminal-graphics, and media-output layer.

Stdlib-only decoders for PNG/GIF/BMP, native Kitty graphics-protocol framing,
an ANSI half-block fallback, ffmpeg/ffprobe bridges for formats Magpie does
not decode itself (JPEG/WebP/AVIF/video), and mpv playback control.

Policy: Magpie owns the pixels and the protocol. Host media tools already in
``pkglist.txt`` (ffmpeg/mpv) are treated as OS capabilities, not browser
dependencies; everything Magpie can decode itself, it decodes itself.
"""
from __future__ import annotations

import base64
import json
import os
import re
import shutil
import socket
import struct
import subprocess
import tempfile
import time
import unicodedata
import zlib
from dataclasses import dataclass
from pathlib import Path

from magpie_fetch import FetchError, cache_media_bytes, run_capture


KITTY_PLACEHOLDER = "\U0010eeee"
_ROW_DIACRITICS = (
    0x0305, 0x030d, 0x030e, 0x0310, 0x0312, 0x033d, 0x033e, 0x033f, 0x0346, 0x034a, 0x034b, 0x034c,
    0x0350, 0x0351, 0x0352, 0x0357, 0x035b, 0x0363, 0x0364, 0x0365, 0x0366, 0x0367, 0x0368, 0x0369,
    0x036a, 0x036b, 0x036c, 0x036d, 0x036e, 0x036f, 0x0483, 0x0484, 0x0485, 0x0486, 0x0487, 0x0592,
    0x0593, 0x0594, 0x0595, 0x0597, 0x0598, 0x0599, 0x059c, 0x059d, 0x059e, 0x059f, 0x05a0, 0x05a1,
    0x05a8, 0x05a9, 0x05ab, 0x05ac, 0x05af, 0x05c4, 0x0610, 0x0611, 0x0612, 0x0613, 0x0614, 0x0615,
    0x0616, 0x0617, 0x0657, 0x0658, 0x0659, 0x065a, 0x065b, 0x065d, 0x065e, 0x06d6, 0x06d7, 0x06d8,
    0x06d9, 0x06da, 0x06db, 0x06dc, 0x06df, 0x06e0, 0x06e1, 0x06e2, 0x06e4, 0x06e7, 0x06e8, 0x06eb,
    0x06ec, 0x0730, 0x0732, 0x0733, 0x0735, 0x0736, 0x073a, 0x073d, 0x073f, 0x0740, 0x0741, 0x0743,
    0x0745, 0x0747, 0x0749, 0x074a, 0x07eb, 0x07ec, 0x07ed, 0x07ee, 0x07ef, 0x07f0, 0x07f1, 0x07f3,
    0x0816, 0x0817, 0x0818, 0x0819, 0x081b, 0x081c, 0x081d, 0x081e, 0x081f, 0x0820, 0x0821, 0x0822,
    0x0823, 0x0825, 0x0826, 0x0827, 0x0829, 0x082a, 0x082b, 0x082c, 0x082d, 0x0951, 0x0953, 0x0954,
    0x0f82, 0x0f83, 0x0f86, 0x0f87, 0x135d, 0x135e, 0x135f, 0x17dd, 0x193a, 0x1a17, 0x1a75, 0x1a76,
    0x1a77, 0x1a78, 0x1a79, 0x1a7a, 0x1a7b, 0x1a7c, 0x1b6b, 0x1b6d, 0x1b6e, 0x1b6f, 0x1b70, 0x1b71,
    0x1b72, 0x1b73, 0x1cd0, 0x1cd1, 0x1cd2, 0x1cda, 0x1cdb, 0x1ce0, 0x1dc0, 0x1dc1, 0x1dc3, 0x1dc4,
    0x1dc5, 0x1dc6, 0x1dc7, 0x1dc8, 0x1dc9, 0x1dcb, 0x1dcc, 0x1dd1, 0x1dd2, 0x1dd3, 0x1dd4, 0x1dd5,
    0x1dd6, 0x1dd7, 0x1dd8, 0x1dd9, 0x1dda, 0x1ddb, 0x1ddc, 0x1ddd, 0x1dde, 0x1ddf, 0x1de0, 0x1de1,
    0x1de2, 0x1de3, 0x1de4, 0x1de5, 0x1de6, 0x1dfe, 0x20d0, 0x20d1, 0x20d4, 0x20d5, 0x20d6, 0x20d7,
    0x20db, 0x20dc, 0x20e1, 0x20e7, 0x20e9, 0x20f0, 0x2cef, 0x2cf0, 0x2cf1, 0x2de0, 0x2de1, 0x2de2,
    0x2de3, 0x2de4, 0x2de5, 0x2de6, 0x2de7, 0x2de8, 0x2de9, 0x2dea, 0x2deb, 0x2dec, 0x2ded, 0x2dee,
    0x2def, 0x2df0, 0x2df1, 0x2df2, 0x2df3, 0x2df4, 0x2df5, 0x2df6, 0x2df7, 0x2df8, 0x2df9, 0x2dfa,
    0x2dfb, 0x2dfc, 0x2dfd, 0x2dfe, 0x2dff, 0xa66f, 0xa67c, 0xa67d, 0xa6f0, 0xa6f1, 0xa8e0, 0xa8e1,
    0xa8e2, 0xa8e3, 0xa8e4, 0xa8e5, 0xa8e6, 0xa8e7, 0xa8e8, 0xa8e9, 0xa8ea, 0xa8eb, 0xa8ec, 0xa8ed,
    0xa8ee, 0xa8ef, 0xa8f0, 0xa8f1, 0xaab0, 0xaab2, 0xaab3, 0xaab7, 0xaab8, 0xaabe, 0xaabf, 0xaac1,
    0xfe20, 0xfe21, 0xfe22, 0xfe23, 0xfe24, 0xfe25, 0xfe26, 0x10a0f, 0x10a38, 0x1d185, 0x1d186, 0x1d187,
    0x1d188, 0x1d189, 0x1d1aa, 0x1d1ab, 0x1d1ac, 0x1d1ad, 0x1d242, 0x1d243, 0x1d244,
)


def kitty_terminal() -> bool:
    if os.environ.get("MAGPIE_PIXELS", "").strip() == "1":
        return True
    if os.environ.get("KITTY_WINDOW_ID"):
        return True
    if "kitty" in (os.environ.get("TERM") or "").lower():
        return True
    return "kitty" in (os.environ.get("TERM_PROGRAM") or "").lower()


def truecolor_terminal() -> bool:
    ct = (os.environ.get("COLORTERM") or "").lower()
    if "truecolor" in ct or "24bit" in ct:
        return True
    return kitty_terminal()


def detect_format(data: bytes, content_type: str = "") -> str:
    ct = (content_type or "").split(";")[0].strip().lower()
    if ct == "image/png":
        return "png"
    if ct in ("image/jpeg", "image/jpg"):
        return "jpeg"
    if ct == "image/gif":
        return "gif"
    if ct == "image/bmp":
        return "bmp"
    if ct == "image/webp":
        return "webp"
    if ct == "image/avif":
        return "avif"
    if ct == "image/svg+xml":
        return "svg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "gif"
    if data.startswith(b"BM"):
        return "bmp"
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "webp"
    if data[4:8] == b"ftyp" and b"avif" in data[4:16]:
        return "avif"
    head = data.lstrip()[:256].lower()
    if head.startswith(b"<svg") or b"<svg" in head[:128]:
        return "svg"
    return "unknown"


def image_dimensions(data: bytes, fmt: str = "") -> tuple[int, int]:
    fmt = fmt or detect_format(data)
    try:
        if fmt == "png" and len(data) >= 24:
            w, h = struct.unpack(">II", data[16:24])
            return (w, h) if w and h else (0, 0)
        if fmt == "gif" and len(data) >= 10:
            return struct.unpack("<HH", data[6:10])
        if fmt == "bmp" and len(data) >= 26:
            return (struct.unpack("<i", data[18:22])[0], abs(struct.unpack("<i", data[22:26])[0]))
        if fmt == "jpeg":
            return jpeg_dimensions(data)
        if fmt == "webp":
            return webp_dimensions(data)
        if fmt == "svg":
            return svg_dimensions(data)
    except (struct.error, IndexError, ValueError):
        return (0, 0)
    return (0, 0)


def jpeg_dimensions(data: bytes) -> tuple[int, int]:
    i = 2
    n = len(data)
    while i + 4 < n:
        if data[i] != 0xFF:
            i += 1
            continue
        marker = data[i + 1]
        i += 2
        if marker in (0xD8, 0xD9) or 0xD0 <= marker <= 0xD7 or marker == 0x01:
            continue
        if i + 2 > n:
            break
        size = struct.unpack(">H", data[i:i + 2])[0]
        if size < 2 or i + size > n:
            break
        if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
            h = struct.unpack(">H", data[i + 3:i + 5])[0]
            w = struct.unpack(">H", data[i + 5:i + 7])[0]
            return (w, h)
        i += size
    return (0, 0)


def webp_dimensions(data: bytes) -> tuple[int, int]:
    if len(data) < 16 or not data.startswith(b"RIFF") or data[8:12] != b"WEBP":
        return (0, 0)
    kind = data[12:16]
    if kind == b"VP8 " and len(data) >= 30:
        bits = struct.unpack("<H", data[26:28])[0] | (struct.unpack("<H", data[28:30])[0] << 16)
        return (bits & 0x3FFF, (bits >> 16) & 0x3FFF)
    if kind == b"VP8L" and len(data) >= 25:
        bits = struct.unpack("<I", data[21:25])[0]
        return ((bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1)
    if kind == b"VP8X" and len(data) >= 30:
        w = struct.unpack(">I", b"\x00" + data[24:27])[0] + 1
        h = struct.unpack(">I", b"\x00" + data[27:30])[0] + 1
        return (w, h)
    return (0, 0)


def svg_dimensions(data: bytes) -> tuple[int, int]:
    head = data[:4096].decode("utf-8", "replace")
    m = re.search(r"<svg[^>]*>", head, re.I | re.S)
    if not m:
        return (0, 0)
    tag = m.group(0)
    w = parse_svg_length(tag, "width")
    h = parse_svg_length(tag, "height")
    if w and h:
        return (w, h)
    m = re.search(r'viewBox\s*=\s*"([^"]+)"', tag, re.I) or re.search(r"viewBox\s*=\s*'([^']+)'", tag, re.I)
    if m:
        try:
            nums = [float(x) for x in m.group(1).split()]
            if len(nums) == 4 and nums[2] > 0 and nums[3] > 0:
                return (int(nums[2]), int(nums[3]))
        except ValueError:
            pass
    return (0, 0)


def parse_svg_length(tag: str, name: str) -> int:
    m = re.search(name + r'\s*=\s*"([^"]+)"', tag, re.I) or re.search(name + r"\s*=\s*'([^']+)'", tag, re.I)
    if not m:
        return 0
    n = re.match(r"\s*([\d.]+)", m.group(1))
    return int(float(n.group(1))) if n else 0


# ── PNG decoder ──────────────────────────────────────────────────────────

def decode_png(data: bytes) -> tuple[int, int, bytes]:
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise FetchError("not a PNG file")
    pos = 8
    width = height = bit_depth = color_type = interlace = 0
    palette: list[tuple[int, int, int]] = []
    transparency: bytes = b""
    idat = bytearray()
    while pos + 8 <= len(data):
        length = struct.unpack(">I", data[pos:pos + 4])[0]
        ctype = data[pos + 4:pos + 8]
        chunk = data[pos + 8:pos + 8 + length]
        if len(chunk) != length:
            raise FetchError("truncated PNG chunk")
        if ctype == b"IHDR":
            width, height, bit_depth, color_type, comp, filt, interlace = struct.unpack(">IIBBBBB", chunk)
            if comp != 0 or filt != 0 or bit_depth not in (1, 2, 4, 8, 16) or color_type not in (0, 2, 3, 4, 6):
                raise FetchError("unsupported PNG variant")
            if width <= 0 or height <= 0 or width * height > 64_000_000:
                raise FetchError("implausible PNG dimensions")
        elif ctype == b"PLTE":
            palette = [(chunk[i], chunk[i + 1], chunk[i + 2]) for i in range(0, len(chunk) - 2, 3)]
        elif ctype == b"tRNS":
            transparency = bytes(chunk)
        elif ctype == b"IDAT":
            idat.extend(chunk)
        elif ctype == b"IEND":
            break
        pos += 12 + length
    if not width or not height:
        raise FetchError("PNG has no image header")
    # Bound inflation BEFORE trusting IDAT: worst case is 16-bit RGBA + filters.
    max_raw = width * height * 5 + height + 64
    try:
        d = zlib.decompressobj()
        raw = d.decompress(bytes(idat), max_raw + 1)
        raw += d.flush(max(0, max_raw + 1 - len(raw)))
    except zlib.error as e:
        raise FetchError(f"PNG would not inflate: {e}") from e
    if len(raw) > max_raw:
        raise FetchError("PNG inflates past the pixel cap")

    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[color_type]

    def decode_rows(blob: bytes, w: int, h: int) -> list[bytearray]:
        stride = (w * channels * bit_depth + 7) // 8
        rows: list[bytearray] = []
        off = 0
        prev = bytearray(stride)
        bpp = max(1, (channels * bit_depth + 7) // 8)
        for _ in range(h):
            if off + 1 + stride > len(blob):
                raise FetchError("PNG scanlines are short")
            f = blob[off]
            off += 1
            cur = bytearray(blob[off:off + stride])
            off += stride
            if f == 1:
                for k in range(bpp, stride):
                    cur[k] = (cur[k] + cur[k - bpp]) & 0xFF
            elif f == 2:
                for k in range(stride):
                    cur[k] = (cur[k] + prev[k]) & 0xFF
            elif f == 3:
                for k in range(stride):
                    a = cur[k - bpp] if k >= bpp else 0
                    cur[k] = (cur[k] + ((a + prev[k]) >> 1)) & 0xFF
            elif f == 4:
                for k in range(stride):
                    a = cur[k - bpp] if k >= bpp else 0
                    b = prev[k]
                    c = prev[k - bpp] if k >= bpp else 0
                    cur[k] = (cur[k] + paeth(a, b, c)) & 0xFF
            elif f != 0:
                raise FetchError(f"unknown PNG filter {f}")
            rows.append(cur)
            prev = cur
        return rows

    pixels: list[list[tuple[int, int, int]]] = [[(0, 0, 0)] * width for _ in range(height)]

    def paint(px: int, py: int, rgb: tuple[int, int, int]) -> None:
        if 0 <= px < width and 0 <= py < height:
            pixels[py][px] = rgb

    def sample_to_rgb(vals: list[int]) -> tuple[int, int, int]:
        if color_type == 0:
            g = vals[0]
            return (g, g, g)
        if color_type == 2:
            return (vals[0], vals[1], vals[2])
        if color_type == 3:
            idx = vals[0]
            if idx < len(palette):
                return palette[idx]
            return (0, 0, 0)
        if color_type == 4:
            g = vals[0]
            return (g, g, g)
        return (vals[0], vals[1], vals[2])

    def rows_to_pixels(rows: list[bytearray], w: int, h: int, ox: int, oy: int, sx: int, sy: int) -> None:
        for ry in range(h):
            row = rows[ry]
            vals: list[int] = []
            if bit_depth == 16:
                vals = [row[k] for k in range(0, len(row), 2)]
            elif bit_depth == 8:
                vals = list(row)
            else:
                scale = 8 // bit_depth
                mask = (1 << bit_depth) - 1
                for byte in row:
                    for shift in range(8 - bit_depth, -1, -bit_depth):
                        vals.append(((byte >> shift) & mask) * 255 // mask)
            need = w * channels
            if len(vals) < need:
                raise FetchError("PNG row is short")
            for x in range(w):
                rgb = sample_to_rgb(vals[x * channels:(x + 1) * channels])
                paint(ox + x * sx, oy + ry * sy, rgb)

    if interlace == 0:
        rows_to_pixels(decode_rows(raw, width, height), width, height, 0, 0, 1, 1)
    elif interlace == 1:
        off = 0
        for ox, oy, sx, sy in ((0, 0, 8, 8), (4, 0, 8, 8), (0, 4, 4, 8), (2, 0, 4, 4), (0, 2, 2, 4), (1, 0, 2, 2), (0, 1, 1, 2)):
            pw = (width - ox + sx - 1) // sx if ox < width else 0
            ph = (height - oy + sy - 1) // sy if oy < height else 0
            if pw <= 0 or ph <= 0:
                continue
            stride = (pw * channels * bit_depth + 7) // 8
            need = ph * (1 + stride)
            rows_to_pixels(decode_rows(raw[off:off + need], pw, ph), pw, ph, ox, oy, sx, sy)
            off += need
    else:
        raise FetchError("unknown PNG interlace")
    out = bytearray()
    for row in pixels:
        for r, g, b in row:
            out.extend((r, g, b))
    _ = transparency
    return width, height, bytes(out)


def paeth(a: int, b: int, c: int) -> int:
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    if pb <= pc:
        return b
    return c


# ── GIF decoder (first frame) ────────────────────────────────────────────

def decode_gif(data: bytes) -> tuple[int, int, bytes]:
    if not data.startswith((b"GIF87a", b"GIF89a")) or len(data) < 13:
        raise FetchError("not a GIF file")
    width, height = struct.unpack("<HH", data[6:10])
    if width <= 0 or height <= 0 or width > 32768 or height > 32768:
        raise FetchError("implausible GIF dimensions")
    if width * height > 64_000_000:
        raise FetchError("GIF is larger than the pixel cap")
    packed = data[10]
    pos = 13
    global_palette: list[tuple[int, int, int]] = []
    if packed & 0x80:
        size = 2 << (packed & 0x07)
        global_palette = [(data[pos + i], data[pos + i + 1], data[pos + i + 2]) for i in range(0, size * 3, 3)]
        pos += size * 3
    transparent = -1
    while pos < len(data):
        sep = data[pos]
        pos += 1
        if sep == 0x3B:
            break
        if sep == 0x21:
            if pos >= len(data):
                break
            label = data[pos]
            pos += 1
            if label == 0xF9 and pos + 6 <= len(data):
                # Graphic Control Extension: transparency lives in block[3]/[4].
                if data[pos] >= 4 and data[pos + 1] & 0x01:
                    transparent = data[pos + 4]
                pos += 1
                while pos < len(data) and data[pos]:
                    pos += 1 + data[pos]
                pos += 1
            else:
                while pos < len(data) and data[pos]:
                    pos += 1 + data[pos]
                pos += 1
            continue
        if sep != 0x2C or pos + 9 > len(data):
            raise FetchError("unsupported GIF block")
        left, top, w, h = struct.unpack("<HHHH", data[pos:pos + 8])
        packed = data[pos + 8]
        pos += 9
        palette = global_palette
        if packed & 0x80:
            size = 2 << (packed & 0x07)
            palette = [(data[pos + i], data[pos + i + 1], data[pos + i + 2]) for i in range(0, size * 3, 3)]
            pos += size * 3
        if pos >= len(data):
            raise FetchError("truncated GIF image")
        min_code = data[pos]
        pos += 1
        blob = bytearray()
        while pos < len(data) and data[pos]:
            size = data[pos]
            pos += 1
            blob.extend(data[pos:pos + size])
            pos += size
        pos += 1
        indices = gif_lzw_decode(bytes(blob), min_code, w * h)
        canvas = bytearray(width * height * 3)
        order: list[int] = []
        if packed & 0x40:
            for start, step in ((0, 8), (4, 8), (2, 4), (1, 2)):
                order.extend(range(start, h, step))
        else:
            order = list(range(h))
        for ry, sy in enumerate(order):
            for x in range(w):
                idx = indices[ry * w + x] if ry * w + x < len(indices) else 0
                rgb = palette[idx] if idx < len(palette) else (0, 0, 0)
                if idx == transparent:
                    continue
                dx, dy = left + x, top + sy
                if 0 <= dx < width and 0 <= dy < height:
                    off = (dy * width + dx) * 3
                    canvas[off:off + 3] = bytes(rgb)
        return width, height, bytes(canvas)
    raise FetchError("GIF has no image frame")


def gif_lzw_decode(blob: bytes, min_code: int, expect: int) -> bytes:
    if not 1 <= min_code <= 8:
        raise FetchError("bad GIF LZW code size")
    clear, eoi = 1 << min_code, (1 << min_code) + 1
    table: list[bytes] = [bytes([i]) for i in range(clear)] + [b"", b""]
    size = min_code + 1
    out = bytearray()
    datum = bits = 0
    pos = 0
    prev = b""

    def read_code() -> int | None:
        nonlocal datum, bits, pos
        while bits < size and pos < len(blob):
            datum |= blob[pos] << bits
            bits += 8
            pos += 1
        if bits < size:
            return None
        code = datum & ((1 << size) - 1)
        datum >>= size
        bits -= size
        return code

    while len(out) < expect:
        code = read_code()
        if code is None:
            break
        if code == clear:
            table = [bytes([i]) for i in range(clear)] + [b"", b""]
            size = min_code + 1
            prev = b""
            continue
        if code == eoi:
            break
        if code < len(table) and table[code]:
            entry = table[code]
        elif code == len(table) and prev:
            entry = prev + prev[:1]
        else:
            raise FetchError("corrupt GIF LZW stream")
        out.extend(entry)
        if prev:
            table.append(prev + entry[:1])
            if len(table) == (1 << size) + 1 and size < 12:
                size += 1
        prev = entry
    if len(out) < expect:
        out.extend(b"\x00" * (expect - len(out)))
    return bytes(out[:expect])


# ── BMP decoder ──────────────────────────────────────────────────────────

def decode_bmp(data: bytes) -> tuple[int, int, bytes]:
    if len(data) < 54 or not data.startswith(b"BM"):
        raise FetchError("not a BMP file")
    off = struct.unpack("<I", data[10:14])[0]
    dib = struct.unpack("<I", data[14:18])[0]
    if dib not in (40, 108, 124) or len(data) < 14 + dib:
        raise FetchError("unsupported BMP header")
    width = struct.unpack("<i", data[18:22])[0]
    height = struct.unpack("<i", data[22:26])[0]
    planes, bpp = struct.unpack("<HH", data[26:30])
    comp = struct.unpack("<I", data[30:34])[0]
    if planes != 1 or width <= 0 or height == 0 or width * abs(height) > 64_000_000:
        raise FetchError("implausible BMP dimensions")
    if comp != 0 or bpp not in (8, 24, 32):
        raise FetchError("unsupported BMP encoding")
    top_down = height < 0
    height = abs(height)
    palette: list[tuple[int, int, int]] = []
    if bpp == 8:
        count = 256
        pos = 14 + dib
        for _ in range(count):
            if pos + 4 > len(data):
                break
            b, g, r = data[pos:pos + 3]
            palette.append((r, g, b))
            pos += 4
    row_bytes = ((width * bpp + 31) // 32) * 4
    out = bytearray(width * height * 3)
    for y in range(height):
        src_y = y if top_down else (height - 1 - y)
        base = off + src_y * row_bytes
        if base + row_bytes > len(data):
            raise FetchError("truncated BMP pixels")
        row = data[base:base + row_bytes]
        for x in range(width):
            if bpp == 24:
                b, g, r = row[x * 3:x * 3 + 3]
            elif bpp == 32:
                b, g, r = row[x * 4:x * 4 + 3]
            else:
                r, g, b = palette[row[x]] if row[x] < len(palette) else (0, 0, 0)
            dest = (y * width + x) * 3
            out[dest:dest + 3] = bytes((r, g, b))
    return width, height, bytes(out)


# ── ffmpeg/ffprobe bridges ───────────────────────────────────────────────

def have_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None


def have_ffprobe() -> bool:
    return shutil.which("ffprobe") is not None


def ffprobe_stream(path: Path) -> dict:
    if not have_ffprobe():
        raise FetchError("ffprobe is not installed")
    rc, out, err = run_capture([
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height,duration,codec_name",
        "-show_entries", "format=duration,size", "-of", "json", str(path),
    ], timeout=15)
    if rc != 0:
        raise FetchError(f"ffprobe could not read media: {err.strip() or 'unknown error'}")
    try:
        return json.loads(out.decode("utf-8", "replace"))
    except ValueError as e:
        raise FetchError(f"ffprobe returned bad JSON: {e}") from e


def rasterize_with_ffmpeg(data: bytes, suffix: str, *, max_side: int = 640) -> tuple[int, int, bytes]:
    if not have_ffmpeg():
        raise FetchError("ffmpeg is not installed")
    tmp = cache_media_bytes(data, suffix)
    info = ffprobe_stream(tmp)
    streams = info.get("streams") or []
    width = int((streams[0].get("width") if streams else 0) or 0)
    height = int((streams[0].get("height") if streams else 0) or 0)
    if not width or not height:
        width, height = image_dimensions(data)
    if not width or not height:
        width, height = 640, 480
    scale = min(1.0, max_side / max(width, height))
    out_w = max(2, int(width * scale) // 2 * 2)
    out_h = max(2, int(height * scale) // 2 * 2)
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(tmp),
        "-frames:v", "1", "-vf", f"scale={out_w}:{out_h}",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1",
    ]
    try:
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
    except subprocess.TimeoutExpired as e:
        raise FetchError("media raster timed out") from e
    except OSError as e:
        raise FetchError(f"ffmpeg would not run: {e}") from e
    if proc.returncode != 0 or len(proc.stdout) != out_w * out_h * 3:
        raise FetchError(f"ffmpeg could not rasterize media: {proc.stderr.decode('utf-8', 'replace').strip() or 'bad frame'}")
    return out_w, out_h, proc.stdout


def video_thumbnail(path: Path, *, max_side: int = 480, seek: float = 1.0) -> tuple[int, int, bytes]:
    if not have_ffmpeg():
        raise FetchError("ffmpeg is not installed")
    info = ffprobe_stream(path)
    streams = info.get("streams") or []
    width = int((streams[0].get("width") if streams else 0) or 0)
    height = int((streams[0].get("height") if streams else 0) or 0)
    if not width or not height:
        width, height = 640, 360
    scale = min(1.0, max_side / max(width, height))
    out_w = max(2, int(width * scale) // 2 * 2)
    out_h = max(2, int(height * scale) // 2 * 2)
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", str(max(0.0, seek)),
        "-i", str(path), "-frames:v", "1", "-vf", f"scale={out_w}:{out_h}",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1",
    ]
    try:
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
    except subprocess.TimeoutExpired as e:
        raise FetchError("video thumbnail timed out") from e
    except OSError as e:
        raise FetchError(f"ffmpeg would not run: {e}") from e
    if proc.returncode != 0 or len(proc.stdout) != out_w * out_h * 3:
        raise FetchError("video thumbnail failed")
    return out_w, out_h, proc.stdout


@dataclass
class DisplayImage:
    image_id: int
    mode: str  # png | rgb
    width: int
    height: int
    payload: bytes
    cols: int
    rows: int


def fit_cells(width: int, height: int, max_cols: int, max_rows: int) -> tuple[int, int]:
    if width <= 0 or height <= 0:
        return (min(max_cols, 32), min(max_rows, 8))
    # Terminal cells are roughly twice as tall as wide; compensate.
    cols = max_cols
    rows = max(1, round(cols * height / max(1, width) / 2))
    if rows > max_rows:
        rows = max_rows
        cols = max(4, round(rows * width / max(1, height) * 2))
    return (max(4, min(max_cols, cols)), max(2, min(max_rows, rows)))


def prepare_display_image(image_id: int, data: bytes, content_type: str, max_cols: int, max_rows: int) -> DisplayImage:
    fmt = detect_format(data, content_type)
    width, height = image_dimensions(data, fmt)
    # Cheap abort on lying headers before any decode or ffmpeg work.
    if width > 32768 or height > 32768 or width * height > 64_000_000:
        raise FetchError("image is larger than the pixel cap")
    cols, rows = fit_cells(width or 640, height or 480, max_cols, max_rows)
    if fmt == "png" and len(data) <= 8_000_000:
        return DisplayImage(image_id, "png", width or cols * 8, height or rows * 16, data, cols, rows)
    if fmt == "png":
        width, height, rgb = decode_png(data)
        return DisplayImage(image_id, "rgb", width, height, rgb, cols, rows)
    if fmt == "gif":
        width, height, rgb = decode_gif(data)
        return DisplayImage(image_id, "rgb", width, height, rgb, cols, rows)
    if fmt == "bmp":
        width, height, rgb = decode_bmp(data)
        return DisplayImage(image_id, "rgb", width, height, rgb, cols, rows)
    suffix = {"jpeg": ".jpg", "webp": ".webp", "avif": ".avif", "svg": ".svg"}.get(fmt, ".img")
    width, height, rgb = rasterize_with_ffmpeg(data, suffix)
    cols, rows = fit_cells(width, height, max_cols, max_rows)
    return DisplayImage(image_id, "rgb", width, height, rgb, cols, rows)


def kitty_transmit(image: DisplayImage) -> bytes:
    if image.image_id <= 0 or image.image_id > 0xFFFFFFFF:
        raise FetchError("bad kitty image id")
    if image.mode == "png":
        payload = base64.b64encode(image.payload)
        base = f"a=T,f=100,i={image.image_id},q=2,U=1,c={image.cols},r={image.rows},"
    elif image.mode == "rgb":
        payload = base64.b64encode(image.payload)
        base = f"a=T,f=24,s={image.width},v={image.height},i={image.image_id},q=2,U=1,c={image.cols},r={image.rows},"
    else:
        raise FetchError(f"unknown display mode {image.mode}")
    out = bytearray()
    first = True
    for i in range(0, len(payload), 4096):
        chunk = payload[i:i + 4096]
        last = i + 4096 >= len(payload)
        control = (base if first else "") + f"m={0 if last else 1}"
        out.extend(b"\x1b_G" + control.encode("ascii") + b";" + chunk + b"\x1b\\")
        first = False
    return bytes(out)


def kitty_placeholder_lines(image_id: int, cols: int, rows: int) -> list[str]:
    if not 1 <= image_id <= 0xFFFFFF:
        raise FetchError("kitty placeholder id out of range")
    if cols < 1 or rows < 1 or rows > len(_ROW_DIACRITICS):
        raise FetchError("bad kitty placeholder rectangle")
    r, g, b = (image_id >> 16) & 0xFF, (image_id >> 8) & 0xFF, image_id & 0xFF
    fg = f"\x1b[38;2;{r};{g};{b}m"
    reset = "\x1b[39m"
    lines = []
    for row in range(rows):
        cell = KITTY_PLACEHOLDER + chr(_ROW_DIACRITICS[row]) + KITTY_PLACEHOLDER * (cols - 1)
        lines.append(fg + cell + reset)
    return lines


def kitty_delete(image_id: int) -> bytes:
    return f"\x1b_Ga=d,d=I,i={image_id},q=2\x1b\\".encode("ascii")


def ansi_thumbnail(rgb: bytes, width: int, height: int, cols: int, rows: int, *, truecolor: bool | None = None) -> list[str]:
    if len(rgb) != width * height * 3 or width <= 0 or height <= 0:
        raise FetchError("bad RGB buffer for thumbnail")
    tc = truecolor_terminal() if truecolor is None else truecolor
    lines = []
    for row in range(max(1, rows)):
        top_y = min(height - 1, (row * 2 * height) // max(1, rows * 2))
        bot_y = min(height - 1, ((row * 2 + 1) * height) // max(1, rows * 2))
        cells = []
        for col in range(max(1, cols)):
            x = min(width - 1, (col * width) // max(1, cols))
            tr, tg, tb = rgb[(top_y * width + x) * 3:(top_y * width + x) * 3 + 3]
            br, bg, bb = rgb[(bot_y * width + x) * 3:(bot_y * width + x) * 3 + 3]
            if tc:
                cells.append(f"\x1b[38;2;{tr};{tg};{tb}m\x1b[48;2;{br};{bg};{bb}m▀\x1b[0m")
            else:
                cells.append(
                    f"\x1b[38;5;{rgb_to_ansi256(tr, tg, tb)}m\x1b[48;5;{rgb_to_ansi256(br, bg, bb)}m▀\x1b[0m"
                )
        lines.append("".join(cells))
    return lines


def rgb_to_ansi256(r: int, g: int, b: int) -> int:
    if r == g == b:
        if r < 8:
            return 16
        if r > 238:
            return 231
        return 232 + round((r - 8) / 247 * 23)
    return 16 + 36 * round(r / 255 * 5) + 6 * round(g / 255 * 5) + round(b / 255 * 5)


# ── mpv playback ─────────────────────────────────────────────────────────

class MediaPlayer:
    """One detached mpv per browser session, driven over its JSON IPC socket."""

    def __init__(self) -> None:
        self.proc: subprocess.Popen | None = None
        self.sock_path = Path(tempfile.gettempdir()) / f"magpie-mpv-{os.getpid()}.sock"
        self.current = ""

    def running(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def play(self, url: str, *, kind: str = "video", title: str = "") -> str:
        if not shutil.which("mpv"):
            raise FetchError("mpv is not installed")
        self.stop()
        try:
            self.sock_path.unlink(missing_ok=True)
        except OSError:
            pass
        cmd = [
            "mpv", "--really-quiet", "--no-terminal", "--no-input-default-bindings",
            f"--input-ipc-server={self.sock_path}", f"--title={title or url}",
            "--ytdl-format=best[height<=720]/best",
        ]
        if kind == "audio":
            cmd.append("--no-video")
        cmd.append(url)
        try:
            self.proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        except OSError as e:
            raise FetchError(f"mpv would not start: {e}") from e
        self.current = url
        return f"playing in mpv: {title or url}"

    def command(self, *args) -> object:
        if not self.running():
            return None
        payload = json.dumps({"command": list(args)}).encode() + b"\n"
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
                s.settimeout(1.0)
                s.connect(str(self.sock_path))
                s.sendall(payload)
                data = s.recv(65536)
        except OSError:
            return None
        try:
            return json.loads(data.decode("utf-8", "replace"))
        except ValueError:
            return None

    def stop(self) -> None:
        if self.running():
            self.command("quit")
            try:
                self.proc.wait(timeout=2)
            except (subprocess.TimeoutExpired, AttributeError):
                try:
                    self.proc.terminate()
                except OSError:
                    pass
        self.proc = None
        self.current = ""
        try:
            self.sock_path.unlink(missing_ok=True)
        except OSError:
            pass

    def status(self) -> str:
        if not self.running():
            return "mpv idle"
        pause = self.command("get_property", "pause")
        pos = self.command("get_property", "time-pos")
        dur = self.command("get_property", "duration")
        name = self.command("get_property", "media-title")

        def val(x, default=0):
            try:
                return x.get("data", default) if isinstance(x, dict) else default
            except (AttributeError, ValueError):
                return default

        title = val(name, self.current)
        return f"{'paused' if val(pause, False) else 'playing'} {fmt_clock(val(pos, 0))}/{fmt_clock(val(dur, 0))} · {title}"


def fmt_clock(sec: float) -> str:
    try:
        s = max(0, int(float(sec)))
    except (TypeError, ValueError):
        return "??:??"
    return f"{s // 60:02d}:{s % 60:02d}"


def check_media_backends() -> dict[str, bool]:
    return {
        "kitty": kitty_terminal(),
        "ffmpeg": have_ffmpeg(),
        "ffprobe": have_ffprobe(),
        "mpv": shutil.which("mpv") is not None,
        "yt-dlp": shutil.which("yt-dlp") is not None,
    }

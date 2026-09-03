"""
Small DDS reader for uncompressed and DXT1/DXT5 color-mask / albedo maps.

BC7 and other modern formats return None so the preview can use HSV fill.
Converted pixels stay in memory; nothing is written next to the game files.
"""

from __future__ import annotations

import struct
from pathlib import Path
from typing import Optional, Tuple

import numpy as np


DDS_MAGIC = b"DDS "


def load_dds_rgba(path: Path) -> Optional[np.ndarray]:
    try:
        data = Path(path).read_bytes()
    except OSError:
        return None
    if len(data) < 128 or data[:4] != DDS_MAGIC:
        return None
    height, width = struct.unpack_from("<II", data, 12)
    pf_flags, fourcc, rgb_bit_count = struct.unpack_from("<I4sI", data, 80)
    if height <= 0 or width <= 0 or height > 8192 or width > 8192:
        return None
    payload = data[128:]
    fourcc_s = fourcc.decode("ascii", errors="ignore")
    try:
        if pf_flags & 0x4 and fourcc_s in ("DXT1", "DXT5"):
            if fourcc_s == "DXT1":
                return _decode_dxt1(payload, width, height)
            return _decode_dxt5(payload, width, height)
        if rgb_bit_count == 32:
            needed = width * height * 4
            if len(payload) < needed:
                return None
            raw = np.frombuffer(payload[:needed], dtype=np.uint8).reshape((height, width, 4))
            # BGRA → RGBA
            return raw[:, :, [2, 1, 0, 3]].copy()
    except (ValueError, struct.error):
        return None
    return None


def _decode_dxt1(data: bytes, width: int, height: int) -> np.ndarray:
    out = np.zeros((height, width, 4), dtype=np.uint8)
    blocks_x = (width + 3) // 4
    blocks_y = (height + 3) // 4
    offset = 0
    for by in range(blocks_y):
        for bx in range(blocks_x):
            block = data[offset : offset + 8]
            offset += 8
            if len(block) < 8:
                return out
            c0, c1, bits = struct.unpack("<HHI", block)
            colors = _dxt_colors(c0, c1, opaque=True)
            _write_block(out, bx, by, bits, colors, width, height)
    return out


def _decode_dxt5(data: bytes, width: int, height: int) -> np.ndarray:
    out = np.zeros((height, width, 4), dtype=np.uint8)
    blocks_x = (width + 3) // 4
    blocks_y = (height + 3) // 4
    offset = 0
    for by in range(blocks_y):
        for bx in range(blocks_x):
            block = data[offset : offset + 16]
            offset += 16
            if len(block) < 16:
                return out
            a0, a1 = block[0], block[1]
            alpha_bits = int.from_bytes(block[2:8], "little")
            c0, c1, bits = struct.unpack_from("<HHI", block, 8)
            colors = _dxt_colors(c0, c1, opaque=True)
            alphas = _dxt_alphas(a0, a1)
            for i in range(16):
                px = bx * 4 + (i % 4)
                py = by * 4 + (i // 4)
                if px >= width or py >= height:
                    continue
                color = colors[(bits >> (2 * i)) & 3]
                alpha = alphas[(alpha_bits >> (3 * i)) & 7]
                out[py, px] = (color[0], color[1], color[2], alpha)
    return out


def _dxt_colors(c0: int, c1: int, opaque: bool) -> Tuple[Tuple[int, int, int, int], ...]:
    def expand(c: int) -> Tuple[int, int, int]:
        r = ((c >> 11) & 31) * 255 // 31
        g = ((c >> 5) & 63) * 255 // 63
        b = (c & 31) * 255 // 31
        return r, g, b

    a = expand(c0)
    b = expand(c1)
    if c0 > c1 or opaque:
        c = tuple((2 * a[i] + b[i]) // 3 for i in range(3))
        d = tuple((a[i] + 2 * b[i]) // 3 for i in range(3))
        return (
            (a[0], a[1], a[2], 255),
            (b[0], b[1], b[2], 255),
            (c[0], c[1], c[2], 255),
            (d[0], d[1], d[2], 255),
        )
    c = tuple((a[i] + b[i]) // 2 for i in range(3))
    return (
        (a[0], a[1], a[2], 255),
        (b[0], b[1], b[2], 255),
        (c[0], c[1], c[2], 255),
        (0, 0, 0, 0),
    )


def _dxt_alphas(a0: int, a1: int) -> Tuple[int, ...]:
    values = [a0, a1]
    if a0 > a1:
        for i in range(1, 7):
            values.append(((7 - i) * a0 + i * a1) // 7)
    else:
        for i in range(1, 5):
            values.append(((5 - i) * a0 + i * a1) // 5)
        values.extend((0, 255))
    return tuple(values)


def _write_block(out, bx, by, bits, colors, width, height) -> None:
    for i in range(16):
        px = bx * 4 + (i % 4)
        py = by * 4 + (i // 4)
        if px >= width or py >= height:
            continue
        out[py, px] = colors[(bits >> (2 * i)) & 3]

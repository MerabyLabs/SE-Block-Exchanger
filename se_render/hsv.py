"""
Keen ColorMaskHSV / HSVOffset conversion.

Space Engineers stores block color as HSVOffset:
  H in [0, 1], S and V in [-1, 1]
Official conversion (MyColorPickerConstants):
  HSV.S = offset.S + 0.8
  HSV.V = offset.V + 0.45
"""

from __future__ import annotations

import colorsys
from typing import Tuple


def hsv_offset_to_standard(h: float, s: float, v: float) -> Tuple[float, float, float]:
    """Convert Keen HSVOffset to standard HSV in [0, 1]."""
    hue = max(0.0, min(1.0, float(h)))
    sat = max(0.0, min(1.0, float(s) + 0.8))
    val = max(0.0, min(1.0, float(v) + 0.45))
    return hue, sat, val


def hsv_offset_to_rgb(h: float, s: float, v: float) -> Tuple[float, float, float]:
    """Convert Keen HSVOffset to linear-ish RGB in [0, 1]."""
    hue, sat, val = hsv_offset_to_standard(h, s, v)
    return colorsys.hsv_to_rgb(hue, sat, val)


def rgb_to_hsv_offset(r: float, g: float, b: float) -> Tuple[float, float, float]:
    """Inverse of hsv_offset_to_rgb for tests and writers."""
    hue, sat, val = colorsys.rgb_to_hsv(
        max(0.0, min(1.0, r)),
        max(0.0, min(1.0, g)),
        max(0.0, min(1.0, b)),
    )
    return hue, sat - 0.8, val - 0.45

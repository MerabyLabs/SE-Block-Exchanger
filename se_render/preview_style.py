"""
CPU-side helpers for the Subgrids 3D preview.

Lighting and seams live in the shaders. These functions classify armor
vs functional blocks, pick interactive framebuffer size, and name the
active GPU batch set so orbit never swaps in the unculled mesh.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Sequence, Tuple


INTERACTIVE_MAX_EDGE = 1440

# Matches GLPreviewRenderer clear and the preview canvas.
PREVIEW_CLEAR_COLOR = (0.027, 0.047, 0.094)

# Unpainted / black ColorMaskHSV must still read lighter than navy.
ARMOR_ALBEDO_FLOOR = 0.36
FUNCTIONAL_ALBEDO_FLOOR = 0.22

# Ships at or below this keep full-resolution orbit. Above it, orbit may
# use a cheaper framebuffer and simplified functional MWM — never boxes
# for official slopes.
HUGE_SHIP_BLOCK_THRESHOLD = 8000

# First useful 3D frame uses a shell-only pass above this count.
PROGRESSIVE_BLOCK_THRESHOLD = 2500

# If GPU/memory cannot take every instance, keep this many and say so.
PREVIEW_INSTANCE_CAP = 20000

# First frame stays an exterior shell; interiors fill on idle.
EXTREME_BLOCK_THRESHOLD = 50000
MWM_REFINE_CHUNK = 32

# First GPU upload: this many CpuBatches per Tk idle slice.
UPLOAD_BATCH_CHUNK = 8


def format_preview_count_caption(
    shown: int,
    total: int,
    *,
    simplified: bool = False,
) -> str:
    """Toolbar line for how many blocks the 3D view is drawing."""
    shown_n = max(0, int(shown))
    total_n = max(shown_n, int(total))
    if simplified and total_n > shown_n:
        return f"3D {shown_n:,} of {total_n:,} — simplified"
    if total_n > shown_n:
        return f"{shown_n:,} of {total_n:,} blocks  ·  3D preview"
    return f"{shown_n:,} blocks  ·  3D preview"


@dataclass(frozen=True)
class BlockStyle:
    """Per-instance preview material. Armor keeps ColorMaskHSV (jitter=0.5)."""

    edge_strength: float
    jitter: float
    spec: float
    metal: float
    rim: float
    tint: Tuple[float, float, float]
    tint_mix: float
    is_armor: bool
    category: str


def use_interactive_lod(block_count: int, interactive: bool) -> bool:
    """True when orbit/pan should use the cheaper huge-ship batch set."""
    return bool(interactive) and int(block_count) > HUGE_SHIP_BLOCK_THRESHOLD


def render_target_size(
    width: int,
    height: int,
    interactive: bool,
    *,
    block_count: int = 0,
) -> Tuple[int, int]:
    """
    Framebuffer size. Idle is always native.

    Orbit keeps native resolution unless the ship is huge *and* the pane
    is larger than INTERACTIVE_MAX_EDGE. Aspect is preserved so lighting
    and seams do not crawl when the blit stretches.
    """
    width = max(64, int(width))
    height = max(64, int(height))
    if not interactive:
        return width, height
    longest = max(width, height)
    huge = int(block_count) > HUGE_SHIP_BLOCK_THRESHOLD
    if not huge or longest <= INTERACTIVE_MAX_EDGE:
        return width, height
    scale = INTERACTIVE_MAX_EDGE / float(longest)
    return max(64, int(round(width * scale))), max(64, int(round(height * scale)))


def active_preview_set(
    explode: float,
    interactive: bool,
    huge: bool,
    block_count: int,
) -> str:
    """
    Which uploaded batch set to draw.

    explode=0 is always a culled assembled set. Selection must not swap
    in the unculled exploded meshes (that pops interiors on click).
    """
    lod = bool(huge) and use_interactive_lod(block_count, interactive)
    if float(explode) > 1e-4:
        return "exploded_lod" if lod else "exploded"
    return "assembled_lod" if lod else "assembled"


@lru_cache(maxsize=4096)
def classify_block(type_id: str = "", subtype: str = "") -> str:
    """Stable category used for functional accent families."""
    blob = f"{type_id} {subtype}".lower()
    if any(token in blob for token in ("window", "glass")):
        return "window"
    if any(token in blob for token in ("cockpit", "controlseat", "flightseat", "helmseat")):
        return "cockpit"
    if any(
        token in blob
        for token in (
            "reactor",
            "battery",
            "generator",
            "solar",
            "hydrogenengine",
            "windturbine",
        )
    ):
        return "power"
    if "thrust" in blob:
        return "thrust"
    if any(
        token in blob
        for token in ("gatling", "missile", "turret", "launcher", "weapon", "railgun")
    ):
        return "weapon"
    if "gyro" in blob:
        return "gyro"
    if any(token in blob for token in ("conveyor", "sorter", "connector", "ejector")):
        return "conveyor"
    if any(
        token in blob
        for token in ("rotor", "hinge", "piston", "motorstator", "motorsuspension")
    ):
        return "mechanical"
    if any(token in blob for token in ("cargo", "container", "collector")):
        return "storage"
    if "armor" in blob:
        return "armor"
    type_l = (type_id or "").lower()
    if type_l in ("cubeblock", "") and "panel" in blob and "lcd" not in blob and "textpanel" not in blob:
        return "armor"
    if type_l in ("cubeblock",):
        return "armor"
    return "functional"


INSPECT_CATEGORIES = (
    "armor",
    "functional",
    "power",
    "thrust",
    "weapon",
    "cockpit",
    "mechanical",
    "conveyor",
)


def inspect_category(type_id: str = "", subtype: str = "") -> str:
    """Hide-by-category bucket. conveyor includes storage."""
    raw = classify_block(type_id, subtype)
    if raw == "storage":
        return "conveyor"
    if raw in INSPECT_CATEGORIES:
        return raw
    return "functional"


def inspect_category_code(type_id: str = "", subtype: str = "") -> int:
    name = inspect_category(type_id, subtype)
    try:
        return INSPECT_CATEGORIES.index(name)
    except ValueError:
        return 1


def is_armor_block(type_id: str = "", subtype: str = "") -> bool:
    return classify_block(type_id, subtype) == "armor"


def block_material(type_id: str = "", subtype: str = "") -> BlockStyle:
    """
    Preview material for a block.

    Armor: matte, official ColorMaskHSV (jitter 0.5), strong inset crease.
    Functional: cooler metal, higher spec, category tint — not painted armor.
    """
    category = classify_block(type_id, subtype)
    jitter = _subtype_jitter(subtype, 0.35, 0.75)
    if category == "armor":
        return BlockStyle(
            edge_strength=1.0,
            jitter=0.5,
            spec=0.22,
            metal=0.0,
            rim=0.08,
            tint=(1.0, 1.0, 1.0),
            tint_mix=0.0,
            is_armor=True,
            category=category,
        )
    if category == "window":
        return BlockStyle(
            edge_strength=0.40,
            jitter=jitter,
            spec=0.88,
            metal=0.35,
            rim=0.30,
            tint=(0.90, 1.04, 1.16),
            tint_mix=0.20,
            is_armor=False,
            category=category,
        )
    if category == "cockpit":
        return BlockStyle(
            edge_strength=0.36,
            jitter=jitter,
            spec=0.90,
            metal=0.52,
            rim=0.30,
            tint=(0.88, 1.02, 1.14),
            tint_mix=0.18,
            is_armor=False,
            category=category,
        )
    if category == "power":
        return BlockStyle(
            edge_strength=0.42,
            jitter=jitter,
            spec=0.78,
            metal=0.72,
            rim=0.24,
            tint=(1.10, 0.93, 0.82),
            tint_mix=0.20,
            is_armor=False,
            category=category,
        )
    if category == "thrust":
        return BlockStyle(
            edge_strength=0.40,
            jitter=jitter,
            spec=0.80,
            metal=0.70,
            rim=0.26,
            tint=(0.82, 0.96, 1.12),
            tint_mix=0.20,
            is_armor=False,
            category=category,
        )
    if category == "weapon":
        return BlockStyle(
            edge_strength=0.44,
            jitter=jitter,
            spec=0.76,
            metal=0.68,
            rim=0.28,
            tint=(1.12, 0.86, 0.80),
            tint_mix=0.22,
            is_armor=False,
            category=category,
        )
    if category == "gyro":
        return BlockStyle(
            edge_strength=0.46,
            jitter=jitter,
            spec=0.74,
            metal=0.66,
            rim=0.22,
            tint=(0.90, 0.98, 1.08),
            tint_mix=0.18,
            is_armor=False,
            category=category,
        )
    if category == "conveyor":
        return BlockStyle(
            edge_strength=0.50,
            jitter=jitter,
            spec=0.62,
            metal=0.55,
            rim=0.18,
            tint=(1.02, 0.96, 0.88),
            tint_mix=0.16,
            is_armor=False,
            category=category,
        )
    if category == "mechanical":
        return BlockStyle(
            edge_strength=0.48,
            jitter=jitter,
            spec=0.70,
            metal=0.64,
            rim=0.20,
            tint=(0.98, 0.94, 0.88),
            tint_mix=0.16,
            is_armor=False,
            category=category,
        )
    if category == "storage":
        return BlockStyle(
            edge_strength=0.48,
            jitter=jitter,
            spec=0.58,
            metal=0.48,
            rim=0.16,
            tint=(0.96, 0.94, 0.86),
            tint_mix=0.16,
            is_armor=False,
            category=category,
        )
    return BlockStyle(
        edge_strength=0.50,
        jitter=jitter,
        spec=0.68,
        metal=0.60,
        rim=0.20,
        tint=(0.94, 0.97, 1.06),
        tint_mix=0.16,
        is_armor=False,
        category=category,
    )


def material_style(type_id: str = "", subtype: str = "") -> Tuple[float, float, float]:
    """Shader params: (edge_strength, jitter, spec)."""
    style = block_material(type_id, subtype)
    return (style.edge_strength, style.jitter, style.spec)


def apply_albedo_tint(
    rgb: Sequence[float],
    style: BlockStyle,
) -> Tuple[float, float, float]:
    """Keep ColorMaskHSV hue; lift value so armor never matches the navy clear."""
    r, g, b = float(rgb[0]), float(rgb[1]), float(rgb[2])
    if not style.is_armor and style.tint_mix > 1e-6:
        t = float(style.tint_mix)
        biased = (r * style.tint[0], g * style.tint[1], b * style.tint[2])
        r = r * (1.0 - t) + biased[0] * t
        g = g * (1.0 - t) + biased[1] * t
        b = b * (1.0 - t) + biased[2] * t
    floor = ARMOR_ALBEDO_FLOOR if style.is_armor else FUNCTIONAL_ALBEDO_FLOOR
    return _lift_albedo((r, g, b), floor)


def _lift_albedo(
    rgb: Tuple[float, float, float],
    floor: float,
) -> Tuple[float, float, float]:
    r, g, b = float(rgb[0]), float(rgb[1]), float(rgb[2])
    lum = 0.30 * r + 0.54 * g + 0.16 * b
    if lum >= floor:
        return (
            max(0.0, min(1.0, r)),
            max(0.0, min(1.0, g)),
            max(0.0, min(1.0, b)),
        )
    if lum < 1e-5:
        return (
            max(0.0, min(1.0, floor * 1.08)),
            max(0.0, min(1.0, floor * 1.16)),
            max(0.0, min(1.0, floor * 1.28)),
        )
    scale = floor / lum
    return (
        max(0.0, min(1.0, r * scale)),
        max(0.0, min(1.0, g * scale)),
        max(0.0, min(1.0, b * scale)),
    )


def _subtype_jitter(subtype: str, lo: float, hi: float) -> float:
    h = 2166136261
    for ch in subtype or "":
        h ^= ord(ch)
        h = (h * 16777619) & 0xFFFFFFFF
    t = (h % 1009) / 1009.0
    return lo + (hi - lo) * t

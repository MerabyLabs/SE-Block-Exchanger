"""
Fleet Aesthetics & Armor Skin / HSV Color Palette Engine.
Provides batch armor reskinning and RGB/HSV color transformation across Space Engineers blueprints.
"""

from __future__ import annotations
import colorsys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Tuple
import xml.etree.ElementTree as ET
import safe_xml


@dataclass
class SkinDefinition:
    skin_id: str
    display_name: str
    category: str
    preview_hex: str


OFFICIAL_SKINS: Dict[str, SkinDefinition] = {
    "None": SkinDefinition("None", "Vanilla Default", "Base", "#94a3b8"),
    "Clean_Armor": SkinDefinition("Clean_Armor", "Clean Armor", "Modern", "#e2e8f0"),
    "Carbon_Fiber": SkinDefinition("Carbon_Fiber", "Carbon Fiber", "Tactical", "#1e293b"),
    "Heavy_Rust": SkinDefinition("Heavy_Rust", "Heavy Rust", "Industrial", "#b45309"),
    "Digital_Camouflage": SkinDefinition("Digital_Camouflage", "Digital Camo", "Military", "#475569"),
    "Battered_Armor": SkinDefinition("Battered_Armor", "Battered Hull", "Combat", "#64748b"),
    "Neon": SkinDefinition("NeonColorable_Armor", "Neon Glow", "Special", "#06b6d4"),
    "Retro": SkinDefinition("Retro", "Retro Sci-Fi", "Vintage", "#f59e0b"),
    "Wasteland_Armor": SkinDefinition("Wasteland_Armor", "Wasteland Raider", "Industrial", "#78350f"),
    "Concrete": SkinDefinition("Concrete", "Reinforced Concrete", "Station", "#9ca3af"),
    "Wood_Planks": SkinDefinition("Wood_Planks", "Wood Planks", "Special", "#854d0e"),
    "Golden_Armor": SkinDefinition("Golden_Armor", "Luxury Gold", "Prestige", "#eab308"),
    "Silver_Armor": SkinDefinition("Silver_Armor", "Polished Silver", "Prestige", "#cbd5e1"),
    "Mossy": SkinDefinition("Mossy_Armor", "Mossy Overgrown", "Organic", "#15803d"),
    "Corrugated": SkinDefinition("Corrugated", "Corrugated Steel", "Industrial", "#64748b"),
}


class SkinPaletteEngine:
    """Engine for batch armor reskinning and global HSV palette modification."""

    @staticmethod
    def rgb_to_se_hsv(r: int, g: int, b: int) -> Tuple[float, float, float]:
        """Converts RGB (0-255) to Space Engineers normalized HSV (-1.0 to 1.0 range)."""
        r_norm, g_norm, b_norm = r / 255.0, g / 255.0, b / 255.0
        h, s, v = colorsys.rgb_to_hsv(r_norm, g_norm, b_norm)
        # Space Engineers HSV mapping:
        # X: Hue in degrees / 360 (0.0 to 1.0)
        # Y: Saturation mapped from (0 to 1) -> (-0.8 to 0.8) or normalized delta
        # Z: Value mapped from (0 to 1) -> (-0.8 to 0.8)
        se_x = round(h, 4)
        se_y = round((s * 2.0) - 1.0, 4)
        se_z = round((v * 2.0) - 1.0, 4)
        return se_x, se_y, se_z

    @staticmethod
    def se_hsv_to_rgb(se_x: float, se_y: float, se_z: float) -> Tuple[int, int, int]:
        """Converts Space Engineers normalized HSV to standard RGB (0-255)."""
        h = max(0.0, min(1.0, se_x))
        s = max(0.0, min(1.0, (se_y + 1.0) / 2.0))
        v = max(0.0, min(1.0, (se_z + 1.0) / 2.0))
        r_f, g_f, b_f = colorsys.hsv_to_rgb(h, s, v)
        return int(round(r_f * 255)), int(round(g_f * 255)), int(round(b_f * 255))

    @staticmethod
    def hex_to_rgb(hex_str: str) -> Tuple[int, int, int]:
        hex_clean = hex_str.lstrip("#")
        if len(hex_clean) == 3:
            hex_clean = "".join(c * 2 for c in hex_clean)
        if len(hex_clean) != 6:
            return 255, 255, 255
        return int(hex_clean[0:2], 16), int(hex_clean[2:4], 16), int(hex_clean[4:6], 16)

    @classmethod
    def apply_skin_and_palette(
        cls,
        source_bp_path: Path,
        target_bp_path: Optional[Path] = None,
        skin_id: Optional[str] = None,
        primary_hex: Optional[str] = None,
        secondary_hex: Optional[str] = None,
        armor_only: bool = False,
    ) -> Tuple[int, int]:
        """
        Applies armor skin and/or color palette to all matching blocks in blueprint.
        Returns (blocks_reskinned, blocks_recolored).
        """
        source_bp_path = Path(source_bp_path)
        sbc_file = source_bp_path / "bp.sbc" if source_bp_path.is_dir() else source_bp_path
        if not sbc_file.is_file():
            raise FileNotFoundError(f"Blueprint SBC not found: {sbc_file}")

        tree = safe_xml.parse(sbc_file)
        root = tree.getroot()

        reskinned_count = 0
        recolored_count = 0

        target_hsv = None
        if primary_hex:
            r, g, b = cls.hex_to_rgb(primary_hex)
            target_hsv = cls.rgb_to_se_hsv(r, g, b)

        actual_skin_tag_val = None
        if skin_id and skin_id != "None":
            skin_def = OFFICIAL_SKINS.get(skin_id)
            actual_skin_tag_val = skin_def.skin_id if skin_def else skin_id

        for block in root.findall(".//CubeGrid/CubeBlocks/MyObjectBuilder_CubeBlock"):
            st_el = block.find("SubtypeName")
            if st_el is None:
                st_el = block.find("SubtypeId")
            subtype = st_el.text.strip() if st_el is not None and st_el.text else ""

            is_armor = "armor" in subtype.lower()
            if armor_only and not is_armor:
                continue

            # 1. Apply Skin
            if skin_id is not None:
                skin_elem = block.find("SkinSubtypeId")
                if skin_id == "None":
                    if skin_elem is not None:
                        block.remove(skin_elem)
                        reskinned_count += 1
                else:
                    if skin_elem is None:
                        skin_elem = ET.SubElement(block, "SkinSubtypeId")
                    skin_elem.text = actual_skin_tag_val
                    reskinned_count += 1

            # 2. Apply Color
            if target_hsv is not None:
                color_elem = block.find("ColorMaskHSV")
                if color_elem is None:
                    color_elem = ET.SubElement(block, "ColorMaskHSV")
                color_elem.set("x", str(target_hsv[0]))
                color_elem.set("y", str(target_hsv[1]))
                color_elem.set("z", str(target_hsv[2]))
                recolored_count += 1

        # Determine output location
        if target_bp_path is None:
            parent = source_bp_path.parent if source_bp_path.is_file() else source_bp_path.parent
            base_name = source_bp_path.parent.name if source_bp_path.name == "bp.sbc" else source_bp_path.stem
            target_bp_path = parent / f"{base_name}_RESKINNED"

        target_bp_path.mkdir(parents=True, exist_ok=True)
        dest_sbc = target_bp_path / "bp.sbc"

        ET.indent(tree, space="  ", level=0)
        tree.write(dest_sbc, encoding="utf-8", xml_declaration=True)

        return reskinned_count, recolored_count

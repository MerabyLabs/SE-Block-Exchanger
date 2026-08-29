"""
Armor Hardening & Lightweighting Combat Optimization Engine.
Intelligently reinforces critical subsystem zones (reactors, jump drives, cockpits, tanks) with Heavy Armor
while keeping outer or non-structural sections lightweight to preserve acceleration and jump range.
"""

from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Set, Tuple
import xml.etree.ElementTree as ET
import safe_xml
from mappings.armor import ARMOR_PAIRS

LIGHT_TO_HEAVY_MAP = dict(ARMOR_PAIRS)
HEAVY_TO_LIGHT_MAP = {target: source for source, target in LIGHT_TO_HEAVY_MAP.items()}


CRITICAL_SUBTYPES: Set[str] = {
    # Power
    "LargeBlockLargeGenerator", "LargeBlockSmallGenerator", "SmallBlockLargeGenerator", "SmallBlockSmallGenerator",
    "LargeBlockBatteryBlock", "SmallBlockBatteryBlock", "LargeBlockLargeHydrogenEngine", "SmallBlockSmallHydrogenEngine",
    # Jump Drives & Navigation
    "LargeJumpDrive", "LargeBlockCockpit", "LargeBlockCockpitIndustrial", "CockpitOpen", "DBSmallBlockFighterCockpit",
    "SmallBlockCockpit", "SmallBlockCaptainsChair",
    # Gas & Fuel Storage
    "LargeHydrogenTank", "LargeHydrogenTankSmall", "SmallHydrogenTank", "SmallHydrogenTankSmall",
    "OxygenTankSmall", "OxygenTankLarge",
    # Logic & AI
    "LargeProgrammableBlock", "SmallProgrammableBlock", "LargeBlockBeacon",
    # Critical Weapons Ammo / Conveyor Hubs
    "LargeBlockLargeContainer", "LargeBlockSmallContainer", "SmallBlockLargeContainer",
}


@dataclass
class HardeningResult:
    total_blocks_scanned: int
    critical_cores_found: int
    armor_blocks_hardened: int
    armor_blocks_lightened: int
    output_path: Path


class ArmorHardeningEngine:
    """Automated proximity-based armor optimizer."""

    @classmethod
    def harden_vital_cores(
        cls,
        source_bp_path: Path,
        target_bp_path: Optional[Path] = None,
        reinforce_radius: int = 2,
    ) -> HardeningResult:
        """
        Detects all critical subsystem coordinates and upgrades all Light Armor blocks
        within the given radius (in voxel grid units) to Heavy Armor equivalents.
        """
        source_bp_path = Path(source_bp_path)
        sbc_file = source_bp_path / "bp.sbc" if source_bp_path.is_dir() else source_bp_path
        if not sbc_file.is_file():
            raise FileNotFoundError(f"Blueprint SBC not found: {sbc_file}")

        tree = safe_xml.parse(sbc_file)
        root = tree.getroot()

        # Phase 1: Locate critical cores
        critical_coords: List[Tuple[int, int, int]] = []
        all_blocks: List[Tuple[ET.Element, int, int, int, str]] = []

        for block in root.findall(".//CubeGrid/CubeBlocks/MyObjectBuilder_CubeBlock"):
            st_el = block.find("SubtypeName")
            if st_el is None:
                st_el = block.find("SubtypeId")
            subtype = st_el.text.strip() if st_el is not None and st_el.text else ""

            min_elem = block.find("Min")
            if min_elem is not None:
                bx = int(min_elem.attrib.get("x", "0"))
                by = int(min_elem.attrib.get("y", "0"))
                bz = int(min_elem.attrib.get("z", "0"))
            else:
                bx, by, bz = 0, 0, 0

            all_blocks.append((block, bx, by, bz, subtype))

            if subtype in CRITICAL_SUBTYPES or any(c in subtype.lower() for c in ("reactor", "jumpdrive", "hydrogentank", "cockpit")):
                critical_coords.append((bx, by, bz))

        # Phase 2: Convert nearby Light Armor to Heavy Armor
        hardened_count = 0
        light_to_heavy_map = LIGHT_TO_HEAVY_MAP

        for block, bx, by, bz, subtype in all_blocks:
            if subtype in light_to_heavy_map:
                # Check proximity to any critical core
                is_near_critical = False
                for cx, cy, cz in critical_coords:
                    # Chebyshev distance (cube radius)
                    dist = max(abs(bx - cx), abs(by - cy), abs(bz - cz))
                    if dist <= reinforce_radius:
                        is_near_critical = True
                        break

                if is_near_critical:
                    new_subtype = light_to_heavy_map[subtype]
                    subtype_elem = block.find("SubtypeName")
                    if subtype_elem is not None:
                        subtype_elem.text = new_subtype
                    else:
                        sub_id = block.find("SubtypeId")
                        if sub_id is not None:
                            sub_id.text = new_subtype
                    hardened_count += 1

        if target_bp_path is None:
            parent = source_bp_path.parent if source_bp_path.is_file() else source_bp_path.parent
            base_name = source_bp_path.parent.name if source_bp_path.name == "bp.sbc" else source_bp_path.stem
            target_bp_path = parent / f"{base_name}_HARDENED"

        target_bp_path.mkdir(parents=True, exist_ok=True)
        dest_sbc = target_bp_path / "bp.sbc"

        ET.indent(tree, space="  ", level=0)
        safe_xml.safe_write(tree, dest_sbc)

        return HardeningResult(
            total_blocks_scanned=len(all_blocks),
            critical_cores_found=len(critical_coords),
            armor_blocks_hardened=hardened_count,
            armor_blocks_lightened=0,
            output_path=target_bp_path,
        )

    @classmethod
    def lightweight_outer_hull(
        cls,
        source_bp_path: Path,
        target_bp_path: Optional[Path] = None,
        preserve_radius: int = 1,
    ) -> HardeningResult:
        """
        Converts Heavy Armor to Light Armor EXCEPT within preserve_radius of vital core systems.
        """
        source_bp_path = Path(source_bp_path)
        sbc_file = source_bp_path / "bp.sbc" if source_bp_path.is_dir() else source_bp_path
        if not sbc_file.is_file():
            raise FileNotFoundError(f"Blueprint SBC not found: {sbc_file}")

        tree = safe_xml.parse(sbc_file)
        root = tree.getroot()

        critical_coords: List[Tuple[int, int, int]] = []
        all_blocks: List[Tuple[ET.Element, int, int, int, str]] = []

        for block in root.findall(".//CubeGrid/CubeBlocks/MyObjectBuilder_CubeBlock"):
            st_el = block.find("SubtypeName")
            if st_el is None:
                st_el = block.find("SubtypeId")
            subtype = st_el.text.strip() if st_el is not None and st_el.text else ""

            min_elem = block.find("Min")
            bx = int(min_elem.attrib.get("x", "0")) if min_elem is not None else 0
            by = int(min_elem.attrib.get("y", "0")) if min_elem is not None else 0
            bz = int(min_elem.attrib.get("z", "0")) if min_elem is not None else 0

            all_blocks.append((block, bx, by, bz, subtype))

            if subtype in CRITICAL_SUBTYPES or any(c in subtype.lower() for c in ("reactor", "jumpdrive", "hydrogentank", "cockpit")):
                critical_coords.append((bx, by, bz))

        lightened_count = 0
        heavy_to_light_map = HEAVY_TO_LIGHT_MAP

        for block, bx, by, bz, subtype in all_blocks:
            if subtype in heavy_to_light_map:
                # Check proximity to any critical core
                is_near_critical = False
                for cx, cy, cz in critical_coords:
                    dist = max(abs(bx - cx), abs(by - cy), abs(bz - cz))
                    if dist <= preserve_radius:
                        is_near_critical = True
                        break

                # If NOT near critical core, lightweight it to light armor
                if not is_near_critical:
                    new_subtype = heavy_to_light_map[subtype]
                    subtype_elem = block.find("SubtypeName")
                    if subtype_elem is not None:
                        subtype_elem.text = new_subtype
                    else:
                        sub_id = block.find("SubtypeId")
                        if sub_id is not None:
                            sub_id.text = new_subtype
                    lightened_count += 1

        if target_bp_path is None:
            parent = source_bp_path.parent if source_bp_path.is_file() else source_bp_path.parent
            base_name = source_bp_path.parent.name if source_bp_path.name == "bp.sbc" else source_bp_path.stem
            target_bp_path = parent / f"{base_name}_LIGHTWEIGHT"

        target_bp_path.mkdir(parents=True, exist_ok=True)
        dest_sbc = target_bp_path / "bp.sbc"

        ET.indent(tree, space="  ", level=0)
        safe_xml.safe_write(tree, dest_sbc)

        return HardeningResult(
            total_blocks_scanned=len(all_blocks),
            critical_cores_found=len(critical_coords),
            armor_blocks_hardened=0,
            armor_blocks_lightened=lightened_count,
            output_path=target_bp_path,
        )

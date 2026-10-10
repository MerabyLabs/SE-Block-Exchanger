"""
Loud warning for mod and unknown subtypes during armor conversion.

Armor light/heavy conversion rewrites known armor subtypes only. Workshop
blocks such as ``STR350_*`` and ``ARYLNX_*`` stay in the blueprint XML.
Space Engineers hides those cubes when the defining mods are not loaded,
which looks like the conversion dropped thrusters or engines.

This module detects those subtypes. It does not remap or delete them.
"""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Dict, Iterable, Mapping, Optional, Set
from xml.etree.ElementTree import Element

import safe_xml
from mappings.armor import ARMOR_PAIRS
from mappings.dlc_substitution import DLC_TO_BASE_PAIRS
from mappings.functional import FUNCTIONAL_PAIRS
from mappings.prototech import PROTOTECH_TO_VANILLA_PAIRS, VANILLA_TO_PROTOTECH_PAIRS
from mappings.thrusters import THRUSTER_PAIRS
from mappings.weapons import WEAPON_PAIRS
from resource_paths import resource_path

MOD_BLOCK_WARNING_HEADLINE = "WARNING: MOD OR UNKNOWN BLOCKS"
MOD_BLOCK_WARNING_DETAIL = (
    "Space Engineers may hide these blocks if the mods are not loaded."
)
QA_GATE_EXIT_CODE = 2
QA_GATE_LINE = (
    "QA GATE: non-vanilla subtypes are in this blueprint. "
    "Do not mark invent-critical CLEAR unless the spawn world has those mods loaded."
)

# Keen-style ids missing from the small cost catalog (gyros, catwalks, …)
# must not raise the mod warning. Author tokens such as STR350_ and ARYLNX_
# are caught before this prefix list.
_KEEN_PREFIXES = (
    "Large",
    "Small",
    "Basic",
    "Window",
    "Interior",
    "Passage",
    "Dead",
    "Armor",
    "Half",
    "Round",
    "Steel",
    "Catwalk",
    "Railing",
    "Stairs",
    "Conveyor",
    "Control",
    "Timer",
    "Button",
    "Sensor",
    "Camera",
    "Beacon",
    "Antenna",
    "Gyro",
    "Cockpit",
    "Door",
    "Airtight",
    "Medical",
    "Survival",
    "Oxygen",
    "Hydrogen",
    "Battery",
    "Reactor",
    "Solar",
    "Wind",
    "Collector",
    "Connector",
    "Merge",
    "Piston",
    "Rotor",
    "Hinge",
    "Wheel",
    "Suspension",
    "Landing",
    "Parachute",
    "Warhead",
    "Decoy",
    "Programmable",
    "Projector",
    "Sound",
    "Text",
    "LCD",
    "Store",
    "Vending",
    "Contract",
    "Safe",
    "Jukebox",
    "Piano",
    "Shower",
    "Bed",
    "Kitchen",
    "Couch",
    "Toilet",
    "Plant",
    "Freight",
    "Buggy",
    "Rover",
    "Industrial",
    "SciFi",
    "Warfare",
    "Contact",
    "Signal",
    "Prototech",
    "Factorum",
    "Offroad",
    "Exhaust",
    "Welder",
    "Grinder",
    "Drill",
    "Assembler",
    "Refinery",
    "Upgrade",
    "Gatling",
    "Missile",
    "Rocket",
    "Artillery",
    "Autocannon",
    "Railgun",
    "Turret",
    "Jump",
    "Gravity",
    "Remote",
    "Spotlight",
    "Neon",
    "Cryo",
)


def _pairs_into(known: Set[str], pairs: Mapping[str, str]) -> None:
    known.update(pairs.keys())
    known.update(pairs.values())


@lru_cache(maxsize=1)
def known_vanilla_subtypes() -> frozenset:
    """
    Built-in armor pairs plus other vanilla endpoints this tool already maps.

    Profile and workshop ids are not included. A subtype in this set is never
    reported as a mod block.
    """
    known: Set[str] = set()
    for pairs in (
        ARMOR_PAIRS,
        THRUSTER_PAIRS,
        WEAPON_PAIRS,
        FUNCTIONAL_PAIRS,
        DLC_TO_BASE_PAIRS,
        VANILLA_TO_PROTOTECH_PAIRS,
        PROTOTECH_TO_VANILLA_PAIRS,
    ):
        _pairs_into(known, pairs)

    cost_path = resource_path("data", "block_costs.json")
    if cost_path.exists():
        payload = json.loads(cost_path.read_text(encoding="utf-8"))
        blocks = payload.get("blocks", {})
        if isinstance(blocks, dict):
            known.update(str(key) for key in blocks.keys())
    return frozenset(known)


def mod_style_author_prefix(subtype: str) -> bool:
    """
    True for workshop-style ids whose first token is an author or pack code.

    ``STR350_Flat`` (digits) and ``ARYLNX_SCIRCOCCO_Epstein_Drive`` (all caps)
    match. Keen names such as ``LargeRoundArmor_Slope`` do not.
    """
    if "_" not in subtype:
        return False
    head = subtype.split("_", 1)[0]
    if len(head) < 2:
        return False
    if any(ch.isdigit() for ch in head):
        return True
    return head.isupper()


def is_unresolved_mod_subtype(subtype: str, known: Optional[Iterable[str]] = None) -> bool:
    """
    True when ``subtype`` is outside built-in armor and known vanilla maps
    and does not use a Keen block id shape.
    """
    if not subtype:
        return False
    catalog = known_vanilla_subtypes() if known is None else frozenset(known)
    if subtype in catalog:
        return False
    if mod_style_author_prefix(subtype):
        return True
    if subtype.startswith(_KEEN_PREFIXES):
        return False
    return True


def iter_cubeblock_subtypes(root: Element) -> Iterable[str]:
    """Every CubeBlocks child, including thrust and other non-armor builders."""
    for block in safe_xml.iter_cube_blocks(root):
        subtype = safe_xml.get_subtype(block)
        if subtype:
            yield subtype


def unresolved_mod_counts(root: Element) -> Dict[str, int]:
    """Map unresolved subtype → block count. Does not modify the tree."""
    counts: Dict[str, int] = {}
    known = known_vanilla_subtypes()
    for subtype in iter_cubeblock_subtypes(root):
        if is_unresolved_mod_subtype(subtype, known):
            counts[subtype] = counts.get(subtype, 0) + 1
    return counts


def format_mod_block_warning(counts: Mapping[str, int]) -> str:
    """Multi-line warning. Empty when ``counts`` is empty."""
    if not counts:
        return ""
    lines = [
        MOD_BLOCK_WARNING_HEADLINE,
        MOD_BLOCK_WARNING_DETAIL,
        "Armor conversion does not remove or remap them; they stay in the blueprint XML.",
        "Spawn this ship only in a world that has the same mods loaded.",
        "",
    ]
    for subtype, count in sorted(counts.items()):
        lines.append(f"  {subtype}  x{count}")
    return "\n".join(lines)


def warning_for_blueprint_file(path) -> str:
    """Scan a ``bp.sbc`` and return the loud warning, or ``\"\"``."""
    tree = safe_xml.parse(path)
    root = tree.getroot()
    if root is None:
        return ""
    return format_mod_block_warning(unresolved_mod_counts(root))


def armor_category_enabled(categories: Optional[Iterable[str]]) -> bool:
    """True when the active category list includes built-in armor."""
    if not categories:
        return False
    return any(str(name).strip().lower() == "armor" for name in categories)

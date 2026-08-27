"""
Prototech and Factorum Endgame Mapping Category.
Provides bidirectional mappings between standard Vanilla blocks and endgame Prototech blocks.
Includes Survival Sanity rules to replace uncraftable Prototech blocks for standard survival projectors.
"""

from typing import Dict, Set
from mappings.registry import MappingCategory

# Standard Vanilla -> Prototech Upgrades
VANILLA_TO_PROTOTECH_PAIRS: Dict[str, str] = {
    # Power & Energy
    "LargeBlockLargeGenerator": "LargePrototechGenerator",
    "LargeBlockSmallGenerator": "LargePrototechGeneratorSmall",
    "LargeBlockBatteryBlock": "PrototechBattery",
    "SmallBlockBatteryBlock": "PrototechBatterySmall",

    # Propulsion
    "LargeBlockLargeThrust": "LargePrototechThruster",
    "LargeBlockSmallThrust": "LargePrototechThrusterSmall",
    "SmallBlockLargeThrust": "SmallPrototechThruster",
    "SmallBlockSmallThrust": "SmallPrototechThrusterSmall",
    "LargeBlockLargeHydrogenThrust": "LargePrototechHydrogenThruster",
    "LargeBlockSmallHydrogenThrust": "LargePrototechHydrogenThrusterSmall",

    # Production & Utility
    "LargeRefinery": "PrototechRefinery",
    "LargeAssembler": "PrototechAssembler",
    "LargeHydrogenEngine": "LargePrototechHydrogenEngine",
    "LargeOxygenGenerator": "LargePrototechO2H2",
    "LargeJumpDrive": "PrototechJumpDrive",

    # Combat & Offense
    "LargeGatlingTurret": "PrototechGatlingTurret",
    "LargeMissileTurret": "PrototechMissileTurret",
    "LargeInteriorTurret": "PrototechInteriorTurret",
    "LargeArtilleryTurret": "PrototechArtilleryTurret",
    "LargeRailgun": "PrototechRailgun",

    # Tools
    "LargeBlockDrill": "PrototechDrill",
    "LargeBlockGrinder": "PrototechGrinder",
    "LargeBlockWelder": "PrototechWelder",
}

# Reverse: Prototech -> Survival-Craftable Vanilla Equivalents (Survival Sanity Mode)
PROTOTECH_TO_VANILLA_PAIRS: Dict[str, str] = {
    v: k for k, v in VANILLA_TO_PROTOTECH_PAIRS.items()
}

# Set of all known Prototech subtypes for fast lookup and survival audits
PROTOTECH_SUBTYPES: Set[str] = set(VANILLA_TO_PROTOTECH_PAIRS.values())


def get_category() -> MappingCategory:
    return MappingCategory(
        name="prototech",
        description="Bidirectional swaps between standard Vanilla blocks and Factorum Prototech tech.",
        pairs=VANILLA_TO_PROTOTECH_PAIRS,
        grid_sizes=("Large", "Small"),
        enabled_by_default=False,
        tags=("endgame", "factorum", "prototech", "upgrade"),
    )


def get_survival_sanity_mapping() -> Dict[str, str]:
    """Returns mapping to downgrade all uncraftable Prototech blocks to standard survival blocks."""
    return dict(PROTOTECH_TO_VANILLA_PAIRS)

"""
Prototech and Factorum Endgame Mapping Category.
Provides bidirectional mappings between standard Vanilla blocks and endgame Prototech blocks.
Includes Survival Sanity rules to replace uncraftable Prototech blocks for standard survival projectors.
"""

from __future__ import annotations

from typing import Dict, Set

# MappingCategory is imported lazily in get_category() to avoid a registry cycle.

# Standard Vanilla -> Prototech Upgrades
VANILLA_TO_PROTOTECH_PAIRS: Dict[str, str] = {
    # Power & Energy
    "LargeBlockLargeGenerator": "LargePrototechGenerator",
    "LargeBlockSmallGenerator": "LargePrototechGeneratorSmall",
    "LargeBlockBatteryBlock": "LargePrototechBattery",
    "SmallBlockBatteryBlock": "SmallPrototechBattery",

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
    "LargeJumpDrive": "LargePrototechJumpDrive",

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
    # Power
    "LargePrototechGenerator": "LargeBlockLargeGenerator",
    "LargePrototechReactor": "LargeBlockLargeGenerator",
    "LargePrototechGeneratorSmall": "LargeBlockSmallGenerator",
    "PrototechBattery": "LargeBlockBatteryBlock",
    "LargePrototechBattery": "LargeBlockBatteryBlock",
    "PrototechBatterySmall": "SmallBlockBatteryBlock",
    "SmallPrototechBattery": "SmallBlockBatteryBlock",
    "PrototechCapacitor": "LargeBlockBatteryBlock",
    "LargePrototechCapacitor": "LargeBlockBatteryBlock",

    # Propulsion
    "LargePrototechThruster": "LargeBlockLargeThrust",
    "LargePrototechThrust": "LargeBlockLargeThrust",
    "LargePrototechThrusterSmall": "LargeBlockSmallThrust",
    "SmallPrototechThruster": "SmallBlockLargeThrust",
    "SmallPrototechThrusterSmall": "SmallBlockSmallThrust",
    "LargePrototechHydrogenThruster": "LargeBlockLargeHydrogenThrust",
    "LargePrototechHydrogenThrusterSmall": "LargeBlockSmallHydrogenThrust",

    # Utility & Production
    "PrototechRefinery": "LargeRefinery",
    "LargePrototechRefinery": "LargeRefinery",
    "PrototechAssembler": "LargeAssembler",
    "LargePrototechAssembler": "LargeAssembler",
    "LargePrototechHydrogenEngine": "LargeHydrogenEngine",
    "LargePrototechO2H2": "LargeOxygenGenerator",
    "PrototechO2H2": "LargeOxygenGenerator",
    "PrototechJumpDrive": "LargeJumpDrive",
    "LargePrototechJumpDrive": "LargeJumpDrive",

    # Combat
    "PrototechGatlingTurret": "LargeGatlingTurret",
    "PrototechMissileTurret": "LargeMissileTurret",
    "PrototechInteriorTurret": "LargeInteriorTurret",
    "PrototechArtilleryTurret": "LargeArtilleryTurret",
    "PrototechRailgun": "LargeRailgun",

    # Tools
    "PrototechDrill": "LargeBlockDrill",
    "LargePrototechDrill": "LargeBlockDrill",
    "PrototechGrinder": "LargeBlockGrinder",
    "LargePrototechGrinder": "LargeBlockGrinder",
    "PrototechWelder": "LargeBlockWelder",
    "LargePrototechWelder": "LargeBlockWelder",
}

# Set of all known Prototech subtypes for fast lookup and survival audits
PROTOTECH_SUBTYPES: Set[str] = set(PROTOTECH_TO_VANILLA_PAIRS.keys())


def get_category():
    from mappings.registry import MappingCategory

    return MappingCategory(
        name="prototech",
        description="Bidirectional swaps between standard Vanilla blocks and Factorum Prototech tech.",
        pairs=VANILLA_TO_PROTOTECH_PAIRS,
        grid_sizes=("Large", "Small"),
        source="endgame",
        enabled_by_default=False,
        tags=("endgame", "factorum", "prototech", "upgrade"),
    )


def get_survival_sanity_mapping() -> Dict[str, str]:
    """Returns mapping to downgrade all uncraftable Prototech blocks to standard survival blocks."""
    return dict(PROTOTECH_TO_VANILLA_PAIRS)


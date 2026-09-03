"""Current SE1 Prototech candidates; unsafe footprint/type changes are disabled."""
from typing import Dict, Set

CATEGORY_NAME = "prototech"
CATEGORY_DESCRIPTION = "Catalog-validated Factorum Prototech conversions."
CATEGORY_TAGS = ("endgame", "factorum", "prototech", "upgrade")

VANILLA_TO_PROTOTECH_PAIRS: Dict[str, str] = {
    "LargeBlockLargeGenerator": "LargePrototechReactor",
    "LargeBlockBatteryBlock": "LargeBlockPrototechBattery",
    "SmallBlockBatteryBlock": "SmallBlockPrototechBattery",
    "LargeBlockLargeThrust": "LargeBlockPrototechThruster",
    "SmallBlockLargeThrust": "SmallBlockPrototechThruster",
    "LargeRefinery": "LargePrototechRefinery",
    "LargeAssembler": "LargePrototechAssembler",
    "OxygenGenerator/": "LargeBlockPrototechOxygenGenerator",
    "LargeJumpDrive": "LargePrototechJumpDrive",
    "LargeBlockGyro": "LargeBlockPrototechGyro",
    "SmallBlockGyro": "SmallBlockPrototechGyro",
    "LargeBlockDrill": "LargeBlockPrototechDrill",
}
PROTOTECH_TO_VANILLA_PAIRS = {target: source for source, target in VANILLA_TO_PROTOTECH_PAIRS.items()}
# Small Prototech refinery/jump drive have no vanilla small-grid counterpart.
PROTOTECH_SUBTYPES: Set[str] = set(PROTOTECH_TO_VANILLA_PAIRS) | {"SmallPrototechRefinery", "SmallPrototechJumpDrive"}


def get_category():
    from mappings.registry import MappingCategory
    return MappingCategory(name=CATEGORY_NAME, description=CATEGORY_DESCRIPTION,
                           pairs=VANILLA_TO_PROTOTECH_PAIRS, enabled_by_default=False,
                           tags=CATEGORY_TAGS, source="endgame")


def get_survival_sanity_mapping() -> Dict[str, str]:
    return dict(PROTOTECH_TO_VANILLA_PAIRS)


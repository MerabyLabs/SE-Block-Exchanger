"""
Functional block upgrade mappings.
"""

from mappings.registry import MappingCategory


FUNCTIONAL_PAIRS = {
    "BasicAssembler": "LargeAssembler",
    "BasicRefinery": "LargeRefinery",
    "LargeBlockSmallGenerator": "LargeBlockLargeGenerator",
    "SmallBlockSmallGenerator": "SmallBlockLargeGenerator",
    "LargeBlockSmallContainer": "LargeBlockLargeContainer",
    "SmallBlockSmallContainer": "SmallBlockLargeContainer",
    "Collector": "FlatCollector",
    "SmallBlockBatteryBlock": "LargeBlockBatteryBlock",
}


def get_category() -> MappingCategory:
    return MappingCategory(
        name="functional",
        description="Upgrades for production, storage, and power-generation blocks.",
        pairs=FUNCTIONAL_PAIRS,
        grid_sizes=("Large", "Small"),
        enabled_by_default=False,
        tags=("utility", "upgrade"),
    )


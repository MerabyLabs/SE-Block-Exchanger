"""
Weapon upgrade mappings.
"""

from mappings.registry import MappingCategory


WEAPON_PAIRS = {
    "LargeGatlingTurret/": "LargeCalibreTurret",
    "LargeInteriorTurret": "LargeCalibreTurret",
    "LargeMissileTurret/": "LargeCalibreTurret",
    "SmallGatlingGun/": "SmallBlockAutocannon",
    "SmallMissileLauncher/": "SmallBlockMediumCalibreGun",
}


def get_category() -> MappingCategory:
    return MappingCategory(
        name="weapons",
        description="Vanilla weapon tier upgrades (gatling/interior/rocket families).",
        pairs=WEAPON_PAIRS,
        grid_sizes=("Large", "Small"),
        enabled_by_default=False,
        tags=("combat", "upgrade"),
    )


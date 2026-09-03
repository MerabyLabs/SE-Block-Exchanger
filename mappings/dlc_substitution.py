"""Known SE1 DLC substitutions. Every pair is validated against real definitions."""
from mappings.registry import MappingCategory

DLC_TO_BASE_PAIRS = {
    # Prosperity, Contact and cockpit variants.
    "LargeBlockOpenSlopedCockpit": "LargeBlockCockpit",
    "LargeBlockClosedSlopedCockpit": "LargeBlockCockpit",
    "SmallBlockOpenSlopedCockpit": "SmallBlockCockpit",
    "SmallBlockClosedSlopedCockpit": "SmallBlockCockpit",
    "LargeBlockBatteryReskin": "LargeBlockBatteryBlock",
    "LargeBlockBatteryReskinOffset": "LargeBlockBatteryBlock",
    "SmallBlockBatteryReskin": "SmallBlockBatteryBlock",
    "LargeBlockModularBridgeCockpit": "LargeBlockCockpit",
    "OpenCockpitLarge": "LargeBlockCockpit",
    "OpenCockpitSmall": "SmallBlockCockpit",
    "BuggyCockpit": "SmallBlockCockpit",
    "RoverCockpit": "SmallBlockCockpit",
    # Default turret definitions deliberately use empty subtypes.
    "LargeGatlingTurretReskin": "LargeGatlingTurret/",
    "LargeMissileTurretReskin": "LargeMissileTurret/",
    "SmallGatlingTurretReskin": "SmallGatlingTurret",
    "SmallMissileTurretReskin": "SmallMissileTurret",
    "LargeBlockSmallThrustSciFi": "LargeBlockSmallThrust",
    "LargeBlockLargeThrustSciFi": "LargeBlockLargeThrust",
    "SmallBlockSmallThrustSciFi": "SmallBlockSmallThrust",
    "SmallBlockLargeThrustSciFi": "SmallBlockLargeThrust",
    "LargeBlockSmallHydrogenThrustIndustrial": "LargeBlockSmallHydrogenThrust",
    "LargeBlockLargeHydrogenThrustIndustrial": "LargeBlockLargeHydrogenThrust",
    "SmallBlockSmallHydrogenThrustIndustrial": "SmallBlockSmallHydrogenThrust",
    "SmallBlockLargeHydrogenThrustIndustrial": "SmallBlockLargeHydrogenThrust",
    "LargeBlockSmallAtmosphericThrustSciFi": "LargeBlockSmallAtmosphericThrust",
    "LargeBlockLargeAtmosphericThrustSciFi": "LargeBlockLargeAtmosphericThrust",
    "SmallBlockSmallAtmosphericThrustSciFi": "SmallBlockSmallAtmosphericThrust",
    "SmallBlockLargeAtmosphericThrustSciFi": "SmallBlockLargeAtmosphericThrust",
}


def get_category() -> MappingCategory:
    return MappingCategory(
        name="dlc_substitution",
        description="Validated DLC alternatives; blocks without a safe counterpart stay unchanged.",
        pairs=DLC_TO_BASE_PAIRS, enabled_by_default=False,
        tags=("utility", "vanilla", "dlc"),
    )

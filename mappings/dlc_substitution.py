"""
DLC to base game (vanilla) replacement mappings.
Helps players eliminate DLC requirements from downloaded blueprints.
Includes coverage for all major DLCs through the 2026 Prosperity Pack.
"""

from mappings.registry import MappingCategory

DLC_TO_BASE_PAIRS = {
    # ============================================================
    # PROSPERITY PACK (2026) -> Vanilla Base Equivalents
    # ============================================================
    "LargeSlopedCockpit": "LargeBlockCockpit",
    "SmallSlopedCockpit": "Cockpit",
    "LargeGridSlopedCockpit": "LargeBlockCockpit",
    "LargeBatteryBank": "LargeBlockBatteryBlock",
    "SmallBatteryBank": "SmallBlockBatteryBlock",
    "FactoryStairs": "LargeStairs",
    "LargeFactoryStairs": "LargeStairs",
    "FactoryRailing": "Railing",
    "LargeFactoryRailing": "Railing",
    "IndustrialWalkway": "SteelCatwalk",
    "LargeIndustrialWalkway": "SteelCatwalk",
    "IndustrialWalkwayCorner": "SteelCatwalkCorner",
    "ConduitConveyor": "ConveyorTube",
    "DecorativeConduit": "ConveyorTube",
    "LargeDecorativeConduit": "LargeBlockConveyor",
    "ProsperityCockpit": "LargeBlockCockpit",
    "ProsperityDesk": "ControlPanel",
    "ProsperityControlStation": "ControlPanel",
    "ProsperityBattery": "LargeBlockBatteryBlock",

    # ============================================================
    # CONTACT PACK (2024) -> Vanilla Base Equivalents
    # ============================================================
    "ContactRadarAntenna": "LargeBlockBeacon",
    "LargeRadarAntenna": "LargeBlockRadioAntenna",
    "RadarAntenna": "LargeBlockRadioAntenna",
    "ContactBridgeCockpit": "LargeBlockCockpit",
    "FactorumConsole": "ControlPanel",
    "ContactWindowCorner": "Window1x1Slope",
    "ContactWindow": "Window1x1Flat",
    "ContactDecorativeBridge": "LargeBlockCockpit",
    "ContactControlTerminal": "ControlPanel",

    # ============================================================
    # SIGNAL PACK (2024) -> Vanilla Base Equivalents
    # ============================================================
    "SignalBeacon": "LargeBlockBeacon",
    "SmallSignalBeacon": "SmallBlockBeacon",
    "BroadcastControllerDecorative": "ControlPanel",
    "ActionTriggerBlockDecorative": "TimerBlock",
    "SignalAntennaCompact": "LargeBlockRadioAntenna",

    # ============================================================
    # THRUSTERS (Industrial & Sci-Fi DLCs to Vanilla counterparts)
    # ============================================================
    # Sci-Fi Ion Thrusters
    "LargeBlockSmallThrustSciFi": "LargeBlockSmallThrust",
    "LargeBlockLargeThrustSciFi": "LargeBlockLargeThrust",
    "SmallBlockSmallThrustSciFi": "SmallBlockSmallThrust",
    "SmallBlockLargeThrustSciFi": "SmallBlockLargeThrust",

    # Sci-Fi Atmospheric Thrusters
    "LargeBlockSmallAtmosphericThrustSciFi": "LargeBlockSmallAtmosphericThrust",
    "LargeBlockLargeAtmosphericThrustSciFi": "LargeBlockLargeAtmosphericThrust",
    "SmallBlockSmallAtmosphericThrustSciFi": "SmallBlockSmallAtmosphericThrust",
    "SmallBlockLargeAtmosphericThrustSciFi": "SmallBlockLargeAtmosphericThrust",

    # Sci-Fi Hydrogen Thrusters
    "LargeBlockSmallHydrogenThrustSciFi": "LargeBlockSmallHydrogenThrust",
    "LargeBlockLargeHydrogenThrustSciFi": "LargeBlockLargeHydrogenThrust",
    "SmallBlockSmallHydrogenThrustSciFi": "SmallBlockSmallHydrogenThrust",
    "SmallBlockLargeHydrogenThrustSciFi": "SmallBlockLargeHydrogenThrust",

    # Industrial Thrusters (Hydrogen / Ion)
    "LargeBlockSmallHydrogenThrustIndustrial": "LargeBlockSmallHydrogenThrust",
    "LargeBlockLargeHydrogenThrustIndustrial": "LargeBlockLargeHydrogenThrust",
    "SmallBlockSmallHydrogenThrustIndustrial": "SmallBlockSmallHydrogenThrust",
    "SmallBlockLargeHydrogenThrustIndustrial": "SmallBlockLargeHydrogenThrust",

    "LargeBlockSmallThrustIndustrial": "LargeBlockSmallThrust",
    "LargeBlockLargeThrustIndustrial": "LargeBlockLargeThrust",
    "SmallBlockSmallThrustIndustrial": "SmallBlockSmallThrust",
    "SmallBlockLargeThrustIndustrial": "SmallBlockLargeThrust",

    # Atmospheric Dusted
    "AtmosphericThrusterDusted": "LargeBlockSmallAtmosphericThrust",

    # ============================================================
    # COCKPITS & CONTROLS (Decorative, Wasteland, Warfare DLCs)
    # ============================================================
    "IndustrialCockpit": "LargeBlockCockpit",
    "IndustrialCockpitSmall": "Cockpit",
    "BuggyCockpit": "Cockpit",
    "CabCockpit": "Cockpit",
    "RoverCockpit": "Cockpit",
    "WastelandCockpit": "Cockpit",
    "OpenCockpitLarge": "LargeBlockCockpit",
    "OpenCockpitSmall": "Cockpit",
    "SubattachedCockpit": "Cockpit",
    "FreightCockpit": "LargeBlockCockpit",
    "TacticalMap": "ControlPanel",
    "DecorativeConsole": "ControlPanel",
    "SciFiBarCounter": "ControlPanel",

    # ============================================================
    # INDUSTRIAL & PRODUCTION BLOCKS
    # ============================================================
    "LargeIndustrialAssembler": "LargeAssembler",
    "LargeIndustrialRefinery": "LargeRefinery",
    "IndustrialSeparator": "LargeBlockSmallContainer",
    "SmallIndustrialContainer": "SmallBlockSmallContainer",
    "LargeIndustrialContainer": "LargeBlockLargeContainer",
    "IndustrialCargo1": "LargeBlockSmallContainer",
    "IndustrialCargo2": "LargeBlockLargeContainer",
    "LargeConveyorPipe": "ConveyorTube",
    "SmallConveyorPipe": "ConveyorTube",

    # ============================================================
    # COMBAT/WEAPONS RESKINS (Warfare 1 & Warfare 2 DLCs)
    # ============================================================
    "GatlingTurretReskin": "LargeGatlingTurret",
    "MissileTurretReskin": "LargeMissileTurret",
    "LargeBlockInteriorTurretWarfare2": "LargeInteriorTurret",
    "SmallBlockGatlingTurretWarfare2": "SmallGatlingTurret",
    "SmallBlockGatlingGunWarfare2": "SmallGatlingGun",
    "WarfareRocketLauncher": "SmallMissileLauncher",
    "WarfareGatlingGun": "SmallGatlingGun",

    # ============================================================
    # DECORATIVE & LIVING BLOCKS (Decorative Packs 1, 2, 3)
    # ============================================================
    "StoreBlockSingle": "StoreBlock",
    "VendingMachineSingle": "VendingMachine",
    "MedicalStationDecorative": "MedicalRoom",
    "SurvivalKitDecorative": "SurvivalKit",
    "SciFiInteriorWall": "InteriorWall",
    "ShowerBlock": "InteriorWall",
    "ArmoryBlock": "LargeBlockSmallContainer",
    "LockersBlock": "LargeBlockSmallContainer",
}


def get_category() -> MappingCategory:
    return MappingCategory(
        name="dlc_substitution",
        description="Replaces paid DLC blocks with standard, base-game (Vanilla) alternatives.",
        pairs=DLC_TO_BASE_PAIRS,
        grid_sizes=("Large", "Small"),
        enabled_by_default=False,
        tags=("utility", "vanilla", "dlc"),
    )

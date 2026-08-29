"""
Test Grid Matrix Generator.
Generates realistic, complex Space Engineers .sbc blueprints covering every subsystem archetype:
1. Battleship_Vindicator (Capital combat grid with mixed armor and propulsion)
2. Industrial_Excavator (DLC-heavy mining and processing rig)
3. Recon_Scout_Drone (Small grid programmable drone with embedded C# MDK script)
4. Prototech_Sanctuary (Endgame Factorum Prototech installation)
5. MultiGrid_Walker (Multi-tiered mechanical subgrid hierarchy)
"""

from pathlib import Path
from typing import Dict


def generate_battleship_xml(name: str = "Battleship_Vindicator") -> str:
    return f"""<?xml version="1.0" encoding="utf-8"?>
<Definitions xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <ShipBlueprints>
    <ShipBlueprint xsi:type="MyObjectBuilder_ShipBlueprintDefinition">
      <Id Type="MyObjectBuilder_ShipBlueprintDefinition" Subtype="{name}" />
      <DisplayName>{name}</DisplayName>
      <CubeGrids>
        <CubeGrid>
          <SubtypeName />
          <EntityId>10001001</EntityId>
          <PersistentFlags>CastShadows</PersistentFlags>
          <PositionAndOrientation>
            <Position x="0.0" y="0.0" z="0.0" />
            <Forward x="0.0" y="0.0" z="-1.0" />
            <Up x="0.0" y="1.0" z="0.0" />
            <Orientation>
              <X>0</X><Y>0</Y><Z>0</Z><W>1</W>
            </Orientation>
          </PositionAndOrientation>
          <GridSizeEnum>Large</GridSizeEnum>
          <CubeBlocks>
            <!-- Heavy Armor Citadel -->
            <MyObjectBuilder_CubeBlock xsi:type="MyObjectBuilder_CubeBlock">
              <SubtypeName>LargeHeavyBlockArmorBlock</SubtypeName>
              <Min x="0" y="0" z="0" />
              <ColorMaskHSV x="0" y="-0.8" z="0" />
            </MyObjectBuilder_CubeBlock>
            <MyObjectBuilder_CubeBlock xsi:type="MyObjectBuilder_CubeBlock">
              <SubtypeName>LargeHeavyBlockArmorSlope</SubtypeName>
              <Min x="1" y="0" z="0" />
            </MyObjectBuilder_CubeBlock>
            <MyObjectBuilder_CubeBlock xsi:type="MyObjectBuilder_CubeBlock">
              <SubtypeName>LargeHeavyBlockArmorCorner</SubtypeName>
              <Min x="1" y="1" z="0" />
            </MyObjectBuilder_CubeBlock>
            
            <!-- Light Armor Outer Hull -->
            <MyObjectBuilder_CubeBlock xsi:type="MyObjectBuilder_CubeBlock">
              <SubtypeName>LargeBlockArmorBlock</SubtypeName>
              <Min x="0" y="0" z="1" />
            </MyObjectBuilder_CubeBlock>
            <MyObjectBuilder_CubeBlock xsi:type="MyObjectBuilder_CubeBlock">
              <SubtypeName>LargeBlockArmorSlope</SubtypeName>
              <Min x="0" y="1" z="1" />
            </MyObjectBuilder_CubeBlock>
            <MyObjectBuilder_CubeBlock xsi:type="MyObjectBuilder_CubeBlock">
              <SubtypeName>LargeBlockArmorCorner</SubtypeName>
              <Min x="1" y="0" z="1" />
            </MyObjectBuilder_CubeBlock>
            <MyObjectBuilder_CubeBlock xsi:type="MyObjectBuilder_CubeBlock">
              <SubtypeName>LargeBlockArmorCornerInv</SubtypeName>
              <Min x="-1" y="0" z="1" />
            </MyObjectBuilder_CubeBlock>

            <!-- Propulsion & Power -->
            <MyObjectBuilder_CubeBlock xsi:type="MyObjectBuilder_Thrust">
              <SubtypeName>LargeBlockLargeThrust</SubtypeName>
              <Min x="0" y="0" z="-4" />
            </MyObjectBuilder_CubeBlock>
            <MyObjectBuilder_CubeBlock xsi:type="MyObjectBuilder_Thrust">
              <SubtypeName>LargeBlockSmallThrust</SubtypeName>
              <Min x="1" y="0" z="-4" />
            </MyObjectBuilder_CubeBlock>
            <MyObjectBuilder_CubeBlock xsi:type="MyObjectBuilder_Thrust">
              <SubtypeName>LargeBlockLargeHydrogenThrust</SubtypeName>
              <Min x="-1" y="0" z="-4" />
            </MyObjectBuilder_CubeBlock>
            <MyObjectBuilder_CubeBlock xsi:type="MyObjectBuilder_BatteryBlock">
              <SubtypeName>LargeBlockBatteryBlock</SubtypeName>
              <Min x="0" y="-1" z="0" />
            </MyObjectBuilder_CubeBlock>
            <MyObjectBuilder_CubeBlock xsi:type="MyObjectBuilder_Reactor">
              <SubtypeName>LargeBlockLargeGenerator</SubtypeName>
              <Min x="0" y="-1" z="-2" />
            </MyObjectBuilder_CubeBlock>

            <!-- Command & Weapons -->
            <MyObjectBuilder_CubeBlock xsi:type="MyObjectBuilder_Cockpit">
              <SubtypeName>LargeBlockCockpit</SubtypeName>
              <EntityId>10001005</EntityId>
              <Min x="0" y="2" z="2" />
            </MyObjectBuilder_CubeBlock>
            <MyObjectBuilder_CubeBlock xsi:type="MyObjectBuilder_LargeMissileTurret">
              <SubtypeName>LargeMissileTurret</SubtypeName>
              <Min x="0" y="3" z="0" />
            </MyObjectBuilder_CubeBlock>
          </CubeBlocks>
          <DisplayName>{name} Main Grid</DisplayName>
        </CubeGrid>
      </CubeGrids>
    </ShipBlueprint>
  </ShipBlueprints>
</Definitions>"""


def generate_dlc_excavator_xml(name: str = "Industrial_Excavator") -> str:
    return f"""<?xml version="1.0" encoding="utf-8"?>
<Definitions xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <ShipBlueprints>
    <ShipBlueprint xsi:type="MyObjectBuilder_ShipBlueprintDefinition">
      <Id Type="MyObjectBuilder_ShipBlueprintDefinition" Subtype="{name}" />
      <DisplayName>{name}</DisplayName>
      <CubeGrids>
        <CubeGrid>
          <EntityId>20002001</EntityId>
          <GridSizeEnum>Large</GridSizeEnum>
          <CubeBlocks>
            <!-- Heavy Armor & Industrial DLCs -->
            <MyObjectBuilder_CubeBlock xsi:type="MyObjectBuilder_CubeBlock">
              <SubtypeName>LargeHeavyBlockArmorBlock</SubtypeName>
              <Min x="0" y="0" z="0" />
            </MyObjectBuilder_CubeBlock>
            
            <!-- Heavy Industry DLC -->
            <MyObjectBuilder_CubeBlock xsi:type="MyObjectBuilder_Refinery">
              <SubtypeName>LargeRefineryIndustrial</SubtypeName>
              <Min x="0" y="1" z="0" />
            </MyObjectBuilder_CubeBlock>
            <MyObjectBuilder_CubeBlock xsi:type="MyObjectBuilder_Assembler">
              <SubtypeName>LargeAssemblerIndustrial</SubtypeName>
              <Min x="0" y="3" z="0" />
            </MyObjectBuilder_CubeBlock>
            <MyObjectBuilder_CubeBlock xsi:type="MyObjectBuilder_CargoContainer">
              <SubtypeName>LargeBlockLargeIndustrialCargo</SubtypeName>
              <Min x="0" y="5" z="0" />
            </MyObjectBuilder_CubeBlock>

            <!-- Contact & Signal DLC (2024-2026) -->
            <MyObjectBuilder_CubeBlock xsi:type="MyObjectBuilder_Beacon">
              <SubtypeName>LargeSignalBeacon</SubtypeName>
              <Min x="0" y="7" z="0" />
            </MyObjectBuilder_CubeBlock>
            <MyObjectBuilder_CubeBlock xsi:type="MyObjectBuilder_Cockpit">
              <SubtypeName>LargeBlockCockpitIndustrial</SubtypeName>
              <Min x="0" y="2" z="2" />
            </MyObjectBuilder_CubeBlock>

            <!-- Base Game Drills -->
            <MyObjectBuilder_CubeBlock xsi:type="MyObjectBuilder_Drill">
              <SubtypeName>LargeBlockDrill</SubtypeName>
              <Min x="0" y="0" z="5" />
            </MyObjectBuilder_CubeBlock>
          </CubeBlocks>
          <DisplayName>{name} Refinery Rig</DisplayName>
        </CubeGrid>
      </CubeGrids>
    </ShipBlueprint>
  </ShipBlueprints>
</Definitions>"""


def generate_pb_drone_xml(name: str = "Recon_Scout_Drone") -> str:
    script_code = """
public Program() {
    Runtime.UpdateFrequency = UpdateFrequency.Update10;
}

public void Main(string argument, UpdateType updateSource) {
    var antenna = GridTerminalSystem.GetBlockWithName("Antenna") as IMyRadioAntenna;
    if (antenna != null) {
        antenna.CustomName = "Scout Active";
    }
}
"""
    import html
    escaped_script = html.escape(script_code)

    return f"""<?xml version="1.0" encoding="utf-8"?>
<Definitions xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <ShipBlueprints>
    <ShipBlueprint xsi:type="MyObjectBuilder_ShipBlueprintDefinition">
      <Id Type="MyObjectBuilder_ShipBlueprintDefinition" Subtype="{name}" />
      <DisplayName>{name}</DisplayName>
      <CubeGrids>
        <CubeGrid>
          <EntityId>30003001</EntityId>
          <GridSizeEnum>Small</GridSizeEnum>
          <CubeBlocks>
            <MyObjectBuilder_CubeBlock xsi:type="MyObjectBuilder_CubeBlock">
              <SubtypeName>SmallBlockArmorBlock</SubtypeName>
              <Min x="0" y="0" z="0" />
            </MyObjectBuilder_CubeBlock>
            <MyObjectBuilder_CubeBlock xsi:type="MyObjectBuilder_CubeBlock">
              <SubtypeName>SmallBlockArmorSlope</SubtypeName>
              <Min x="0" y="1" z="0" />
            </MyObjectBuilder_CubeBlock>
            <MyObjectBuilder_CubeBlock xsi:type="MyObjectBuilder_BatteryBlock">
              <SubtypeName>SmallBlockBatteryBlock</SubtypeName>
              <Min x="0" y="0" z="1" />
            </MyObjectBuilder_CubeBlock>
            <MyObjectBuilder_CubeBlock xsi:type="MyObjectBuilder_Gyro">
              <SubtypeName>SmallBlockGyro</SubtypeName>
              <Min x="0" y="0" z="-1" />
            </MyObjectBuilder_CubeBlock>
            <MyObjectBuilder_CubeBlock xsi:type="MyObjectBuilder_RadioAntenna">
              <SubtypeName>SmallBlockRadioAntenna</SubtypeName>
              <Min x="0" y="1" z="1" />
            </MyObjectBuilder_CubeBlock>
            
            <!-- Programmable Block with MDK C# Script -->
            <MyObjectBuilder_CubeBlock xsi:type="MyObjectBuilder_MyProgrammableBlock">
              <SubtypeName>SmallProgrammableBlock</SubtypeName>
              <EntityId>30003009</EntityId>
              <Min x="0" y="2" z="0" />
              <CustomName>Autopilot Brain</CustomName>
              <Program>{escaped_script}</Program>
            </MyObjectBuilder_CubeBlock>
          </CubeBlocks>
          <DisplayName>{name} Frame</DisplayName>
        </CubeGrid>
      </CubeGrids>
    </ShipBlueprint>
  </ShipBlueprints>
</Definitions>"""


def generate_prototech_station_xml(name: str = "Prototech_Sanctuary") -> str:
    return f"""<?xml version="1.0" encoding="utf-8"?>
<Definitions xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <ShipBlueprints>
    <ShipBlueprint xsi:type="MyObjectBuilder_ShipBlueprintDefinition">
      <Id Type="MyObjectBuilder_ShipBlueprintDefinition" Subtype="{name}" />
      <DisplayName>{name}</DisplayName>
      <CubeGrids>
        <CubeGrid>
          <EntityId>40004001</EntityId>
          <GridSizeEnum>Large</GridSizeEnum>
          <CubeBlocks>
            <!-- Heavy Armor Structure -->
            <MyObjectBuilder_CubeBlock xsi:type="MyObjectBuilder_CubeBlock">
              <SubtypeName>LargeHeavyBlockArmorBlock</SubtypeName>
              <Min x="0" y="0" z="0" />
            </MyObjectBuilder_CubeBlock>

            <!-- Factorum Prototech Blocks -->
            <MyObjectBuilder_CubeBlock xsi:type="MyObjectBuilder_Reactor">
              <SubtypeName>LargePrototechReactor</SubtypeName>
              <Min x="0" y="1" z="0" />
            </MyObjectBuilder_CubeBlock>
            <MyObjectBuilder_CubeBlock xsi:type="MyObjectBuilder_Thrust">
              <SubtypeName>LargeBlockLargePrototechThrust</SubtypeName>
              <Min x="0" y="-1" z="-3" />
            </MyObjectBuilder_CubeBlock>
            <MyObjectBuilder_CubeBlock xsi:type="MyObjectBuilder_JumpDrive">
              <SubtypeName>LargePrototechJumpDrive</SubtypeName>
              <Min x="0" y="2" z="0" />
            </MyObjectBuilder_CubeBlock>
            <MyObjectBuilder_CubeBlock xsi:type="MyObjectBuilder_Gyro">
              <SubtypeName>LargePrototechGyro</SubtypeName>
              <Min x="0" y="0" z="2" />
            </MyObjectBuilder_CubeBlock>
          </CubeBlocks>
          <DisplayName>{name} Citadel</DisplayName>
        </CubeGrid>
      </CubeGrids>
    </ShipBlueprint>
  </ShipBlueprints>
</Definitions>"""


def generate_multigrid_walker_xml(name: str = "MultiGrid_Walker") -> str:
    return f"""<?xml version="1.0" encoding="utf-8"?>
<Definitions xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <ShipBlueprints>
    <ShipBlueprint xsi:type="MyObjectBuilder_ShipBlueprintDefinition">
      <Id Type="MyObjectBuilder_ShipBlueprintDefinition" Subtype="{name}" />
      <DisplayName>{name}</DisplayName>
      <CubeGrids>
        <!-- Main Torso Grid -->
        <CubeGrid>
          <EntityId>50005001</EntityId>
          <GridSizeEnum>Large</GridSizeEnum>
          <CubeBlocks>
            <MyObjectBuilder_CubeBlock xsi:type="MyObjectBuilder_CubeBlock">
              <SubtypeName>LargeBlockArmorBlock</SubtypeName>
              <Min x="0" y="0" z="0" />
            </MyObjectBuilder_CubeBlock>
            <MyObjectBuilder_CubeBlock xsi:type="MyObjectBuilder_MotorAdvancedStator">
              <SubtypeName>LargeAdvancedStator</SubtypeName>
              <EntityId>50005002</EntityId>
              <Min x="1" y="0" z="0" />
              <TopPartEntityId>50005003</TopPartEntityId>
            </MyObjectBuilder_CubeBlock>
            <MyObjectBuilder_CubeBlock xsi:type="MyObjectBuilder_ExtendedPistonBase">
              <SubtypeName>LargePistonBase</SubtypeName>
              <EntityId>50005004</EntityId>
              <Min x="-1" y="0" z="0" />
              <TopBlockId>50005005</TopBlockId>
            </MyObjectBuilder_CubeBlock>
          </CubeBlocks>
          <DisplayName>{name} Torso</DisplayName>
        </CubeGrid>

        <!-- Right Arm Subgrid -->
        <CubeGrid>
          <EntityId>50005010</EntityId>
          <GridSizeEnum>Large</GridSizeEnum>
          <CubeBlocks>
            <MyObjectBuilder_CubeBlock xsi:type="MyObjectBuilder_MotorAdvancedRotor">
              <SubtypeName>LargeAdvancedRotor</SubtypeName>
              <EntityId>50005003</EntityId>
              <Min x="0" y="0" z="0" />
            </MyObjectBuilder_CubeBlock>
            <MyObjectBuilder_CubeBlock xsi:type="MyObjectBuilder_CubeBlock">
              <SubtypeName>LargeBlockArmorBlock</SubtypeName>
              <Min x="1" y="0" z="0" />
            </MyObjectBuilder_CubeBlock>
          </CubeBlocks>
          <DisplayName>{name} Right Arm</DisplayName>
        </CubeGrid>

        <!-- Left Leg Subgrid -->
        <CubeGrid>
          <EntityId>50005020</EntityId>
          <GridSizeEnum>Large</GridSizeEnum>
          <CubeBlocks>
            <MyObjectBuilder_CubeBlock xsi:type="MyObjectBuilder_PistonTop">
              <SubtypeName>PistonSubpart</SubtypeName>
              <EntityId>50005005</EntityId>
              <Min x="0" y="0" z="0" />
            </MyObjectBuilder_CubeBlock>
            <MyObjectBuilder_CubeBlock xsi:type="MyObjectBuilder_CubeBlock">
              <SubtypeName>LargeBlockArmorBlock</SubtypeName>
              <Min x="0" y="-1" z="0" />
            </MyObjectBuilder_CubeBlock>
          </CubeBlocks>
          <DisplayName>{name} Left Leg</DisplayName>
        </CubeGrid>
      </CubeGrids>
    </ShipBlueprint>
  </ShipBlueprints>
</Definitions>"""


def generate_all_test_grids(target_dir: Path) -> Dict[str, Path]:
    target_dir = Path(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    generators = {
        "Battleship_Vindicator": generate_battleship_xml,
        "Industrial_Excavator": generate_dlc_excavator_xml,
        "Recon_Scout_Drone": generate_pb_drone_xml,
        "Prototech_Sanctuary": generate_prototech_station_xml,
        "MultiGrid_Walker": generate_multigrid_walker_xml,
    }

    created_paths = {}
    for name, gen_func in generators.items():
        bp_folder = target_dir / name
        bp_folder.mkdir(parents=True, exist_ok=True)
        sbc_file = bp_folder / "bp.sbc"
        sbc_file.write_text(gen_func(name), encoding="utf-8")
        created_paths[name] = bp_folder

    return created_paths


if __name__ == "__main__":
    out = Path("test_fixtures_grids")
    res = generate_all_test_grids(out)
    print(f"Generated {len(res)} test grids in {out}")

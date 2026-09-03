import unittest
import xml.etree.ElementTree as ET

from se_render.orientation import transform_point
from se_render.scene_graph import extract_scene_from_root


ROTOR_BLUEPRINT = """<?xml version="1.0"?>
<Definitions xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <ShipBlueprints>
    <ShipBlueprint>
      <CubeGrids>
        <CubeGrid>
          <EntityId>100</EntityId>
          <DisplayName>Hull</DisplayName>
          <GridSizeEnum>Large</GridSizeEnum>
          <CubeBlocks>
            <MyObjectBuilder_CubeBlock xsi:type="MyObjectBuilder_MotorStator">
              <SubtypeName>LargeStator</SubtypeName>
              <EntityId>10</EntityId>
              <Min x="0" y="0" z="0" />
              <BlockOrientation Forward="Forward" Up="Up" />
              <ColorMaskHSV x="0" y="0" z="0" />
              <TopBlockId>20</TopBlockId>
              <CurrentPosition>0</CurrentPosition>
            </MyObjectBuilder_CubeBlock>
            <MyObjectBuilder_CubeBlock>
              <SubtypeName>LargeBlockArmorBlock</SubtypeName>
              <Min x="2" y="0" z="0" />
              <BlockOrientation Forward="Forward" Up="Up" />
              <ColorMaskHSV x="0.25" y="0.1" z="0.2" />
            </MyObjectBuilder_CubeBlock>
          </CubeBlocks>
        </CubeGrid>
        <CubeGrid>
          <EntityId>200</EntityId>
          <DisplayName>RotorHead</DisplayName>
          <GridSizeEnum>Large</GridSizeEnum>
          <CubeBlocks>
            <MyObjectBuilder_CubeBlock>
              <SubtypeName>LargeBlockArmorBlock</SubtypeName>
              <EntityId>20</EntityId>
              <Min x="0" y="0" z="0" />
              <ColorMaskHSV x="0.8" y="-0.2" z="0.1" />
            </MyObjectBuilder_CubeBlock>
          </CubeBlocks>
        </CubeGrid>
      </CubeGrids>
    </ShipBlueprint>
  </ShipBlueprints>
</Definitions>
"""


class SceneGraphTests(unittest.TestCase):
    def test_extracts_orientation_hsv_and_assembles_rotor(self):
        root = ET.fromstring(ROTOR_BLUEPRINT)
        scene = extract_scene_from_root(root)
        self.assertEqual(scene.total_blocks, 3)
        self.assertEqual(scene.main_grid_name, "Hull")
        hull = [b for b in scene.blocks if b.grid_name == "Hull"]
        head = [b for b in scene.blocks if b.grid_name == "RotorHead"]
        self.assertEqual(len(hull), 2)
        self.assertEqual(len(head), 1)
        armor = next(b for b in hull if b.subtype == "LargeBlockArmorBlock")
        self.assertEqual(armor.forward, "Forward")
        self.assertAlmostEqual(armor.hsv[0], 0.25)
        self.assertTrue(all(0.0 <= c <= 1.0 for c in armor.color_rgb))
        self.assertTrue(head[0].is_subgrid)

        hull_origin = transform_point(next(b for b in hull if b.subtype == "LargeStator").world_matrix, (0, 0, 0))
        head_origin = transform_point(head[0].world_matrix, (0, 0, 0))
        # Child is attached above the stator, not stacked at the same origin.
        self.assertGreater(abs(head_origin[1] - hull_origin[1]), 0.4)

    def test_uses_stored_grid_poses_when_present(self):
        xml = """<?xml version="1.0"?>
        <Definitions>
          <CubeGrid>
            <EntityId>1</EntityId>
            <DisplayName>A</DisplayName>
            <GridSizeEnum>Small</GridSizeEnum>
            <PositionAndOrientation>
              <Position x="100" y="0" z="0" />
              <Forward x="0" y="0" z="-1" />
              <Up x="0" y="1" z="0" />
            </PositionAndOrientation>
            <CubeBlocks>
              <MyObjectBuilder_CubeBlock>
                <SubtypeName>SmallBlockArmorBlock</SubtypeName>
                <Min x="0" y="0" z="0" />
              </MyObjectBuilder_CubeBlock>
            </CubeBlocks>
          </CubeGrid>
        </Definitions>
        """
        scene = extract_scene_from_root(ET.fromstring(xml))
        self.assertEqual(len(scene.blocks), 1)
        pos = transform_point(scene.blocks[0].world_matrix, (0, 0, 0))
        self.assertAlmostEqual(pos[0], 100.25, places=5)

    def test_sibling_grids_all_appear_in_scene(self):
        xml = """<?xml version="1.0"?>
        <Definitions xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
          <CubeGrid>
            <EntityId>1</EntityId>
            <DisplayName>Hull</DisplayName>
            <GridSizeEnum>Large</GridSizeEnum>
            <CubeBlocks>
              <MyObjectBuilder_CubeBlock><SubtypeName>LargeBlockArmorBlock</SubtypeName><Min x="0" y="0" z="0" /></MyObjectBuilder_CubeBlock>
              <MyObjectBuilder_CubeBlock><SubtypeName>LargeBlockArmorBlock</SubtypeName><Min x="1" y="0" z="0" /></MyObjectBuilder_CubeBlock>
            </CubeBlocks>
          </CubeGrid>
          <CubeGrid>
            <EntityId>2</EntityId>
            <DisplayName>Turret</DisplayName>
            <GridSizeEnum>Large</GridSizeEnum>
            <CubeBlocks>
              <MyObjectBuilder_CubeBlock><SubtypeName>LargeBlockArmorBlock</SubtypeName><Min x="0" y="0" z="0" /></MyObjectBuilder_CubeBlock>
            </CubeBlocks>
          </CubeGrid>
        </Definitions>
        """
        scene = extract_scene_from_root(ET.fromstring(xml))
        self.assertEqual(scene.total_blocks, 3)
        self.assertEqual(len([b for b in scene.blocks if b.grid_name == "Turret"]), 1)


if __name__ == "__main__":
    unittest.main()

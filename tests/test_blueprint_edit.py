import tempfile
import unittest
from pathlib import Path

import safe_xml
from blueprint_edit import (
    apply_edits_to_tree,
    save_blueprint_as,
    unique_edited_dir,
)
from se_render.scene_graph import extract_scene_from_root


TWO_BLOCK = """<?xml version="1.0"?>
<Definitions xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <ShipBlueprints>
    <ShipBlueprint>
      <Id>
        <TypeId>MyObjectBuilder_ShipBlueprintDefinition</TypeId>
        <SubtypeId>FixtureShip</SubtypeId>
      </Id>
      <DisplayName>FixtureShip</DisplayName>
      <CubeGrids>
        <CubeGrid>
          <EntityId>100</EntityId>
          <DisplayName>Hull</DisplayName>
          <GridSizeEnum>Large</GridSizeEnum>
          <CubeBlocks>
            <MyObjectBuilder_CubeBlock>
              <SubtypeName>LargeBlockArmorBlock</SubtypeName>
              <EntityId>10</EntityId>
              <Min x="0" y="0" z="0" />
              <BlockOrientation Forward="Forward" Up="Up" />
              <ColorMaskHSV x="0" y="0" z="0" />
            </MyObjectBuilder_CubeBlock>
            <MyObjectBuilder_CubeBlock>
              <SubtypeName>LargeBlockArmorBlock</SubtypeName>
              <EntityId>11</EntityId>
              <Min x="1" y="0" z="0" />
              <BlockOrientation Forward="Forward" Up="Up" />
              <ColorMaskHSV x="0" y="0" z="0" />
            </MyObjectBuilder_CubeBlock>
          </CubeBlocks>
        </CubeGrid>
      </CubeGrids>
    </ShipBlueprint>
  </ShipBlueprints>
</Definitions>
"""


class BlueprintSaveAsTests(unittest.TestCase):
    def test_save_as_deletes_one_block_and_leaves_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "FixtureShip"
            source.mkdir()
            (source / "bp.sbc").write_text(TWO_BLOCK, encoding="utf-8")
            original = (source / "bp.sbc").read_text(encoding="utf-8")
            dest = unique_edited_dir(source)
            ident = ("100", (1, 0, 0), "11")
            written = save_blueprint_as(source, [ident], {}, dest_dir=dest)
            self.assertEqual(written, dest)
            self.assertTrue((dest / "bp.sbc").exists())
            self.assertEqual((source / "bp.sbc").read_text(encoding="utf-8"), original)
            tree = safe_xml.parse(dest / "bp.sbc")
            scene = extract_scene_from_root(tree.getroot())
            self.assertEqual(scene.total_blocks, 1)
            self.assertEqual(scene.blocks[0].entity_id, "10")
            self.assertEqual(scene.blocks[0].local_min, (0, 0, 0))

    def test_apply_move_rewrites_min(self):
        import xml.etree.ElementTree as ET

        tree = ET.ElementTree(ET.fromstring(TWO_BLOCK))
        removed, count = apply_edits_to_tree(
            tree,
            deleted=[],
            moves={("100", (0, 0, 0), "10"): (3, 1, 0)},
        )
        self.assertEqual(removed, 0)
        self.assertEqual(count, 1)
        scene = extract_scene_from_root(tree.getroot())
        first = next(b for b in scene.blocks if b.entity_id == "10")
        self.assertEqual(first.local_min, (3, 1, 0))

    def test_refuses_overwrite_without_flag(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "Ship"
            source.mkdir()
            (source / "bp.sbc").write_text(TWO_BLOCK, encoding="utf-8")
            with self.assertRaises((FileExistsError, ValueError)):
                save_blueprint_as(source, [], {}, dest_dir=source, overwrite_original=False)


if __name__ == "__main__":
    unittest.main()

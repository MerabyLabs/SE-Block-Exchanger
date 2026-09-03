import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from blueprint_analytics import BlueprintAnalyticsEngine
from blueprint_document import (
    BlueprintDocument,
    BlueprintDocumentCache,
    JobToken,
    inspect_result_applies,
)
from blueprint_scanner import BlueprintScanner
from mappings import build_registry
from se_render.hsv import hsv_offset_to_rgb, hsv_offset_to_standard
from se_render.orientation import identity_mat4
from se_render.scene_graph import (
    GridPose,
    PreviewScene,
    _HSV_RGB_CACHE,
    _color_rgb,
    extract_scene_from_root,
)
from subgrid_engine.hierarchy_parser import SubgridHierarchyParser
from tests.test_blueprint_document import _write_ship
from tests.test_scene_graph import ROTOR_BLUEPRINT
from ui.blueprint_panel import highlight_cards_by_visible_index
from ui.preview_panel import xml_reload_required


CHILD_LARGER_THAN_PARENT = """<?xml version="1.0"?>
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
              <TopBlockId>20</TopBlockId>
            </MyObjectBuilder_CubeBlock>
          </CubeBlocks>
        </CubeGrid>
        <CubeGrid>
          <EntityId>200</EntityId>
          <DisplayName>RotorHead</DisplayName>
          <GridSizeEnum>Small</GridSizeEnum>
          <CubeBlocks>
            <MyObjectBuilder_CubeBlock>
              <SubtypeName>SmallBlockArmorBlock</SubtypeName>
              <EntityId>20</EntityId>
              <Min x="0" y="0" z="0" />
            </MyObjectBuilder_CubeBlock>
            <MyObjectBuilder_CubeBlock>
              <SubtypeName>SmallBlockArmorBlock</SubtypeName>
              <Min x="1" y="0" z="0" />
            </MyObjectBuilder_CubeBlock>
            <MyObjectBuilder_CubeBlock>
              <SubtypeName>SmallBlockArmorBlock</SubtypeName>
              <Min x="2" y="0" z="0" />
            </MyObjectBuilder_CubeBlock>
            <MyObjectBuilder_CubeBlock>
              <SubtypeName>SmallBlockArmorBlock</SubtypeName>
              <Min x="3" y="0" z="0" />
            </MyObjectBuilder_CubeBlock>
            <MyObjectBuilder_CubeBlock>
              <SubtypeName>SmallBlockArmorBlock</SubtypeName>
              <Min x="4" y="0" z="0" />
            </MyObjectBuilder_CubeBlock>
          </CubeBlocks>
        </CubeGrid>
      </CubeGrids>
    </ShipBlueprint>
  </ShipBlueprints>
</Definitions>
"""

DUPLICATE_HULL_NAMES = """<?xml version="1.0"?>
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
              <TopBlockId>20</TopBlockId>
            </MyObjectBuilder_CubeBlock>
            <MyObjectBuilder_CubeBlock>
              <SubtypeName>LargeBlockArmorBlock</SubtypeName>
              <Min x="1" y="0" z="0" />
            </MyObjectBuilder_CubeBlock>
          </CubeBlocks>
        </CubeGrid>
        <CubeGrid>
          <EntityId>200</EntityId>
          <DisplayName>Hull</DisplayName>
          <GridSizeEnum>Large</GridSizeEnum>
          <CubeBlocks>
            <MyObjectBuilder_CubeBlock>
              <SubtypeName>LargeBlockArmorBlock</SubtypeName>
              <EntityId>20</EntityId>
              <Min x="0" y="0" z="0" />
            </MyObjectBuilder_CubeBlock>
          </CubeBlocks>
        </CubeGrid>
      </CubeGrids>
    </ShipBlueprint>
  </ShipBlueprints>
</Definitions>
"""

SMALL_THEN_LARGE = """<?xml version="1.0"?>
<Definitions>
  <CubeGrid>
    <EntityId>1</EntityId>
    <DisplayName>Nose</DisplayName>
    <GridSizeEnum>Small</GridSizeEnum>
    <CubeBlocks>
      <MyObjectBuilder_CubeBlock>
        <SubtypeName>SmallBlockArmorBlock</SubtypeName>
        <Min x="0" y="0" z="0" />
      </MyObjectBuilder_CubeBlock>
    </CubeBlocks>
  </CubeGrid>
  <CubeGrid>
    <EntityId>2</EntityId>
    <DisplayName>Hull</DisplayName>
    <GridSizeEnum>Large</GridSizeEnum>
    <CubeBlocks>
      <MyObjectBuilder_CubeBlock>
        <SubtypeName>LargeBlockArmorBlock</SubtypeName>
        <Min x="0" y="0" z="0" />
      </MyObjectBuilder_CubeBlock>
      <MyObjectBuilder_CubeBlock>
        <SubtypeName>LargeBlockArmorBlock</SubtypeName>
        <Min x="1" y="0" z="0" />
      </MyObjectBuilder_CubeBlock>
      <MyObjectBuilder_CubeBlock>
        <SubtypeName>LargeBlockArmorBlock</SubtypeName>
        <Min x="2" y="0" z="0" />
      </MyObjectBuilder_CubeBlock>
    </CubeBlocks>
  </CubeGrid>
</Definitions>
"""


def _scanner() -> BlueprintScanner:
    return BlueprintScanner(
        registry=build_registry(include_builtin=True),
        enabled_categories=["armor"],
        persist_cache=False,
    )


def _write_xml(folder: Path, xml: str) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "bp.sbc"
    path.write_text(xml, encoding="utf-8")
    return path


class InPlaceEditRefreshTests(unittest.TestCase):
    def test_refresh_path_and_document_cache_after_health_fix(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / "Ship"
            _write_ship(folder, 4, "Ship")
            scanner = _scanner()
            infos = scanner.scan_blueprints(root)
            self.assertEqual(len(infos), 1)
            self.assertNotIn("LargeBlockCockpit", infos[0].subtype_counts)
            cache = BlueprintDocumentCache()
            first = cache.get_or_load(folder)
            engine = BlueprintAnalyticsEngine()
            self.assertTrue(engine.apply_fix(folder / "bp.sbc", "add_control_block"))
            stale = scanner.blueprints_cache[0]
            self.assertNotIn("LargeBlockCockpit", stale.subtype_counts)
            cache.invalidate(folder)
            refreshed = scanner.refresh_path(folder)
            self.assertIsNotNone(refreshed)
            self.assertIn("LargeBlockCockpit", refreshed.subtype_counts)
            self.assertGreater(refreshed.block_count, stale.block_count)
            remapped = scanner.remap_cached()
            self.assertIn("LargeBlockCockpit", remapped[0].subtype_counts)
            second = cache.get_or_load(folder)
            self.assertIsNot(first, second)
            self.assertGreater(second.block_count, first.block_count)

    def test_xml_reload_required_after_invalidate(self):
        path = "/tmp/ship/bp.sbc"
        self.assertFalse(xml_reload_required(path, path))
        self.assertTrue(xml_reload_required(None, path))
        self.assertTrue(xml_reload_required("/other", path))


class CancelledScanCommitTests(unittest.TestCase):
    def test_cancelled_scan_does_not_replace_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            root_a = Path(tmp) / "folder_a"
            root_b = Path(tmp) / "folder_b"
            _write_ship(root_a / "ShipA", 3, "ShipA")
            _write_ship(root_b / "ShipB", 5, "ShipB")
            scanner = _scanner()
            first = scanner.scan_blueprints(root_a)
            self.assertEqual([bp.name for bp in first], ["ShipA"])

            calls = {"n": 0}

            def cancel() -> bool:
                calls["n"] += 1
                return calls["n"] > 1

            second = scanner.scan_blueprints(root_b, cancel=cancel)
            self.assertEqual([bp.name for bp in second], ["ShipA"])
            self.assertEqual(
                [Path(record.stamp.path).parent.name for record in scanner._records],
                ["ShipA"],
            )
            remapped = scanner.remap_cached()
            self.assertEqual([bp.name for bp in remapped], ["ShipA"])


class InspectStaleCallbackTests(unittest.TestCase):
    def test_inspect_result_requires_current_generation_and_path(self):
        token = JobToken()
        generation = token.begin()
        self.assertTrue(inspect_result_applies(token, generation, Path("/a"), Path("/a")))
        token.cancel()
        self.assertFalse(inspect_result_applies(token, generation, Path("/a"), Path("/a")))
        again = token.begin()
        self.assertFalse(inspect_result_applies(token, again, Path("/b"), Path("/a")))
        self.assertFalse(inspect_result_applies(token, again, None, Path("/b")))


class HierarchyFromSceneTests(unittest.TestCase):
    def test_rotor_from_scene_keeps_mechanical_links(self):
        scene = extract_scene_from_root(ET.fromstring(ROTOR_BLUEPRINT))
        structure = SubgridHierarchyParser.from_scene(scene)
        from_xml = SubgridHierarchyParser.parse_element(ET.fromstring(ROTOR_BLUEPRINT))
        self.assertEqual(structure.root_node.grid_name, from_xml.root_node.grid_name)
        self.assertTrue(structure.root_node.is_main_grid)
        self.assertFalse(structure.root_node.children[0].is_main_grid)
        self.assertGreaterEqual(len(structure.mechanical_links), 1)
        self.assertEqual(structure.mechanical_links[0].base_entity_id, "100")
        self.assertEqual(structure.mechanical_links[0].top_entity_id, "200")

    def test_child_larger_than_parent_does_not_duplicate_main(self):
        root = ET.fromstring(CHILD_LARGER_THAN_PARENT)
        scene = extract_scene_from_root(root)
        self.assertEqual(scene.main_grid_name, "Hull")
        self.assertEqual(scene.main_grid_entity_id, "100")
        from_scene = SubgridHierarchyParser.from_scene(scene)
        from_xml = SubgridHierarchyParser.parse_element(root)
        self.assertEqual(from_scene.root_node.entity_id, from_xml.root_node.entity_id)
        self.assertEqual(from_scene.root_node.entity_id, "100")
        mains = [from_scene.root_node] + from_scene.root_node.children + from_scene.orphaned_grids
        self.assertEqual(sum(1 for node in mains if node.is_main_grid), 1)
        self.assertEqual(len(from_scene.root_node.children), 1)
        self.assertEqual(from_scene.root_node.children[0].entity_id, "200")
        self.assertFalse(from_scene.root_node.children[0].is_main_grid)

    def test_from_scene_ignores_wrong_main_name_when_child_is_larger(self):
        hull = GridPose("100", "Hull", "Large", identity_mat4(), True)
        head = GridPose("200", "RotorHead", "Small", identity_mat4(), True, "Rotor (LargeStator)")
        scene = PreviewScene(
            grids=[hull, head],
            main_grid_name="RotorHead",
            main_grid_entity_id="",
            parent_of={"200": "100"},
            blocks=[],
            total_blocks=6,
        )
        # Block counts come from scene.blocks; seed via dummy instances on each grid.
        from se_render.scene_graph import BlockInstance

        def _block(gid: str, name: str, n: int) -> list:
            return [
                BlockInstance(
                    grid_name=name,
                    grid_entity_id=gid,
                    grid_size="Large",
                    is_subgrid=gid != "100",
                    subtype="Armor",
                    type_id="CubeBlock",
                    entity_id=f"{gid}-{i}",
                    min_x=i,
                    min_y=0,
                    min_z=0,
                    forward="Forward",
                    up="Up",
                    hsv=(0.0, 0.0, 0.0),
                    color_rgb=(1.0, 1.0, 1.0),
                    skin="None",
                    world_matrix=identity_mat4(),
                    local_min=(i, 0, 0),
                )
                for i in range(n)
            ]

        scene.blocks = _block("100", "Hull", 1) + _block("200", "RotorHead", 5)
        structure = SubgridHierarchyParser.from_scene(scene)
        self.assertEqual(structure.root_node.entity_id, "100")
        self.assertTrue(structure.root_node.is_main_grid)
        self.assertEqual(len(structure.root_node.children), 1)
        self.assertFalse(structure.root_node.children[0].is_main_grid)
        self.assertEqual(len(structure.mechanical_links), 1)

    def test_duplicate_display_names_mark_one_main(self):
        root = ET.fromstring(DUPLICATE_HULL_NAMES)
        from_scene = SubgridHierarchyParser.from_scene(extract_scene_from_root(root))
        from_xml = SubgridHierarchyParser.parse_element(root)
        self.assertEqual(from_scene.root_node.entity_id, from_xml.root_node.entity_id)
        self.assertTrue(from_scene.root_node.is_main_grid)
        self.assertEqual(sum(1 for _depth, node in from_scene.iter_nodes() if node.is_main_grid), 1)
        self.assertEqual(from_scene.root_node.children[0].grid_name, "Hull")
        self.assertFalse(from_scene.root_node.children[0].is_main_grid)


class CardHighlightTests(unittest.TestCase):
    def test_filtered_visible_index_highlights_matching_card(self):
        class FakeCard:
            def __init__(self, index: int) -> None:
                self.index = index
                self.selected = False

            def set_selected(self, value: bool) -> None:
                self.selected = value

        cards = [FakeCard(0), FakeCard(-1), FakeCard(1)]
        highlight_cards_by_visible_index(cards, {1})
        self.assertFalse(cards[0].selected)
        self.assertFalse(cards[1].selected)
        self.assertTrue(cards[2].selected)


class CanonicalMainGridSizeTests(unittest.TestCase):
    def test_reordered_small_then_large_uses_largest_non_child(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "Mixed"
            _write_xml(folder, SMALL_THEN_LARGE)
            info = _scanner().parse_folder(folder)
            self.assertEqual(info.grid_size, "Large")
            doc = BlueprintDocument.load(folder)
            self.assertEqual(doc.grid_size, "Large")

    def test_larger_child_does_not_steal_main_grid_size(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "Rotor"
            _write_xml(folder, CHILD_LARGER_THAN_PARENT)
            info = _scanner().parse_folder(folder)
            self.assertEqual(info.grid_size, "Large")


class ThrusterAuditTests(unittest.TestCase):
    def test_empty_direction_counts_still_warn_when_six_thrusters(self):
        engine = BlueprintAnalyticsEngine()
        counts = {f"FakeThrust{i}": 1 for i in range(6)}
        result = engine.analyze_counts(
            counts,
            blueprint_name="X",
            thruster_forwards={},
            thruster_count=6,
        )
        codes = [issue.code for issue in result.health_issues]
        self.assertIn("thruster_imbalance", codes)

    def test_unread_orientation_inferred_from_subtype_counts(self):
        engine = BlueprintAnalyticsEngine()
        counts = {f"FakeThrust{i}": 1 for i in range(6)}
        result = engine.analyze_counts(counts, blueprint_name="X", thruster_forwards={})
        self.assertTrue(any(issue.code == "thruster_imbalance" for issue in result.health_issues))

    def test_scan_records_thruster_count_without_orientation(self):
        xml = """<?xml version="1.0"?>
        <Definitions>
          <CubeGrid>
            <GridSizeEnum>Large</GridSizeEnum>
            <CubeBlocks>
              %s
            </CubeBlocks>
          </CubeGrid>
        </Definitions>
        """ % "".join(
            f'<MyObjectBuilder_CubeBlock><SubtypeName>LargeBlockSmallThrust</SubtypeName>'
            f'<Min x="{i}" y="0" z="0" /></MyObjectBuilder_CubeBlock>'
            for i in range(6)
        )
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "Thrust"
            _write_xml(folder, xml)
            info = _scanner().parse_folder(folder)
            self.assertEqual(info.thruster_count, 6)
            self.assertEqual(info.thruster_forwards, {})


class ColorCacheExactKeyTests(unittest.TestCase):
    def test_nearby_hsv_offsets_do_not_share_a_rounded_key(self):
        _HSV_RGB_CACHE.clear()
        first = (0.0, 0.123456, 0.0)
        second = (0.0, 0.123461, 0.0)
        self.assertEqual(round(first[1], 5), round(second[1], 5))
        rgb_a = _color_rgb(first)
        rgb_b = _color_rgb(second)
        self.assertEqual(rgb_a, hsv_offset_to_rgb(*first))
        self.assertEqual(rgb_b, hsv_offset_to_rgb(*second))
        self.assertIn(first, _HSV_RGB_CACHE)
        self.assertIn(second, _HSV_RGB_CACHE)
        hue, sat, val = hsv_offset_to_standard(0.2, 0.1, 0.05)
        self.assertAlmostEqual(sat, 0.9)
        self.assertAlmostEqual(val, 0.50)


if __name__ == "__main__":
    unittest.main()

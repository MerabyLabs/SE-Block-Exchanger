"""Regression tests for Opus AFTER-review P0/P1 bugs still present at 13db930."""

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
import xml.etree.ElementTree as ET

from blueprint_analytics import BlueprintAnalyticsEngine
from blueprint_document import JobHub, catalog_completion_allowed
from blueprint_edit import (
    GridEditSession,
    _index_cube_blocks,
    _lookup_indexed_block,
    _rename_blueprint,
    apply_edits_to_tree,
)
from blueprint_scanner import BlueprintScanner
from mappings import build_registry
from se_render.hsv import hsv_offset_to_rgb
from se_render.scene_graph import extract_scene_from_root
from tests.test_blueprint_edit import TWO_BLOCK
from ui.blueprint_panel import (
    blueprint_for_card,
    search_pack_order,
    visible_index_for_path,
)
from ui.preview_panel import pending_catalog_for
from ui.widgets.ship_canvas import ShipCanvas


RENAME_SHIP = """<?xml version="1.0"?>
<Definitions xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <ShipBlueprints>
    <ShipBlueprint>
      <Id>
        <TypeId>MyObjectBuilder_ShipBlueprintDefinition</TypeId>
        <SubtypeId>OldShip</SubtypeId>
      </Id>
      <DisplayName>OldShip</DisplayName>
      <CubeGrids>
        <CubeGrid>
          <EntityId>100</EntityId>
          <DisplayName>HullGrid</DisplayName>
          <GridSizeEnum>Large</GridSizeEnum>
          <CubeBlocks>
            <MyObjectBuilder_CubeBlock>
              <SubtypeName>LargeBlockArmorBlock</SubtypeName>
              <EntityId>10</EntityId>
              <Min x="0" y="0" z="0" />
              <CustomName>MyArmor</CustomName>
              <Component>
                <Id>
                  <SubtypeId>SteelPlate</SubtypeId>
                </Id>
              </Component>
            </MyObjectBuilder_CubeBlock>
            <MyObjectBuilder_Cockpit>
              <SubtypeName>LargeBlockCockpit</SubtypeName>
              <EntityId>42</EntityId>
              <Min x="1" y="0" z="0" />
              <CustomName>Helm</CustomName>
            </MyObjectBuilder_Cockpit>
          </CubeBlocks>
        </CubeGrid>
      </CubeGrids>
    </ShipBlueprint>
  </ShipBlueprints>
</Definitions>
"""

UNNAMED_BLOCK = """<?xml version="1.0"?>
<Definitions>
  <CubeGrid>
    <EntityId>1</EntityId>
    <DisplayName>Bare</DisplayName>
    <GridSizeEnum>Large</GridSizeEnum>
    <CubeBlocks>
      <MyObjectBuilder_CubeBlock>
        <SubtypeName>LargeBlockArmorBlock</SubtypeName>
        <Min x="0" y="0" z="0" />
      </MyObjectBuilder_CubeBlock>
      <MyObjectBuilder_CubeBlock>
        <Min x="1" y="0" z="0" />
      </MyObjectBuilder_CubeBlock>
      <MyObjectBuilder_Cockpit>
        <SubtypeName>LargeBlockCockpit</SubtypeName>
        <Min x="2" y="0" z="0" />
      </MyObjectBuilder_Cockpit>
    </CubeBlocks>
  </CubeGrid>
</Definitions>
"""

COLLIDING_MIN = """<?xml version="1.0"?>
<Definitions>
  <ShipBlueprints>
    <ShipBlueprint>
      <CubeGrids>
        <CubeGrid>
          <EntityId>100</EntityId>
          <CubeBlocks>
            <MyObjectBuilder_CubeBlock>
              <SubtypeName>LargeBlockArmorBlock</SubtypeName>
              <Min x="0" y="0" z="0" />
            </MyObjectBuilder_CubeBlock>
            <MyObjectBuilder_CubeBlock>
              <SubtypeName>LargeBlockArmorBlock</SubtypeName>
              <Min x="0" y="0" z="0" />
            </MyObjectBuilder_CubeBlock>
            <MyObjectBuilder_CubeBlock>
              <SubtypeName>LargeBlockArmorBlock</SubtypeName>
              <Min x="1" y="0" z="0" />
              <EntityId>99</EntityId>
            </MyObjectBuilder_CubeBlock>
          </CubeBlocks>
        </CubeGrid>
      </CubeGrids>
    </ShipBlueprint>
  </ShipBlueprints>
</Definitions>
"""


class RenameBlueprintTests(unittest.TestCase):
    def test_save_as_renames_only_blueprint_id_and_display(self):
        root = ET.fromstring(RENAME_SHIP)
        _rename_blueprint(root, "EditedCopy")
        ship = root.find(".//ShipBlueprint")
        self.assertEqual(ship.find("DisplayName").text, "EditedCopy")
        self.assertEqual(ship.find("Id/SubtypeId").text, "EditedCopy")
        self.assertEqual(root.find(".//CubeGrid/DisplayName").text, "HullGrid")
        customs = [el.text for el in root.findall(".//CustomName")]
        self.assertEqual(customs, ["MyArmor", "Helm"])
        self.assertEqual(root.find(".//Component/Id/SubtypeId").text, "SteelPlate")
        self.assertEqual(root.find(".//CubeBlocks//SubtypeName").text, "LargeBlockArmorBlock")


class IndexedLookupTests(unittest.TestCase):
    def test_empty_grid_wrong_eid_does_not_match_min(self):
        root = ET.fromstring(TWO_BLOCK)
        index = _index_cube_blocks(root)
        ident = ("", (0, 0, 0), "99999")
        self.assertIsNone(_lookup_indexed_block(ident, index))
        removed, moved = apply_edits_to_tree(ET.ElementTree(root), deleted=[ident], moves={})
        self.assertEqual(removed, 0)
        self.assertEqual(moved, 0)
        self.assertEqual(len(root.findall(".//MyObjectBuilder_CubeBlock")), 2)

    def test_wrong_eid_does_not_match_cockpit_at_same_min(self):
        root = ET.fromstring(RENAME_SHIP)
        index = _index_cube_blocks(root)
        cockpit = next(
            b for b in extract_scene_from_root(root).blocks if b.subtype == "LargeBlockCockpit"
        )
        ident = ("", cockpit.local_min, "99999")
        self.assertEqual(ident[1], (1, 0, 0))
        self.assertIsNone(_lookup_indexed_block(ident, index))
        tree = ET.ElementTree(ET.fromstring(RENAME_SHIP))
        removed, _moved = apply_edits_to_tree(tree, deleted=[ident], moves={})
        self.assertEqual(removed, 0)
        scene = extract_scene_from_root(tree.getroot())
        self.assertEqual({b.subtype for b in scene.blocks}, {"LargeBlockArmorBlock", "LargeBlockCockpit"})


class EditIndexRebuildTests(unittest.TestCase):
    def test_move_after_delete_does_not_mutate_detached_node(self):
        tree = ET.ElementTree(ET.fromstring(TWO_BLOCK))
        removed, moved = apply_edits_to_tree(
            tree,
            deleted=[("100", (0, 0, 0), "10")],
            moves={("100", (0, 0, 0), ""): (9, 9, 9)},
        )
        self.assertEqual(removed, 1)
        self.assertEqual(moved, 0)
        scene = extract_scene_from_root(tree.getroot())
        self.assertEqual(scene.total_blocks, 1)
        self.assertEqual(scene.blocks[0].entity_id, "11")
        self.assertEqual(scene.blocks[0].local_min, (1, 0, 0))

    def test_min_only_delete_removes_every_match(self):
        tree = ET.ElementTree(ET.fromstring(COLLIDING_MIN))
        removed, moved = apply_edits_to_tree(
            tree,
            deleted=[("100", (0, 0, 0), "")],
            moves={},
        )
        self.assertEqual(removed, 2)
        self.assertEqual(moved, 0)
        scene = extract_scene_from_root(tree.getroot())
        self.assertEqual(scene.total_blocks, 1)
        self.assertEqual(scene.blocks[0].entity_id, "99")


class SearchPackOrderTests(unittest.TestCase):
    def test_filter_clear_keeps_original_pack_order_and_path_select(self):
        cards = []
        blueprints = []
        for i, name in enumerate(("Alpha", "Beta", "Charlie")):
            bp = SimpleNamespace(name=name, display_name=name, path=Path(f"/ships/{name}"))
            card = SimpleNamespace(bp_info=bp, index=i)
            cards.append(card)
            blueprints.append(bp)

        filtered = search_pack_order(cards, blueprints, "ha")
        self.assertEqual([c.bp_info.name for c in filtered], ["Alpha", "Charlie"])
        cleared = search_pack_order(cards, blueprints, "")
        self.assertEqual([c.bp_info.name for c in cleared], ["Alpha", "Beta", "Charlie"])

        # Old pack() reappend after a Beta-only filter would put Beta first.
        stale_top = cards[1]
        stale_top.index = 0
        selected = blueprint_for_card(blueprints, stale_top)
        self.assertEqual(selected.name, "Beta")
        self.assertEqual(visible_index_for_path(cleared and blueprints, cards[0].bp_info.path), 0)
        self.assertNotEqual(blueprint_for_card(blueprints, cards[0]).name, selected.name)


class ColorLegendTests(unittest.TestCase):
    def test_missing_color_mask_keeps_rgb_none_for_subtype_legend(self):
        root = ET.fromstring(UNNAMED_BLOCK)
        scene = extract_scene_from_root(root)
        cockpit = next(b for b in scene.blocks if b.subtype == "LargeBlockCockpit")
        armor = next(b for b in scene.blocks if b.subtype == "LargeBlockArmorBlock")
        self.assertIsNone(cockpit.color_rgb)
        self.assertIsNone(armor.color_rgb)
        fill, _outline = ShipCanvas._get_block_color(cockpit.subtype, False, cockpit.color_rgb)
        from ui.theme import TacticalTheme
        self.assertEqual(fill, TacticalTheme.COLOR_COCKPIT)

    def test_present_mask_still_uses_keen_s_v_offset(self):
        xml = """<?xml version="1.0"?>
        <Definitions>
          <CubeGrid>
            <CubeBlocks>
              <MyObjectBuilder_CubeBlock>
                <SubtypeName>LargeBlockArmorBlock</SubtypeName>
                <ColorMaskHSV x="0.1" y="0.2" z="0.3" />
              </MyObjectBuilder_CubeBlock>
            </CubeBlocks>
          </CubeGrid>
        </Definitions>
        """
        scene = extract_scene_from_root(ET.fromstring(xml))
        block = scene.blocks[0]
        self.assertEqual(block.color_rgb, hsv_offset_to_rgb(0.1, 0.2, 0.3))


class HonestBlockCountTests(unittest.TestCase):
    def test_card_analytics_and_scene_agree_without_inventing_block(self):
        root = ET.fromstring(UNNAMED_BLOCK)
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "Bare"
            folder.mkdir()
            (folder / "bp.sbc").write_text(UNNAMED_BLOCK, encoding="utf-8")
            scanner = BlueprintScanner(
                registry=build_registry(include_builtin=True),
                enabled_categories=["armor"],
                persist_cache=False,
            )
            info = scanner.parse_folder(folder)
        engine = BlueprintAnalyticsEngine()
        analytics = engine.analyze_root(root, blueprint_name="Bare")
        from_counts = engine.analyze_counts(
            info.subtype_counts,
            blueprint_name="Bare",
            grid_size=info.grid_size,
            block_count=info.block_count,
        )
        scene = extract_scene_from_root(root)
        self.assertEqual(info.block_count, 3)
        self.assertEqual(analytics.block_count, 3)
        self.assertEqual(from_counts.block_count, 3)
        self.assertEqual(scene.total_blocks, 3)
        self.assertNotIn("Block", info.subtype_counts)
        self.assertNotIn("Block", analytics.block_counts)
        self.assertNotIn("Block", {b.subtype for b in scene.blocks})
        self.assertEqual(sum(info.subtype_counts.values()), 2)


class ResetVisibilityHiddenTests(unittest.TestCase):
    def test_reset_clears_session_hidden_and_renderer_ids(self):
        from ui.widgets.ship_preview import ShipPreviewHost

        host = ShipPreviewHost.__new__(ShipPreviewHost)
        host._hide_layers = 2
        host._hidden_categories = {"armor"}
        host._hide_armor = True
        host._isolated = True
        host._edits = GridEditSession()
        host._edits.hidden.add(("100", (0, 0, 0), "10"))
        host._renderer = SimpleNamespace(
            hidden_subtypes={"Gyro"},
            hide_armor=True,
            isolate_id=3.0,
            hidden_ids={1, 2},
        )
        host._cat_buttons = {}
        host._layer_slider = SimpleNamespace(set=lambda *_a, **_k: None)
        host._layer_label = SimpleNamespace(configure=lambda **_k: None)
        host._apply_dissect_chrome = lambda: None
        host._refresh_status = lambda: None
        host._schedule_redraw = lambda **_k: None
        synced = []

        def _sync() -> None:
            synced.append(set(host._edits.hidden))
            host._renderer.hidden_ids = set()

        host._sync_user_hidden = _sync
        host._reset_visibility()
        self.assertEqual(host._edits.hidden, set())
        self.assertEqual(host._renderer.hidden_ids, set())
        self.assertEqual(synced, [set()])


class BuildReadyStatusTests(unittest.TestCase):
    def test_non_progressive_ready_clears_building_before_status(self):
        from ui.widgets.ship_preview import ShipPreviewHost

        host = ShipPreviewHost.__new__(ShipPreviewHost)
        host._job = SimpleNamespace(is_current=lambda _g: True)
        host._install_valid = True
        host._ensure_renderer = lambda: SimpleNamespace()
        host._upload_cpu = lambda _cpu: True
        host._mesh_ready = False
        host._cpu_scene = None
        host._cpu_stage = ""
        host._simplified = False
        host._shown_count = 0
        host._set_dissect_enabled = lambda _v: None
        host._apply_dissect_chrome = lambda: None
        host._sync_user_hidden = lambda: None
        host._apply_mode = lambda: None
        host._schedule_redraw = lambda **_k: None
        host.after = lambda *_a, **_k: None
        host._building = True
        seen = []

        def _status() -> None:
            seen.append(host._building)

        host._refresh_status = _status
        cpu = SimpleNamespace(
            stage="full",
            simplified=False,
            shown_count=4,
            has_functional_mwm=False,
            huge=False,
            exploded=False,
        )
        host._on_build_ready(1, cpu, refine=False)
        self.assertEqual(seen, [False])
        self.assertFalse(host._building)


class FileClearCatalogTests(unittest.TestCase):
    def test_catalog_failure_after_clear_is_rejected(self):
        hub = JobHub()
        generation = hub.catalog.begin()
        hub.cancel_catalog()
        self.assertFalse(
            catalog_completion_allowed(hub.catalog, generation, cleared=False)
        )
        again = hub.catalog.begin()
        self.assertFalse(catalog_completion_allowed(hub.catalog, again, cleared=True))
        self.assertIsNone(pending_catalog_for(None, object()))

    def test_clear_does_not_cancel_in_flight_scan(self):
        hub = JobHub()
        scan_gen = hub.scan.begin()
        inspect_gen = hub.inspect.begin()
        hub.catalog.begin()
        hub.cancel_catalog()
        self.assertTrue(hub.scan.is_current(scan_gen))
        self.assertTrue(hub.inspect.is_current(inspect_gen))


class AtomicScanMetaTests(unittest.TestCase):
    def test_persist_uses_atomic_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp) / "scan_meta_v1.json"
            folder = Path(tmp) / "Ship"
            folder.mkdir()
            (folder / "bp.sbc").write_text(TWO_BLOCK, encoding="utf-8")
            with mock.patch("safe_xml.atomic_write_text", wraps=__import__("safe_xml").atomic_write_text) as wrote:
                scanner = BlueprintScanner(
                    registry=build_registry(include_builtin=True),
                    enabled_categories=["armor"],
                    persist_cache=cache,
                )
                scanner.scan_blueprints(Path(tmp))
            self.assertTrue(wrote.called)
            self.assertTrue(cache.is_file())


if __name__ == "__main__":
    unittest.main()

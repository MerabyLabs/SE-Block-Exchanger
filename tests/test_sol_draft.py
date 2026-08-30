"""Sol draft follow-ups: Min-only edit chains, races, 2D blit, table chunks."""

import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from blueprint_analytics import BlueprintAnalyticsEngine, first_free_min
from blueprint_document import (
    JobToken,
    install_detection_applies,
    save_as_result_applies,
    scan_callback_applies,
)
from blueprint_edit import (
    GridEditSession,
    apply_edits_to_tree,
    collapse_min_only_moves,
)
from se_render.hsv import hsv_offset_to_rgb
from se_render.scene_graph import extract_scene_from_root
from ui.selective_exchange_panel import (
    TABLE_ROW_CHUNK,
    chunk_table_rows,
    table_build_progress,
)
from ui.theme import TacticalTheme
from ui.widgets.ship_canvas import (
    VoxelBlock,
    build_map_frame,
    collect_projected_cells,
    map_status_caption,
    rasterize_projected_cells,
    render_map_bitmap,
)


NAMELESS_TWO = """<?xml version="1.0"?>
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
              <Min x="5" y="0" z="0" />
            </MyObjectBuilder_CubeBlock>
          </CubeBlocks>
        </CubeGrid>
      </CubeGrids>
    </ShipBlueprint>
  </ShipBlueprints>
</Definitions>
"""

NAMELESS_NEIGHBOR = """<?xml version="1.0"?>
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
              <Min x="1" y="0" z="0" />
            </MyObjectBuilder_CubeBlock>
          </CubeBlocks>
        </CubeGrid>
      </CubeGrids>
    </ShipBlueprint>
  </ShipBlueprints>
</Definitions>
"""


def _mins(root) -> set:
    scene = extract_scene_from_root(root)
    return {b.local_min for b in scene.blocks}


class MinOnlyEditChainTests(unittest.TestCase):
    def test_sequential_session_moves_keep_one_key(self):
        session = GridEditSession()
        first = ("100", (0, 0, 0), "")
        session.move(first, (0, 0, 0), (1, 0, 0))
        after_rebuild = ("100", (1, 0, 0), "")
        dest = session.move(after_rebuild, (1, 0, 0), (1, 0, 0))
        self.assertEqual(dest, (2, 0, 0))
        deleted, moves = session.committed_edits()
        self.assertEqual(deleted, set())
        self.assertEqual(moves, {first: (2, 0, 0)})

    def test_sequential_min_moves_do_not_move_the_neighbor(self):
        session = GridEditSession()
        session.move(("100", (0, 0, 0), ""), (0, 0, 0), (1, 0, 0))
        session.move(("100", (1, 0, 0), ""), (1, 0, 0), (1, 0, 0))
        tree = ET.ElementTree(ET.fromstring(NAMELESS_NEIGHBOR))
        deleted, moves = session.committed_edits()
        removed, moved = apply_edits_to_tree(tree, deleted, moves)
        self.assertEqual(removed, 0)
        self.assertEqual(moved, 1)
        self.assertEqual(_mins(tree.getroot()), {(2, 0, 0), (1, 0, 0)})

    def test_chained_raw_moves_collapse_when_intermediate_is_empty(self):
        tree = ET.ElementTree(ET.fromstring(NAMELESS_TWO))
        raw = {
            ("100", (0, 0, 0), ""): (1, 0, 0),
            ("100", (1, 0, 0), ""): (2, 0, 0),
        }
        collapsed = collapse_min_only_moves(tree.getroot(), raw)
        self.assertEqual(collapsed, {("100", (0, 0, 0), ""): (2, 0, 0)})
        removed, moved = apply_edits_to_tree(tree, [], raw)
        self.assertEqual(removed, 0)
        self.assertEqual(moved, 1)
        self.assertEqual(_mins(tree.getroot()), {(2, 0, 0), (5, 0, 0)})

    def test_move_then_delete_without_entity_id_removes_the_block(self):
        session = GridEditSession()
        session.move(("100", (0, 0, 0), ""), (0, 0, 0), (3, 0, 0))
        session.delete(("100", (3, 0, 0), ""))
        deleted, moves = session.committed_edits()
        self.assertEqual(deleted, {("100", (0, 0, 0), "")})
        self.assertEqual(moves, {})
        tree = ET.ElementTree(ET.fromstring(NAMELESS_TWO))
        removed, moved = apply_edits_to_tree(tree, deleted, moves)
        self.assertEqual(removed, 1)
        self.assertEqual(moved, 0)
        self.assertEqual(_mins(tree.getroot()), {(5, 0, 0)})

    def test_raw_move_then_delete_retargets_dest_identity(self):
        tree = ET.ElementTree(ET.fromstring(NAMELESS_TWO))
        removed, moved = apply_edits_to_tree(
            tree,
            deleted=[("100", (3, 0, 0), "")],
            moves={("100", (0, 0, 0), ""): (3, 0, 0)},
        )
        self.assertEqual(removed, 1)
        self.assertEqual(moved, 0)
        self.assertEqual(_mins(tree.getroot()), {(5, 0, 0)})


class RaceGateTests(unittest.TestCase):
    def test_stale_detect_does_not_override_manual_install(self):
        token = JobToken()
        generation = token.begin()
        self.assertTrue(
            install_detection_applies(
                token, generation, cleared=False, saved_install="", incoming_path="/steam"
            )
        )
        token.begin()
        self.assertFalse(
            install_detection_applies(
                token, generation, cleared=False, saved_install="/manual", incoming_path="/steam"
            )
        )
        current = token.begin()
        self.assertFalse(
            install_detection_applies(
                token,
                current,
                cleared=False,
                saved_install="/manual",
                incoming_path="/steam",
            )
        )
        cleared = token.begin()
        self.assertTrue(
            install_detection_applies(
                token, cleared, cleared=True, saved_install="", incoming_path="/steam"
            )
        )

    def test_stale_scan_not_found_is_rejected(self):
        token = JobToken()
        first = token.begin()
        second = token.begin()
        self.assertFalse(scan_callback_applies(token, first))
        self.assertTrue(scan_callback_applies(token, second))

    def test_save_as_toasts_only_current_generation(self):
        self.assertTrue(save_as_result_applies(2, 2))
        self.assertFalse(save_as_result_applies(1, 2))
        self.assertFalse(save_as_result_applies(1, 2, in_flight=True))


class RasterizeMapTests(unittest.TestCase):
    def test_legend_and_keen_mask_survive_blit(self):
        blocks = [
            VoxelBlock(0, 0, 0, "LargeBlockCockpit", "Hull", False),
            VoxelBlock(1, 0, 0, "LargeBlockArmorBlock", "Hull", False, color_rgb=hsv_offset_to_rgb(0.1, 0.2, 0.3)),
        ]
        cells = collect_projected_cells(blocks, "Top")
        self.assertEqual(cells[(0, 0)][0], TacticalTheme.COLOR_COCKPIT)
        self.assertNotEqual(cells[(1, 0)][0], TacticalTheme.COLOR_COCKPIT)
        image = rasterize_projected_cells(
            cells,
            width=64,
            height=64,
            step=8,
            cx=32,
            cy=32,
            mid_x=0.5,
            mid_y=0,
            projection="Top",
            draw_grid=False,
        )
        self.assertEqual(image.size, (64, 64))
        cockpit = _hex_rgb(TacticalTheme.COLOR_COCKPIT)
        self.assertEqual(image.getpixel((30, 34)), cockpit)

    def test_ten_thousand_cells_rasterize_without_dropping_keys(self):
        blocks = [
            VoxelBlock(i % 100, 0, i // 100, "LargeBlockArmorBlock", "Hull", False)
            for i in range(10000)
        ]
        cells = collect_projected_cells(blocks, "Top")
        self.assertEqual(len(cells), 10000)

    def test_render_map_bitmap_matches_collect_raster(self):
        blocks = [
            VoxelBlock(0, 0, 0, "LargeBlockCockpit", "Hull", False),
            VoxelBlock(2, 0, 1, "LargeBlockArmorBlock", "Hull", False),
        ]
        image = render_map_bitmap(
            blocks,
            projection="Top",
            width=64,
            height=64,
            scale=8,
            pan_x=0,
            pan_y=0,
        )
        self.assertIsNotNone(image)
        self.assertEqual(image.size, (64, 64))
        isolated = render_map_bitmap(
            blocks,
            projection="Top",
            width=64,
            height=64,
            scale=8,
            pan_x=0,
            pan_y=0,
            grid_entity_id="missing",
        )
        self.assertIsNone(isolated)

    def test_build_map_frame_precomputes_bounds_caption_and_fit(self):
        blocks = [
            VoxelBlock(0, 0, 0, "LargeBlockArmorBlock", "Hull", False),
            VoxelBlock(9, 2, 4, "LargeBlockArmorBlock", "Hull", False),
            VoxelBlock(1, 0, 0, "LargeBlockArmorBlock", "Turret", False, grid_entity_id="t1"),
        ]
        frame = build_map_frame(
            blocks,
            projection="Top",
            width=200,
            height=160,
            scale=16,
            pan_x=0,
            pan_y=0,
            fit=True,
        )
        self.assertEqual(frame.count, 3)
        self.assertEqual(frame.min_c, (0, 0, 0))
        self.assertEqual(frame.max_c, (9, 2, 4))
        self.assertTrue(frame.fitted)
        self.assertEqual(frame.caption, map_status_caption(3, (0, 0, 0), (9, 2, 4)))
        self.assertIn("3 blocks", frame.caption)
        self.assertIsNotNone(frame.image)
        turret = build_map_frame(
            blocks,
            projection="Top",
            width=64,
            height=64,
            scale=8,
            pan_x=0,
            pan_y=0,
            grid_filter="Turret",
            grid_entity_id="t1",
        )
        self.assertEqual(turret.count, 1)
        self.assertIn("Turret", turret.caption)
        self.assertIn("1", turret.caption)


class SelectiveTableChunkTests(unittest.TestCase):
    def test_progress_and_chunks_cover_every_row(self):
        self.assertEqual(table_build_progress(40, 301), "Building table… 40 of 301")
        self.assertEqual(table_build_progress(301, 301), "")
        rows = [(f"T{i}", i) for i in range(301)]
        seen = []
        start = 0
        while start < len(rows):
            chunk, start = chunk_table_rows(rows, start, TABLE_ROW_CHUNK)
            seen.extend(chunk)
        self.assertEqual(len(seen), 301)
        self.assertEqual(seen[0][0], "T0")
        self.assertEqual(seen[-1][0], "T300")


class ApplyFixOriginTests(unittest.TestCase):
    def test_prefers_origin_when_empty(self):
        self.assertEqual(first_free_min({(1, 0, 0), (2, 0, 0)}), (0, 0, 0))

    def test_occupied_origin_uses_first_empty_neighbor(self):
        self.assertEqual(first_free_min({(0, 0, 0), (5, 0, 0)}), (1, 0, 0))

    def test_control_fix_skips_occupied_origin(self):
        import tempfile

        xml = NAMELESS_TWO
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bp.sbc"
            path.write_text(xml, encoding="utf-8")
            engine = BlueprintAnalyticsEngine()
            self.assertTrue(engine.apply_fix(path, "add_control_block"))
            root = ET.parse(path).getroot()
            blocks = list(root.findall(".//CubeBlocks/*"))
            mins = []
            cockpit_min = None
            for block in blocks:
                min_elem = block.find("Min")
                if min_elem is None:
                    continue
                mn = (
                    int(float(min_elem.attrib.get("x", 0))),
                    int(float(min_elem.attrib.get("y", 0))),
                    int(float(min_elem.attrib.get("z", 0))),
                )
                mins.append(mn)
                subtype = (block.findtext("SubtypeName") or "").strip()
                if "Cockpit" in subtype:
                    cockpit_min = mn
            self.assertEqual(len(blocks), 3)
            self.assertEqual(len(set(mins)), 3)
            self.assertEqual(cockpit_min, (1, 0, 0))
            self.assertNotEqual(cockpit_min, (0, 0, 0))


def _hex_rgb(color: str):
    raw = color.lstrip("#")
    return int(raw[0:2], 16), int(raw[2:4], 16), int(raw[4:6], 16)


if __name__ == "__main__":
    unittest.main()

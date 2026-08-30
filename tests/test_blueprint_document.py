import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest import mock

from blueprint_analytics import BlueprintAnalyticsEngine
from blueprint_document import (
    BlueprintDocument,
    BlueprintDocumentCache,
    CancelledError,
    JobHub,
    JobToken,
    catalog_completion_allowed,
    dry_run_from_counts,
    inspect_result_applies,
)
from blueprint_scanner import BlueprintScanner
from mappings import build_registry
from se_armor_replacer import ArmorBlockReplacer
from se_render.scene_graph import extract_scene_from_root, voxels_from_scene
from subgrid_engine.hierarchy_parser import SubgridHierarchyParser
from tests.test_scene_graph import ROTOR_BLUEPRINT


def _write_ship(folder: Path, blocks: int, name: str = "Ship") -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    parts = [
        '<?xml version="1.0"?>\n<Definitions>\n',
        f'  <CubeGrid><EntityId>1</EntityId><DisplayName>{name}</DisplayName>',
        "<GridSizeEnum>Large</GridSizeEnum><CubeBlocks>\n",
    ]
    for i in range(blocks):
        subtype = "LargeBlockArmorBlock" if i % 2 == 0 else "LargeHeavyBlockArmorBlock"
        x, y, z = i % 10, (i // 10) % 10, i // 100
        parts.append(
            f'<MyObjectBuilder_CubeBlock><SubtypeName>{subtype}</SubtypeName>'
            f'<Min x="{x}" y="{y}" z="{z}" /></MyObjectBuilder_CubeBlock>\n'
        )
    parts.append("</CubeBlocks></CubeGrid></Definitions>\n")
    bp = folder / "bp.sbc"
    bp.write_text("".join(parts), encoding="utf-8")
    return bp


class DocumentSharingTests(unittest.TestCase):
    def test_voxels_stay_lazy_until_read(self):
        root = ET.fromstring(ROTOR_BLUEPRINT)
        doc = BlueprintDocument.from_root(root, display_name="RotorShip")
        self.assertIsNone(doc._voxels)
        self.assertEqual(len(doc.voxels), 3)
        self.assertIsNotNone(doc._voxels)
        self.assertIs(doc.voxels, doc._voxels)

    def test_one_extract_feeds_scene_voxels_and_structure(self):
        root = ET.fromstring(ROTOR_BLUEPRINT)
        doc = BlueprintDocument.from_root(root, display_name="RotorShip")
        scene = extract_scene_from_root(root)
        self.assertEqual(doc.block_count, 3)
        self.assertEqual(doc.scene.total_blocks, scene.total_blocks)
        self.assertEqual(len(doc.voxels), 3)
        self.assertEqual(doc.structure.total_grids, 2)
        self.assertEqual(doc.structure.total_blocks, 3)
        self.assertEqual(doc.structure.root_node.grid_name, "Hull")
        self.assertEqual(len(doc.structure.root_node.children), 1)
        self.assertEqual(doc.structure.root_node.children[0].grid_name, "RotorHead")
        hull_voxel = next(v for v in doc.voxels if v["subtype"] == "LargeBlockArmorBlock" and not v["is_subgrid"])
        hull_block = next(b for b in doc.scene.blocks if b.subtype == "LargeBlockArmorBlock" and not b.is_subgrid)
        self.assertEqual(hull_voxel["hsv"], hull_block.hsv)
        self.assertEqual(hull_voxel["color_rgb"], hull_block.color_rgb)

    def test_voxels_from_scene_match_extract(self):
        scene = extract_scene_from_root(ET.fromstring(ROTOR_BLUEPRINT))
        voxels = voxels_from_scene(scene)
        self.assertEqual(len(voxels), len(scene.blocks))
        self.assertTrue(any(v["is_subgrid"] for v in voxels))

    def test_structure_from_scene_matches_xml_parser(self):
        root = ET.fromstring(ROTOR_BLUEPRINT)
        scene = extract_scene_from_root(root)
        from_scene = SubgridHierarchyParser.from_scene(scene)
        from_xml = SubgridHierarchyParser.parse_element(root)
        self.assertEqual(from_scene.total_grids, from_xml.total_grids)
        self.assertEqual(from_scene.total_blocks, from_xml.total_blocks)
        self.assertEqual(from_scene.root_node.grid_name, from_xml.root_node.grid_name)
        self.assertEqual(len(from_scene.root_node.children), len(from_xml.root_node.children))
        self.assertGreaterEqual(len(from_scene.mechanical_links), 1)
        self.assertTrue(from_scene.root_node.is_main_grid)
        self.assertFalse(from_scene.root_node.children[0].is_main_grid)


class DocumentCacheTests(unittest.TestCase):
    def test_cache_defaults_to_two_entries_and_evicts(self):
        cache = BlueprintDocumentCache()
        self.assertEqual(cache.max_entries, 2)
        with tempfile.TemporaryDirectory() as tmp:
            folders = []
            for name in ("A", "B", "C"):
                folder = Path(tmp) / name
                _write_ship(folder, 3, name)
                folders.append(folder)
                cache.get_or_load(folder)
            self.assertIsNone(cache.get(folders[0]))
            self.assertIsNotNone(cache.get(folders[1]))
            self.assertIsNotNone(cache.get(folders[2]))

    def test_cache_hit_same_mtime(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "A"
            path = _write_ship(folder, 4)
            cache = BlueprintDocumentCache()
            first = cache.get_or_load(folder)
            second = cache.get_or_load(folder)
            self.assertIs(first, second)
            self.assertEqual(first.stamp.path, str(path))

    def test_cache_miss_after_rewrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "A"
            _write_ship(folder, 4)
            cache = BlueprintDocumentCache()
            first = cache.get_or_load(folder)
            _write_ship(folder, 6)
            second = cache.get_or_load(folder)
            self.assertIsNot(first, second)
            self.assertEqual(second.block_count, 6)

    def test_cancel_stale_load(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "A"
            _write_ship(folder, 3)
            cache = BlueprintDocumentCache()
            token = JobToken()
            generation = token.begin()
            token.cancel()
            with self.assertRaises(CancelledError):
                cache.get_or_load(folder, token=token, generation=generation)
            self.assertIsNone(cache.get(folder))


class DryRunSharingTests(unittest.TestCase):
    def test_counts_match_replace_blocks(self):
        root = ET.fromstring(
            """<?xml version="1.0"?>
            <Definitions>
              <CubeGrid><CubeBlocks>
                <MyObjectBuilder_CubeBlock><SubtypeName>LargeBlockArmorBlock</SubtypeName></MyObjectBuilder_CubeBlock>
                <MyObjectBuilder_CubeBlock><SubtypeName>LargeBlockArmorBlock</SubtypeName></MyObjectBuilder_CubeBlock>
                <MyObjectBuilder_CubeBlock><SubtypeName>LargeHeavyBlockArmorBlock</SubtypeName></MyObjectBuilder_CubeBlock>
              </CubeBlocks></CubeGrid>
            </Definitions>
            """
        )
        tree = ET.ElementTree(root)
        registry = build_registry(include_builtin=True)
        replacer = ArmorBlockReplacer(
            verbose=False,
            reverse=False,
            enabled_categories=["armor"],
            registry=registry,
            include_profiles=False,
        )
        replacer.replace_blocks(tree, dry_run=True)
        before_walk = {}
        after_walk = {}
        for source, target in replacer.change_log:
            before_walk[source] = before_walk.get(source, 0) + 1
            after_walk[target] = after_walk.get(target, 0) + 1
        counts = {"LargeBlockArmorBlock": 2, "LargeHeavyBlockArmorBlock": 1}
        before, after, report, n = dry_run_from_counts(counts, replacer.mapping)
        self.assertEqual(n, 2)
        self.assertEqual(before, before_walk)
        self.assertEqual(after, after_walk)
        self.assertIn("LargeBlockArmorBlock -> LargeHeavyBlockArmorBlock", report)
        self.assertEqual(report, replacer.get_dry_run_report())


class ScanCacheTests(unittest.TestCase):
    def test_second_scan_and_category_change_do_not_reparse(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_ship(root / "A", 8, "A")
            _write_ship(root / "B", 5, "B")
            scanner = BlueprintScanner(
                registry=build_registry(include_builtin=True),
                enabled_categories=["armor"],
                persist_cache=False,
            )
            with mock.patch("blueprint_scanner.safe_xml.parse", wraps=__import__("safe_xml").parse) as parsed:
                first = scanner.scan_blueprints(root)
                parse_count = parsed.call_count
                self.assertEqual(len(first), 2)
                second = scanner.scan_blueprints(root)
                self.assertEqual(parsed.call_count, parse_count)
                self.assertEqual(len(second), 2)
                armor_ready = sum(first[0].convertible_counts.values())
                scanner.set_enabled_categories(["thrusters"])
                remapped = scanner.remap_cached()
                self.assertEqual(parsed.call_count, parse_count)
                self.assertEqual(sum(remapped[0].convertible_counts.values()), 0)
                self.assertGreater(armor_ready, 0)
                scanner.scan_blueprints(root)
                self.assertEqual(parsed.call_count, parse_count)

    def test_mtime_change_reparses(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / "A"
            _write_ship(folder, 4, "A")
            scanner = BlueprintScanner(
                registry=build_registry(include_builtin=True),
                enabled_categories=["armor"],
                persist_cache=False,
            )
            with mock.patch("blueprint_scanner.safe_xml.parse", wraps=__import__("safe_xml").parse) as parsed:
                scanner.scan_blueprints(root)
                first_count = parsed.call_count
                _write_ship(folder, 9, "A")
                infos = scanner.scan_blueprints(root)
                self.assertGreater(parsed.call_count, first_count)
                self.assertEqual(infos[0].block_count, 9)


class AnalyticsCountsTests(unittest.TestCase):
    def test_analyze_counts_matches_analyze_root(self):
        xml = """<?xml version="1.0"?>
        <Definitions>
          <CubeGrid>
            <GridSizeEnum>Large</GridSizeEnum>
            <CubeBlocks>
              <MyObjectBuilder_CubeBlock><SubtypeName>LargeBlockArmorBlock</SubtypeName></MyObjectBuilder_CubeBlock>
              <MyObjectBuilder_CubeBlock><SubtypeName>LargeBlockArmorBlock</SubtypeName></MyObjectBuilder_CubeBlock>
              <MyObjectBuilder_CubeBlock><SubtypeName>LargeBlockBatteryBlock</SubtypeName></MyObjectBuilder_CubeBlock>
            </CubeBlocks>
          </CubeGrid>
        </Definitions>
        """
        root = ET.fromstring(xml)
        engine = BlueprintAnalyticsEngine()
        from_root = engine.analyze_root(root, blueprint_name="X")
        from_counts = engine.analyze_counts(
            {"LargeBlockArmorBlock": 2, "LargeBlockBatteryBlock": 1},
            blueprint_name="X",
            grid_size="Large",
        )
        self.assertEqual(from_root.block_count, from_counts.block_count)
        self.assertEqual(from_root.pcu_total, from_counts.pcu_total)
        self.assertEqual(from_root.mass_total, from_counts.mass_total)
        self.assertEqual(from_root.block_counts, from_counts.block_counts)

    def test_infer_cache_reuses_unknown_armor(self):
        engine = BlueprintAnalyticsEngine()
        first = engine.db.get_block("LargeWeirdArmorSlope")
        second = engine.db.get_block("LargeWeirdArmorSlope")
        self.assertIsNotNone(first)
        self.assertIs(first, second)


class JobTokenTests(unittest.TestCase):
    def test_begin_invalidates_previous(self):
        token = JobToken()
        first = token.begin()
        self.assertTrue(token.is_current(first))
        second = token.begin()
        self.assertFalse(token.is_current(first))
        self.assertTrue(token.is_current(second))

    def test_inspect_result_applies_checks_path(self):
        token = JobToken()
        generation = token.begin()
        self.assertTrue(inspect_result_applies(token, generation, Path("/ship"), Path("/ship")))
        self.assertFalse(inspect_result_applies(token, generation, Path("/ship"), Path("/other")))

    def test_catalog_completion_rejected_after_clear(self):
        hub = JobHub()
        generation = hub.catalog.begin()
        self.assertTrue(catalog_completion_allowed(hub.catalog, generation, cleared=False))
        hub.cancel_stale()
        self.assertFalse(catalog_completion_allowed(hub.catalog, generation, cleared=False))
        again = hub.catalog.begin()
        self.assertFalse(catalog_completion_allowed(hub.catalog, again, cleared=True))
        self.assertTrue(catalog_completion_allowed(hub.catalog, again, cleared=False))

    def test_cancel_catalog_leaves_scan_and_inspect(self):
        hub = JobHub()
        scan_gen = hub.scan.begin()
        inspect_gen = hub.inspect.begin()
        catalog_gen = hub.catalog.begin()
        hub.cancel_catalog()
        self.assertTrue(hub.scan.is_current(scan_gen))
        self.assertTrue(hub.inspect.is_current(inspect_gen))
        self.assertFalse(hub.catalog.is_current(catalog_gen))


if __name__ == "__main__":
    unittest.main()

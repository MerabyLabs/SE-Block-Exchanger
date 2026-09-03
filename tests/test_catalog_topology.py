import tempfile
import unittest
from pathlib import Path

from se_assets.cube_catalog import CubeBlockCatalog, _iter_definitions, infer_cube_topology
from se_assets.install_locator import validate_install
from se_assets.mesh_cache import MeshLibrary
from se_render.topology import known_topologies, topology_mesh


CUBE_SBC = """<?xml version="1.0"?>
<Definitions xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <CubeBlocks>
    <Definition>
      <Id>
        <TypeId>CubeBlock</TypeId>
        <SubtypeId>LargeBlockArmorBlock</SubtypeId>
      </Id>
      <CubeSize>Large</CubeSize>
      <BlockTopology>Cube</BlockTopology>
      <Size x="1" y="1" z="1" />
      <CubeDefinition>
        <CubeTopology>Box</CubeTopology>
      </CubeDefinition>
      <Model>Models\\Cubes\\Large\\ArmorBlock</Model>
    </Definition>
    <Definition>
      <Id>
        <TypeId>CubeBlock</TypeId>
        <SubtypeId>LargeBlockArmorSlope</SubtypeId>
      </Id>
      <CubeSize>Large</CubeSize>
      <BlockTopology>Cube</BlockTopology>
      <Size x="1" y="1" z="1" />
      <CubeDefinition>
        <CubeTopology>Slope</CubeTopology>
      </CubeDefinition>
    </Definition>
    <Definition>
      <Id>
        <TypeId>Reactor</TypeId>
        <SubtypeId>LargeBlockLargeGenerator</SubtypeId>
      </Id>
      <CubeSize>Large</CubeSize>
      <BlockTopology>TriangleMesh</BlockTopology>
      <Size x="3" y="3" z="3" />
      <Model>Models\\Cubes\\Large\\Reactor</Model>
    </Definition>
  </CubeBlocks>
</Definitions>
"""


class CatalogTests(unittest.TestCase):
    def test_parses_cubeblocks_and_caches(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "SE"
            cubes = root / "Content" / "Data" / "CubeBlocks"
            cubes.mkdir(parents=True)
            (root / "Bin64").mkdir()
            (root / "Content" / "Models").mkdir(parents=True)
            (root / "Bin64" / "SpaceEngineers.exe").write_bytes(b"mz")
            (cubes / "CubeBlocks_Armor.sbc").write_text(CUBE_SBC, encoding="utf-8")
            self.assertTrue(validate_install(root))
            cache = Path(tmp) / "cache.json"
            catalog = CubeBlockCatalog(cache_path=cache)
            catalog.load(root)
            self.assertGreaterEqual(len(catalog), 3)
            armor = catalog.get("CubeBlock", "LargeBlockArmorBlock")
            self.assertIsNotNone(armor)
            self.assertEqual(armor.cube_topology, "Box")
            self.assertEqual(armor.block_topology, "Cube")
            reactor = catalog.get("Reactor", "LargeBlockLargeGenerator")
            self.assertEqual(reactor.size, (3, 3, 3))
            self.assertTrue(cache.is_file())

            again = CubeBlockCatalog(cache_path=cache)
            again.load(root)
            self.assertEqual(len(again), len(catalog))
            self.assertEqual(again.get("CubeBlock", "LargeBlockArmorSlope").cube_topology, "Slope")

    def test_cubeblocks_parent_is_not_walked_twice(self):
        import xml.etree.ElementTree as ET

        root = ET.fromstring(CUBE_SBC)
        yielded = list(_iter_definitions(root))
        self.assertEqual(len(yielded), 3)


class TopologyInferenceTests(unittest.TestCase):
    def test_official_cube_definition_and_stale_box_cache(self):
        self.assertEqual(infer_cube_topology("LargeBlockArmorSlope", "Slope"), "Slope")
        self.assertEqual(infer_cube_topology("LargeBlockArmorSlope", "Box"), "Slope")
        self.assertEqual(infer_cube_topology("LargeBlockArmorSlope2Base", "Box"), "Slope2Base")
        self.assertEqual(infer_cube_topology("LargeBlockArmorBlock", "Box"), "Box")
        self.assertEqual(infer_cube_topology("LargeBlockArmorCorner", ""), "Corner")


class TopologyTests(unittest.TestCase):
    def test_box_and_slope_have_triangles(self):
        box = topology_mesh("Box")
        slope = topology_mesh("Slope")
        self.assertGreaterEqual(box.indices.size, 36)
        self.assertGreaterEqual(slope.indices.size, 12)
        self.assertEqual(box.positions.shape[1], 3)
        self.assertIn("Box", known_topologies())
        self.assertIn("Slope", known_topologies())

    def test_unknown_topology_falls_back_to_box(self):
        unknown = topology_mesh("NotARealTopology")
        box = topology_mesh("Box")
        self.assertEqual(unknown.indices.size, box.indices.size)

    def test_mesh_library_box_fallback_without_install(self):
        library = MeshLibrary(None)
        mesh = library.mesh_for(None, "MissingBlock", (1, 1, 1), "Large")
        self.assertGreater(mesh.vertex_count, 0)


if __name__ == "__main__":
    unittest.main()

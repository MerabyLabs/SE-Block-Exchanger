import unittest
import xml.etree.ElementTree as ET

from blueprint_edit import apply_edits_to_tree
from se_assets.mesh_cache import MeshLibrary
from se_render.preview_build import (
    STAGE_SHELL,
    build_preview_cpu,
    filter_batches,
    instance_count,
    refine_mwm_cpu,
    should_alias_lod_sets,
    split_upload_chunks,
)
from se_render.scene_graph import PreviewScene, voxels_from_scene
from se_render.topology import topology_mesh
from tests.test_preview_render import _block, _catalog_with, _def


class LodAliasAndChunkTests(unittest.TestCase):
    def test_assembled_lod_aliases_same_list(self):
        catalog = _catalog_with(_def("CubeBlock", "LargeBlockArmorBlock", "Box"))
        blocks = [_block((i, 0, 0), entity=str(i)) for i in range(4)]
        cpu = build_preview_cpu(PreviewScene(blocks=blocks, total_blocks=4), catalog)
        self.assertTrue(should_alias_lod_sets(cpu.assembled, cpu.assembled_lod))
        self.assertTrue(should_alias_lod_sets(cpu.exploded, cpu.exploded_lod))
        self.assertFalse(should_alias_lod_sets(cpu.assembled, cpu.exploded))

    def test_upload_chunks_split_without_dropping_batches(self):
        catalog = _catalog_with(_def("CubeBlock", "LargeBlockArmorBlock", "Box"))
        blocks = [_block((i, 0, 0), entity=str(i)) for i in range(3)]
        cpu = build_preview_cpu(PreviewScene(blocks=blocks, total_blocks=3), catalog)
        chunks = split_upload_chunks(cpu.assembled, 1)
        self.assertEqual(sum(len(chunk) for chunk in chunks), len(cpu.assembled))


class MwmRefinePatchTests(unittest.TestCase):
    def test_refine_replaces_only_affected_instances(self):
        catalog = _catalog_with(
            _def("CubeBlock", "LargeBlockArmorBlock", "Box"),
            _def(
                "Reactor",
                "LargeBlockLargeGenerator",
                topology="",
                block_topology="TriangleMesh",
                size=(3, 3, 3),
            ),
        )
        reactor_def = catalog.get("Reactor", "LargeBlockLargeGenerator")
        reactor_def = _def(
            "Reactor",
            "LargeBlockLargeGenerator",
            topology="",
            block_topology="TriangleMesh",
            size=(3, 3, 3),
        )
        # _def does not set model_path; rebuild catalog entry with a path so _needs_mwm is true.
        from se_assets.cube_catalog import BlockDefinition

        reactor_def = BlockDefinition(
            type_id="Reactor",
            subtype_id="LargeBlockLargeGenerator",
            cube_size="Large",
            block_topology="TriangleMesh",
            cube_topology="",
            size_x=3,
            size_y=3,
            size_z=3,
            model_path="Models\\Cubes\\Large\\Reactor",
            model_offset=(0.0, 0.0, 0.0),
        )
        catalog.definitions[reactor_def.key] = reactor_def
        catalog.by_subtype[reactor_def.subtype_id] = reactor_def

        armor = [_block((i, 0, 0), entity=str(i)) for i in range(12)]
        reactor = _block((0, 5, 0), "LargeBlockLargeGenerator", "Reactor", entity="r")
        blocks = armor + [reactor]
        scene = PreviewScene(blocks=blocks, total_blocks=len(blocks))
        library = MeshLibrary(None)
        cpu = build_preview_cpu(scene, catalog, library, stage=STAGE_SHELL)
        before_ids = [int(i) for batch in cpu.assembled for i in batch.instance_ids]
        self.assertIn(12, before_ids)
        box_tris = topology_mesh("Box").triangle_count
        slope = topology_mesh("Slope")
        key = library.cache_key(
            reactor_def, reactor.subtype, reactor_def.size, reactor.grid_size, skip_mwm=False
        )
        library._meshes[key] = slope

        patched = refine_mwm_cpu(cpu, catalog, library, [reactor_def])
        after_ids = [int(i) for batch in patched.assembled for i in batch.instance_ids]
        self.assertEqual(sorted(before_ids), sorted(after_ids))
        reactor_batch = next(
            batch for batch in patched.assembled if 12 in [int(i) for i in batch.instance_ids]
        )
        self.assertEqual(reactor_batch.positions.shape[0], slope.vertex_count)
        self.assertNotEqual(reactor_batch.indices.size // 3, box_tris)
        self.assertEqual(instance_count(patched.assembled), instance_count(cpu.assembled))


class IsolateByEntityIdTests(unittest.TestCase):
    def test_duplicate_grid_names_filter_by_entity_id(self):
        catalog = _catalog_with(_def("CubeBlock", "LargeBlockArmorBlock", "Box"))
        a = _block((0, 0, 0), entity="a", grid="Turret", gid="10")
        b = _block((2, 0, 0), entity="b", grid="Turret", gid="20")
        hull = _block((4, 0, 0), entity="h", grid="Hull", gid="1")
        cpu = build_preview_cpu(PreviewScene(blocks=[a, b, hull], total_blocks=3), catalog)
        named = filter_batches(cpu.assembled, grid_name="Turret")
        by_id = filter_batches(cpu.assembled, grid_entity_id="10")
        named_ids = {int(i) for batch in named for i in batch.instance_ids}
        id_ids = {int(i) for batch in by_id for i in batch.instance_ids}
        self.assertEqual(named_ids, {0, 1})
        self.assertEqual(id_ids, {0})
        self.assertTrue(all(eid == "10" for batch in by_id for eid in batch.grid_entity_ids))

    def test_voxels_carry_grid_entity_id(self):
        block = _block((0, 0, 0), entity="a", grid="Turret", gid="99")
        scene = PreviewScene(blocks=[block], total_blocks=1)
        voxels = voxels_from_scene(scene)
        self.assertEqual(voxels[0]["grid_entity_id"], "99")

    def test_scene_filter_grid_uses_entity_id(self):
        a = _block((0, 0, 0), entity="a", grid="Turret", gid="10")
        b = _block((2, 0, 0), entity="b", grid="Turret", gid="20")
        scene = PreviewScene(blocks=[a, b], total_blocks=2)
        filtered = scene.filter_grid(grid_name="Turret", grid_entity_id="20")
        self.assertEqual(len(filtered.blocks), 1)
        self.assertEqual(filtered.blocks[0].entity_id, "b")


class EditIdentityIndexTests(unittest.TestCase):
    def test_index_apply_deletes_and_moves_in_one_pass(self):
        xml = """<?xml version="1.0"?>
        <Definitions>
          <CubeGrid>
            <EntityId>100</EntityId>
            <CubeBlocks>
              <MyObjectBuilder_CubeBlock>
                <EntityId>10</EntityId>
                <Min x="0" y="0" z="0" />
              </MyObjectBuilder_CubeBlock>
              <MyObjectBuilder_CubeBlock>
                <EntityId>11</EntityId>
                <Min x="1" y="0" z="0" />
              </MyObjectBuilder_CubeBlock>
              <MyObjectBuilder_CubeBlock>
                <EntityId>12</EntityId>
                <Min x="2" y="0" z="0" />
              </MyObjectBuilder_CubeBlock>
            </CubeBlocks>
          </CubeGrid>
        </Definitions>
        """
        tree = ET.ElementTree(ET.fromstring(xml))
        removed, moved = apply_edits_to_tree(
            tree,
            deleted=[("100", (2, 0, 0), "12")],
            moves={("100", (0, 0, 0), "10"): (8, 1, 0)},
        )
        self.assertEqual(removed, 1)
        self.assertEqual(moved, 1)
        from se_render.scene_graph import extract_scene_from_root

        scene = extract_scene_from_root(tree.getroot())
        self.assertEqual(scene.total_blocks, 2)
        moved_block = next(b for b in scene.blocks if b.entity_id == "10")
        self.assertEqual(moved_block.local_min, (8, 1, 0))


class PreviewPendingKeyTests(unittest.TestCase):
    def test_preview_key_stable_for_same_payload(self):
        from ui.preview_panel import PreviewPanel

        key_a = PreviewPanel._preview_key(
            None,
            ({"A": 2}, {"B": 2}, "ok"),
        )
        key_b = PreviewPanel._preview_key(
            None,
            ({"A": 2}, {"B": 2}, "ok"),
        )
        key_c = PreviewPanel._preview_key(
            None,
            ({"A": 3}, {"B": 2}, "ok"),
        )
        self.assertEqual(key_a, key_b)
        self.assertNotEqual(key_a, key_c)


if __name__ == "__main__":
    unittest.main()

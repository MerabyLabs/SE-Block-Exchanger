import time
import unittest

import numpy as np

from se_render.camera import (
    clip_planes_for_view,
    clip_planes_from_aabb,
    fit_distance,
    perspective,
    wheel_zoom_inward,
)
from se_render.hsv import hsv_offset_to_rgb
from se_render.occupancy import FACE_NEG_X, FACE_POS_X, is_fully_enclosed, is_solid_box
from se_render.orientation import translation_mat4
from se_render.camera import (
    OrbitCamera,
    zoom_factor_for_distance,
    zoom_toward_target,
)
from se_render.dissection import (
    ARMOR_EXPLODE_WEIGHT,
    DISSECT_DECKS,
    DISSECT_PEEL,
    DISSECT_RADIAL,
    FUNCTIONAL_EXPLODE_WEIGHT,
    deck_max_offsets,
    dissect_max_offsets,
    peel_max_offsets,
    pick_identity,
    radial_max_offsets,
    selection_caption,
    selection_meta,
)
from se_render.occupancy import (
    occupancy_padded_volume,
    occupancy_shell_layers,
    occupied_cells,
    occupied_exterior_face_count,
    plan_blocks,
    plan_visible_face_count,
    block_shell_layer,
)
from se_render.preview_build import (
    STAGE_SHELL,
    BuildGeneration,
    PickRecord,
    apply_dissect_mode,
    build_preview_cpu,
    explode_max_offsets,
    explode_offset,
    instance_count,
    triangle_count,
)
from se_render.preview_style import (
    ARMOR_ALBEDO_FLOOR,
    HUGE_SHIP_BLOCK_THRESHOLD,
    INTERACTIVE_MAX_EDGE,
    PREVIEW_CLEAR_COLOR,
    active_preview_set,
    apply_albedo_tint,
    block_material,
    format_preview_count_caption,
    material_style,
    render_target_size,
    use_interactive_lod,
)
from se_render.scene_graph import BlockInstance, PreviewScene
from se_render.topology import (
    FACE_NONE,
    cull_mesh_faces,
    face_uvs_for_triangle,
    flatten_indexed_mesh,
    simplify_mesh,
    topology_mesh,
)


class PreviewStyleTests(unittest.TestCase):
    def test_interactive_render_caps_long_edge(self):
        self.assertEqual(render_target_size(800, 600, False), (800, 600))
        self.assertEqual(render_target_size(800, 600, True), (800, 600))
        self.assertEqual(render_target_size(1920, 1080, True, block_count=100), (1920, 1080))
        rw, rh = render_target_size(1920, 1080, True, block_count=20000)
        self.assertLessEqual(max(rw, rh), INTERACTIVE_MAX_EDGE)
        self.assertGreaterEqual(min(rw, rh), 64)
        self.assertAlmostEqual(rw / rh, 1920 / 1080, places=2)
        self.assertEqual(render_target_size(1920, 1080, False, block_count=20000), (1920, 1080))

    def test_armor_keeps_official_hsv_without_jitter(self):
        edge, jitter, spec = material_style("CubeBlock", "LargeBlockArmorBlock")
        self.assertGreaterEqual(edge, 0.9)
        self.assertAlmostEqual(jitter, 0.5)
        self.assertLess(spec, 0.4)
        rgb = hsv_offset_to_rgb(0.0, 0.0, 0.0)
        self.assertTrue(all(0.0 <= c <= 1.0 for c in rgb))
        self.assertNotAlmostEqual(rgb[0], rgb[1])

    def test_functional_blocks_differ_from_armor(self):
        armor = material_style("CubeBlock", "LargeBlockArmorBlock")
        reactor = material_style("Reactor", "LargeBlockLargeGenerator")
        self.assertLess(reactor[0], armor[0])
        self.assertNotAlmostEqual(reactor[1], 0.5)
        self.assertGreater(reactor[2], armor[2])

    def test_functional_categories_do_not_match_armor_style(self):
        armor = block_material("CubeBlock", "LargeBlockArmorBlock")
        gyro = block_material("Gyro", "LargeBlockGyro")
        container = block_material("CargoContainer", "LargeBlockSmallContainer")
        battery = block_material("BatteryBlock", "LargeBlockBattery")
        self.assertTrue(armor.is_armor)
        for style in (gyro, container, battery):
            self.assertFalse(style.is_armor)
            self.assertNotEqual(style, armor)
            self.assertGreater(style.metal, armor.metal)
            self.assertGreater(style.spec, armor.spec)
        self.assertNotEqual(gyro, container)
        self.assertNotEqual(gyro, battery)
        self.assertNotEqual(container, battery)
        self.assertEqual(gyro.category, "gyro")
        self.assertEqual(container.category, "storage")
        self.assertEqual(battery.category, "power")


class FaceUvTests(unittest.TestCase):
    def test_unit_quad_triangles_span_face(self):
        normal = (0.0, 0.0, 1.0)
        a = face_uvs_for_triangle((0, 0, 1), (1, 0, 1), (1, 1, 1), normal)
        b = face_uvs_for_triangle((0, 0, 1), (1, 1, 1), (0, 1, 1), normal)
        for uvs in (a, b):
            xs = [p[0] for p in uvs]
            ys = [p[1] for p in uvs]
            self.assertAlmostEqual(min(xs), 0.0, places=5)
            self.assertAlmostEqual(max(xs), 1.0, places=5)
            self.assertAlmostEqual(min(ys), 0.0, places=5)
            self.assertAlmostEqual(max(ys), 1.0, places=5)

    def test_box_mesh_has_face_uvs_and_flat_normals(self):
        box = topology_mesh("Box")
        self.assertEqual(box.uvs.shape, (box.vertex_count, 2))
        self.assertGreaterEqual(box.uvs.min(), -1e-5)
        self.assertLessEqual(box.uvs.max(), 1.0 + 1e-5)
        self.assertLess(box.uvs.min(), 0.05)
        self.assertGreater(box.uvs.max(), 0.95)
        # Inset keeps armor faces from sharing a plane.
        self.assertGreater(box.positions.min(), 0.0)
        self.assertLess(box.positions.max(), 1.0)

    def test_flatten_indexed_mesh_is_unique_per_corner(self):
        positions = np.array(
            ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (1.0, 1.0, 0.0), (0.0, 1.0, 0.0)),
            dtype=np.float32,
        )
        indices = np.array((0, 1, 2, 0, 2, 3), dtype=np.uint32)
        mesh = flatten_indexed_mesh(positions, indices)
        self.assertEqual(mesh.vertex_count, 6)
        self.assertEqual(mesh.indices.size, 6)
        n0 = mesh.normals[0]
        self.assertTrue(np.allclose(n0, mesh.normals[1]))
        self.assertAlmostEqual(abs(float(n0[2])), 1.0, places=5)


class CameraMatrixTests(unittest.TestCase):
    def test_perspective_flip_y_negates_m11(self):
        normal = perspective(50.0, 16.0 / 9.0, 0.1, 100.0, flip_y=False)
        flipped = perspective(50.0, 16.0 / 9.0, 0.1, 100.0, flip_y=True)
        self.assertAlmostEqual(flipped[1][1], -normal[1][1], places=6)
        self.assertAlmostEqual(flipped[0][0], normal[0][0], places=6)


class OrbitDoesNotRebuildTests(unittest.TestCase):
    def test_orbit_and_render_reuse_uploaded_batches(self):
        from se_render.gl_backend import reset_gl_probe, try_create_context
        from se_render.orientation import identity_mat4
        from se_render.scene_graph import BlockInstance, PreviewScene
        from se_render.viewport import GLPreviewRenderer

        reset_gl_probe()
        ctx = try_create_context()
        if ctx is None:
            self.skipTest("OpenGL 3.3 context is not available")
        ctx.release()

        renderer = GLPreviewRenderer()
        self.addCleanup(renderer.release)
        self.assertTrue(renderer.available)
        block = BlockInstance(
            grid_name="Hull",
            grid_entity_id="1",
            grid_size="Large",
            is_subgrid=False,
            subtype="LargeBlockArmorBlock",
            type_id="CubeBlock",
            entity_id="10",
            min_x=0,
            min_y=0,
            min_z=0,
            forward="Forward",
            up="Up",
            hsv=(0.0, 0.0, 0.0),
            color_rgb=hsv_offset_to_rgb(0.0, 0.0, 0.0),
            skin="None",
            world_matrix=identity_mat4(),
            local_min=(0, 0, 0),
        )
        scene = PreviewScene(blocks=[block], main_grid_name="Hull", total_blocks=1)
        renderer.load(scene)
        generation = renderer.upload_generation
        self.assertGreaterEqual(generation, 1)
        self.assertTrue(renderer._sets["assembled"])
        renderer.camera.orbit(0.2, -0.1)
        renderer.camera.pan(4.0, -3.0)
        renderer.camera.zoom(0.9)
        pixels = renderer.render(320, 240, interactive=True)
        self.assertIsNotNone(pixels)
        self.assertEqual(renderer.upload_generation, generation)
        pixels_full = renderer.render(320, 240, interactive=False)
        self.assertIsNotNone(pixels_full)
        self.assertEqual(renderer.upload_generation, generation)


def _cube(min_xyz, entity="1", grid="Hull", gid="g1", matrix=None) -> BlockInstance:
    x, y, z = min_xyz
    world = matrix if matrix is not None else translation_mat4((x * 2.5, y * 2.5, z * 2.5))
    return BlockInstance(
        grid_name=grid,
        grid_entity_id=gid,
        grid_size="Large",
        is_subgrid=False,
        subtype="LargeBlockArmorBlock",
        type_id="CubeBlock",
        entity_id=entity,
        min_x=x,
        min_y=y,
        min_z=z,
        forward="Forward",
        up="Up",
        hsv=(0.0, 0.0, 0.0),
        color_rgb=hsv_offset_to_rgb(0.0, 0.0, 0.0),
        skin="None",
        world_matrix=world,
        local_min=(x, y, z),
    )


class OccupancyCullingTests(unittest.TestCase):
    def test_two_adjacent_cubes_cull_shared_faces(self):
        from se_assets.cube_catalog import BlockDefinition, CubeBlockCatalog

        catalog = CubeBlockCatalog()
        for subtype in ("LargeBlockArmorBlock",):
            definition = BlockDefinition(
                type_id="CubeBlock",
                subtype_id=subtype,
                cube_size="Large",
                block_topology="Cube",
                cube_topology="Box",
                size_x=1,
                size_y=1,
                size_z=1,
                model_path="",
                model_offset=(0.0, 0.0, 0.0),
            )
            catalog.definitions[definition.key] = definition
            catalog.by_subtype[subtype] = definition
        a = _cube((0, 0, 0), "a")
        b = _cube((1, 0, 0), "b")
        plans = plan_blocks([a, b], catalog)
        self.assertEqual(plans[0].cull_mask & FACE_POS_X, FACE_POS_X)
        self.assertEqual(plans[1].cull_mask & FACE_NEG_X, FACE_NEG_X)
        self.assertEqual(plans[0].cull_mask & FACE_NEG_X, 0)
        self.assertFalse(plans[0].fully_enclosed)
        self.assertFalse(plans[1].fully_enclosed)

    def test_solid_3x3x3_skips_center_and_restores_when_exploded(self):
        from se_assets.cube_catalog import BlockDefinition, CubeBlockCatalog

        catalog = CubeBlockCatalog()
        definition = BlockDefinition(
            type_id="CubeBlock",
            subtype_id="LargeBlockArmorBlock",
            cube_size="Large",
            block_topology="Cube",
            cube_topology="Box",
            size_x=1,
            size_y=1,
            size_z=1,
            model_path="",
            model_offset=(0.0, 0.0, 0.0),
        )
        catalog.definitions[definition.key] = definition
        catalog.by_subtype[definition.subtype_id] = definition
        blocks = [
            _cube((x, y, z), f"{x}{y}{z}")
            for x in range(3)
            for y in range(3)
            for z in range(3)
        ]
        plans = plan_blocks(blocks, catalog)
        center = next(p for b, p in zip(blocks, plans) if b.local_min == (1, 1, 1))
        corner = next(p for b, p in zip(blocks, plans) if b.local_min == (0, 0, 0))
        self.assertTrue(center.fully_enclosed)
        self.assertTrue(is_fully_enclosed({c for p in plans for c in p.cells}, center.cells))
        self.assertFalse(corner.fully_enclosed)
        scene = PreviewScene(blocks=blocks, main_grid_name="Hull", total_blocks=27)
        cpu = build_preview_cpu(scene, catalog)
        self.assertLess(instance_count(cpu.assembled), instance_count(cpu.exploded))
        self.assertEqual(instance_count(cpu.exploded), 27)
        self.assertLess(triangle_count(cpu.assembled), triangle_count(cpu.exploded))
        self.assertEqual(active_preview_set(0.0, False, False, 27), "assembled")
        self.assertLess(instance_count(cpu.assembled), 27)

    def test_slope_hypotenuse_is_not_tagged(self):
        slope = topology_mesh("Slope")
        self.assertTrue(any(int(a) == FACE_NONE for a in slope.face_axes.tolist()))
        self.assertTrue(any(int(a) != FACE_NONE for a in slope.face_axes.tolist()))


class ExplodeOffsetTests(unittest.TestCase):
    def test_explode_moves_outward_from_grid_centroid(self):
        left = _cube((0, 0, 0), "L", matrix=translation_mat4((0.0, 0.0, 0.0)))
        right = _cube((4, 0, 0), "R", matrix=translation_mat4((10.0, 0.0, 0.0)))
        offsets = explode_max_offsets([left, right])
        self.assertLess(offsets[0][0], 0.0)
        self.assertGreater(offsets[1][0], 0.0)
        half = explode_offset((0.0, 0.0, 0.0), (5.0, 0.0, 0.0), 0.5, 8.0)
        full = explode_offset((0.0, 0.0, 0.0), (5.0, 0.0, 0.0), 1.0, 8.0)
        self.assertAlmostEqual(half[0] * 2.0, full[0], places=5)

    def test_child_grid_explodes_around_its_own_centroid(self):
        hull = _cube((0, 0, 0), "h", grid="Hull", gid="1", matrix=translation_mat4((0.0, 0.0, 0.0)))
        child_a = _cube((0, 0, 0), "a", grid="Turret", gid="2", matrix=translation_mat4((40.0, 8.0, 0.0)))
        child_b = _cube((1, 0, 0), "b", grid="Turret", gid="2", matrix=translation_mat4((45.0, 8.0, 0.0)))
        offsets = explode_max_offsets([hull, child_a, child_b])
        # Child blocks should separate from each other, not fly toward world origin.
        self.assertLess(offsets[1][0], 0.0)
        self.assertGreater(offsets[2][0], 0.0)


class LodThresholdTests(unittest.TestCase):
    def test_threshold_skips_only_huge_interactive(self):
        self.assertEqual(HUGE_SHIP_BLOCK_THRESHOLD, 8000)
        self.assertFalse(use_interactive_lod(100, True))
        self.assertFalse(use_interactive_lod(8000, True))
        self.assertTrue(use_interactive_lod(8001, True))
        self.assertFalse(use_interactive_lod(8001, False))

    def test_explode_zero_uses_culled_batch_only(self):
        self.assertEqual(active_preview_set(0.0, False, True, 20000), "assembled")
        self.assertEqual(active_preview_set(0.0, True, True, 20000), "assembled_lod")
        self.assertEqual(active_preview_set(0.5, False, True, 20000), "exploded")
        self.assertEqual(active_preview_set(0.5, True, True, 20000), "exploded_lod")
        self.assertEqual(active_preview_set(0.0, True, False, 20000), "assembled")


class BuildJobAndCatalogPathTests(unittest.TestCase):
    def test_stale_generation_is_ignored(self):
        job = BuildGeneration()
        first = job.begin()
        second = job.begin()
        self.assertFalse(job.is_current(first))
        self.assertTrue(job.is_current(second))
        job.cancel()
        self.assertFalse(job.is_current(second))

    def test_orbit_render_does_not_call_catalog_load(self):
        from se_assets.cube_catalog import CubeBlockCatalog
        from se_render.gl_backend import reset_gl_probe, try_create_context
        from se_render.viewport import GLPreviewRenderer

        reset_gl_probe()
        ctx = try_create_context()
        if ctx is None:
            self.skipTest("OpenGL 3.3 context is not available")
        ctx.release()

        renderer = GLPreviewRenderer()
        self.addCleanup(renderer.release)
        scene = PreviewScene(blocks=[_cube((0, 0, 0))], main_grid_name="Hull", total_blocks=1)
        renderer.load(scene)
        generation = renderer.upload_generation

        def boom(*_a, **_k):
            raise AssertionError("catalog.load must not run on the orbit/draw path")

        original = CubeBlockCatalog.load
        CubeBlockCatalog.load = boom
        try:
            renderer.camera.orbit(0.1, 0.1)
            self.assertIsNotNone(renderer.render(160, 120, interactive=True))
            renderer.explode = 0.4
            self.assertIsNotNone(renderer.render(160, 120, interactive=True))
        finally:
            CubeBlockCatalog.load = original
        self.assertEqual(renderer.upload_generation, generation)


def _catalog_with(*defs):
    from se_assets.cube_catalog import CubeBlockCatalog

    catalog = CubeBlockCatalog()
    for definition in defs:
        catalog.definitions[definition.key] = definition
        catalog.by_subtype[definition.subtype_id] = definition
    return catalog


def _def(type_id, subtype, topology="Box", block_topology="Cube", size=(1, 1, 1)):
    from se_assets.cube_catalog import BlockDefinition

    return BlockDefinition(
        type_id=type_id,
        subtype_id=subtype,
        cube_size="Large",
        block_topology=block_topology,
        cube_topology=topology,
        size_x=size[0],
        size_y=size[1],
        size_z=size[2],
        model_path="",
        model_offset=(0.0, 0.0, 0.0),
    )


def _block(min_xyz, subtype="LargeBlockArmorBlock", type_id="CubeBlock", entity="1", grid="Hull", gid="g1"):
    x, y, z = min_xyz
    return BlockInstance(
        grid_name=grid,
        grid_entity_id=gid,
        grid_size="Large",
        is_subgrid=False,
        subtype=subtype,
        type_id=type_id,
        entity_id=entity,
        min_x=x,
        min_y=y,
        min_z=z,
        forward="Forward",
        up="Up",
        hsv=(0.0, 0.0, 0.0),
        color_rgb=hsv_offset_to_rgb(0.0, 0.0, 0.0),
        skin="None",
        world_matrix=translation_mat4((x * 2.5, y * 2.5, z * 2.5)),
        local_min=(x, y, z),
    )


class SlopeOccupancyTests(unittest.TestCase):
    def test_occupancy_does_not_cull_exposed_slope_hypotenuse(self):
        catalog = _catalog_with(
            _def("CubeBlock", "LargeBlockArmorSlope", "Slope"),
            _def("CubeBlock", "LargeBlockArmorBlock", "Box"),
        )
        slope = _block((0, 0, 0), "LargeBlockArmorSlope", entity="s")
        below = _block((0, -1, 0), "LargeBlockArmorBlock", entity="b")
        plans = plan_blocks([slope, below], catalog)
        mesh = topology_mesh("Slope")
        culled = cull_mesh_faces(mesh, plans[0].cull_mask)
        none_before = sum(1 for a in mesh.face_axes.tolist() if int(a) == FACE_NONE)
        none_after = sum(1 for a in culled.face_axes.tolist() if int(a) == FACE_NONE)
        self.assertGreater(none_before, 0)
        self.assertEqual(none_before, none_after)
        self.assertGreater(culled.triangle_count, 0)

    def test_surrounded_slope_is_not_skipped(self):
        catalog = _catalog_with(
            _def("CubeBlock", "LargeBlockArmorSlope", "Slope"),
            _def("CubeBlock", "LargeBlockArmorBlock", "Box"),
        )
        slope_def = catalog.get("CubeBlock", "LargeBlockArmorSlope")
        self.assertFalse(is_solid_box(slope_def))
        blocks = []
        for x in range(3):
            for y in range(3):
                for z in range(3):
                    if (x, y, z) == (1, 1, 1):
                        blocks.append(_block((x, y, z), "LargeBlockArmorSlope", entity="slope"))
                    else:
                        blocks.append(_block((x, y, z), entity=f"{x}{y}{z}"))
        plans = plan_blocks(blocks, catalog)
        center = next(p for b, p in zip(blocks, plans) if b.subtype == "LargeBlockArmorSlope")
        self.assertFalse(center.fully_enclosed)
        scene = PreviewScene(blocks=blocks, main_grid_name="Hull", total_blocks=27)
        cpu = build_preview_cpu(scene, catalog)
        slope_index = next(i for i, b in enumerate(blocks) if b.subtype == "LargeBlockArmorSlope")
        assembled_ids = [int(i) for batch in cpu.assembled for i in batch.instance_ids.tolist()]
        self.assertIn(slope_index, assembled_ids)
        self.assertEqual(instance_count(cpu.exploded), 27)


class LodKeepsTopologyTests(unittest.TestCase):
    def test_lod_does_not_replace_slope_with_box(self):
        from se_assets.mesh_cache import MeshLibrary

        library = MeshLibrary(None)
        slope_def = _def("CubeBlock", "LargeBlockArmorSlope", "Slope")
        box_def = _def("CubeBlock", "LargeBlockArmorBlock", "Box")
        full = library.mesh_for(slope_def, lod=False)
        lod = library.mesh_for(slope_def, lod=True)
        boxed = library.mesh_for(box_def, lod=True)
        prefer = library.mesh_for(slope_def, prefer_box=True)
        self.assertEqual(full.triangle_count, lod.triangle_count)
        self.assertEqual(full.triangle_count, prefer.triangle_count)
        self.assertNotEqual(lod.triangle_count, boxed.triangle_count)
        self.assertGreater(lod.triangle_count, 0)

    def test_simplify_mesh_keeps_largest_triangles(self):
        box = topology_mesh("Box")
        simple = simplify_mesh(box, max_triangles=8)
        self.assertLessEqual(simple.triangle_count, 8)
        self.assertGreater(simple.triangle_count, 0)


class OrbitCameraMathTests(unittest.TestCase):
    def test_zoom_toward_slides_pivot_inward(self):
        before = (0.0, 0.0, 0.0)
        point = (10.0, 0.0, 0.0)
        after = zoom_toward_target(before, point, 0.8)
        self.assertGreater(after[0], 0.0)
        self.assertLess(after[0], 10.0)
        self.assertAlmostEqual(after[1], 0.0, places=5)
        cam = OrbitCamera()
        cam.target = [0.0, 0.0, 0.0]
        cam.distance = 40.0
        cam.zoom_toward(0.8, (10.0, 0.0, 0.0))
        self.assertLess(cam.distance, 40.0)
        self.assertGreater(cam.target[0], 0.0)
        inward = zoom_factor_for_distance(8.0, True)
        far = zoom_factor_for_distance(800.0, True)
        self.assertLess(inward, 1.0)
        self.assertGreater(inward, far)

    def test_frame_selection_keeps_yaw_and_clamps_pitch(self):
        cam = OrbitCamera()
        cam.yaw = 1.1
        cam.pitch = 0.2
        cam.frame_selection((5.0, 1.0, -2.0), 2.0)
        self.assertAlmostEqual(cam.yaw, 1.1, places=5)
        self.assertAlmostEqual(cam.pitch, 0.2, places=5)
        self.assertAlmostEqual(cam.target[0], 5.0, places=5)
        cam.orbit(0.0, 40.0)
        self.assertLessEqual(cam.pitch, 1.2)
        cam.orbit(0.0, -40.0)
        self.assertGreaterEqual(cam.pitch, -1.2)

    def test_pan_is_distance_scaled(self):
        near = OrbitCamera()
        far = OrbitCamera()
        near.distance = 10.0
        far.distance = 200.0
        near.pan(20.0, 0.0)
        far.pan(20.0, 0.0)
        near_move = abs(near.target[0]) + abs(near.target[2])
        far_move = abs(far.target[0]) + abs(far.target[2])
        self.assertGreater(far_move, near_move * 5.0)


class CameraClipTests(unittest.TestCase):
    def test_clip_planes_from_aabb_are_tight(self):
        near, far = clip_planes_from_aabb((0.0, 0.0, 50.0), (-10.0, -10.0, -10.0), (10.0, 10.0, 10.0))
        self.assertGreater(near, 0.1)
        self.assertLess(near, 50.0)
        self.assertGreater(far, 50.0)
        self.assertLess(far / near, 40.0)

    def test_huge_ship_clip_ratio_stays_usable(self):
        near, far = clip_planes_for_view(400.0, 150.0)
        self.assertGreater(near, 10.0)
        self.assertLess(far / near, 12.0)
        self.assertGreater(far, 400.0)

    def test_stale_origin_aabb_does_not_clip_framed_hull(self):
        eye = (172.0, 96.0, 142.0)
        target = (61.25, 23.75, 11.25)
        radius = 70.0
        near, far = clip_planes_from_aabb(
            eye,
            (-1.0, -1.0, -1.0),
            (1.0, 1.0, 1.0),
            target=target,
            radius=radius,
        )
        dist = ((eye[0] - target[0]) ** 2 + (eye[1] - target[1]) ** 2 + (eye[2] - target[2]) ** 2) ** 0.5
        self.assertLess(near, dist - radius * 0.5)
        self.assertGreater(far, dist + radius * 0.5)


def _offset_len(offset):
    return (offset[0] ** 2 + offset[1] ** 2 + offset[2] ** 2) ** 0.5


class DissectModelTests(unittest.TestCase):
    def test_peel_opens_stick_ends_along_long_axis(self):
        blocks = [_cube((x, 0, 0), str(x)) for x in range(9)]
        peel = peel_max_offsets(blocks)
        self.assertLess(peel[0][0], -0.5)
        self.assertGreater(peel[8][0], 0.5)
        self.assertGreater(abs(peel[0][0]), abs(peel[4][0]))
        self.assertGreater(abs(peel[8][0]), abs(peel[4][0]))
        self.assertLess(abs(peel[4][0]), 0.35)

    def test_functional_explode_weight_is_below_armor(self):
        self.assertGreaterEqual(FUNCTIONAL_EXPLODE_WEIGHT, 0.1)
        self.assertLessEqual(FUNCTIONAL_EXPLODE_WEIGHT, 0.25)
        self.assertLess(FUNCTIONAL_EXPLODE_WEIGHT, ARMOR_EXPLODE_WEIGHT)
        armor = [_cube((x, 0, 0), str(x)) for x in range(4)]
        gyro = _block((4, 0, 0), "LargeBlockGyro", "Gyro", entity="g")
        peel = peel_max_offsets(armor + [gyro])
        self.assertLess(_offset_len(peel[4]), _offset_len(peel[0]) * 0.45)
        self.assertGreater(_offset_len(peel[0]), _offset_len(peel[4]))

    def test_functional_cluster_shares_one_offset(self):
        gyros = [
            _block((x, 0, 0), "LargeBlockGyro", "Gyro", entity=str(x))
            for x in range(3)
        ]
        peel = peel_max_offsets(gyros)
        self.assertAlmostEqual(peel[0][0], peel[1][0], places=5)
        self.assertAlmostEqual(peel[1][0], peel[2][0], places=5)

    def test_deck_offsets_differ_on_one_axis(self):
        blocks = [
            _cube((x, y, z), f"{x}{y}{z}")
            for x in range(4)
            for y in range(3)
            for z in range(2)
        ]
        decks = deck_max_offsets(blocks)
        by_y = {}
        for block, offset in zip(blocks, decks):
            by_y.setdefault(block.local_min[1], []).append(offset)
            self.assertAlmostEqual(offset[0], 0.0, places=5)
            self.assertAlmostEqual(offset[2], 0.0, places=5)
        self.assertEqual(len(by_y), 3)
        for layer_offsets in by_y.values():
            first = layer_offsets[0]
            for other in layer_offsets[1:]:
                self.assertAlmostEqual(other[1], first[1], places=5)
        ys = sorted(by_y)
        self.assertNotAlmostEqual(by_y[ys[0]][0][1], by_y[ys[-1]][0][1], places=5)

    def test_radial_opens_stick_ends_locally(self):
        blocks = [_cube((x, 0, 0), str(x)) for x in range(9)]
        radial = radial_max_offsets(blocks)
        self.assertEqual(len(radial), 9)
        end_open = abs(radial[0][0] - radial[1][0])
        mid_shift = abs(radial[0][0] - radial[4][0])
        self.assertGreater(end_open, 1.5)
        self.assertGreater(end_open, mid_shift * 0.12)
        tail_open = abs(radial[8][0] - radial[7][0])
        self.assertGreater(tail_open, 1.5)
        center = (10.0, 0.0, 0.0)
        far = (20.0, 0.0, 0.0)
        outward = (
            radial[8][0] * (far[0] - center[0])
            + radial[8][1] * (far[1] - center[1])
            + radial[8][2] * (far[2] - center[2])
        )
        self.assertGreater(outward, 0.0)
        self.assertEqual(dissect_max_offsets(blocks, DISSECT_RADIAL), radial)

    def test_radial_end_trio_on_slab_not_rigid(self):
        blocks = [
            _cube((x, y, 0), f"{x}{y}")
            for x in range(15)
            for y in range(3)
        ]
        radial = radial_max_offsets(blocks)
        end = [radial[i] for i, b in enumerate(blocks) if b.local_min[0] == 0]
        self.assertEqual(len(end), 3)
        spread = max(_offset_len((a[0] - b[0], a[1] - b[1], a[2] - b[2])) for a in end for b in end)
        self.assertGreater(spread, 1.0)

    def test_radial_functional_weight_and_child_grid(self):
        armor = [_cube((x, 0, 0), str(x)) for x in range(4)]
        gyro = _block((4, 0, 0), "LargeBlockGyro", "Gyro", entity="g")
        radial = radial_max_offsets(armor + [gyro])
        self.assertLess(_offset_len(radial[4]), _offset_len(radial[0]) * 0.45)
        hull = _cube((0, 0, 0), "h", grid="Hull", gid="1", matrix=translation_mat4((0.0, 0.0, 0.0)))
        child_a = _cube((0, 0, 0), "a", grid="Turret", gid="2", matrix=translation_mat4((40.0, 8.0, 0.0)))
        child_b = _cube((1, 0, 0), "b", grid="Turret", gid="2", matrix=translation_mat4((45.0, 8.0, 0.0)))
        child = radial_max_offsets([hull, child_a, child_b])
        self.assertLess(child[1][0], 0.0)
        self.assertGreater(child[2][0], 0.0)

    def test_occupancy_outer_layer_leaves_3x3x3_center(self):
        occupied = {(x, y, z) for x in range(3) for y in range(3) for z in range(3)}
        layers = occupancy_shell_layers(occupied)
        self.assertEqual(layers[(1, 1, 1)], 1)
        self.assertEqual(layers[(0, 0, 0)], 0)
        remaining = {cell for cell, layer in layers.items() if layer >= 1}
        self.assertEqual(remaining, {(1, 1, 1)})
        center_cells = occupied_cells((1, 1, 1), (1, 1, 1))
        self.assertEqual(block_shell_layer(center_cells, layers), 1)

    def test_child_grid_peel_is_local(self):
        hull = _cube((0, 0, 0), "h", grid="Hull", gid="1", matrix=translation_mat4((0.0, 0.0, 0.0)))
        child_a = _cube((0, 0, 0), "a", grid="Turret", gid="2", matrix=translation_mat4((40.0, 8.0, 0.0)))
        child_b = _cube((1, 0, 0), "b", grid="Turret", gid="2", matrix=translation_mat4((45.0, 8.0, 0.0)))
        peel = peel_max_offsets([hull, child_a, child_b])
        self.assertLess(peel[1][0], 0.0)
        self.assertGreater(peel[2][0], 0.0)

    def test_pick_identity_and_caption(self):
        rec = PickRecord(
            instance_id=7,
            grid_name="Hull",
            subtype="LargeBlockGyro",
            center=(3.0, 1.0, 2.0),
            aabb_min=(2.0, 0.0, 1.0),
            aabb_max=(4.0, 2.0, 3.0),
            explode_offset=(1.0, 0.0, 0.0),
            type_id="Gyro",
            entity_id="99",
            grid_entity_id="g1",
            local_min=(3, 1, 2),
            is_armor=False,
            explode_peel=(1.0, 0.0, 0.0),
            explode_decks=(0.0, 2.0, 0.0),
            explode_radial=(3.0, 0.0, 0.0),
        )
        self.assertEqual(pick_identity(rec), ("g1", (3, 1, 2), "99"))
        self.assertEqual(rec.identity(), ("g1", (3, 1, 2), "99"))
        caption = selection_caption(rec)
        self.assertIn("Gyro", caption)
        self.assertIn("LargeBlockGyro", caption)
        self.assertIn("3", caption)
        meta = selection_meta(rec)
        self.assertEqual(meta["local_min"], (3, 1, 2))
        self.assertEqual(meta["instance_id"], 7)
        self.assertEqual(rec.offset_for_mode(DISSECT_DECKS)[1], 2.0)
        self.assertEqual(rec.offset_for_mode(DISSECT_RADIAL)[0], 3.0)
        self.assertEqual(rec.offset_for_mode(DISSECT_PEEL)[0], 1.0)

    def test_cpu_scene_stores_three_offset_channels(self):
        catalog = _catalog_with(_def("CubeBlock", "LargeBlockArmorBlock", "Box"))
        blocks = [_cube((x, 0, 0), str(x)) for x in range(5)]
        scene = PreviewScene(blocks=blocks, main_grid_name="Hull", total_blocks=5)
        cpu = build_preview_cpu(scene, catalog)
        apply_dissect_mode(cpu, DISSECT_PEEL, catalog)
        apply_dissect_mode(cpu, DISSECT_RADIAL, catalog)
        batch = cpu.exploded[0]
        self.assertEqual(batch.explode_peel.shape[1], 3)
        self.assertEqual(batch.explode_decks.shape[1], 3)
        self.assertEqual(batch.explode_radial.shape[1], 3)
        self.assertTrue(np.allclose(batch.explode, batch.explode_peel))
        self.assertFalse(np.allclose(batch.explode_peel, batch.explode_radial))
        self.assertEqual(len(cpu.picks), 5)
        self.assertEqual(cpu.picks[0].identity()[1], blocks[0].local_min)
        self.assertIn(DISSECT_PEEL, cpu.dissect_modes)
        self.assertIn(DISSECT_RADIAL, cpu.dissect_modes)


class TwoPassBatchTests(unittest.TestCase):
    def test_armor_and_functional_are_separate_batches(self):
        catalog = _catalog_with(
            _def("CubeBlock", "LargeBlockArmorBlock", "Box"),
            _def("Gyro", "LargeBlockGyro", "Box", "TriangleMesh", (1, 1, 1)),
        )
        armor = _block((0, 0, 0), entity="a")
        gyro = _block((2, 0, 0), "LargeBlockGyro", "Gyro", entity="g")
        scene = PreviewScene(blocks=[armor, gyro], main_grid_name="Hull", total_blocks=2)
        cpu = build_preview_cpu(scene, catalog)
        kinds = {batch.kind for batch in cpu.assembled}
        self.assertIn("armor", kinds)
        self.assertIn("functional", kinds)
        armor_idx = next(i for i, b in enumerate(cpu.assembled) if b.kind == "armor")
        func_idx = next(i for i, b in enumerate(cpu.assembled) if b.kind == "functional")
        self.assertLess(armor_idx, func_idx)


class SparseOccupancyTests(unittest.TestCase):
    def test_far_apart_blocks_do_not_allocate_dense_volume(self):
        occupied = {(0, 0, 0), (400, 400, 400)}
        volume = occupancy_padded_volume(occupied)
        self.assertGreater(volume, 1_000_000)
        started = time.perf_counter()
        layers = occupancy_shell_layers(occupied)
        elapsed = time.perf_counter() - started
        self.assertLess(elapsed, 0.25)
        self.assertEqual(len(layers), 2)
        self.assertEqual(layers[(0, 0, 0)], 0)
        self.assertEqual(layers[(400, 400, 400)], 0)


class ProgressiveBuildTests(unittest.TestCase):
    def test_shell_pass_16k_box_armor_is_nonempty(self):
        catalog = _catalog_with(_def("CubeBlock", "LargeBlockArmorBlock", "Box"))
        # 32×32×16 = 16,384 — large-grid scale without a real blueprint.
        blocks = [
            _cube((x, y, z), f"{x}-{y}-{z}")
            for x in range(32)
            for y in range(32)
            for z in range(16)
        ]
        scene = PreviewScene(blocks=blocks, main_grid_name="Hull", total_blocks=len(blocks))
        started = time.perf_counter()
        cpu = build_preview_cpu(scene, catalog, stage=STAGE_SHELL)
        elapsed = time.perf_counter() - started
        self.assertGreater(len(cpu.assembled), 0)
        self.assertGreater(instance_count(cpu.assembled), 0)
        self.assertEqual(cpu.stage, STAGE_SHELL)
        self.assertGreater(cpu.shown_count, 10)
        self.assertFalse(cpu.exploded)
        self.assertEqual(cpu.dissect_modes, [])
        # Generous ceiling so CI still passes; catches O(n²) regressions.
        self.assertLess(elapsed, 8.0, f"16k shell took {elapsed:.2f}s")

    def test_simplified_caption_reports_n_of_m(self):
        self.assertEqual(
            format_preview_count_caption(12400, 16200, simplified=True),
            "3D 12,400 of 16,200 — simplified",
        )
        self.assertEqual(
            format_preview_count_caption(16200, 16200, simplified=False),
            "16,200 blocks  ·  3D preview",
        )
        self.assertIn("of", format_preview_count_caption(6157, 13929, simplified=False))


class WheelZoomHelperTests(unittest.TestCase):
    def test_wheel_delta_windows_and_x11(self):
        self.assertTrue(wheel_zoom_inward(delta=120))
        self.assertFalse(wheel_zoom_inward(delta=-120))
        self.assertTrue(wheel_zoom_inward(button=4))
        self.assertFalse(wheel_zoom_inward(button=5))
        self.assertIsNone(wheel_zoom_inward(delta=0))
        self.assertIsNone(wheel_zoom_inward(delta=None, button=None))
        inward = zoom_factor_for_distance(40.0, True)
        outward = zoom_factor_for_distance(40.0, False)
        self.assertLess(inward, 1.0)
        self.assertGreater(outward, 1.0)


class ArmorAlbedoFloorTests(unittest.TestCase):
    def test_unpainted_armor_is_lighter_than_navy_clear(self):
        style = block_material("CubeBlock", "LargeBlockArmorBlock")
        lifted = apply_albedo_tint(hsv_offset_to_rgb(0.0, 0.0, 0.0), style)
        lum = 0.30 * lifted[0] + 0.54 * lifted[1] + 0.16 * lifted[2]
        clear = 0.30 * PREVIEW_CLEAR_COLOR[0] + 0.54 * PREVIEW_CLEAR_COLOR[1] + 0.16 * PREVIEW_CLEAR_COLOR[2]
        self.assertGreaterEqual(lum, ARMOR_ALBEDO_FLOOR)
        self.assertGreater(lum, clear * 2.5)
        black = apply_albedo_tint((0.0, 0.0, 0.0), style)
        black_lum = 0.30 * black[0] + 0.54 * black[1] + 0.16 * black[2]
        self.assertGreaterEqual(black_lum, ARMOR_ALBEDO_FLOOR)


class LargeGridHullVisibilityTests(unittest.TestCase):
    def test_shell_pass_50x20x10_hull_fills_and_fits(self):
        catalog = _catalog_with(_def("CubeBlock", "LargeBlockArmorBlock", "Box"))
        blocks = []
        for x in range(50):
            for y in range(20):
                for z in range(10):
                    if x in (0, 49) or y in (0, 19) or z in (0, 9):
                        blocks.append(_cube((x, y, z), f"{x}-{y}-{z}"))
        scene = PreviewScene(blocks=blocks, main_grid_name="Hull", total_blocks=len(blocks))
        cpu = build_preview_cpu(scene, catalog, stage=STAGE_SHELL)
        self.assertGreater(cpu.shown_count, 10)
        self.assertGreater(cpu.shown_count, 0.05 * len(blocks))
        extent = (
            cpu.aabb_max[0] - cpu.aabb_min[0],
            cpu.aabb_max[1] - cpu.aabb_min[1],
            cpu.aabb_max[2] - cpu.aabb_min[2],
        )
        self.assertGreater(extent[0], 50 * 2.5 * 0.7)
        cam = OrbitCamera()
        cam.frame(cpu.center, cpu.radius)
        self.assertGreater(cam.distance, cpu.radius)
        self.assertGreater(cam.distance, fit_distance(cpu.radius) * 0.9)

    def test_hollow_10x10x10_keeps_majority_of_exterior_faces(self):
        catalog = _catalog_with(_def("CubeBlock", "LargeBlockArmorBlock", "Box"))
        blocks = []
        occupied = set()
        for x in range(10):
            for y in range(10):
                for z in range(10):
                    if x in (0, 9) or y in (0, 9) or z in (0, 9):
                        blocks.append(_cube((x, y, z), f"{x}-{y}-{z}"))
                        occupied.add((x, y, z))
        plans = plan_blocks(blocks, catalog)
        exterior = occupied_exterior_face_count(occupied)
        visible = plan_visible_face_count(plans)
        self.assertGreater(exterior, 0)
        self.assertGreaterEqual(visible, 0.5 * exterior)
        scene = PreviewScene(blocks=blocks, main_grid_name="Hull", total_blocks=len(blocks))
        cpu = build_preview_cpu(scene, catalog, stage=STAGE_SHELL)
        self.assertGreater(cpu.shown_count, 0.5 * len(blocks))


if __name__ == "__main__":
    unittest.main()

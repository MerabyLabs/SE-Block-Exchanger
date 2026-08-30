import inspect
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np

from app_settings import AppSettings, SettingsStore
from blueprint_document import (
    BlueprintDocumentCache,
    CancelledError,
    JobToken,
    build_ready_applies,
    subgrids_ui_applies,
)
from se_assets.cube_catalog import BlockDefinition, CubeBlockCatalog
from se_assets.mesh_cache import MeshLibrary
from se_render.dissection import DISSECT_DECKS, DISSECT_PEEL, DISSECT_RADIAL, radial_combine_offsets
from se_render.occupancy import build_occupancy
from se_render.preview_build import (
    STAGE_FULL,
    STAGE_SHELL,
    BuildGeneration,
    CpuBatch,
    PreviewCpuCache,
    PreviewCpuScene,
    apply_dissect_mode,
    build_preview_cpu,
    copy_cpu_for_dissect,
    cpu_cache_key,
    pending_mwm_definitions,
    pending_mwm_patches,
    split_batches_for_upload,
)
from se_render.preview_style import (
    fallback_banner_text,
    mwm_progress_caption,
    should_defer_catalog_box_build,
    staged_3d_caption,
)
from se_render.scene_graph import PreviewScene, extract_scene_from_root
from tests.test_preview_render import _block, _catalog_with, _cube, _def
from tests.test_scene_graph import ROTOR_BLUEPRINT
from tests.test_blueprint_document import _write_ship
from ui.preview_panel import PreviewPanel
from ui.widgets.ship_preview import ShipPreviewHost


class StalePublishTests(unittest.TestCase):
    def test_switch_a_b_c_cannot_publish_stale_ui(self):
        published = []

        class Panel:
            def __init__(self):
                self.generation = 0
                self.path = None

            def begin_switch(self, path):
                self.generation += 1
                self.path = Path(path)
                return self.generation

            def publish(self, path, payload, generation):
                if not subgrids_ui_applies(self.generation, generation, self.path, path):
                    return
                published.append(payload)

        panel = Panel()
        gen_a = panel.begin_switch("/ships/A")
        gen_b = panel.begin_switch("/ships/B")
        gen_c = panel.begin_switch("/ships/C")
        panel.publish("/ships/A", "A", gen_a)
        panel.publish("/ships/B", "B", gen_b)
        panel.publish("/ships/C", "C", gen_c)
        self.assertEqual(published, ["C"])

    def test_switch_a_b_c_cannot_publish_stale_3d(self):
        job = BuildGeneration()
        gen_a = job.begin()
        gen_b = job.begin()
        gen_c = job.begin()
        published = []

        def on_ready(generation, name):
            if not build_ready_applies(job, generation):
                return
            published.append(name)

        on_ready(gen_a, "A")
        on_ready(gen_b, "B")
        on_ready(gen_c, "C")
        self.assertEqual(published, ["C"])

    def test_build_ready_rejects_invalid_install(self):
        job = BuildGeneration()
        gen = job.begin()
        self.assertFalse(build_ready_applies(job, gen, install_valid=False))
        self.assertTrue(build_ready_applies(job, gen, install_valid=True))


class CancelTokenTests(unittest.TestCase):
    def test_cancel_stops_extract_and_document_load(self):
        token = JobToken()
        generation = token.begin()
        token.cancel()
        root = ET.fromstring(ROTOR_BLUEPRINT)
        with self.assertRaises(CancelledError):
            extract_scene_from_root(root, token=token, generation=generation)
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "A"
            _write_ship(folder, 8)
            cache = BlueprintDocumentCache()
            with self.assertRaises(CancelledError):
                cache.get_or_load(folder, token=token, generation=generation)
            self.assertIsNone(cache.get(folder))

    def test_cancel_token_stops_old_cpu_build(self):
        job = BuildGeneration()
        generation = job.begin()
        job.cancel()
        blocks = [_block((i, 0, 0), entity=str(i)) for i in range(64)]
        cpu = build_preview_cpu(
            PreviewScene(blocks=blocks, total_blocks=len(blocks)),
            generation=generation,
            stage=STAGE_SHELL,
            cancel=job,
        )
        self.assertEqual(cpu.assembled, [])
        self.assertEqual(cpu.shown_count, 0)

    def test_occupancy_cancel_stops_mid_loop(self):
        calls = {"n": 0}

        def cancel():
            calls["n"] += 1
            return calls["n"] > 1

        blocks = [_block((i, 0, 0), entity=str(i)) for i in range(300)]
        occupied = build_occupancy(blocks, cancel=cancel)
        self.assertEqual(occupied, {})
        self.assertGreater(calls["n"], 1)


class HonestCaptionTests(unittest.TestCase):
    def test_staged_captions_are_honest(self):
        self.assertEqual(staged_3d_caption(catalog_wait=True), "Loading 3D…  ·  indexing game files")
        self.assertEqual(
            staged_3d_caption(switching=True, mesh_ready=False, ship_name="Hull"),
            "Loading 3D…  ·  Hull",
        )
        self.assertEqual(
            staged_3d_caption(building=True, mesh_ready=False),
            "Loading 3D…  ·  Indexed",
        )
        self.assertEqual(
            staged_3d_caption(
                building=True,
                mesh_ready=False,
                stage="shell",
                shown=1200,
                total=16000,
            ),
            "Loading 3D…  ·  shell 1,200 of 16,000",
        )
        self.assertIn("Shell 1,200 of 16,000", staged_3d_caption(stage="shell", shown=1200, total=16000, mesh_ready=True))
        self.assertIn("Models", staged_3d_caption(stage="meshes", shown=800, total=16000, mesh_ready=True))
        interior = staged_3d_caption(
            stage="full",
            shown=16000,
            total=16000,
            mesh_ready=True,
            refining=True,
        )
        self.assertIn("Interior", interior)
        self.assertIn("refining", interior)
        isolated = staged_3d_caption(
            mesh_ready=True,
            isolated_name="RotorHead",
            isolated_count=12,
        )
        self.assertIn("RotorHead", isolated)
        self.assertIn("12", isolated)

    def test_mwm_caption_distinguishes_cached_mesh_from_patched_instances(self):
        self.assertEqual(
            mwm_progress_caption(mesh_cached=False, done=1, total=3),
            "Decoding models 1 of 3",
        )
        self.assertEqual(
            mwm_progress_caption(mesh_cached=True, done=2, total=4),
            "Patched models 2 of 4",
        )
        cached = staged_3d_caption(
            stage="meshes",
            mesh_ready=True,
            mwm_cached=True,
            mwm_done=2,
            mwm_total=4,
        )
        decoding = staged_3d_caption(
            stage="meshes",
            mesh_ready=True,
            mwm_cached=False,
            mwm_done=1,
            mwm_total=3,
        )
        self.assertIn("Patched models 2 of 4", cached)
        self.assertIn("Decoding models 1 of 3", decoding)

    def test_fallback_banner_distinguishes_clear_from_missing(self):
        cleared = fallback_banner_text(cleared=True, install_valid=False)
        missing = fallback_banner_text(cleared=False, install_valid=False)
        self.assertIn("cleared", cleared.lower())
        self.assertNotIn("cleared", missing.lower())
        self.assertIn("not found", missing.lower())
        using = fallback_banner_text(cleared=False, install_valid=True, path_text="C:/SE")
        self.assertIn("C:/SE", using)

    def test_no_throwaway_box_build_while_catalog_in_flight(self):
        self.assertTrue(should_defer_catalog_box_build(None, True))
        self.assertFalse(should_defer_catalog_box_build(None, False))
        self.assertFalse(should_defer_catalog_box_build(object(), True))


class NoBindAllTests(unittest.TestCase):
    def test_preview_modules_do_not_call_bind_all(self):
        from ui.widgets.ship_preview import ShipPreviewHost

        grab = inspect.getsource(ShipPreviewHost._grab_wheel)
        release = inspect.getsource(ShipPreviewHost._maybe_release_wheel)
        destroy = inspect.getsource(ShipPreviewHost.destroy)
        self.assertNotIn("self.bind_all", grab)
        self.assertNotIn(".bind_all(", grab)
        self.assertNotIn("self.bind_all", release)
        self.assertNotIn("self.unbind_all", destroy)
        for rel in (
            "ui/widgets/ship_preview.py",
            "ui/widgets/ship_canvas.py",
            "ui/preview_panel.py",
        ):
            text = Path(rel).read_text(encoding="utf-8")
            self.assertNotIn(".bind_all(", text)
            self.assertNotIn("bind_all(", text.replace("Never call CTk bind_all.", ""))


def _cpu_batch(n: int, extra_mesh_bytes: int = 0) -> CpuBatch:
    mesh_n = max(3, extra_mesh_bytes // 12)
    return CpuBatch(
        positions=np.zeros((mesh_n, 3), dtype=np.float32),
        normals=np.zeros((mesh_n, 3), dtype=np.float32),
        uvs=np.zeros((mesh_n, 2), dtype=np.float32),
        indices=np.array([0, 1, 2], dtype=np.uint32),
        models=np.zeros((n, 16), dtype=np.float32),
        colors=np.zeros((n, 3), dtype=np.float32),
        params=np.zeros((n, 3), dtype=np.float32),
        explode=np.zeros((n, 3), dtype=np.float32),
        instance_ids=np.arange(n, dtype=np.float32),
        grid_names=["Hull"] * n,
        accents=np.zeros((n, 3), dtype=np.float32),
        explode_peel=np.zeros((n, 3), dtype=np.float32),
        explode_decks=np.zeros((n, 3), dtype=np.float32),
        explode_radial=np.zeros((n, 3), dtype=np.float32),
        inspect=np.zeros((n, 3), dtype=np.float32),
        grid_entity_ids=["g1"] * n,
    )


def _python_radial_combine(global_off, stretch, peel_off, station_off, neigh_off, weight):
    out = []
    for i, w in enumerate(weight):
        out.append((
            (global_off[i][0] + stretch[i][0] + peel_off[i][0] + station_off[i][0] + neigh_off[i][0]) * w,
            (global_off[i][1] + stretch[i][1] + peel_off[i][1] + station_off[i][1] + neigh_off[i][1]) * w,
            (global_off[i][2] + stretch[i][2] + peel_off[i][2] + station_off[i][2] + neigh_off[i][2]) * w,
        ))
    return np.asarray(out, dtype=np.float64)


class CpuSceneCacheTests(unittest.TestCase):
    def test_a_b_a_hits_without_rebuild_and_third_ship_evicts(self):
        cache = PreviewCpuCache(max_entries=2)
        cpu_a = PreviewCpuScene(stage=STAGE_FULL, shown_count=1)
        cpu_b = PreviewCpuScene(stage=STAGE_FULL, shown_count=2)
        cpu_c = PreviewCpuScene(stage=STAGE_FULL, shown_count=3)
        cache.put(cpu_cache_key("A", 10, 1, STAGE_FULL), cpu_a)
        cache.put(cpu_cache_key("B", 10, 1, STAGE_FULL), cpu_b)
        self.assertIs(cache.get_best("A", 10, 1), cpu_a)
        self.assertIs(cache.get_best("B", 10, 1), cpu_b)
        cache.put(cpu_cache_key("C", 10, 1, STAGE_FULL), cpu_c)
        self.assertIsNone(cache.get_best("A", 10, 1))
        self.assertIs(cache.get_best("B", 10, 1), cpu_b)
        self.assertIs(cache.get_best("C", 10, 1), cpu_c)

    def test_same_ship_full_replaces_shell_so_peer_stays(self):
        cache = PreviewCpuCache(max_entries=2)
        cpu_a = PreviewCpuScene(stage=STAGE_FULL, shown_count=8)
        cpu_b_shell = PreviewCpuScene(stage=STAGE_SHELL, shown_count=4)
        cpu_b_full = PreviewCpuScene(stage=STAGE_FULL, shown_count=9)
        cache.put(cpu_cache_key("A", 1, 0, STAGE_FULL), cpu_a)
        cache.put(cpu_cache_key("B", 1, 0, STAGE_SHELL), cpu_b_shell)
        cache.put(cpu_cache_key("B", 1, 0, STAGE_FULL), cpu_b_full)
        self.assertIs(cache.get_best("A", 1, 0), cpu_a)
        self.assertIs(cache.get_best("B", 1, 0), cpu_b_full)
        self.assertIsNone(cache.get(cpu_cache_key("B", 1, 0, STAGE_SHELL)))

    def test_mtime_or_catalog_gen_misses(self):
        cache = PreviewCpuCache(max_entries=2)
        cpu = PreviewCpuScene(stage=STAGE_FULL)
        cache.put(cpu_cache_key("A", 1, 0, STAGE_FULL), cpu)
        self.assertIsNone(cache.get_best("A", 2, 0))
        self.assertIsNone(cache.get_best("A", 1, 1))

    def test_clear_drops_display_not_cpu_cache(self):
        src = inspect.getsource(ShipPreviewHost.clear)
        self.assertNotIn("_cpu_cache", src)
        self.assertNotIn("invalidate", src)
        start = inspect.getsource(ShipPreviewHost._start_build)
        self.assertIn("get_best", start)
        self.assertIn("build_preview_cpu", start)


class DissectHandoffTests(unittest.TestCase):
    def test_fast_peel_radial_decks_publishes_only_decks(self):
        job = BuildGeneration()
        published = []

        def on_ready(dissect_gen, mode):
            if not job.is_current(dissect_gen):
                return
            published.append(mode)

        peel = job.begin()
        radial = job.begin()
        decks = job.begin()
        on_ready(radial, DISSECT_RADIAL)
        on_ready(peel, DISSECT_PEEL)
        on_ready(decks, DISSECT_DECKS)
        self.assertEqual(published, [DISSECT_DECKS])

    def test_copy_and_apply_do_not_mutate_live_cpu(self):
        catalog = _catalog_with(_def("CubeBlock", "LargeBlockArmorBlock", "Box"))
        blocks = [_cube((x, 0, 0), str(x)) for x in range(5)]
        live = build_preview_cpu(PreviewScene(blocks=blocks, main_grid_name="Hull", total_blocks=5), catalog)
        before = np.array(live.assembled[0].explode, copy=True)
        working = copy_cpu_for_dissect(live)
        apply_dissect_mode(working, DISSECT_PEEL, catalog)
        self.assertIsNot(working, live)
        self.assertIsNot(working.assembled[0], live.assembled[0])
        self.assertTrue(np.allclose(live.assembled[0].explode, before))
        self.assertNotIn(DISSECT_PEEL, live.dissect_modes)
        self.assertIn(DISSECT_PEEL, working.dissect_modes)
        working.assembled[0].explode[0] = (9.0, 9.0, 9.0)
        self.assertFalse(np.allclose(live.assembled[0].explode[0], (9.0, 9.0, 9.0)))

    def test_dissect_and_interior_workers_copy_before_touching_cpu(self):
        dissect = inspect.getsource(ShipPreviewHost._start_dissect_prepare)
        self.assertIn("copy_cpu_for_dissect", dissect)
        self.assertIn("self._dissect_job.begin()", dissect)
        interior = inspect.getsource(ShipPreviewHost._start_interior_fill)
        self.assertIn("copy_cpu_for_dissect", interior)
        ready = inspect.getsource(ShipPreviewHost._on_dissect_ready)
        self.assertIn("is_current", ready)
        self.assertLess(ready.find("is_current"), ready.find("self._cpu_scene = cpu"))


class MwmPatchVsCacheTests(unittest.TestCase):
    def test_cached_library_mesh_still_needs_instance_patch(self):
        defn = BlockDefinition(
            type_id="MyObjectBuilder_Thrust",
            subtype_id="LargeBlockSmallThrust",
            cube_size="Large",
            block_topology="TriangleMesh",
            cube_topology="",
            size_x=1,
            size_y=1,
            size_z=1,
            model_path="Models/Cubes/large/thrust.mwm",
            model_offset=(0.0, 0.0, 0.0),
        )
        catalog = CubeBlockCatalog()
        catalog.definitions[defn.key] = defn
        catalog.by_subtype[defn.subtype_id] = defn
        library = MeshLibrary()
        library._meshes[library.cache_key(defn, defn.subtype_id, defn.size, "Large")] = object()
        blocks = [_block((0, 0, 0), subtype=defn.subtype_id, type_id=defn.type_id)]
        self.assertEqual(pending_mwm_definitions(blocks, catalog, library), [])
        pending = pending_mwm_patches(blocks, catalog, library, patched_keys=set())
        self.assertEqual(len(pending), 1)
        self.assertTrue(pending[0].mesh_cached)
        self.assertEqual(
            pending_mwm_patches(blocks, catalog, library, patched_keys={defn.key}),
            [],
        )


class UploadBudgetTests(unittest.TestCase):
    def test_split_keeps_every_instance_id(self):
        batch = _cpu_batch(1000)
        parts = split_batches_for_upload([batch], max_instances=512, max_bytes=10**9)
        self.assertGreater(len(parts), 1)
        ids = np.concatenate([part.instance_ids for part in parts])
        self.assertEqual(sorted(int(round(float(i))) for i in ids), list(range(1000)))

    def test_byte_budget_splits_a_heavy_mesh_batch(self):
        batch = _cpu_batch(6, extra_mesh_bytes=3_000_000)
        parts = split_batches_for_upload([batch], max_instances=512, max_bytes=2_000_000)
        self.assertGreater(len(parts), 1)
        ids = np.concatenate([part.instance_ids for part in parts])
        self.assertEqual(sorted(int(round(float(i))) for i in ids), list(range(6)))


class RadialCombineTests(unittest.TestCase):
    def test_vectorized_combine_matches_python_to_1e_6(self):
        rng = np.random.default_rng(7)
        n = 64
        global_off = rng.normal(size=(n, 3)).tolist()
        stretch = rng.normal(size=(n, 3)).tolist()
        peel_off = rng.normal(size=(n, 3)).tolist()
        station_off = rng.normal(size=(n, 3)).tolist()
        neigh_off = rng.normal(size=(n, 3)).tolist()
        weight = rng.random(n).tolist()
        got = radial_combine_offsets(global_off, stretch, peel_off, station_off, neigh_off, weight)
        expect = _python_radial_combine(global_off, stretch, peel_off, station_off, neigh_off, weight)
        self.assertTrue(np.allclose(got, expect, atol=1e-6, rtol=0.0))


class SessionPrefAndPrewarmTests(unittest.TestCase):
    def test_projection_and_dissect_roundtrip_in_settings(self):
        loaded = AppSettings.from_dict({
            "subgrids_projection": "Side",
            "subgrids_dissect_mode": "decks",
        })
        self.assertEqual(loaded.subgrids_projection, "Side")
        self.assertEqual(loaded.subgrids_dissect_mode, "decks")
        with tempfile.TemporaryDirectory() as tmp:
            store = SettingsStore(Path(tmp) / "settings.json")
            store.save(loaded)
            again = store.load()
        self.assertEqual(again.subgrids_projection, "Side")
        self.assertEqual(again.subgrids_dissect_mode, "decks")
        self.assertEqual(again.to_dict()["subgrids_projection"], "Side")

    def test_prewarm_builds_chrome_after_list_paint(self):
        src = inspect.getsource(PreviewPanel.prewarm_subgrids)
        self.assertIn("_ensure_subgrids_widgets", src)
        self.assertNotIn("_render_subgrids", src)
        self.assertNotIn("on_need_subgrids", src)
        app = Path("ui/app.py").read_text(encoding="utf-8")
        self.assertIn("after_idle(self.preview_panel.prewarm_subgrids)", app)
        self.assertIn("subgrids_projection", app)
        self.assertIn("subgrids_dissect_mode", app)


if __name__ == "__main__":
    unittest.main()

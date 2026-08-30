import inspect
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

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
    STAGE_MESHES,
    STAGE_SHELL,
    BuildGeneration,
    CpuBatch,
    PreviewCpuCache,
    PreviewCpuScene,
    apply_dissect_mode,
    build_preview_cpu,
    copy_cpu_for_dissect,
    cpu_cache_key,
    ensure_exploded_batches,
    pending_mwm_definitions,
    pending_mwm_patches,
    refine_mwm_cpu,
    split_batches_for_upload,
    _build_instance_columns,
)
from se_render.preview_style import (
    dissect_prepare_should_spawn,
    fallback_banner_text,
    gl_upload_should_yield,
    mwm_progress_caption,
    should_defer_catalog_box_build,
    stale_shell_blocks_edits,
    staged_3d_caption,
)
from se_render.occupancy import plan_blocks
from se_assets.mwm_loader import load_mwm
from se_render.viewport import GLPreviewRenderer
from ui.preview_panel import (
    PreviewPanel,
    subgrids_already_showing,
    subgrids_map_payload,
    subgrids_same_ship_is_noop,
)
from se_render.scene_graph import PreviewScene, extract_scene_from_root
from tests.test_preview_render import _block, _catalog_with, _cube, _def
from tests.test_scene_graph import ROTOR_BLUEPRINT
from tests.test_blueprint_document import _write_ship
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
        self.assertTrue(should_defer_catalog_box_build(None, False))
        self.assertFalse(should_defer_catalog_box_build(None, False, catalog_failed=True))
        self.assertFalse(should_defer_catalog_box_build(object(), True))
        self.assertFalse(should_defer_catalog_box_build(object(), False, catalog_failed=True))


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
        self.assertIn("prewarm_gl", src)
        self.assertNotIn("_render_subgrids", src)
        self.assertNotIn("on_need_subgrids", src)
        app = Path("ui/app.py").read_text(encoding="utf-8")
        self.assertIn("after_idle(self.preview_panel.prewarm_subgrids)", app)
        self.assertIn("subgrids_projection", app)
        self.assertIn("subgrids_dissect_mode", app)

    def test_prewarm_is_scheduled_after_install_apply_not_only_list_load(self):
        from ui.app import TacticalCommandCenter

        apply = inspect.getsource(TacticalCommandCenter._apply_se_install_state)
        retry = inspect.getsource(TacticalCommandCenter._retry_prewarm_gl)
        loaded = inspect.getsource(TacticalCommandCenter._on_blueprints_loaded)
        locate = inspect.getsource(TacticalCommandCenter.locate_space_engineers)
        clear = inspect.getsource(TacticalCommandCenter.clear_space_engineers_path)
        select = inspect.getsource(TacticalCommandCenter.on_blueprint_select)
        self.assertIn("after_idle(self._retry_prewarm_gl)", apply)
        self.assertIn("prewarm_gl", retry)
        self.assertIn("space_engineers_cleared", retry)
        self.assertIn("after_idle(self.preview_panel.prewarm_subgrids)", loaded)
        self.assertIn("_apply_se_install_state", locate)
        self.assertNotIn("try_init", select)
        self.assertNotIn("prewarm_gl", select)
        self.assertNotIn("_retry_prewarm_gl", select)
        self.assertNotIn("try_init", clear)
        self.assertNotIn("prewarm_gl", clear)
        self.assertNotIn("_retry_prewarm_gl", clear)
        state = inspect.getsource(PreviewPanel.set_se_preview_state)
        self.assertIn("prewarm_gl", state)

    def test_prewarm_noops_before_install_then_runs_after_apply(self):
        host = ShipPreviewHost.__new__(ShipPreviewHost)
        host._gl_failed = False
        host._install_valid = False
        host._install_cleared = False
        host._renderer = None
        host._gl_init_job = None
        inits = []
        host._run_gl_init = lambda: inits.append("init")
        host._cancel_gl_init_job = lambda: None
        host.prewarm_gl()
        self.assertEqual(inits, [])
        host._install_valid = True
        host.prewarm_gl()
        self.assertEqual(inits, ["init"])
        host._install_cleared = True
        host.prewarm_gl()
        self.assertEqual(inits, ["init"])

    def test_retry_prewarm_after_clear_does_not_init(self):
        from ui.app import TacticalCommandCenter

        app = TacticalCommandCenter.__new__(TacticalCommandCenter)
        app._closing = False
        app.settings = SimpleNamespace(space_engineers_cleared=True)
        app._se_install_status = SimpleNamespace(valid=True)
        called = []
        app.preview_panel = SimpleNamespace(prewarm_gl=lambda: called.append(1))
        app._retry_prewarm_gl()
        self.assertEqual(called, [])
        app.settings.space_engineers_cleared = False
        app._retry_prewarm_gl()
        self.assertEqual(called, [1])


class GlTurnBudgetTests(unittest.TestCase):
    def test_yield_helper_requires_first_slice_then_time_or_bytes(self):
        self.assertFalse(gl_upload_should_yield(False, 1.0, 9_000_000))
        self.assertTrue(gl_upload_should_yield(True, 0.02, 0, time_budget_s=0.008))
        self.assertTrue(gl_upload_should_yield(True, 0.0, 2_000_000, byte_budget=2_000_000))
        self.assertFalse(gl_upload_should_yield(True, 0.001, 100, time_budget_s=0.008, byte_budget=2_000_000))

    def test_continue_uploads_one_batch_then_yields_on_zero_budget(self):
        renderer = GLPreviewRenderer.__new__(GLPreviewRenderer)
        renderer.available = True
        renderer._incoming_cpu = None
        renderer._incoming_refit = True
        renderer._pending_patch_release = {}
        renderer._sets = {"assembled": [], "exploded": [], "assembled_lod": [], "exploded_lod": []}
        renderer._alias_assembled_lod = False
        renderer._alias_exploded_lod = False
        renderer._secondary_pending = False
        renderer.upload_generation = 0
        calls = []

        def fake_upload(name, batches, append=False):
            calls.append((name, len(batches), append))

        renderer._upload_named = fake_upload
        renderer._finish_lod_aliases = lambda: None
        renderer._chunk_queue = [("assembled", [_cpu_batch(2), _cpu_batch(2), _cpu_batch(2)], 0)]
        more = renderer.continue_cpu_upload(8, time_budget_s=0.0, byte_budget=1)
        self.assertTrue(more)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][1], 1)
        self.assertEqual(len(renderer._chunk_queue[0][1]) - renderer._chunk_queue[0][2], 2)

    def test_patch_and_secondary_queue_instead_of_sync_upload(self):
        renderer = GLPreviewRenderer.__new__(GLPreviewRenderer)
        renderer.available = True
        renderer._cpu = None
        renderer._incoming_cpu = None
        renderer._pending_patch_release = {}
        renderer._chunk_queue = []
        renderer._grid_filter = None
        renderer._grid_entity_id = None
        renderer._secondary_pending = False
        renderer._sets = {"assembled": [], "exploded": [], "assembled_lod": [], "exploded_lod": []}
        renderer.upload_generation = 0
        renderer._break_set_aliases = lambda: None
        renderer._write_inspect_hidden = lambda: None
        cpu = PreviewCpuScene(
            assembled=[_cpu_batch(4)],
            exploded=[_cpu_batch(4)],
            assembled_lod=[],
            exploded_lod=[],
            huge=True,
        )
        renderer.patch_assembled(cpu)
        self.assertTrue(any(str(item[0]).startswith("patch:") for item in renderer._chunk_queue))
        renderer._chunk_queue = []
        renderer._cpu = cpu
        queued = renderer.upload_secondary_sets()
        self.assertTrue(queued)
        self.assertTrue(any(item[0] == "exploded" for item in renderer._chunk_queue))

    def test_constructor_does_not_init_gl(self):
        src = inspect.getsource(GLPreviewRenderer.__init__)
        self.assertIn("if init:", src)
        self.assertIn("try_init", src)
        apply = inspect.getsource(ShipPreviewHost._apply_mode)
        start = inspect.getsource(ShipPreviewHost._start_build)
        switch = inspect.getsource(ShipPreviewHost.begin_switch)
        load = inspect.getsource(ShipPreviewHost.load_scene)
        select = inspect.getsource(__import__("ui.app", fromlist=["TacticalCommandCenter"]).TacticalCommandCenter.on_blueprint_select)
        for body in (apply, start, switch, load, select):
            self.assertNotIn("try_init", body)
            self.assertNotIn("GLPreviewRenderer()", body)
            self.assertNotIn("GLPreviewRenderer(init=True)", body)
        prewarm = inspect.getsource(ShipPreviewHost.prewarm_gl)
        self.assertIn("_run_gl_init", prewarm)
        self.assertNotIn("try_init", select)


class StaleShellEditTests(unittest.TestCase):
    def test_switching_blocks_edits_and_save_as_uses_selected_path(self):
        self.assertTrue(stale_shell_blocks_edits(switching=True, mesh_ready=True))
        self.assertTrue(stale_shell_blocks_edits(switching=False, mesh_ready=False))
        self.assertTrue(stale_shell_blocks_edits(switching=False, mesh_ready=True, catalog_wait=True))
        self.assertFalse(stale_shell_blocks_edits(switching=False, mesh_ready=True))
        pick = inspect.getsource(ShipPreviewHost._pick_at)
        nudge = inspect.getsource(ShipPreviewHost._nudge_selected)
        save = inspect.getsource(ShipPreviewHost._save_as_new)
        switch = inspect.getsource(ShipPreviewHost.begin_switch)
        self.assertIn("_edits_live", pick)
        self.assertIn("_edits_live", nudge)
        self.assertIn("_edits_live", save)
        self.assertIn("_source_path", save)
        self.assertIn("_set_dissect_enabled(False)", switch)


class DeferredExplodedTests(unittest.TestCase):
    def test_full_stage_does_not_build_exploded_until_asked(self):
        catalog = _catalog_with(_def("CubeBlock", "LargeBlockArmorBlock", "Box"))
        blocks = [_cube((x, 0, 0), str(x)) for x in range(3)]
        cpu = build_preview_cpu(
            PreviewScene(blocks=blocks, main_grid_name="Hull", total_blocks=3),
            catalog,
            stage=STAGE_FULL,
        )
        self.assertFalse(cpu.exploded)
        ensure_exploded_batches(cpu, catalog)
        self.assertTrue(cpu.exploded)
        self.assertEqual(sum(int(b.models.shape[0]) for b in cpu.exploded), 3)
        interior = inspect.getsource(ShipPreviewHost._start_interior_fill)
        self.assertIn("_explode <= 1e-4", interior)


class CooperativeCancelTests(unittest.TestCase):
    def test_plan_columns_refine_exploded_and_mwm_honor_cancel(self):
        catalog = _catalog_with(_def("CubeBlock", "LargeBlockArmorBlock", "Box"))
        blocks = [_block((i, 0, 0), entity=str(i)) for i in range(300)]
        calls = {"n": 0}

        def cancel():
            calls["n"] += 1
            return calls["n"] > 1

        self.assertEqual(plan_blocks(blocks, catalog, cancel=cancel), [])
        calls["n"] = 0
        cols = _build_instance_columns(blocks, catalog, [0] * len(blocks), cancel=cancel)
        self.assertEqual(int(cols.models.shape[0]), 300)
        self.assertGreater(calls["n"], 1)
        scene = PreviewScene(blocks=blocks[:8], total_blocks=8)
        cpu = build_preview_cpu(scene, catalog, stage=STAGE_SHELL)
        stopped = {"n": 0}

        def stop():
            stopped["n"] += 1
            return True

        same = refine_mwm_cpu(cpu, catalog, MeshLibrary(), [object()], cancel=stop)
        self.assertIs(same, cpu)
        exploded_before = list(cpu.exploded)
        ensure_exploded_batches(cpu, catalog, cancel=stop)
        self.assertEqual(cpu.exploded, exploded_before)
        self.assertIsNone(load_mwm(Path("/no/such/file.mwm"), cancel=lambda: True))


class TabRevisitNoopTests(unittest.TestCase):
    def test_same_ship_payload_is_noop(self):
        scene = object()
        structure = object()
        self.assertTrue(
            subgrids_same_ship_is_noop(
                path="/ships/A",
                current_path="/ships/A",
                scene=scene,
                pending_scene=scene,
                structure=structure,
                pending_structure=structure,
                rendered_for=3,
                revision=3,
            )
        )
        self.assertFalse(
            subgrids_same_ship_is_noop(
                path="/ships/B",
                current_path="/ships/A",
                scene=scene,
                pending_scene=scene,
                structure=structure,
                pending_structure=structure,
                rendered_for=3,
                revision=3,
            )
        )
        src = inspect.getsource(__import__("ui.preview_panel", fromlist=["PreviewPanel"]).PreviewPanel.update_subgrids)
        self.assertIn("subgrids_same_ship_is_noop", src)
        start = inspect.getsource(ShipPreviewHost._start_build)
        self.assertIn("source_blocks is self._scene.blocks", start)


class SliderSupersedeTests(unittest.TestCase):
    def test_offsets_keep_slider_on_uniforms(self):
        self.assertFalse(
            dissect_prepare_should_spawn(
                have_offsets=True,
                have_exploded=True,
                preparing=False,
                preparing_mode=None,
                wanted_mode=DISSECT_PEEL,
            )
        )
        self.assertFalse(
            dissect_prepare_should_spawn(
                have_offsets=False,
                have_exploded=False,
                preparing=True,
                preparing_mode=DISSECT_PEEL,
                wanted_mode=DISSECT_PEEL,
            )
        )
        self.assertTrue(
            dissect_prepare_should_spawn(
                have_offsets=False,
                have_exploded=False,
                preparing=True,
                preparing_mode=DISSECT_PEEL,
                wanted_mode=DISSECT_RADIAL,
            )
        )

    def _bare_host(self, cpu):
        host = ShipPreviewHost.__new__(ShipPreviewHost)
        host._job = BuildGeneration()
        host._dissect_job = BuildGeneration()
        host._dissect_preparing = False
        host._dissect_wanted = None
        host._cpu_scene = cpu
        host._mesh_ready = True
        host._dissect_mode = DISSECT_PEEL
        host._install_valid = True
        host._refine_cancelled = False
        host._catalog = None
        host._meshes = None
        host._renderer = None
        host._explode = 0.0
        host._apply_dissect_chrome = lambda: None
        host._refresh_status = lambda: None
        host._schedule_redraw = lambda **_k: None
        host._arm_idle_redraw = lambda: None
        host._queue_secondary_upload = lambda *_a, **_k: None
        host.after = lambda *_a, **_k: None
        return host

    def test_slider_motions_keep_one_live_worker(self):
        cpu = PreviewCpuScene()
        host = self._bare_host(cpu)
        started = []

        class FakeThread:
            def __init__(self, target=None, daemon=None, **_k):
                self.target = target

            def start(self):
                started.append(self)

        with mock.patch("ui.widgets.ship_preview.threading.Thread", FakeThread):
            for i in range(12):
                host._set_explode(0.08 + i * 0.04)
        self.assertEqual(len(started), 1)
        self.assertEqual(host._dissect_job.generation, 1)
        self.assertEqual(host._dissect_wanted, DISSECT_PEEL)
        host._dissect_mode = DISSECT_RADIAL
        with mock.patch("ui.widgets.ship_preview.threading.Thread", FakeThread):
            host._ensure_dissect_ready()
        self.assertEqual(len(started), 2)
        self.assertEqual(host._dissect_job.generation, 2)
        self.assertEqual(host._dissect_wanted, DISSECT_RADIAL)
        cpu.dissect_modes = [DISSECT_PEEL]
        cpu.exploded = [object()]
        host._dissect_mode = DISSECT_PEEL
        host._dissect_preparing = False
        host._dissect_wanted = None
        with mock.patch("ui.widgets.ship_preview.threading.Thread", FakeThread):
            for _ in range(8):
                host._set_explode(0.4)
        self.assertEqual(len(started), 2)


class SwitchNudgeGenerationTests(unittest.TestCase):
    def test_begin_switch_plus_nudge_does_not_bump_incoming_build(self):
        host = ShipPreviewHost.__new__(ShipPreviewHost)
        host._job = BuildGeneration()
        host._dissect_job = BuildGeneration()
        host._upload_chunk_job = None
        host._renderer = None
        host._switching = False
        host._mesh_ready = True
        host._catalog_wait = False
        host._install_valid = True
        host._building = False
        host._pending_swap = False
        host._refine_cancelled = False
        host._ship_name = "A"
        host._cpu_stage = STAGE_FULL
        host._grid_filter = None
        host._grid_entity_id = None
        host._grid_isolate_key = None
        host._isolated_count = None
        host._scene = PreviewScene(blocks=[_cube((0, 0, 0))], total_blocks=1)
        rec = host._scene.blocks[0]
        host._selected_rec = SimpleNamespace(
            instance_id=0,
            grid_name=rec.grid_name,
            entity_id=rec.entity_id,
            local_min=rec.local_min,
        )
        from blueprint_edit import GridEditSession

        host._edits = GridEditSession()
        host._set_dissect_enabled = lambda _v: None
        host._refresh_status = lambda: None
        host._apply_cancel_refine_chrome = lambda: None
        host._sync_user_hidden = lambda: None
        host._schedule_redraw = lambda **_k: None
        host._cpu_cache = PreviewCpuCache()
        host._source_path = None
        host._job.begin()
        host.begin_switch("B")
        incoming = host._job.begin()
        host._nudge_selected((1, 0, 0))
        self.assertEqual(host._job.generation, incoming)
        self.assertTrue(host._job.is_current(incoming))
        self.assertTrue(build_ready_applies(host._job, incoming, install_valid=True))
        before = host._job.generation
        host._rebuild_after_edit()
        self.assertEqual(host._job.generation, before)


class CachedMwmRevisitTests(unittest.TestCase):
    def test_refine_advances_stage_and_a_b_a_skips_pending(self):
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
        blocks = [_block((0, 0, 0), subtype=defn.subtype_id, type_id=defn.type_id)]
        scene = PreviewScene(blocks=blocks, main_grid_name="Hull", total_blocks=1)
        cpu = build_preview_cpu(scene, catalog, library, stage=STAGE_SHELL)
        self.assertEqual(cpu.stage, STAGE_SHELL)
        patched = refine_mwm_cpu(cpu, catalog, library, [defn])
        self.assertEqual(patched.stage, STAGE_MESHES)
        self.assertIn(defn.key, patched.mwm_patched_keys)
        patched.stage = STAGE_FULL
        cache = PreviewCpuCache()
        cache.put(cpu_cache_key("A", 10, 1, STAGE_FULL), patched)
        cache.put(cpu_cache_key("B", 10, 1, STAGE_FULL), PreviewCpuScene(stage=STAGE_FULL))
        again = cache.get_best("A", 10, 1)
        self.assertIs(again, patched)
        self.assertEqual(again.stage, STAGE_FULL)
        self.assertEqual(
            pending_mwm_patches(blocks, catalog, library, patched_keys=again.mwm_patched_keys),
            [],
        )

    def test_cached_full_stage_does_not_request_mwm_refine(self):
        host = ShipPreviewHost.__new__(ShipPreviewHost)
        host._install_valid = True
        host._gl_failed = False
        host._scene = SimpleNamespace(blocks=[object()] * 3000)
        host._catalog = object()
        host._catalog_in_flight = False
        host._catalog_failed = False
        host._mesh_ready = False
        host._cpu_scene = None
        host._switching = False
        host._job = BuildGeneration()
        host._cpu_cache = PreviewCpuCache()
        host._catalog_gen = 0
        host._source_stamp = lambda: ("/A", 10)
        host._mwm_patched_keys = set()
        host._mwm_done = 0
        host._mwm_total = 0
        host._cpu_stage = ""
        host._refine_cancelled = False
        host._catalog_wait = False
        host._refresh_status = lambda: None
        host._apply_cancel_refine_chrome = lambda: None
        host._apply_mode = lambda: None
        cpu = PreviewCpuScene(stage=STAGE_FULL, mwm_patched_keys={"thrust"})
        host._cpu_cache.put(cpu_cache_key("/A", 10, 0, STAGE_FULL), cpu)
        seen = []
        host._on_build_ready = lambda gen, cached, refine=False: seen.append((gen, cached, refine))
        queued = []
        host.after = lambda _ms, fn=None, **_k: queued.append(fn) or 1
        host._start_build()
        self.assertEqual(host._mwm_patched_keys, {"thrust"})
        self.assertTrue(queued)
        queued[0]()
        self.assertEqual(len(seen), 1)
        self.assertIs(seen[0][1], cpu)
        self.assertFalse(seen[0][2])
        start = inspect.getsource(ShipPreviewHost._start_build)
        self.assertIn("_adopt_cached_cpu_meta", start)
        remember = inspect.getsource(ShipPreviewHost._remember_cpu)
        self.assertIn("mwm_patched_keys", remember)
        mwm = inspect.getsource(ShipPreviewHost._start_mwm_refine)
        self.assertGreater(mwm.find("pending_mwm_patches"), mwm.find("def task"))

    def test_pending_mwm_honors_cancel(self):
        catalog = _catalog_with(_def("CubeBlock", "LargeBlockArmorBlock", "Box"))
        blocks = [_block((i, 0, 0), entity=str(i)) for i in range(300)]
        calls = {"n": 0}

        def cancel():
            calls["n"] += 1
            return True

        self.assertEqual(
            pending_mwm_patches(blocks, catalog, MeshLibrary(), cancel=cancel),
            [],
        )
        self.assertGreaterEqual(calls["n"], 1)


class SkipVoxelsWhen3dTests(unittest.TestCase):
    def test_map_payload_never_reads_voxels_property(self):
        class ExplosiveDoc:
            _map_blocks = None
            _voxels = None

            @property
            def voxels(self):
                raise AssertionError("voxels_from_scene ran on Tk")

        self.assertEqual(subgrids_map_payload(True, ExplosiveDoc()), (None, None))
        self.assertEqual(subgrids_map_payload(False, ExplosiveDoc()), (None, None))
        doc = ExplosiveDoc()
        doc._map_blocks = ["cube"]
        self.assertEqual(subgrids_map_payload(True, doc), (None, ["cube"]))
        self.assertEqual(subgrids_map_payload(False, doc), (None, ["cube"]))
        doc2 = ExplosiveDoc()
        doc2._voxels = [{"x": 0}]
        self.assertEqual(subgrids_map_payload(False, doc2), ([{"x": 0}], None))
        self.assertEqual(subgrids_map_payload(True, doc2), (None, None))

    def test_already_showing_covers_2d_and_3d(self):
        preview_3d = SimpleNamespace(_switching=False, _mesh_ready=True, _mode="3d", ship_canvas=None)
        self.assertTrue(subgrids_already_showing(path="/A", current_path="/A", preview=preview_3d))
        preview_2d = SimpleNamespace(
            _switching=False,
            _mesh_ready=False,
            _mode="2d",
            ship_canvas=SimpleNamespace(blocks=[object()]),
        )
        self.assertTrue(subgrids_already_showing(path="/A", current_path="/A", preview=preview_2d))
        preview_2d._switching = True
        self.assertFalse(subgrids_already_showing(path="/A", current_path="/A", preview=preview_2d))
        self.assertFalse(subgrids_already_showing(path="/B", current_path="/A", preview=preview_3d))

    def test_ensure_and_ready_skip_voxels_property_when_3d(self):
        from ui.app import TacticalCommandCenter

        ensure = inspect.getsource(TacticalCommandCenter._ensure_subgrids_document)
        ready = inspect.getsource(TacticalCommandCenter._on_document_ready)
        publish = inspect.getsource(TacticalCommandCenter._publish_subgrids_document)
        inspect_now = inspect.getsource(TacticalCommandCenter._run_inspect_now)
        select = inspect.getsource(TacticalCommandCenter.on_blueprint_select)
        self.assertIn("subgrids_map_payload", publish)
        self.assertIn("_publish_subgrids_document", ensure)
        self.assertIn("_publish_subgrids_document", ready)
        self.assertIn("ensure_map_blocks", inspect_now)
        self.assertNotIn("prepare_2d", inspect_now)
        self.assertLess(select.find("_ensure_subgrids_document"), select.find("_apply_instant_inspect"))
        render = inspect.getsource(PreviewPanel._render_subgrids)
        want = render[render.find("want_3d") :]
        self.assertIn("load_scene(scene, voxels=None, blocks=map_blocks)", want)
        self.assertNotIn("voxels_to_blocks", render)
        tabs = inspect.getsource(PreviewPanel._on_tab_changed)
        self.assertIn('_mode", "") == "3d"', tabs)
        canvas = __import__("ui.widgets.ship_canvas", fromlist=["ShipCanvas"]).ShipCanvas
        for method in (
            canvas.load_structure_data,
            canvas.fit_to_view,
            canvas.filter_by_grid,
            canvas.redraw,
            canvas._request_map_bitmap,
        ):
            body = inspect.getsource(method)
            self.assertNotIn("collect_projected_cells", body)
            self.assertNotIn("rasterize_projected_cells", body)
            self.assertNotIn("bounds_for(", body)
            self.assertNotIn("bounds_for_blocks", body)
            self.assertNotIn("_visible_blocks", body)
            self.assertNotIn("_update_status_caption", body)
        request_src = inspect.getsource(canvas._request_map_bitmap)
        self.assertIn("build_map_frame", request_src)
        self.assertIn("threading.Thread", request_src)
        self.assertIn("except Exception", request_src)
        self.assertIn("_request_map_bitmap", inspect.getsource(canvas.fit_to_view))
        self.assertNotIn("self.bounds_for", inspect.getsource(canvas.load_structure_data))
        load_src = inspect.getsource(ShipPreviewHost.load_scene)
        self.assertIn("self._switching = False", load_src)
        materialize = inspect.getsource(ShipPreviewHost._materialize_2d_fallback)
        self.assertNotIn("voxels_from_scene", materialize)
        self.assertNotIn("voxels_to_blocks", materialize)
        queue = inspect.getsource(ShipPreviewHost._queue_2d_materialize)
        self.assertIn("threading.Thread", queue)
        self.assertIn("voxels_from_scene", queue)
        self.assertIn("voxels_to_blocks", queue)

    def test_cache_hit_does_not_materialize_voxels_when_3d(self):
        from ui.app import TacticalCommandCenter

        class ExplosiveDoc:
            structure = object()
            scene = object()
            path = Path("/ships/A/bp.sbc")
            display_name = "A"
            _map_blocks = None
            _voxels = None

            @property
            def voxels(self):
                raise AssertionError("voxels_from_scene ran on Tk")

        seen = []
        inspect_calls = []
        app = TacticalCommandCenter.__new__(TacticalCommandCenter)
        app.selected_blueprint = SimpleNamespace(path=Path("/ships/A"), display_name="A")
        app._closing = False
        app._document = None
        app._documents = SimpleNamespace(get=lambda _p: ExplosiveDoc())
        app.toasts = SimpleNamespace(toast=lambda *_a, **_k: None)
        app.preview_panel = SimpleNamespace(
            subgrids_generation=1,
            ship_preview=SimpleNamespace(will_show_3d=lambda: True),
            update_subgrids=lambda *a, **k: seen.append(k),
        )
        app._inspect_blueprint_async = lambda immediate=False: inspect_calls.append(immediate)
        app._ensure_subgrids_document()
        self.assertEqual(len(seen), 1)
        self.assertIsNone(seen[0].get("voxels"))
        self.assertIsNone(seen[0].get("blocks"))
        self.assertEqual(inspect_calls, [True])

    def test_2d_cache_without_map_blocks_does_not_walk_voxels_on_tk(self):
        from ui.app import TacticalCommandCenter

        class ExplosiveDoc:
            structure = object()
            scene = object()
            path = Path("/ships/A/bp.sbc")
            display_name = "A"
            _map_blocks = None

            @property
            def voxels(self):
                raise AssertionError("voxels_from_scene ran on Tk")

        inspect_calls = []
        app = TacticalCommandCenter.__new__(TacticalCommandCenter)
        app.selected_blueprint = SimpleNamespace(path=Path("/ships/A"), display_name="A")
        app._closing = False
        app._document = None
        app._documents = SimpleNamespace(get=lambda _p: ExplosiveDoc())
        app.toasts = SimpleNamespace(toast=lambda *_a, **_k: None)
        app.preview_panel = SimpleNamespace(
            subgrids_generation=1,
            ship_preview=SimpleNamespace(will_show_3d=lambda: False),
            update_subgrids=lambda *a, **k: (_ for _ in ()).throw(AssertionError("Tk rebuilt 2D from cache")),
        )
        app._inspect_blueprint_async = lambda immediate=False: inspect_calls.append(immediate)
        app._ensure_subgrids_document()
        self.assertEqual(inspect_calls, [True])


class VisibleBoundsSkipTests(unittest.TestCase):
    def test_apply_visible_bounds_skips_when_filter_unchanged(self):
        renderer = GLPreviewRenderer.__new__(GLPreviewRenderer)
        renderer._cpu = PreviewCpuScene(
            picks=[],
            aabb_min=(-1.0, -1.0, -1.0),
            aabb_max=(1.0, 1.0, 1.0),
        )
        renderer._grid_filter = None
        renderer._grid_entity_id = None
        renderer._bounds_key = None
        calls = {"n": 0}

        def counting():
            calls["n"] += 1
            return []

        renderer._visible_picks = counting
        renderer._apply_visible_bounds()
        renderer._apply_visible_bounds()
        self.assertEqual(calls["n"], 1)
        renderer._grid_filter = "Turret"
        renderer._apply_visible_bounds()
        self.assertEqual(calls["n"], 2)
        filt = inspect.getsource(GLPreviewRenderer.set_grid_filter)
        self.assertIn("isolate_grid_instances", filt)
        self.assertNotIn("_upload_named", filt)
        upload = inspect.getsource(GLPreviewRenderer.upload_cpu_scene)
        self.assertIn("drain", upload)
        edit = inspect.getsource(ShipPreviewHost._on_edit_rebuild)
        self.assertIn("_upload_cpu", edit)
        self.assertNotIn("upload_cpu_scene", edit)
        rebuild = inspect.getsource(ShipPreviewHost._rebuild_after_edit)
        self.assertIn("_edits_live", rebuild)


class DeadOrphanRemovalTests(unittest.TestCase):
    def test_listed_orphans_have_zero_callers(self):
        import ui.preview_panel as preview_panel
        import se_render.preview_style as preview_style

        self.assertFalse(hasattr(preview_panel, "subgrids_voxels_for_ui"))
        self.assertFalse(hasattr(preview_style, "FIRST_UPLOAD_CHUNK"))
        self.assertFalse(hasattr(preview_style, "UPLOAD_BATCH_CHUNK"))
        viewport = inspect.getsource(GLPreviewRenderer)
        self.assertNotIn("def _upload_secondary", viewport)
        self.assertNotIn("def _patch_named", viewport)
        self.assertIn("def _queue_patch_named", viewport)
        self.assertIn("def _patch_one", viewport)
        self.assertIn("def upload_secondary_sets", viewport)
        host = inspect.getsource(ShipPreviewHost)
        self.assertNotIn("def _ensure_renderer", host)
        self.assertNotIn("def _refine_is_cancelled", host)
        begin = inspect.getsource(GLPreviewRenderer.begin_cpu_upload)
        self.assertNotIn("chunk_size", begin)
        self.assertIn("def continue_cpu_upload", viewport)


if __name__ == "__main__":
    unittest.main()

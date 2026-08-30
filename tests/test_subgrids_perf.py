import inspect
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from blueprint_document import (
    BlueprintDocumentCache,
    CancelledError,
    JobToken,
    build_ready_applies,
    subgrids_ui_applies,
)
from se_render.occupancy import build_occupancy
from se_render.preview_build import STAGE_SHELL, BuildGeneration, build_preview_cpu
from se_render.preview_style import (
    fallback_banner_text,
    should_defer_catalog_box_build,
    staged_3d_caption,
)
from se_render.scene_graph import PreviewScene, extract_scene_from_root
from tests.test_preview_render import _block
from tests.test_scene_graph import ROTOR_BLUEPRINT
from tests.test_blueprint_document import _write_ship


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


if __name__ == "__main__":
    unittest.main()

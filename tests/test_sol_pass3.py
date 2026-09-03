import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import numpy as np
import xml.etree.ElementTree as ET

from blueprint_document import JobHub
from blueprint_edit import apply_edits_to_tree, save_blueprint_as, unique_edited_dir
from se_render.preview_style import format_preview_count_caption
from se_render.scene_graph import extract_scene_from_root
from se_render.viewport import (
    GLPreviewRenderer,
    cpu_batch_delta_key,
    plan_batch_delta,
    scene_bounds_caption,
)
from tests.test_blueprint_edit import TWO_BLOCK
from tests.test_preview_render import _block
from se_render.scene_graph import PreviewScene
from ui.preview_panel import pending_catalog_for


class ResetVisibilityInspectTests(unittest.TestCase):
    def test_clearing_hidden_subtypes_rewrites_inspect_z(self):
        class FakeBuf:
            def write(self, data) -> None:
                self.payload = data

        renderer = GLPreviewRenderer.__new__(GLPreviewRenderer)
        renderer.hidden_ids = set()
        renderer.hidden_subtypes = {"Gyro"}
        renderer._cpu = SimpleNamespace(
            picks=[SimpleNamespace(instance_id=1, subtype="Gyro")]
        )
        arr = np.zeros((2, 3), dtype=np.float32)
        arr[0, 2] = 1.0
        buf = FakeBuf()
        renderer._sets = {
            "assembled": [{"inspect": arr, "inspect_buf": buf, "instance_ids": [1, 2]}]
        }
        renderer.hidden_subtypes = set()
        renderer._write_inspect_hidden()
        self.assertEqual(float(arr[0, 2]), 0.0)
        self.assertEqual(float(arr[1, 2]), 0.0)


class ChunkPatchOverlapTests(unittest.TestCase):
    def test_patch_assembled_cancels_leftover_shell_chunks(self):
        renderer = GLPreviewRenderer.__new__(GLPreviewRenderer)
        renderer.available = False
        renderer._chunk_queue = [("assembled", [], 8)]
        renderer._cpu = None
        from se_render.preview_build import PreviewCpuScene

        renderer.patch_assembled(PreviewCpuScene())
        self.assertEqual(renderer._chunk_queue, [])

    def test_break_aliases_then_detach_releases_shared_lod(self):
        class FakeRel:
            def __init__(self) -> None:
                self.released = False

            def release(self) -> None:
                self.released = True

        renderer = GLPreviewRenderer.__new__(GLPreviewRenderer)
        obj = FakeRel()
        batches = [{"release": [obj]}]
        renderer._sets = {"assembled": batches, "assembled_lod": batches}
        renderer._break_set_aliases()
        self.assertIsNot(renderer._sets["assembled_lod"], renderer._sets["assembled"])
        renderer._detach_and_release("assembled")
        self.assertTrue(obj.released)


class BatchDeltaTests(unittest.TestCase):
    def test_keeps_unchanged_and_uploads_changed_without_dropping_ids(self):
        def cpu(ids, verts, idxs, inst):
            return SimpleNamespace(
                instance_ids=np.array(ids, dtype=np.float32),
                positions=np.zeros((verts, 3), dtype=np.float32),
                indices=np.zeros(idxs, dtype=np.int32),
                models=np.zeros((inst, 16), dtype=np.float32),
            )

        old = [
            {
                "instance_ids": np.array([0, 1, 2], dtype=np.float32),
                "vertex_count": 8,
                "index_count": 36,
                "instances": 3,
            },
            {
                "instance_ids": np.array([3], dtype=np.float32),
                "vertex_count": 8,
                "index_count": 36,
                "instances": 1,
            },
        ]
        new = [
            cpu([0, 1, 2], 8, 36, 3),
            cpu([3], 24, 90, 1),
        ]
        actions, release = plan_batch_delta(old, new)
        self.assertEqual(actions, [("keep", 0), ("upload", 1)])
        self.assertEqual(release, [1])
        kept_ids = set(int(i) for i in old[0]["instance_ids"])
        uploaded_ids = set(int(i) for i in new[1].instance_ids)
        self.assertEqual(kept_ids | uploaded_ids, {0, 1, 2, 3})
        self.assertEqual(cpu_batch_delta_key(new[0])[3], 3)


class HonestUploadCaptionTests(unittest.TestCase):
    def test_caption_shows_uploaded_of_total_while_uploading(self):
        self.assertEqual(
            format_preview_count_caption(8, 100, uploading=True),
            "8 of 100 blocks  ·  uploading",
        )
        scene = PreviewScene(blocks=[_block((0, 0, 0))], total_blocks=20)
        text = scene_bounds_caption(scene, declared_total=20, shown=8, uploading=True)
        self.assertIn("uploading", text)
        self.assertIn("8", text)
        self.assertNotIn("simplified", text)


class IndexedLookupTests(unittest.TestCase):
    def test_mismatched_entity_id_does_not_edit_min_neighbor(self):
        tree = ET.ElementTree(ET.fromstring(TWO_BLOCK))
        removed, moved = apply_edits_to_tree(
            tree,
            deleted=[("100", (0, 0, 0), "999")],
            moves={},
        )
        self.assertEqual(removed, 0)
        self.assertEqual(moved, 0)
        scene = extract_scene_from_root(tree.getroot())
        self.assertEqual(scene.total_blocks, 2)
        self.assertEqual({b.entity_id for b in scene.blocks}, {"10", "11"})


class SaveAsTransactionalTests(unittest.TestCase):
    def test_failure_after_copytree_removes_partial_dest(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "Ship"
            source.mkdir()
            (source / "bp.sbc").write_text(TWO_BLOCK, encoding="utf-8")
            dest = unique_edited_dir(source)
            with mock.patch(
                "blueprint_edit.apply_edits_to_tree",
                side_effect=RuntimeError("boom"),
            ):
                with self.assertRaises(RuntimeError):
                    save_blueprint_as(source, [], {}, dest_dir=dest)
            self.assertFalse(dest.exists())
            self.assertTrue((source / "bp.sbc").is_file())


class FileClearCatalogTests(unittest.TestCase):
    def test_pending_catalog_clears_when_catalog_is_none(self):
        self.assertIsNone(pending_catalog_for(None, object()))
        self.assertEqual(pending_catalog_for("cat", "mesh"), ("cat", "mesh"))

    def test_file_clear_cancels_only_catalog(self):
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

"""ModernGL ship preview hosted as a CustomTkinter pane."""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from se_assets.cube_catalog import CubeBlockCatalog
from se_assets.mesh_cache import MeshLibrary
from se_render.camera import (
    OrbitCamera,
    aabb_center_radius,
    clip_planes_from_aabb,
    flatten,
    look_at,
    perspective,
)
from se_render.gl_backend import last_gl_error, mark_gl_failed, try_create_context
from se_render.dissection import DISSECT_MODE_INDEX, DISSECT_PEEL, explode_offset_for_mode
from se_render.preview_build import (
    CpuBatch,
    PickRecord,
    PreviewCpuScene,
    build_preview_cpu,
    filter_batches,
    should_alias_lod_sets,
)
from se_render.preview_style import (
    UPLOAD_BATCH_CHUNK,
    active_preview_set,
    format_preview_count_caption,
    render_target_size,
)
from se_render.scene_graph import PreviewScene
from se_render.shaders import FRAGMENT_SHADER, VERTEX_SHADER


def cpu_batch_delta_key(batch: CpuBatch) -> tuple:
    """Identity of a CPU batch: instance set + mesh size. Used for GPU patch reuse."""
    return (
        frozenset(int(i) for i in batch.instance_ids),
        int(batch.positions.shape[0]),
        int(batch.indices.size),
        int(batch.models.shape[0]),
    )


def gpu_batch_delta_key(batch: dict) -> tuple:
    ids = batch.get("instance_ids")
    return (
        frozenset(int(i) for i in ids) if ids is not None else frozenset(),
        int(batch.get("vertex_count") or 0),
        int(batch.get("index_count") or batch.get("count") or 0),
        int(batch.get("instances") or 0),
    )


def plan_batch_delta(
    old_gpu: Sequence[dict],
    new_cpu: Sequence[CpuBatch],
) -> Tuple[List[Tuple[str, int]], List[int]]:
    """
    Map each new CPU batch to keep-an-old-GPU-batch or upload.
    Returns (actions, release_old_indices). Actions are ('keep', old_i) or ('upload', new_j).
    """
    old_by_key: Dict[tuple, List[int]] = {}
    for i, old in enumerate(old_gpu):
        old_by_key.setdefault(gpu_batch_delta_key(old), []).append(i)
    actions: List[Tuple[str, int]] = []
    used: set = set()
    for j, new in enumerate(new_cpu):
        slots = old_by_key.get(cpu_batch_delta_key(new)) or []
        if slots:
            idx = slots.pop(0)
            actions.append(("keep", idx))
            used.add(idx)
        else:
            actions.append(("upload", j))
    release = [i for i in range(len(old_gpu)) if i not in used]
    return actions, release


def _ray_aabb(
    origin: Sequence[float],
    direction: Sequence[float],
    aabb_min: Sequence[float],
    aabb_max: Sequence[float],
) -> Optional[float]:
    tmin = 0.0
    tmax = 1e9
    for i in range(3):
        d = float(direction[i])
        o = float(origin[i])
        lo = float(aabb_min[i])
        hi = float(aabb_max[i])
        if abs(d) < 1e-8:
            if o < lo or o > hi:
                return None
            continue
        inv = 1.0 / d
        t1 = (lo - o) * inv
        t2 = (hi - o) * inv
        if t1 > t2:
            t1, t2 = t2, t1
        tmin = max(tmin, t1)
        tmax = min(tmax, t2)
        if tmax < tmin:
            return None
    return tmin


class GLPreviewRenderer:
    """Off-screen ModernGL renderer. Safe to construct; check .available."""

    def __init__(self) -> None:
        self.available = False
        self.error = ""
        self._ctx = None
        self._prog = None
        self._fbo = None
        self._fbo_color = None
        self._fbo_depth = None
        self._size = (0, 0)
        self._aabb_min = (-1.0, -1.0, -1.0)
        self._aabb_max = (1.0, 1.0, 1.0)
        self._render_origin = (0.0, 0.0, 0.0)
        self._secondary_pending = False
        self._sets: Dict[str, List[dict]] = {
            "assembled": [],
            "exploded": [],
            "assembled_lod": [],
            "exploded_lod": [],
        }
        self._cpu: Optional[PreviewCpuScene] = None
        self._grid_filter: Optional[str] = None
        self._grid_entity_id: Optional[str] = None
        self._chunk_queue: List[tuple] = []
        self._alias_assembled_lod = False
        self._alias_exploded_lod = False
        self.camera = OrbitCamera()
        self._center = (0.0, 0.0, 0.0)
        self._radius = 10.0
        self.block_count = 0
        self.upload_generation = 0
        self.explode = 0.0
        self.dissect_mode = DISSECT_PEEL
        self.hide_armor = False
        self.isolate_id = -1.0
        self.selected_id = -1.0
        self.hide_layers = 0
        self.category_mask = 0
        self.hidden_ids: set = set()
        self.hidden_subtypes: set = set()
        self.pull = 0.35
        self._view_f32 = np.zeros(16, dtype=np.float32)
        self._proj_f32 = np.zeros(16, dtype=np.float32)
        self.camera_user_moved = False
        self.try_init()

    def try_init(self) -> bool:
        if self.available and self._ctx is not None:
            return True
        ctx = try_create_context()
        if ctx is None:
            self.error = last_gl_error() or "OpenGL context failed."
            self.available = False
            return False
        try:
            prog = ctx.program(vertex_shader=VERTEX_SHADER, fragment_shader=FRAGMENT_SHADER)
        except Exception as exc:
            self.error = str(exc)
            mark_gl_failed(self.error)
            try:
                ctx.release()
            except Exception:
                pass
            self.available = False
            return False
        self._ctx = ctx
        self._prog = prog
        prog["u_light_dir"].value = (-0.42, -0.78, -0.46)
        prog["u_fill_dir"].value = (0.62, 0.18, 0.55)
        prog["u_explode"].value = 0.0
        prog["u_selected_id"].value = -1.0
        prog["u_pull"].value = 0.0
        prog["u_dissect_mode"].value = 0.0
        prog["u_hide_armor"].value = 0.0
        prog["u_isolate_id"].value = -1.0
        prog["u_hide_layers"].value = 0.0
        prog["u_category_mask"].value = 0.0
        self.available = True
        return True

    def release(self) -> None:
        self._release_all_sets()
        self._release_fbo()
        if self._prog is not None:
            try:
                self._prog.release()
            except Exception:
                pass
            self._prog = None
        if self._ctx is not None:
            try:
                self._ctx.release()
            except Exception:
                pass
            self._ctx = None
        self.available = False
        self._cpu = None

    def clear_scene(self) -> None:
        self._release_all_sets()
        self._cpu = None
        self.block_count = 0
        self.selected_id = -1.0
        self._aabb_min = (-1.0, -1.0, -1.0)
        self._aabb_max = (1.0, 1.0, 1.0)
        self._render_origin = (0.0, 0.0, 0.0)
        self.camera_user_moved = False

    def _release_all_sets(self) -> None:
        seen: List[List[dict]] = []
        for key in list(self._sets):
            batches = self._sets[key]
            if any(batches is other for other in seen):
                self._sets[key] = []
                continue
            seen.append(batches)
            self._release_batches(batches)
            self._sets[key] = []

    def _release_batches(self, batches: List[dict]) -> None:
        for batch in batches:
            for obj in batch.get("release", []):
                try:
                    obj.release()
                except Exception:
                    pass
        batches.clear()

    def load(
        self,
        scene: PreviewScene,
        catalog: Optional[CubeBlockCatalog] = None,
        meshes: Optional[MeshLibrary] = None,
        grid_filter: Optional[str] = None,
    ) -> None:
        """Synchronous path for tests. Product UI uses upload_cpu_scene instead."""
        if not self.available:
            return
        cpu = build_preview_cpu(scene, catalog, meshes or MeshLibrary())
        self.upload_cpu_scene(cpu)
        self.set_grid_filter(grid_filter)

    def upload_cpu_scene(
        self,
        cpu: PreviewCpuScene,
        *,
        grid_filter: Optional[str] = None,
        defer_secondary: bool = False,
        refit: bool = True,
    ) -> None:
        if not self.available:
            return
        prev_empty = self._cpu is None or self.block_count == 0 or self._radius <= 1.0
        if grid_filter is not None:
            self._grid_filter = grid_filter or None
        self._cpu = cpu
        self.block_count = cpu.block_count
        self._center = cpu.center
        self._radius = cpu.radius
        self._aabb_min = cpu.aabb_min
        self._aabb_max = cpu.aabb_max
        self._apply_visible_bounds()
        more = self._begin_set_uploads(cpu, defer_secondary=defer_secondary)
        if more:
            while self.continue_cpu_upload(10**9):
                pass
        self.upload_generation += 1
        should_fit = refit or (not self.camera_user_moved) or prev_empty
        if should_fit:
            self.camera.frame(self._center, self._radius, keep_orientation=True)
            if refit:
                self.camera_user_moved = False

    def begin_cpu_upload(
        self,
        cpu: PreviewCpuScene,
        *,
        grid_filter: Optional[str] = None,
        grid_entity_id: Optional[str] = None,
        defer_secondary: bool = False,
        refit: bool = True,
        chunk_size: int = UPLOAD_BATCH_CHUNK,
    ) -> bool:
        """Upload metadata + first assembled slice. Returns True if more batches remain."""
        if not self.available:
            return False
        prev_empty = self._cpu is None or self.block_count == 0 or self._radius <= 1.0
        if grid_filter is not None:
            self._grid_filter = grid_filter or None
        if grid_entity_id is not None:
            self._grid_entity_id = grid_entity_id or None
        self._cpu = cpu
        self.block_count = cpu.block_count
        self._center = cpu.center
        self._radius = cpu.radius
        self._aabb_min = cpu.aabb_min
        self._aabb_max = cpu.aabb_max
        self._apply_visible_bounds()
        self._begin_set_uploads(cpu, defer_secondary=defer_secondary)
        self.upload_generation += 1
        should_fit = refit or (not self.camera_user_moved) or prev_empty
        if should_fit:
            self.camera.frame(self._center, self._radius, keep_orientation=True)
            if refit:
                self.camera_user_moved = False
        return bool(self._chunk_queue)

    def continue_cpu_upload(self, chunk_size: int = UPLOAD_BATCH_CHUNK) -> bool:
        """Upload the next slice of pending GPU batches. True if more remain."""
        if not self.available or not self._chunk_queue:
            self._finish_lod_aliases()
            return False
        size = max(1, int(chunk_size))
        name, batches, offset = self._chunk_queue[0]
        nxt = offset + size
        slice_batches = batches[offset:nxt]
        self._upload_named(name, slice_batches, append=offset > 0)
        if nxt >= len(batches):
            self._chunk_queue.pop(0)
        else:
            self._chunk_queue[0] = (name, batches, nxt)
        if not self._chunk_queue:
            self._finish_lod_aliases()
            self.upload_generation += 1
            return False
        return True

    def cancel_chunked_upload(self) -> None:
        self._chunk_queue = []

    def upload_pending(self) -> bool:
        return bool(self._chunk_queue)

    def uploaded_instance_count(self) -> int:
        batches = self._sets.get("assembled") or []
        return sum(int(batch.get("instances") or 0) for batch in batches)

    def _begin_set_uploads(self, cpu: PreviewCpuScene, *, defer_secondary: bool) -> bool:
        self._break_set_aliases()
        self._chunk_queue = []
        assembled = filter_batches(cpu.assembled, self._grid_filter, self._grid_entity_id)
        self._alias_assembled_lod = should_alias_lod_sets(cpu.assembled, cpu.assembled_lod) or not cpu.huge
        self._alias_exploded_lod = should_alias_lod_sets(cpu.exploded, cpu.exploded_lod) or not cpu.huge
        self._chunk_queue.append(("assembled", assembled, 0))
        if not self._alias_assembled_lod:
            self._chunk_queue.append(
                ("assembled_lod", filter_batches(cpu.assembled_lod, self._grid_filter, self._grid_entity_id), 0)
            )
        if defer_secondary:
            self._sets["exploded"] = []
            self._sets["exploded_lod"] = []
            self._secondary_pending = True
        else:
            exploded = filter_batches(cpu.exploded, self._grid_filter, self._grid_entity_id)
            self._chunk_queue.append(("exploded", exploded, 0))
            if not self._alias_exploded_lod:
                self._chunk_queue.append(
                    ("exploded_lod", filter_batches(cpu.exploded_lod, self._grid_filter, self._grid_entity_id), 0)
                )
            self._secondary_pending = False
        return True

    def _finish_lod_aliases(self) -> None:
        if self._alias_assembled_lod:
            self._sets["assembled_lod"] = self._sets.get("assembled") or []
        if not self._secondary_pending and self._alias_exploded_lod:
            self._sets["exploded_lod"] = self._sets.get("exploded") or []

    def patch_assembled(self, cpu: PreviewCpuScene) -> None:
        """Patch assembled after an MWM refine. Cancel leftover shell chunks; reuse unchanged GPU batches."""
        self.cancel_chunked_upload()
        if not self.available:
            self._cpu = cpu
            return
        self._cpu = cpu
        self.block_count = cpu.block_count
        self._break_set_aliases()
        assembled = filter_batches(cpu.assembled, self._grid_filter, self._grid_entity_id)
        self._patch_named("assembled", assembled)
        if should_alias_lod_sets(cpu.assembled, cpu.assembled_lod) or not cpu.huge:
            self._sets["assembled_lod"] = self._sets["assembled"]
        else:
            self._patch_named(
                "assembled_lod",
                filter_batches(cpu.assembled_lod, self._grid_filter, self._grid_entity_id),
            )
        if cpu.exploded and not self._secondary_pending:
            self._patch_named("exploded", filter_batches(cpu.exploded, self._grid_filter, self._grid_entity_id))
            if should_alias_lod_sets(cpu.exploded, cpu.exploded_lod) or not cpu.huge:
                self._sets["exploded_lod"] = self._sets["exploded"]
        self.upload_generation += 1
        self._write_inspect_hidden()

    def upload_secondary_sets(self) -> None:
        """Exploded / LOD-exploded buffers. Safe to call after the first blit."""
        if not self.available or self._cpu is None:
            return
        self._upload_secondary()
        self.upload_generation += 1

    def write_dissect_offsets(self, mode: str, offsets: np.ndarray) -> None:
        """Rewrite one explode channel. Does not remesh or clone instances."""
        from se_render.dissection import DISSECT_DECKS, DISSECT_RADIAL

        key = (mode or "peel").strip().lower()
        buf_key = "decks" if key == DISSECT_DECKS else ("radial" if key == DISSECT_RADIAL else "peel")
        off = np.ascontiguousarray(offsets, dtype=np.float32).reshape(-1, 3)
        seen = []
        for batches in self._sets.values():
            if any(batches is other for other in seen):
                continue
            seen.append(batches)
            for batch in batches:
                buf = (batch.get("explode_bufs") or {}).get(buf_key)
                ids = batch.get("instance_ids")
                if buf is None or ids is None:
                    continue
                index = np.asarray(ids, dtype=np.int64)
                if index.size == 0:
                    continue
                payload = np.ascontiguousarray(off[index], dtype=np.float32)
                try:
                    buf.write(payload.tobytes())
                except Exception:
                    pass

    def _break_set_aliases(self) -> None:
        """Stop lod lists from aliasing assembled/exploded so release can free GPU memory."""
        for lod_key, src_key in (("assembled_lod", "assembled"), ("exploded_lod", "exploded")):
            if self._sets.get(lod_key) is self._sets.get(src_key):
                self._sets[lod_key] = []

    def _upload_secondary(self) -> None:
        cpu = self._cpu
        if cpu is None:
            return
        if self._sets.get("exploded_lod") is self._sets.get("exploded"):
            self._sets["exploded_lod"] = []
        exploded = filter_batches(cpu.exploded, self._grid_filter, self._grid_entity_id)
        self._upload_named("exploded", exploded)
        if should_alias_lod_sets(cpu.exploded, cpu.exploded_lod) or not cpu.huge:
            self._sets["exploded_lod"] = self._sets["exploded"]
        else:
            self._upload_named(
                "exploded_lod",
                filter_batches(cpu.exploded_lod, self._grid_filter, self._grid_entity_id),
            )
        self._secondary_pending = False

    def set_grid_filter(
        self,
        grid_name: Optional[str] = None,
        grid_entity_id: Optional[str] = None,
    ) -> None:
        """Rebind instance buffers only — isolate must not remesh."""
        name = grid_name or None
        eid = grid_entity_id or None
        if (
            name == self._grid_filter
            and eid == self._grid_entity_id
            and self._cpu is not None
            and not self._secondary_pending
        ):
            self.refit_to_visible()
            return
        self._grid_filter = name
        self._grid_entity_id = eid
        if self._cpu is None or not self.available:
            return
        cpu = self._cpu
        self._apply_visible_bounds()
        self._break_set_aliases()
        assembled = filter_batches(cpu.assembled, self._grid_filter, self._grid_entity_id)
        self._upload_named("assembled", assembled)
        if should_alias_lod_sets(cpu.assembled, cpu.assembled_lod) or not cpu.huge:
            self._sets["assembled_lod"] = self._sets["assembled"]
        else:
            self._upload_named(
                "assembled_lod",
                filter_batches(cpu.assembled_lod, self._grid_filter, self._grid_entity_id),
            )
        if self._secondary_pending:
            self._sets["exploded"] = []
            self._sets["exploded_lod"] = []
        else:
            self._upload_secondary()
        self.upload_generation += 1
        self.camera.frame(self._center, self._radius, keep_orientation=True)

    def isolate_grid_instances(
        self,
        grid_entity_id: Optional[str],
        grid_name: Optional[str],
        extra_hidden: Optional[set] = None,
    ) -> None:
        """Hide other grids via inspect.z — no remesh / re-upload."""
        self._grid_entity_id = grid_entity_id or None
        self._grid_filter = grid_name or None
        hidden = set(extra_hidden or ())
        if self._cpu is not None and (self._grid_entity_id or self._grid_filter):
            for rec in self._cpu.picks:
                if self._grid_entity_id:
                    if rec.grid_entity_id != self._grid_entity_id:
                        hidden.add(rec.instance_id)
                elif rec.grid_name != self._grid_filter:
                    hidden.add(rec.instance_id)
        self.hidden_ids = hidden
        self._write_inspect_hidden()
        self._apply_visible_bounds()

    def _visible_picks(self) -> List[PickRecord]:
        if self._cpu is None:
            return []
        recs = self._cpu.picks
        if self._grid_entity_id:
            return [rec for rec in recs if rec.grid_entity_id == self._grid_entity_id]
        if self._grid_filter:
            return [rec for rec in recs if rec.grid_name == self._grid_filter]
        return list(recs)

    def _apply_visible_bounds(self) -> None:
        """AABB / origin from visible picks so clip and GPU share one center."""
        if self._cpu is None:
            return
        recs = self._visible_picks()
        if recs:
            self._aabb_min = (
                min(rec.aabb_min[0] for rec in recs),
                min(rec.aabb_min[1] for rec in recs),
                min(rec.aabb_min[2] for rec in recs),
            )
            self._aabb_max = (
                max(rec.aabb_max[0] for rec in recs),
                max(rec.aabb_max[1] for rec in recs),
                max(rec.aabb_max[2] for rec in recs),
            )
        else:
            self._aabb_min = self._cpu.aabb_min
            self._aabb_max = self._cpu.aabb_max
        self._center, self._radius = aabb_center_radius(self._aabb_min, self._aabb_max)
        self._render_origin = self._center

    def refit_to_visible(self) -> None:
        """Frame the camera on the isolated grid, or the full ship."""
        if self._cpu is None:
            return
        self._apply_visible_bounds()
        self.camera.frame(self._center, self._radius, keep_orientation=True)

    def _detach_and_release(self, name: str) -> None:
        batches = self._sets.get(name) or []
        shared = [key for key, value in self._sets.items() if key != name and value is batches]
        if shared:
            self._sets[name] = []
            return
        self._release_batches(batches)
        self._sets[name] = []

    def _patch_named(self, name: str, batches: Sequence[CpuBatch]) -> None:
        """Reuse GPU batches whose instance set + mesh size still match."""
        old = list(self._sets.get(name) or [])
        actions, release = plan_batch_delta(old, batches)
        if release:
            self._release_batches([old[i] for i in release])
        uploaded: List[dict] = []
        for action, idx in actions:
            if action == "keep":
                uploaded.append(old[idx])
            else:
                uploaded.extend(self._gpu_batches_from_cpu([batches[idx]]))
        self._sets[name] = uploaded

    def _gpu_batches_from_cpu(self, batches: Sequence[CpuBatch]) -> List[dict]:
        ctx = self._ctx
        assert ctx is not None and self._prog is not None
        uploaded: List[dict] = []
        for batch in batches:
            if batch.positions.size == 0 or batch.indices.size == 0 or batch.models.shape[0] == 0:
                continue
            vbo = ctx.buffer(batch.positions.tobytes())
            nbo = ctx.buffer(batch.normals.tobytes())
            uvbo = ctx.buffer(batch.uvs.tobytes())
            ibo = ctx.buffer(batch.indices.tobytes())
            models = _shift_instance_models(batch.models, self._render_origin)
            mbo = ctx.buffer(models.tobytes())
            cbo = ctx.buffer(batch.colors.tobytes())
            pbo = ctx.buffer(batch.params.tobytes())
            abo = ctx.buffer(batch.accents.tobytes())
            peel = _offset_channel(batch, "explode_peel")
            decks = _offset_channel(batch, "explode_decks")
            radial = _offset_channel(batch, "explode_radial")
            ebo_peel = ctx.buffer(np.ascontiguousarray(peel, dtype=np.float32).tobytes())
            ebo_decks = ctx.buffer(np.ascontiguousarray(decks, dtype=np.float32).tobytes())
            ebo_radial = ctx.buffer(np.ascontiguousarray(radial, dtype=np.float32).tobytes())
            inspect = _inspect_channel(batch)
            ibo_inspect = ctx.buffer(inspect.tobytes())
            ido = ctx.buffer(batch.instance_ids.tobytes())
            vao = ctx.vertex_array(
                self._prog,
                [
                    (vbo, "3f", "in_position"),
                    (nbo, "3f", "in_normal"),
                    (uvbo, "2f", "in_uv"),
                    (cbo, "3f /i", "in_instance_color"),
                    (pbo, "3f /i", "in_instance_params"),
                    (abo, "3f /i", "in_instance_accent"),
                    (ebo_peel, "3f /i", "in_explode_peel"),
                    (ebo_decks, "3f /i", "in_explode_decks"),
                    (ebo_radial, "3f /i", "in_explode_radial"),
                    (ibo_inspect, "3f /i", "in_inspect"),
                    (ido, "f /i", "in_instance_id"),
                    (mbo, "16f /i", "in_model"),
                ],
                ibo,
            )
            uploaded.append(
                {
                    "vao": vao,
                    "count": len(batch.indices),
                    "instances": int(batch.models.shape[0]),
                    "vertex_count": int(batch.positions.shape[0]),
                    "index_count": int(batch.indices.size),
                    "kind": batch.kind,
                    "inspect": inspect,
                    "inspect_buf": ibo_inspect,
                    "instance_ids": batch.instance_ids,
                    "explode_bufs": {
                        "peel": ebo_peel,
                        "decks": ebo_decks,
                        "radial": ebo_radial,
                    },
                    "release": [
                        vbo, nbo, uvbo, ibo, mbo, cbo, pbo, abo,
                        ebo_peel, ebo_decks, ebo_radial, ibo_inspect, ido, vao,
                    ],
                }
            )
        return uploaded

    def _upload_named(self, name: str, batches: Sequence[CpuBatch], *, append: bool = False) -> None:
        if append:
            uploaded = self._sets.get(name) or []
            uploaded.extend(self._gpu_batches_from_cpu(batches))
        else:
            self._detach_and_release(name)
            uploaded = self._gpu_batches_from_cpu(batches)
        self._sets[name] = uploaded

    def _active_batches(self, interactive: bool) -> List[dict]:
        huge = bool(self._cpu and self._cpu.huge)
        if self.hide_layers > 0 and (self._sets.get("exploded") or []):
            exploded = self._sets.get("exploded") or []
            if exploded:
                return exploded
        key = active_preview_set(self.explode, interactive, huge, self.block_count)
        batches = self._sets.get(key) or []
        if batches:
            return batches
        return self._sets.get("assembled") or []

    def fit(self) -> None:
        self.camera.frame(self._center, self._radius)

    def _release_fbo(self) -> None:
        for obj in (self._fbo, self._fbo_color, self._fbo_depth):
            if obj is None:
                continue
            try:
                obj.release()
            except Exception:
                pass
        self._fbo = None
        self._fbo_color = None
        self._fbo_depth = None
        self._size = (0, 0)

    def _ensure_fbo(self, width: int, height: int) -> None:
        ctx = self._ctx
        assert ctx is not None
        width = max(64, int(width))
        height = max(64, int(height))
        if self._fbo is not None and self._size == (width, height):
            return
        self._release_fbo()
        color = ctx.texture((width, height), 3)
        try:
            depth = ctx.depth_texture((width, height))
        except Exception:
            depth = ctx.depth_renderbuffer((width, height))
        self._fbo_color = color
        self._fbo_depth = depth
        self._fbo = ctx.framebuffer(color_attachments=[color], depth_attachment=depth)
        self._size = (width, height)

    def _clip_planes(self) -> Tuple[float, float]:
        amin, amax = self._aabb_min, self._aabb_max
        if self.explode > 1e-4:
            pad = self._radius * float(self.explode) * 1.45
            amin = (amin[0] - pad, amin[1] - pad, amin[2] - pad)
            amax = (amax[0] + pad, amax[1] + pad, amax[2] + pad)
        return clip_planes_from_aabb(
            self.camera.eye(),
            amin,
            amax,
            target=self.camera.target,
            radius=self._radius,
        )

    @property
    def framebuffer_size(self) -> Tuple[int, int]:
        return self._size

    def render(self, width: int, height: int, interactive: bool = False) -> Optional[bytes]:
        if not self.available or self._ctx is None or self._prog is None:
            return None
        rw, rh = render_target_size(width, height, interactive, block_count=self.block_count)
        self._ensure_fbo(rw, rh)
        assert self._fbo is not None
        aspect = self._size[0] / max(1, self._size[1])
        near, far = self._clip_planes()
        ox, oy, oz = self._render_origin
        eye = self.camera.eye()
        target = self.camera.target
        shifted_eye = (eye[0] - ox, eye[1] - oy, eye[2] - oz)
        shifted_target = (target[0] - ox, target[1] - oy, target[2] - oz)
        self._view_f32[:] = flatten(look_at(shifted_eye, shifted_target, (0.0, 1.0, 0.0)))
        self._proj_f32[:] = flatten(perspective(50.0, aspect, near, far, flip_y=True))
        self._prog["u_view"].write(self._view_f32.tobytes())
        self._prog["u_proj"].write(self._proj_f32.tobytes())
        self._prog["u_camera_pos"].value = shifted_eye
        self._prog["u_explode"].value = float(self.explode)
        self._prog["u_selected_id"].value = float(self.selected_id)
        self._prog["u_pull"].value = float(self.pull)
        self._prog["u_dissect_mode"].value = float(DISSECT_MODE_INDEX.get(self.dissect_mode, 0))
        self._prog["u_hide_armor"].value = 1.0 if self.hide_armor else 0.0
        self._prog["u_isolate_id"].value = float(self.isolate_id)
        self._prog["u_hide_layers"].value = float(self.hide_layers)
        self._prog["u_category_mask"].value = float(self.category_mask)
        self._fbo.use()
        self._ctx.viewport = (0, 0, self._size[0], self._size[1])
        self._ctx.enable(self._ctx.DEPTH_TEST)
        self._ctx.disable(self._ctx.CULL_FACE)
        self._ctx.clear(0.027, 0.047, 0.094, 1.0)
        for batch in self._active_batches(interactive):
            batch["vao"].render(instances=batch["instances"])
        return self._fbo.read(components=3, alignment=1)

    def pick(self, x: float, y: float, width: int, height: int) -> Optional[PickRecord]:
        if self._cpu is None:
            return None
        aspect = max(width, 1) / max(height, 1)
        near, far = self._clip_planes()
        proj = perspective(50.0, aspect, near, far, flip_y=True)
        origin, direction = self.camera.screen_ray(x, y, width, height, proj)
        best: Optional[PickRecord] = None
        best_t = 1e9
        extra_pull = self.pull if self.selected_id >= 0.0 else 0.0
        isolating = self.isolate_id >= 0.0
        for rec in self._cpu.picks:
            if self._grid_entity_id and rec.grid_entity_id != self._grid_entity_id:
                continue
            if self._grid_filter and not self._grid_entity_id and rec.grid_name != self._grid_filter:
                continue
            if isolating and abs(rec.instance_id - self.isolate_id) > 0.5:
                continue
            if not self.record_visible(rec, isolating=isolating):
                continue
            pull = extra_pull if abs(rec.instance_id - self.selected_id) < 0.5 else 0.0
            offset = explode_offset_for_mode(rec, self.dissect_mode)
            shift = (
                offset[0] * (self.explode + pull),
                offset[1] * (self.explode + pull),
                offset[2] * (self.explode + pull),
            )
            aabb_min = (
                rec.aabb_min[0] + shift[0],
                rec.aabb_min[1] + shift[1],
                rec.aabb_min[2] + shift[2],
            )
            aabb_max = (
                rec.aabb_max[0] + shift[0],
                rec.aabb_max[1] + shift[1],
                rec.aabb_max[2] + shift[2],
            )
            hit = _ray_aabb(origin, direction, aabb_min, aabb_max)
            if hit is not None and hit < best_t:
                best_t = hit
                best = rec
        return best

    def select(self, instance_id: Optional[int]) -> None:
        self.selected_id = float(instance_id) if instance_id is not None else -1.0
        if instance_id is None:
            self.isolate_id = -1.0

    def record_visible(self, rec: PickRecord, *, isolating: Optional[bool] = None) -> bool:
        if isolating is None:
            isolating = self.isolate_id >= 0.0
        if isolating and abs(rec.instance_id - self.isolate_id) > 0.5:
            return False
        if rec.instance_id in self.hidden_ids:
            return False
        if rec.subtype in self.hidden_subtypes:
            return False
        if rec.shell_layer < self.hide_layers:
            return False
        if self.hide_armor and rec.is_armor and not isolating:
            return False
        bit = 1 << int(getattr(rec, "category_code", 0) or 0)
        if self.category_mask & bit:
            return False
        return True

    def frame_selection(self, rec: Optional[PickRecord]) -> None:
        if rec is None:
            self.refit_to_visible()
            return
        span = max(
            rec.aabb_max[0] - rec.aabb_min[0],
            rec.aabb_max[1] - rec.aabb_min[1],
            rec.aabb_max[2] - rec.aabb_min[2],
            1.0,
        )
        self.camera.frame_selection(rec.center, span * 0.6 + 1.2)

    def set_user_hidden(self, instance_ids: Sequence[int]) -> None:
        self.hidden_ids = {int(i) for i in instance_ids}
        self._write_inspect_hidden()

    def _write_inspect_hidden(self) -> None:
        hidden = self.hidden_ids
        subtypes = self.hidden_subtypes
        subtype_ids = set()
        if self._cpu is not None and subtypes:
            subtype_ids = {
                rec.instance_id for rec in self._cpu.picks if rec.subtype in subtypes
            }
        for batches in self._sets.values():
            for batch in batches:
                arr = batch.get("inspect")
                buf = batch.get("inspect_buf")
                ids = batch.get("instance_ids")
                if arr is None or buf is None or ids is None:
                    continue
                for slot, iid in enumerate(ids):
                    inst = int(round(float(iid)))
                    arr[slot, 2] = 1.0 if (inst in hidden or inst in subtype_ids) else 0.0
                try:
                    buf.write(arr.tobytes())
                except Exception:
                    pass


def _shift_instance_models(models: np.ndarray, origin: Sequence[float]) -> np.ndarray:
    """Column-major translations relative to the hull origin (GPU float32 precision)."""
    out = np.array(models, dtype=np.float32, copy=True)
    if out.size == 0:
        return out
    out[:, 12] -= float(origin[0])
    out[:, 13] -= float(origin[1])
    out[:, 14] -= float(origin[2])
    return np.ascontiguousarray(out, dtype=np.float32)


def _inspect_channel(batch: CpuBatch) -> np.ndarray:
    arr = getattr(batch, "inspect", None)
    n = int(batch.models.shape[0]) if getattr(batch, "models", None) is not None else 0
    if arr is None or getattr(arr, "size", 0) == 0:
        return np.zeros((n, 3), dtype=np.float32)
    return np.ascontiguousarray(arr, dtype=np.float32)


def _offset_channel(batch: CpuBatch, name: str) -> np.ndarray:
    arr = getattr(batch, name, None)
    if arr is None or getattr(arr, "size", 0) == 0:
        return batch.explode
    return arr


def scene_bounds_caption(
    scene: PreviewScene,
    grid_filter: Optional[str] = None,
    declared_total: Optional[int] = None,
    *,
    shown: Optional[int] = None,
    simplified: bool = False,
    grid_entity_id: Optional[str] = None,
    uploading: bool = False,
) -> str:
    if grid_entity_id or grid_filter:
        blocks = scene.filter_grid(grid_filter, grid_entity_id).blocks
    else:
        blocks = scene.blocks
    if not blocks:
        return "No blocks on this grid." if (grid_filter or grid_entity_id) else "No ship loaded"
    prefix = f"{grid_filter}  ·  " if grid_filter else ""
    count = int(shown) if shown is not None else len(blocks)
    total = int(declared_total or scene.total_blocks or len(blocks))
    if grid_filter:
        if uploading and total > count:
            return f"{prefix}{count:,} of {total:,} blocks  ·  uploading"
        return f"{prefix}{count:,} blocks  ·  3D preview"
    return prefix + format_preview_count_caption(count, total, simplified=simplified, uploading=uploading)

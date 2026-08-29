"""ModernGL ship preview hosted as a CustomTkinter pane."""

from __future__ import annotations

from typing import Dict, List, Optional

import numpy as np

from se_assets.cube_catalog import CubeBlockCatalog
from se_assets.mesh_cache import MeshLibrary
from se_render.camera import OrbitCamera, flatten, perspective
from se_render.gl_backend import last_gl_error, mark_gl_failed, try_create_context
from se_render.orientation import cell_size_meters, mul_mat4, translation_mat4
from se_render.scene_graph import BlockInstance, PreviewScene
from se_render.shaders import FRAGMENT_SHADER, VERTEX_SHADER
from se_render.topology import MeshData


class GLPreviewRenderer:
    """Off-screen ModernGL renderer. Safe to construct; check .available."""

    def __init__(self) -> None:
        self.available = False
        self.error = ""
        self._ctx = None
        self._prog = None
        self._fbo = None
        self._size = (0, 0)
        self._batches: List[dict] = []
        self.camera = OrbitCamera()
        self._center = (0.0, 0.0, 0.0)
        self._radius = 10.0
        self.block_count = 0
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
        self.available = True
        return True

    def release(self) -> None:
        self._batches = []
        if self._fbo is not None:
            try:
                self._fbo.release()
            except Exception:
                pass
            self._fbo = None
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

    def load(
        self,
        scene: PreviewScene,
        catalog: Optional[CubeBlockCatalog] = None,
        meshes: Optional[MeshLibrary] = None,
        grid_filter: Optional[str] = None,
    ) -> None:
        if not self.available:
            return
        visible = scene.filter_grid(grid_filter).blocks if grid_filter else scene.blocks
        self.block_count = len(visible)
        library = meshes or MeshLibrary()
        groups: Dict[int, List[BlockInstance]] = {}
        mesh_for_group: Dict[int, MeshData] = {}
        for block in visible:
            definition = catalog.get(block.type_id, block.subtype) if catalog else None
            size = definition.size if definition is not None else (1, 1, 1)
            mesh = library.mesh_for(definition, block.subtype, size, block.grid_size)
            key = id(mesh)
            groups.setdefault(key, []).append(block)
            mesh_for_group[key] = mesh

        self._rebuild_batches(groups, mesh_for_group, catalog)
        self._compute_bounds(visible)
        self.camera.frame(self._center, self._radius)

    def _rebuild_batches(
        self,
        groups: Dict[int, List[BlockInstance]],
        meshes: Dict[int, MeshData],
        catalog: Optional[CubeBlockCatalog],
    ) -> None:
        ctx = self._ctx
        assert ctx is not None and self._prog is not None
        for batch in self._batches:
            for obj in batch.get("release", []):
                try:
                    obj.release()
                except Exception:
                    pass
        self._batches = []
        for key, instances in groups.items():
            mesh = meshes[key]
            if mesh.vertex_count == 0 or mesh.indices.size == 0:
                continue
            vbo = ctx.buffer(np.ascontiguousarray(mesh.positions).tobytes())
            nbo = ctx.buffer(np.ascontiguousarray(mesh.normals).tobytes())
            ibo = ctx.buffer(np.ascontiguousarray(mesh.indices).tobytes())
            models = np.zeros((len(instances), 16), dtype=np.float32)
            colors = np.zeros((len(instances), 3), dtype=np.float32)
            for i, block in enumerate(instances):
                definition = catalog.get(block.type_id, block.subtype) if catalog else None
                sx, sy, sz = definition.size if definition is not None else (1, 1, 1)
                cell = cell_size_meters(block.grid_size)
                offset = translation_mat4((
                    (sx - 1) * 0.5 * cell,
                    (sy - 1) * 0.5 * cell,
                    (sz - 1) * 0.5 * cell,
                ))
                model = mul_mat4(block.world_matrix, offset)
                models[i] = np.array(flatten(model), dtype=np.float32)
                colors[i] = block.color_rgb
            mbo = ctx.buffer(models.tobytes())
            cbo = ctx.buffer(colors.tobytes())
            vao = ctx.vertex_array(
                self._prog,
                [
                    (vbo, "3f", "in_position"),
                    (nbo, "3f", "in_normal"),
                    (cbo, "3f /i", "in_instance_color"),
                    (mbo, "16f /i", "in_model"),
                ],
                ibo,
            )
            self._batches.append(
                {
                    "vao": vao,
                    "count": len(mesh.indices),
                    "instances": len(instances),
                    "release": [vbo, nbo, ibo, mbo, cbo, vao],
                }
            )

    def _compute_bounds(self, blocks: List[BlockInstance]) -> None:
        if not blocks:
            self._center = (0.0, 0.0, 0.0)
            self._radius = 10.0
            return
        xs, ys, zs = [], [], []
        for block in blocks:
            t = (block.world_matrix[0][3], block.world_matrix[1][3], block.world_matrix[2][3])
            xs.append(t[0])
            ys.append(t[1])
            zs.append(t[2])
        self._center = (
            (min(xs) + max(xs)) * 0.5,
            (min(ys) + max(ys)) * 0.5,
            (min(zs) + max(zs)) * 0.5,
        )
        span = max(max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs), 2.5)
        self._radius = span * 0.6 + 4.0

    def fit(self) -> None:
        self.camera.frame(self._center, self._radius)

    def _ensure_fbo(self, width: int, height: int) -> None:
        ctx = self._ctx
        assert ctx is not None
        width = max(64, int(width))
        height = max(64, int(height))
        if self._fbo is not None and self._size == (width, height):
            return
        if self._fbo is not None:
            try:
                self._fbo.release()
            except Exception:
                pass
        color = ctx.texture((width, height), 3)
        depth = ctx.depth_renderbuffer((width, height))
        self._fbo = ctx.framebuffer(color_attachments=[color], depth_attachment=depth)
        self._size = (width, height)

    def render(self, width: int, height: int) -> Optional[bytes]:
        if not self.available or self._ctx is None or self._prog is None:
            return None
        self._ensure_fbo(width, height)
        assert self._fbo is not None
        aspect = self._size[0] / max(1, self._size[1])
        near = max(0.1, self.camera.distance / 80.0)
        far = max(near + 10.0, self.camera.distance + self._radius * 8.0)
        self._prog["u_view"].write(np.array(flatten(self.camera.view_matrix()), dtype=np.float32).tobytes())
        self._prog["u_proj"].write(np.array(flatten(perspective(50.0, aspect, near, far)), dtype=np.float32).tobytes())
        self._prog["u_light_dir"].value = (-0.35, -0.85, -0.4)
        self._prog["u_camera_pos"].value = self.camera.eye()
        self._fbo.use()
        self._ctx.viewport = (0, 0, self._size[0], self._size[1])
        self._ctx.enable(self._ctx.DEPTH_TEST)
        self._ctx.disable(self._ctx.CULL_FACE)
        self._ctx.clear(0.027, 0.047, 0.094, 1.0)
        for batch in self._batches:
            batch["vao"].render(instances=batch["instances"])
        return self._fbo.read(components=3, alignment=1)


def scene_bounds_caption(scene: PreviewScene, grid_filter: Optional[str] = None) -> str:
    blocks = scene.filter_grid(grid_filter).blocks if grid_filter else scene.blocks
    if not blocks:
        return "No blocks on this grid." if grid_filter else "No ship loaded"
    prefix = f"{grid_filter}  ·  " if grid_filter else ""
    return f"{prefix}{len(blocks):,} blocks  ·  3D preview"

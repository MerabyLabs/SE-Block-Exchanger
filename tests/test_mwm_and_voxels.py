import struct
import tempfile
import unittest
from pathlib import Path
import xml.etree.ElementTree as ET

from se_assets.mwm_loader import load_mwm
from subgrid_engine.visualizer_matrix import GridMatrixVisualizer


def _write_string(text: str) -> bytes:
    encoded = text.encode("ascii")
    return bytes([len(encoded)]) + encoded


def _u32(value: int) -> bytes:
    return struct.pack("<I", value)


def _hfloat_bytes(value: float) -> bytes:
    # Pack as IEEE754 binary16 via round-trip through struct if available,
    # otherwise store a crude half-float for 0/1 values used here.
    import struct as st

    f32 = st.unpack("<I", st.pack("<f", value))[0]
    sign = (f32 >> 31) & 1
    exp = (f32 >> 23) & 0xFF
    frac = f32 & 0x7FFFFF
    if exp == 0:
        h = sign << 15
    elif exp == 255:
        h = (sign << 15) | 0x7C00
    else:
        e = exp - 127 + 15
        if e <= 0 or e >= 31:
            h = sign << 15
        else:
            h = (sign << 15) | (e << 10) | (frac >> 13)
    return st.pack("<H", h)


def _build_minimal_mwm() -> bytes:
    # Placeholder index, then rewrite offsets after payload is known.
    vertices = _write_string("Vertices") + _u32(3)
    for x, y, z in ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)):
        vertices += _hfloat_bytes(x) + _hfloat_bytes(y) + _hfloat_bytes(z) + _hfloat_bytes(1.0)
    uvs = _write_string("TexCoords0") + _u32(3)
    for _ in range(3):
        uvs += _hfloat_bytes(0.0) + _hfloat_bytes(0.0)
    parts = _write_string("MeshParts") + _u32(1)
    parts += _u32(0)  # material hash
    parts += _u32(3)  # index count
    parts += _u32(0) + _u32(1) + _u32(2)
    parts += bytes([0])  # no material

    header = _write_string("Mesh") + _u32(0) + _write_string("Version:1062001")
    # index will be appended after we know header+index size
    tags = ("Vertices", "TexCoords0", "MeshParts")
    # Compute index size: u32 count + for each (1+len(name)+4)
    index_size = 4 + sum(1 + len(t) + 4 for t in tags)
    base = len(header) + index_size
    offsets = {
        "Vertices": base,
        "TexCoords0": base + len(vertices),
        "MeshParts": base + len(vertices) + len(uvs),
    }
    index = _u32(3)
    for tag in tags:
        index += _write_string(tag) + _u32(offsets[tag])
    return header + index + vertices + uvs + parts


def _build_lod_list_mwm(paths: list) -> bytes:
    payload = _write_string("LODs") + _u32(len(paths))
    for rel in paths:
        payload += struct.pack("<f", 20.0) + _write_string(rel) + b"\x00"
    header = _write_string("Debug") + _u32(1) + _write_string("Version:01157002")
    index_size = 4 + (1 + len("LODs") + 4)
    base = len(header) + index_size
    index = _u32(1) + _write_string("LODs") + _u32(base)
    return header + index + payload


def _build_geometry_asset_mwm(relative: str) -> bytes:
    payload = _write_string("GeometryDataAsset") + _write_string(relative)
    header = _write_string("Debug") + _u32(1) + _write_string("Version:01157002")
    index_size = 4 + (1 + len("GeometryDataAsset") + 4)
    base = len(header) + index_size
    index = _u32(1) + _write_string("GeometryDataAsset") + _u32(base)
    return header + index + payload


def _build_two_part_mwm() -> bytes:
    vertices = _write_string("Vertices") + _u32(4)
    for x, y, z in ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (1.0, 1.0, 0.0), (0.0, 1.0, 0.0)):
        vertices += _hfloat_bytes(x) + _hfloat_bytes(y) + _hfloat_bytes(z) + _hfloat_bytes(1.0)
    uvs = _write_string("TexCoords0") + _u32(4)
    for _ in range(4):
        uvs += _hfloat_bytes(0.0) + _hfloat_bytes(0.0)
    mat = _write_string("Steel") + _u32(1)
    mat += _write_string("ColorMetalTexture") + _write_string("cm.dds")
    mat += struct.pack("<f", 0.0) + _write_string("MESH")
    parts = _write_string("MeshParts") + _u32(2)
    parts += _u32(1) + _u32(3) + _u32(0) + _u32(1) + _u32(2) + bytes([1]) + mat
    parts += _u32(2) + _u32(3) + _u32(0) + _u32(2) + _u32(3) + bytes([0])
    header = _write_string("Mesh") + _u32(0) + _write_string("Version:01157002")
    tags = ("Vertices", "TexCoords0", "MeshParts")
    index_size = 4 + sum(1 + len(t) + 4 for t in tags)
    base = len(header) + index_size
    offsets = {
        "Vertices": base,
        "TexCoords0": base + len(vertices),
        "MeshParts": base + len(vertices) + len(uvs),
    }
    index = _u32(3)
    for tag in tags:
        index += _write_string(tag) + _u32(offsets[tag])
    return header + index + vertices + uvs + parts


class MwmLoaderTests(unittest.TestCase):
    def test_reads_minimal_triangle(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "box.mwm"
            path.write_bytes(_build_minimal_mwm())
            mesh = load_mwm(path)
            self.assertIsNotNone(mesh)
            self.assertEqual(len(mesh.positions), 3)
            self.assertEqual(mesh.indices, [0, 1, 2])

    def test_missing_file_returns_none(self):
        self.assertIsNone(load_mwm(Path("/no/such/model.mwm")))

    def test_follows_nul_terminated_lod_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            child = root / "Gyro_LOD3.mwm"
            child.write_bytes(_build_minimal_mwm())
            parent = root / "Gyro.mwm"
            parent.write_bytes(_build_lod_list_mwm(["Cubes\\Gyro_LOD3"]))
            mesh = load_mwm(parent, quality="low")
            self.assertIsNotNone(mesh)
            self.assertEqual(len(mesh.positions), 3)

    def test_follows_geometry_data_asset(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            child = root / "Gyro_LOD2.mwm"
            child.write_bytes(_build_minimal_mwm())
            parent = root / "Gyro.mwm"
            parent.write_bytes(_build_geometry_asset_mwm("Gyro_LOD2"))
            mesh = load_mwm(parent)
            self.assertIsNotNone(mesh)
            self.assertEqual(len(mesh.positions), 3)
            self.assertEqual(mesh.indices, [0, 1, 2])

    def test_new_material_keeps_second_mesh_part(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "parts.mwm"
            path.write_bytes(_build_two_part_mwm())
            mesh = load_mwm(path)
            self.assertIsNotNone(mesh)
            self.assertEqual(len(mesh.positions), 4)
            self.assertEqual(len(mesh.indices), 6)
            self.assertEqual(mesh.indices, [0, 1, 2, 0, 2, 3])


class VoxelExtractTests(unittest.TestCase):
    def test_includes_keen_hsv(self):
        xml = """<?xml version="1.0"?>
        <Definitions>
          <CubeGrid>
            <DisplayName>G</DisplayName>
            <GridSizeEnum>Large</GridSizeEnum>
            <CubeBlocks>
              <MyObjectBuilder_CubeBlock>
                <SubtypeName>LargeBlockArmorBlock</SubtypeName>
                <Min x="1" y="2" z="3" />
                <ColorMaskHSV x="0.1" y="0.2" z="0.3" />
              </MyObjectBuilder_CubeBlock>
            </CubeBlocks>
          </CubeGrid>
        </Definitions>
        """
        voxels = GridMatrixVisualizer.extract_voxels_from_root(ET.fromstring(xml))
        self.assertEqual(len(voxels), 1)
        self.assertEqual(voxels[0]["x"], 1)
        self.assertAlmostEqual(voxels[0]["hsv"][1], 0.2)
        self.assertIsNotNone(voxels[0]["color_rgb"])


if __name__ == "__main__":
    unittest.main()

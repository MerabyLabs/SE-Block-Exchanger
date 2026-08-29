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

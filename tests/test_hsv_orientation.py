import math
import unittest

from se_render.hsv import hsv_offset_to_rgb, hsv_offset_to_standard, rgb_to_hsv_offset
from se_render.orientation import (
    BASE6,
    cell_size_meters,
    orientation_matrix,
    pose_matrix,
    transform_dir,
    transform_point,
)


class HsvOffsetTests(unittest.TestCase):
    def test_official_offset_to_standard(self):
        h, s, v = hsv_offset_to_standard(0.0, 0.0, 0.0)
        self.assertAlmostEqual(h, 0.0)
        self.assertAlmostEqual(s, 0.8)
        self.assertAlmostEqual(v, 0.45)

    def test_clamps_and_roundtrip_neutral_gray(self):
        rgb = hsv_offset_to_rgb(0.0, -0.8, 0.55)
        self.assertTrue(all(0.0 <= c <= 1.0 for c in rgb))
        # S = 0, V = 1 → white
        self.assertAlmostEqual(rgb[0], 1.0, places=5)
        self.assertAlmostEqual(rgb[1], 1.0, places=5)
        self.assertAlmostEqual(rgb[2], 1.0, places=5)
        back = rgb_to_hsv_offset(*rgb)
        self.assertAlmostEqual(back[1], -0.8, places=5)
        self.assertAlmostEqual(back[2], 0.55, places=5)


class OrientationTests(unittest.TestCase):
    def test_cell_sizes(self):
        self.assertEqual(cell_size_meters("Large"), 2.5)
        self.assertEqual(cell_size_meters("Small"), 0.5)

    def test_default_orientation_is_identity_axes(self):
        right, up, backward = orientation_matrix("Forward", "Up")
        self.assertEqual(right, BASE6["Right"])
        self.assertEqual(up, BASE6["Up"])
        self.assertEqual(backward, BASE6["Backward"])

    def test_rotated_forward_left(self):
        right, up, backward = orientation_matrix("Left", "Up")
        # Forward=Left (-X) → backward = +X
        self.assertEqual(backward, BASE6["Right"])
        self.assertEqual(up, BASE6["Up"])

    def test_pose_places_origin(self):
        matrix = pose_matrix((10.0, 4.0, -2.0), BASE6["Forward"], BASE6["Up"])
        origin = transform_point(matrix, (0.0, 0.0, 0.0))
        self.assertEqual(origin, (10.0, 4.0, -2.0))
        fwd = transform_dir(matrix, (0.0, 0.0, -1.0))
        self.assertTrue(math.isclose(fwd[2], -1.0, abs_tol=1e-6))


if __name__ == "__main__":
    unittest.main()

import inspect
import unittest

from ui.widgets.ship_preview import ShipPreviewHost


class ShipPreviewWheelBindTests(unittest.TestCase):
    def test_grab_wheel_does_not_call_ctk_bind_all(self):
        grab = inspect.getsource(ShipPreviewHost._grab_wheel)
        release = inspect.getsource(ShipPreviewHost._maybe_release_wheel)
        destroy = inspect.getsource(ShipPreviewHost.destroy)
        enter = inspect.getsource(ShipPreviewHost._on_gl_enter)
        self.assertNotIn("self.bind_all", grab)
        self.assertNotIn("self.unbind_all", grab)
        self.assertNotIn("self.unbind_all", release)
        self.assertNotIn("self.unbind_all", destroy)
        self.assertIn("focus_set", grab)
        self.assertIn("_grab_wheel", enter)


if __name__ == "__main__":
    unittest.main()

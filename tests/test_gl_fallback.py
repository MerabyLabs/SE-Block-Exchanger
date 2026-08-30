import unittest

from se_render.gl_backend import gl_is_available, last_gl_error, reset_gl_probe, try_create_context


class GlFallbackTests(unittest.TestCase):
    def test_probe_does_not_raise(self):
        reset_gl_probe()
        available = gl_is_available()
        self.assertIsInstance(available, bool)
        if not available:
            self.assertTrue(last_gl_error())

    def test_try_create_context_is_optional(self):
        ctx = try_create_context()
        if ctx is not None:
            ctx.release()


if __name__ == "__main__":
    unittest.main()

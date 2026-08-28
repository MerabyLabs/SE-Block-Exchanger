"""Tests for hardened XML parsing."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import safe_xml


class TestSafeXml(unittest.TestCase):
    def test_parse_valid_blueprint(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bp.sbc"
            path.write_text(
                '<?xml version="1.0"?><Definitions><CubeBlocks/></Definitions>',
                encoding="utf-8",
            )
            tree = safe_xml.parse(path)
            self.assertEqual(tree.getroot().tag, "Definitions")

    def test_hardened_flag_matches_defusedxml(self):
        try:
            import defusedxml.ElementTree  # noqa: F401

            self.assertTrue(safe_xml.HARDENED)
        except ImportError:
            self.assertFalse(safe_xml.HARDENED)

    def test_rejects_external_entity_when_hardened(self):
        if not safe_xml.HARDENED:
            self.skipTest("defusedxml is not installed")

        with tempfile.TemporaryDirectory() as tmp:
            marker = Path(tmp) / "marker.txt"
            marker.write_text("xxe-probe", encoding="utf-8")
            payload = Path(tmp) / "evil.xml"
            payload.write_text(
                (
                    '<?xml version="1.0"?>'
                    f'<!DOCTYPE foo [<!ENTITY xxe SYSTEM "{marker.as_uri()}">]>'
                    "<root><data>&xxe;</data></root>"
                ),
                encoding="utf-8",
            )
            with self.assertRaises(Exception):
                safe_xml.parse(payload)


if __name__ == "__main__":
    unittest.main()

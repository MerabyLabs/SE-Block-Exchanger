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
            payload = Path(tmp) / "evil.xml"
            # Dummy DTD probe for XXE rejection — not a credential or secret.
            payload.write_text(
                (
                    '<?xml version="1.0"?>'
                    '<!DOCTYPE probe [<!ENTITY sample SYSTEM "file:///nonexistent-xxe-probe">]>'
                    "<root><data>&sample;</data></root>"
                ),
                encoding="utf-8",
            )
            with self.assertRaises(Exception):
                safe_xml.parse(payload)

    def test_safe_write_and_get_subtype(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bp.sbc"
            path.write_text(
                '<?xml version="1.0"?><Definitions><CubeBlocks>'
                "<MyObjectBuilder_CubeBlock><SubtypeName>LargeBlockArmorBlock</SubtypeName>"
                "</MyObjectBuilder_CubeBlock></CubeBlocks></Definitions>",
                encoding="utf-8",
            )
            tree = safe_xml.parse(path)
            block = tree.getroot().find(".//MyObjectBuilder_CubeBlock")
            self.assertEqual(safe_xml.get_subtype(block), "LargeBlockArmorBlock")
            out = Path(tmp) / "out.sbc"
            safe_xml.safe_write(tree, out)
            self.assertTrue(out.exists())
            self.assertEqual(safe_xml.parse(out).getroot().tag, "Definitions")


if __name__ == "__main__":
    unittest.main()

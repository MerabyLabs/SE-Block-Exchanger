"""Tests for ArmorBlockReplacer features not covered by the original suite."""

from __future__ import annotations

import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
import tempfile

from blueprint_fixtures import write_blueprint, write_blueprint_dir
from mappings.armor import ARMOR_PAIRS
from mappings.dlc_substitution import DLC_TO_BASE_PAIRS
from mappings.functional import FUNCTIONAL_PAIRS
from mappings.registry import MappingValidationError
from mappings.thrusters import THRUSTER_PAIRS
from mappings.weapons import WEAPON_PAIRS
from se_armor_replacer import ArmorBlockReplacer, _split_categories
from verify_mappings import verify


class TestReplacerExtended(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_all_categories_excludes_conflicting_profiles(self):
        replacer = ArmorBlockReplacer(enabled_categories=["all"], include_profiles=True)
        names = set(replacer.enabled_categories)
        self.assertEqual(names, {"armor", "dlc_substitution", "functional", "thrusters", "weapons"})
        self.assertIn("LargeBlockSmallThrustSciFi", replacer.mapping)
        self.assertIn("LargeBlockArmorBlock", replacer.mapping)

    def test_conflicting_profiles_cannot_be_merged(self):
        with self.assertRaises(MappingValidationError):
            ArmorBlockReplacer(
                enabled_categories=[
                    "profile:weaponcore upgrades:wc fixed weapons",
                    "profile:assertive armaments:aa small weapons",
                ],
                include_profiles=True,
            )

    def test_split_categories_helpers(self):
        self.assertEqual(_split_categories(None, True), ["all"])
        self.assertIsNone(_split_categories(None, False))
        self.assertEqual(_split_categories("armor, thrusters", False), ["armor", "thrusters"])

    def test_subtype_id_only_block_is_converted(self):
        root = ET.Element("Definitions")
        cubes = ET.SubElement(ET.SubElement(ET.SubElement(root, "ShipBlueprints"), "ShipBlueprint"), "CubeBlocks")
        block = ET.SubElement(cubes, "MyObjectBuilder_CubeBlock")
        ET.SubElement(block, "SubtypeId").text = "LargeBlockArmorBlock"
        path = self.root / "bp.sbc"
        ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)

        replacer = ArmorBlockReplacer(include_profiles=False)
        scanned, replaced = replacer.process_blueprint(str(path), create_backup=False)
        self.assertEqual(scanned, 1)
        self.assertEqual(replaced, 1)
        tree = ET.parse(path)
        self.assertEqual(tree.find(".//SubtypeId").text, "LargeHeavyBlockArmorBlock")

    def test_find_blueprint_nested_folder(self):
        nested = self.root / "local" / "Ship"
        write_blueprint_dir(nested.parent, "Ship", ["LargeBlockArmorBlock"])
        replacer = ArmorBlockReplacer(include_profiles=False)
        found = replacer.find_blueprint_file(self.root)
        self.assertEqual(found.name, "bp.sbc")

    def test_find_blueprint_picks_sorted_sbc_when_no_bp(self):
        zebra = self.root / "zebra"
        alpha = self.root / "alpha"
        zebra.mkdir()
        alpha.mkdir()
        (zebra / "ship.sbc").write_text("<Definitions/>", encoding="utf-8")
        (alpha / "ship.sbc").write_text("<Definitions/>", encoding="utf-8")
        replacer = ArmorBlockReplacer(include_profiles=False)
        found = replacer.find_blueprint_file(self.root)
        self.assertEqual(found, alpha / "ship.sbc")

    def test_missing_sbc_error_mentions_any_sbc(self):
        replacer = ArmorBlockReplacer(include_profiles=False)
        with self.assertRaises(FileNotFoundError) as ctx:
            replacer.find_blueprint_file(self.root)
        message = str(ctx.exception)
        self.assertIn("Could not find bp.sbc", message)
        self.assertIn("any .sbc", message)

    def test_backup_numbering(self):
        path = write_blueprint(self.root / "bp.sbc", ["LargeBlockArmorBlock"])
        replacer = ArmorBlockReplacer(include_profiles=False)
        first = replacer.backup_file(path)
        second = replacer.backup_file(path)
        self.assertEqual(first.name, "bp.sbc.backup")
        self.assertEqual(second.name, "bp.sbc.backup1")
        self.assertTrue(first.exists())
        self.assertTrue(second.exists())

    def test_binary_cache_removed_on_write(self):
        path = write_blueprint(self.root / "bp.sbc", ["LargeBlockArmorBlock"])
        cache = self.root / "bp.sbcB5"
        cache.write_text("binary", encoding="utf-8")
        replacer = ArmorBlockReplacer(include_profiles=False)
        replacer.process_blueprint(str(path), create_backup=False)
        self.assertFalse(cache.exists())

    def test_invalid_xml_raises_value_error(self):
        path = self.root / "bp.sbc"
        path.write_text("<not-xml", encoding="utf-8")
        replacer = ArmorBlockReplacer(include_profiles=False)
        with self.assertRaises(ValueError):
            replacer.process_blueprint(str(path), create_backup=False)

    def test_empty_tree_returns_zero(self):
        replacer = ArmorBlockReplacer(include_profiles=False)
        tree = ET.ElementTree(ET.Element("Definitions"))
        self.assertEqual(replacer.replace_blocks(tree), 0)

    def test_verbose_logging_and_summary(self):
        path = write_blueprint(self.root / "bp.sbc", ["LargeBlockSmallThrust"])
        replacer = ArmorBlockReplacer(
            verbose=True,
            enabled_categories=["thrusters"],
            include_profiles=False,
        )
        replacer.process_blueprint(str(path), create_backup=False)
        summary = replacer.get_replacement_summary()
        self.assertIn("thrusters", summary)
        self.assertIn("replaced 1", summary)

    def test_dry_run_report_empty(self):
        replacer = ArmorBlockReplacer(include_profiles=False)
        self.assertEqual(replacer.get_dry_run_report(), "No changes would be made.")

    def test_profile_category_short_name_resolution(self):
        replacer = ArmorBlockReplacer(
            enabled_categories=["build vision utility"],
            include_profiles=True,
        )
        self.assertTrue(any(name.endswith(":build vision utility") for name in replacer.enabled_categories))

    def test_unknown_and_ambiguous_categories(self):
        with self.assertRaises(ValueError):
            ArmorBlockReplacer(enabled_categories=["nope"], include_profiles=False)

    def test_builtin_pair_counts(self):
        self.assertEqual(len(ARMOR_PAIRS), 70)
        self.assertEqual(len(THRUSTER_PAIRS), 6)
        self.assertEqual(len(WEAPON_PAIRS), 5)
        self.assertEqual(len(FUNCTIONAL_PAIRS), 6)
        self.assertEqual(len(DLC_TO_BASE_PAIRS), 45)

    def test_verify_mappings_passes(self):
        verify()

    def test_list_categories_shape(self):
        replacer = ArmorBlockReplacer(include_profiles=False)
        rows = replacer.list_categories()
        names = {row[0] for row in rows}
        self.assertIn("armor", names)
        self.assertTrue(all(count > 0 for _, _, count in rows))


if __name__ == "__main__":
    unittest.main()

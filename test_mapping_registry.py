import unittest

from mappings import build_registry
from mappings.registry import MappingCategory, MappingRegistry, MappingValidationError


class TestMappingRegistry(unittest.TestCase):
    def test_builtin_categories_exist(self):
        registry = build_registry(include_builtin=True)
        names = [category.name for category in registry.list_categories()]
        self.assertIn("armor", names)
        self.assertIn("thrusters", names)
        self.assertIn("weapons", names)
        self.assertIn("functional", names)

    def test_build_mapping_from_selected_categories(self):
        registry = build_registry(include_builtin=True)
        mapping = registry.build_mapping(reverse=False, enabled_categories=["armor", "thrusters"])
        self.assertIn("LargeBlockArmorBlock", mapping)
        self.assertIn("LargeBlockSmallThrust", mapping)
        self.assertNotIn("SmallGatlingGun", mapping)

    def test_reverse_mapping(self):
        registry = build_registry(include_builtin=True)
        reverse_map = registry.build_mapping(reverse=True, enabled_categories=["armor"])
        self.assertEqual(reverse_map["LargeHeavyBlockArmorBlock"], "LargeBlockArmorBlock")

    def test_invalid_category_detected(self):
        registry = MappingRegistry()
        bad = MappingCategory(
            name="bad",
            description="bad",
            pairs={"A": "B", "B": "A"},
        )
        with self.assertRaises(MappingValidationError):
            registry.register(bad)

    def test_dlc_category_exists(self):
        registry = build_registry(include_builtin=True)
        self.assertTrue(registry.exists("dlc_substitution"))
        self.assertTrue(registry.exists("ARMOR"))
        self.assertFalse(registry.exists("missing"))

    def test_enable_flags_and_unregister(self):
        registry = build_registry(include_builtin=True)
        registry.set_enabled("thrusters", True)
        self.assertTrue(registry.is_enabled("thrusters"))
        mapping = registry.build_mapping()
        self.assertIn("LargeBlockArmorBlock", mapping)
        self.assertIn("LargeBlockSmallThrust", mapping)
        registry.unregister("thrusters")
        self.assertFalse(registry.exists("thrusters"))

    def test_duplicate_source_across_categories(self):
        registry = MappingRegistry()
        registry.register(
            MappingCategory(name="a", description="A", pairs={"X": "Y"})
        )
        registry.register(
            MappingCategory(name="b", description="B", pairs={"X": "Z"})
        )
        with self.assertRaises(MappingValidationError):
            registry.build_mapping(enabled_categories=["a", "b"])

    def test_empty_name_rejected(self):
        registry = MappingRegistry()
        with self.assertRaises(MappingValidationError):
            registry.register(MappingCategory(name=" ", description="d", pairs={"A": "B"}))

    def test_identity_mapping_rejected(self):
        with self.assertRaises(MappingValidationError):
            MappingRegistry.validate_pairs({"Same": "Same"})

    def test_get_unknown_category(self):
        registry = MappingRegistry()
        with self.assertRaises(KeyError):
            registry.get("nope")
        with self.assertRaises(KeyError):
            registry.set_enabled("nope", True)


if __name__ == "__main__":
    unittest.main()


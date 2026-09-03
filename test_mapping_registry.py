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
        self.assertNotIn("LargeBlockSmallThrust", mapping)
        self.assertTrue(next(c for c in registry.list_categories() if c.name == "thrusters").validation_issues)
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


if __name__ == "__main__":
    unittest.main()


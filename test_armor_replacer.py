"""
Unit tests for Space Engineers Armor Block Replacer
"""

import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
import tempfile
import shutil
from se_armor_replacer import ArmorBlockReplacer
from blueprint_scanner import BlueprintScanner


class TestArmorBlockReplacer(unittest.TestCase):
    """Test cases for ArmorBlockReplacer class."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.replacer = ArmorBlockReplacer(verbose=False)
        self.test_dir = Path(tempfile.mkdtemp())
    
    def tearDown(self):
        """Clean up test files."""
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)
    
    def create_test_blueprint(self, blocks: list) -> Path:
        """Create a test blueprint XML file with specified blocks."""
        root = ET.Element('Definitions')
        root.set('xmlns:xsi', 'http://www.w3.org/2001/XMLSchema-instance')
        root.set('xmlns:xsd', 'http://www.w3.org/2001/XMLSchema')
        
        ship_blueprints = ET.SubElement(root, 'ShipBlueprints')
        ship_blueprint = ET.SubElement(ship_blueprints, 'ShipBlueprint')
        cube_blocks = ET.SubElement(ship_blueprint, 'CubeBlocks')
        
        for subtype_id in blocks:
            block = ET.SubElement(cube_blocks, 'MyObjectBuilder_CubeBlock')
            subtype_id_elem = ET.SubElement(block, 'SubtypeId')
            subtype_id_elem.text = subtype_id
            subtype_name_elem = ET.SubElement(block, 'SubtypeName')
            subtype_name_elem.text = subtype_id
        
        tree = ET.ElementTree(root)
        test_file = self.test_dir / 'bp.sbc'
        tree.write(test_file, encoding='utf-8', xml_declaration=True)
        
        return test_file
    
    def test_light_to_heavy_replacement(self):
        """Test basic light armor to heavy armor replacement."""
        test_blocks = ['LargeBlockArmorBlock', 'SmallBlockArmorBlock']
        test_file = self.create_test_blueprint(test_blocks)
        
        blocks_scanned, replacements = self.replacer.process_blueprint(
            str(test_file), create_backup=False
        )
        
        self.assertEqual(blocks_scanned, 2)
        self.assertEqual(replacements, 2)
        
        # Verify the replacements
        tree = ET.parse(test_file)
        subtype_ids = [elem.text for elem in tree.findall('.//SubtypeId')]
        subtype_names = [elem.text for elem in tree.findall('.//SubtypeName')]
        
        for collection in (subtype_ids, subtype_names):
            self.assertIn('LargeHeavyBlockArmorBlock', collection)
            self.assertIn('SmallHeavyBlockArmorBlock', collection)
            self.assertNotIn('LargeBlockArmorBlock', collection)
            self.assertNotIn('SmallBlockArmorBlock', collection)
    
    def test_no_replacements_needed(self):
        """Test blueprint with no light armor blocks."""
        test_blocks = ['LargeHeavyBlockArmorBlock', 'SmallReactor']
        test_file = self.create_test_blueprint(test_blocks)
        
        blocks_scanned, replacements = self.replacer.process_blueprint(
            str(test_file), create_backup=False
        )
        
        self.assertEqual(blocks_scanned, 2)
        self.assertEqual(replacements, 0)
    
    def test_mixed_blocks(self):
        """Test blueprint with mix of light armor and other blocks."""
        test_blocks = [
            'LargeBlockArmorBlock',
            'LargeReactor',
            'SmallBlockArmorSlope',
            'SmallCockpit'
        ]
        test_file = self.create_test_blueprint(test_blocks)
        
        blocks_scanned, replacements = self.replacer.process_blueprint(
            str(test_file), create_backup=False
        )
        
        self.assertEqual(blocks_scanned, 4)
        self.assertEqual(replacements, 2)
    
    def test_backup_creation(self):
        """Test that backup files are created."""
        test_blocks = ['LargeBlockArmorBlock']
        test_file = self.create_test_blueprint(test_blocks)
        
        self.replacer.process_blueprint(str(test_file), create_backup=True)
        
        backup_file = test_file.with_suffix('.sbc.backup')
        self.assertTrue(backup_file.exists())
    
    def test_output_to_different_file(self):
        """Test saving output to a different file."""
        test_blocks = ['LargeBlockArmorBlock']
        test_file = self.create_test_blueprint(test_blocks)
        output_file = self.test_dir / 'output.sbc'
        
        self.replacer.process_blueprint(
            str(test_file), 
            str(output_file), 
            create_backup=False
        )
        
        self.assertTrue(output_file.exists())
        
        # Verify original is unchanged
        original_tree = ET.parse(test_file)
        original_ids = [elem.text for elem in original_tree.findall('.//SubtypeId')]
        original_names = [elem.text for elem in original_tree.findall('.//SubtypeName')]
        self.assertIn('LargeBlockArmorBlock', original_ids)
        self.assertIn('LargeBlockArmorBlock', original_names)
        
        # Verify output has replacements
        output_tree = ET.parse(output_file)
        output_ids = [elem.text for elem in output_tree.findall('.//SubtypeId')]
        output_names = [elem.text for elem in output_tree.findall('.//SubtypeName')]
        self.assertIn('LargeHeavyBlockArmorBlock', output_ids)
        self.assertIn('LargeHeavyBlockArmorBlock', output_names)
    
    def test_all_armor_types(self):
        """Test all defined armor type replacements."""
        light_blocks = list(ArmorBlockReplacer.ARMOR_REPLACEMENTS.keys())
        test_file = self.create_test_blueprint(light_blocks)
        
        blocks_scanned, replacements = self.replacer.process_blueprint(
            str(test_file), create_backup=False
        )
        
        self.assertEqual(blocks_scanned, len(light_blocks))
        self.assertEqual(replacements, len(light_blocks))
        
        # Verify all were replaced
        tree = ET.parse(test_file)
        subtype_ids = [elem.text for elem in tree.findall('.//SubtypeId')]
        subtype_names = [elem.text for elem in tree.findall('.//SubtypeName')]
        
        for collection in (subtype_ids, subtype_names):
            for light_armor in light_blocks:
                self.assertNotIn(light_armor, collection)
            for heavy_armor in ArmorBlockReplacer.ARMOR_REPLACEMENTS.values():
                self.assertIn(heavy_armor, collection)
    
    def test_replacement_summary(self):
        """Test the replacement summary method."""
        test_blocks = ['LargeBlockArmorBlock', 'SmallBlockArmorBlock']
        test_file = self.create_test_blueprint(test_blocks)
        
        self.replacer.process_blueprint(str(test_file), create_backup=False)
        summary = self.replacer.get_replacement_summary()
        
        self.assertIn('2 blocks', summary)
        self.assertIn('replaced 2 light armor', summary)


class TestArmorMappings(unittest.TestCase):
    """Test cases for armor block mappings."""
    
    def test_large_grid_mappings_exist(self):
        """Verify large grid armor mappings are defined."""
        mappings = ArmorBlockReplacer.ARMOR_REPLACEMENTS
        
        self.assertIn('LargeBlockArmorBlock', mappings)
        self.assertIn('LargeBlockArmorSlope', mappings)
        self.assertIn('LargeBlockArmorCorner', mappings)
    
    def test_small_grid_mappings_exist(self):
        """Verify small grid armor mappings are defined."""
        mappings = ArmorBlockReplacer.ARMOR_REPLACEMENTS
        
        self.assertIn('SmallBlockArmorBlock', mappings)
        self.assertIn('SmallBlockArmorSlope', mappings)
        self.assertIn('SmallBlockArmorCorner', mappings)
    
    def test_mapping_values_are_heavy(self):
        """Verify all mapping values contain 'Heavy'."""
        for light, heavy in ArmorBlockReplacer.ARMOR_REPLACEMENTS.items():
            self.assertIn('Heavy', heavy, 
                         f"Mapping {light} -> {heavy} doesn't contain 'Heavy'")
    
    def test_no_duplicate_mappings(self):
        """Verify no duplicate keys or values in mappings."""
        mappings = ArmorBlockReplacer.ARMOR_REPLACEMENTS
        
        # Check for duplicate keys (should be impossible with dict, but verify)
        keys = list(mappings.keys())
        self.assertEqual(len(keys), len(set(keys)))
        
        # Check for duplicate values
        values = list(mappings.values())
        self.assertEqual(len(values), len(set(values)))


class TestReverseMode(unittest.TestCase):
    """Test cases for heavy-to-light (reverse) conversion."""
    
    def setUp(self):
        self.replacer = ArmorBlockReplacer(verbose=False, reverse=True)
        self.test_dir = Path(tempfile.mkdtemp())
    
    def tearDown(self):
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)
    
    def _make_bp(self, blocks):
        root = ET.Element('Definitions')
        ship = ET.SubElement(ET.SubElement(root, 'ShipBlueprints'), 'ShipBlueprint')
        cubes = ET.SubElement(ship, 'CubeBlocks')
        for name in blocks:
            b = ET.SubElement(cubes, 'MyObjectBuilder_CubeBlock')
            ET.SubElement(b, 'SubtypeId').text = name
            ET.SubElement(b, 'SubtypeName').text = name
        path = self.test_dir / 'bp.sbc'
        ET.ElementTree(root).write(path, encoding='utf-8', xml_declaration=True)
        return path
    
    def test_heavy_to_light_basic(self):
        """Reverse mode converts heavy blocks to light."""
        path = self._make_bp(['LargeHeavyBlockArmorBlock', 'SmallHeavyBlockArmorSlope'])
        scanned, replaced = self.replacer.process_blueprint(str(path), create_backup=False)
        self.assertEqual(replaced, 2)
        tree = ET.parse(path)
        ids = [e.text for e in tree.findall('.//SubtypeId')]
        self.assertIn('LargeBlockArmorBlock', ids)
        self.assertIn('SmallBlockArmorSlope', ids)
    
    def test_reverse_ignores_light_blocks(self):
        """Reverse mode does not touch light armor blocks."""
        path = self._make_bp(['LargeBlockArmorBlock', 'SmallReactor'])
        _, replaced = self.replacer.process_blueprint(str(path), create_backup=False)
        self.assertEqual(replaced, 0)
    
    def test_reverse_all_heavy_types(self):
        """Reverse mode handles every heavy mapping."""
        heavy_blocks = list(ArmorBlockReplacer.HEAVY_TO_LIGHT.keys())
        path = self._make_bp(heavy_blocks)
        scanned, replaced = self.replacer.process_blueprint(str(path), create_backup=False)
        self.assertEqual(replaced, len(heavy_blocks))


class TestDryRun(unittest.TestCase):
    """Test cases for dry-run (preview) mode."""
    
    def setUp(self):
        self.replacer = ArmorBlockReplacer(verbose=False)
        self.test_dir = Path(tempfile.mkdtemp())
    
    def tearDown(self):
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)
    
    def _make_bp(self, blocks):
        root = ET.Element('Definitions')
        ship = ET.SubElement(ET.SubElement(root, 'ShipBlueprints'), 'ShipBlueprint')
        cubes = ET.SubElement(ship, 'CubeBlocks')
        for name in blocks:
            b = ET.SubElement(cubes, 'MyObjectBuilder_CubeBlock')
            ET.SubElement(b, 'SubtypeId').text = name
            ET.SubElement(b, 'SubtypeName').text = name
        path = self.test_dir / 'bp.sbc'
        ET.ElementTree(root).write(path, encoding='utf-8', xml_declaration=True)
        return path
    
    def test_dry_run_does_not_modify(self):
        """Dry-run must not alter the file content."""
        path = self._make_bp(['LargeBlockArmorBlock'])
        original = path.read_bytes()
        self.replacer.process_blueprint(str(path), create_backup=False, dry_run=True)
        self.assertEqual(path.read_bytes(), original)
    
    def test_dry_run_report(self):
        """Dry-run report lists the planned changes."""
        path = self._make_bp(['LargeBlockArmorBlock', 'LargeBlockArmorBlock',
                              'SmallBlockArmorSlope'])
        self.replacer.process_blueprint(str(path), create_backup=False, dry_run=True)
        report = self.replacer.get_dry_run_report()
        self.assertIn('LargeBlockArmorBlock', report)
        self.assertIn('LargeHeavyBlockArmorBlock', report)


class TestExtendedMappings(unittest.TestCase):
    """Tests for expanded / DLC block mappings and cross-module consistency."""
    
    def test_extended_mappings_exist(self):
        """Verify DLC / decorative shapes are present."""
        m = ArmorBlockReplacer.LIGHT_TO_HEAVY
        # Spot-check a handful of extended shapes
        self.assertIn('LargeBlockArmorHalfSlopeCorner', m)
        self.assertIn('SmallBlockArmorRoundSlope', m)
    
    def test_reverse_mapping_completeness(self):
        """Every HEAVY_TO_LIGHT key must appear as a value in LIGHT_TO_HEAVY."""
        for heavy in ArmorBlockReplacer.HEAVY_TO_LIGHT:
            self.assertIn(heavy, ArmorBlockReplacer.LIGHT_TO_HEAVY.values())
    
    def test_scanner_block_sets_match_replacer(self):
        """BlueprintScanner block sets must be derived from ArmorBlockReplacer."""
        self.assertEqual(BlueprintScanner.LIGHT_ARMOR_BLOCKS,
                         set(ArmorBlockReplacer.LIGHT_TO_HEAVY.keys()))
        self.assertEqual(BlueprintScanner.HEAVY_ARMOR_BLOCKS,
                         set(ArmorBlockReplacer.LIGHT_TO_HEAVY.values()))


if __name__ == '__main__':
    unittest.main()

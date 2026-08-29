"""
Unit tests for PB Doctor ScriptFixer automated repair engine.
"""

import unittest
from pb_doctor import ScriptFixer, PBScriptValidator


class TestPBScriptFixer(unittest.TestCase):
    def test_01_strip_forbidden_namespaces(self):
        code = """using System;
using System.IO;
using System.Threading;
using System.Net;
using VRage.Game;

public Program() {}
public void Main(string arg, UpdateType src) {}
"""
        fixed, fixes = ScriptFixer.fix_script(code)
        self.assertNotIn("System.IO", fixed)
        self.assertNotIn("System.Threading", fixed)
        self.assertNotIn("System.Net", fixed)
        self.assertIn("using System;", fixed)
        self.assertIn("using VRage.Game;", fixed)
        self.assertGreater(len(fixes), 0)

        report = PBScriptValidator.validate_script("TestPB", fixed)
        self.assertEqual(report.error_count, 0)
        self.assertEqual(report.compliance_score, 100)

    def test_06_allowed_usings_pass_validator(self):
        code = """using System;
using System.Collections.Generic;
using VRage.Game;

public Program() {}
public void Main(string arg, UpdateType src) {
    var items = new List<int>();
}
"""
        report = PBScriptValidator.validate_script("AllowedUsings", code)
        self.assertEqual(report.error_count, 0)
        self.assertTrue(report.is_valid)

    def test_02_inject_missing_main(self):
        code = """public Program() {
    Echo("Init");
}
"""
        fixed, fixes = ScriptFixer.fix_script(code)
        self.assertIn("void Main(", fixed)
        self.assertTrue(any("Main" in f for f in fixes))

        report = PBScriptValidator.validate_script("TestPB", fixed)
        self.assertTrue(report.has_main_method)

    def test_03_inject_missing_program_constructor(self):
        code = """public void Main(string arg, UpdateType src) {
    Echo("Running");
}
"""
        fixed, fixes = ScriptFixer.fix_script(code)
        self.assertIn("Program()", fixed)
        self.assertTrue(any("Program" in f for f in fixes))

        report = PBScriptValidator.validate_script("TestPB", fixed)
        self.assertTrue(report.has_program_constructor)

    def test_04_fix_unbalanced_braces(self):
        code = """public Program() {
    if (true) {
        Echo("Nested");
"""
        fixed, fixes = ScriptFixer.fix_script(code)
        self.assertEqual(fixed.count("{"), fixed.count("}"))
        self.assertTrue(any("brace" in f for f in fixes))

    def test_05_empty_code_injects_template(self):
        fixed, fixes = ScriptFixer.fix_script("")
        self.assertIn("public Program()", fixed)
        self.assertIn("public void Main(", fixed)
        self.assertGreater(len(fixes), 0)


if __name__ == "__main__":
    unittest.main()

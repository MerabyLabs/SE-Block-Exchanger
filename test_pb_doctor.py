"""
Unit tests for PB Script Doctor engine.
"""

import unittest
from pb_doctor import PBScriptValidator


class TestPBScriptDoctor(unittest.TestCase):
    def test_valid_script(self):
        code = """
public Program() {
    Runtime.UpdateFrequency = UpdateFrequency.Update10;
}

public void Main(string argument, UpdateType updateSource) {
    Echo("System operational");
}

public void Save() {
}
"""
        report = PBScriptValidator.validate_script("ValidScript", code)
        self.assertTrue(report.is_valid)
        self.assertEqual(report.error_count, 0)
        self.assertTrue(report.has_program_constructor)
        self.assertTrue(report.has_main_method)
        self.assertTrue(report.has_save_method)
        self.assertEqual(report.compliance_score, 100)

    def test_forbidden_namespace_and_missing_main(self):
        code = """
using System.IO;
using System.Threading;

public class Broken {
    public void Run() {
        File.WriteAllText("test.txt", "exploit");
    }
}
"""
        report = PBScriptValidator.validate_script("BrokenScript", code)
        self.assertFalse(report.is_valid)
        self.assertGreater(report.error_count, 0)
        rule_ids = [d.rule_id for d in report.diagnostics]
        self.assertIn("FORBIDDEN_NAMESPACE", rule_ids)
        self.assertIn("MISSING_MAIN", rule_ids)

    def test_unbalanced_braces_and_regions(self):
        code = """
#region Config
public void Main() {
    if (true) {
        Echo("test");
#endregion
"""
        report = PBScriptValidator.validate_script("UnbalancedScript", code)
        self.assertFalse(report.is_valid)
        rule_ids = [d.rule_id for d in report.diagnostics]
        self.assertIn("UNBALANCED_BRACES", rule_ids)

    def test_braces_in_strings_and_comments_are_ignored(self):
        code = """
public Program() {}
public void Main(string argument, UpdateType updateSource) {
    Echo("json { not code }");
    // leftover { in a comment
    var template = "{ template }";
}
"""
        report = PBScriptValidator.validate_script("StringBraces", code)
        rule_ids = [d.rule_id for d in report.diagnostics]
        self.assertNotIn("UNBALANCED_BRACES", rule_ids)
        self.assertEqual(report.error_count, 0)

    def test_region_in_comment_is_ignored(self):
        code = """
public Program() {}
public void Main() {
    // #region not a real region
}
"""
        report = PBScriptValidator.validate_script("CommentRegion", code)
        rule_ids = [d.rule_id for d in report.diagnostics]
        self.assertNotIn("UNBALANCED_REGIONS", rule_ids)

    def test_forbidden_tokens_in_strings_and_comments_are_ignored(self):
        code = """
public Program() {}
public void Main() {
    Echo("System.IO is mentioned only as text");
    // using System.Threading;
}
"""
        report = PBScriptValidator.validate_script("MentionOnly", code)
        rule_ids = [d.rule_id for d in report.diagnostics]
        self.assertNotIn("FORBIDDEN_NAMESPACE", rule_ids)
        self.assertEqual(report.error_count, 0)


if __name__ == "__main__":
    unittest.main()

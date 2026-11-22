"""Tests for tell selection, checker dispatch and grouped results."""
import unittest
from unittest.mock import Mock, patch

from src.gui.tell_results import TELL_CHOICES, TELL_SPECS, analyze_tells, tell_columns, tell_description
from src.importers.fmmlx_xml_import.xml_importer import XmlImporter


class TellResultsTests(unittest.TestCase):
    """Verify the tell definitions and checker results."""

    def test_choices_and_descriptions(self):
        """Show all nine tell IDs with their full descriptions."""
        self.assertEqual(TELL_CHOICES, ("Check All Tells", "Check Tell TO1", "Check Tell TO2", "Check Tell TO3",
                                       "Check Tell OC1", "Check Tell OC2", "Check Tell OC3", "Check Tell OC4",
                                       "Check Tell OC5", "Check Tell TH1"))
        self.assertEqual(tell_description("Check Tell TO1"),
                         ("TO1: Name of Associated Class", "Emulation of Classification Relationships"))

    def test_single_and_batch_columns(self):
        """Include model names only in the batch table."""
        self.assertEqual(tell_columns(False), ("Affected Parts", "Indicators", "Transform?"))
        self.assertEqual(tell_columns(True), ("Model Name", "Affected Parts", "Indicators", "Transform?"))

    def test_all_tells_group_actual_checker_hits_by_part_and_model(self):
        """Collect all matching tell identifiers for each model part."""
        model, _report = XmlImporter().import_file("models/fmmlx/c13_inst_level_not_lower.xml")
        rows = analyze_tells("Check All Tells", [("First", model), ("Second", model)])
        self.assertEqual([row.model_name for row in rows], ["First", "Second"])
        self.assertTrue(all(row.affected_parts == "Class" for row in rows))
        self.assertEqual(rows[0].indicators, ", ".join(spec.identifier for spec in TELL_SPECS))
        self.assertIn("TO1: Name of Associated Class", rows[0].indicator_details)
        self.assertEqual(analyze_tells("Check Tell OC1", [("First", model)])[0].indicators, "OC1")

    def test_each_tell_calls_its_own_method(self):
        """Dispatch each tell to the corresponding checker method."""
        checker = Mock()
        part = Mock()
        part.get_name.return_value = "Part"
        for spec in TELL_SPECS:
            getattr(checker, spec.method).return_value = [part]
        with patch("src.gui.tell_results.TellChecker", return_value=checker):
            for spec in TELL_SPECS:
                checker.reset_mock()
                rows = analyze_tells(f"Check Tell {spec.identifier}", [("Model", object())])
                getattr(checker, spec.method).assert_called_once_with()
                self.assertEqual(rows[0].indicators, spec.identifier)
                self.assertEqual(rows[0].indicator_details, spec.heading)


if __name__ == "__main__":
    unittest.main()

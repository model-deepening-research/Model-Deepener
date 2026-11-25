"""Tests for tell selection, checker dispatch and grouped results."""
import unittest
from unittest.mock import Mock, patch

from src.gui.tell_results import TELL_CHOICES, TELL_SPECS, TellAnalysisCache, analyze_tells, tell_columns, tell_description
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
        self.assertEqual(tell_columns(False), ("Model Name", "Format", "Affected Parts", "Tell", "Transform?"))
        self.assertEqual(tell_columns(True), ("Model Name", "Format", "Affected Parts", "Tell", "Transform?"))

    def test_all_tells_group_actual_checker_hits_by_part_and_model(self):
        """Collect all matching tell identifiers for each model part."""
        model, _report = XmlImporter().import_file("models/fmmlx/c13_inst_level_not_lower.xml")
        rows = analyze_tells("Check All Tells", [("First", model), ("Second", model)])
        self.assertEqual([row.model_name for row in rows], ["First", "Second"])
        self.assertTrue(all(row.affected_parts == "Class" for row in rows))
        self.assertEqual(rows[0].indicators, "OC1")
        self.assertIn("OC1: Class Name", rows[0].indicator_details)
        self.assertEqual(analyze_tells("Check Tell OC1", [("First", model)])[0].indicators, "OC1")

    def test_every_checked_model_without_hits_gets_a_placeholder(self):
        models = [("First", object(), "XMI"), ("Second", object(), "Ecore")]
        with patch("src.gui.tell_results.TellChecker") as checker:
            for spec in TELL_SPECS:
                getattr(checker.return_value, spec.method).return_value = []
            rows = analyze_tells("Check All Tells", models)
        self.assertEqual([(row.model_name, row.model_format, row.affected_parts, row.indicators, row.is_placeholder)
                          for row in rows],
                         [("First", "XMI", "No affected parts found.", "", True),
                          ("Second", "Ecore", "No affected parts found.", "", True)])

    def test_each_tell_calls_its_own_method(self):
        """Dispatch each tell to the corresponding checker method."""
        checker = Mock()
        part = Mock()
        element = Mock()
        element.get_name.return_value = "Part"
        part.get_model_elements.return_value = [element]
        for spec in TELL_SPECS:
            getattr(checker, spec.method).return_value = [part]
        with patch("src.gui.tell_results.TellChecker", return_value=checker):
            for spec in TELL_SPECS:
                checker.reset_mock()
                rows = analyze_tells(f"Check Tell {spec.identifier}", [("Model", object())])
                getattr(checker, spec.method).assert_called_once_with()
                self.assertEqual(rows[0].indicators, spec.identifier)
                self.assertEqual(rows[0].indicator_details, spec.heading)

    def test_cache_reuses_tells_and_invalidates_modified_model(self):
        model, _ = XmlImporter().import_file("models/fmmlx/c13_inst_level_not_lower.xml")
        cache = TellAnalysisCache()
        with patch("src.gui.tell_results.TellChecker", wraps=__import__(
                "src.gui.tell_results", fromlist=["TellChecker"]).TellChecker) as checker:
            all_rows = analyze_tells("Check All Tells", [("Model", model)], cache=cache)
            self.assertEqual(checker.call_count, 1)
            analyze_tells("Check Tell OC1", [("Model", model)], cache=cache)
            self.assertEqual(checker.call_count, 1)
            cache.decisions[all_rows[0].key] = "Yes"
            model.mlm_objects[0].name += " changed"
            analyze_tells("Check Tell OC1", [("Model", model)], cache=cache)
            self.assertEqual(checker.call_count, 2)
            self.assertFalse(cache.decisions)

    def test_single_tell_first_only_computes_missing_tells(self):
        model, _ = XmlImporter().import_file("models/fmmlx/c13_inst_level_not_lower.xml")
        cache = TellAnalysisCache()
        with patch("src.gui.tell_results.TellChecker") as cls:
            checker = cls.return_value
            for spec in TELL_SPECS:
                getattr(checker, spec.method).return_value = []
            analyze_tells("Check Tell OC1", [("Model", model)], cache=cache)
            analyze_tells("Check All Tells", [("Model", model)], cache=cache)
            for spec in TELL_SPECS:
                self.assertEqual(getattr(checker, spec.method).call_count, 1)

    def test_all_checks_prepare_each_selection_without_rechecking(self):
        model, _ = XmlImporter().import_file("models/fmmlx/c13_inst_level_not_lower.xml")
        models = [("Model", model, "FMMLx")]
        cache = TellAnalysisCache()
        with patch("src.gui.tell_results.TellChecker") as cls:
            checker = cls.return_value
            for spec in TELL_SPECS:
                getattr(checker, spec.method).return_value = []
            analyze_tells("Check All Tells", models, cache=cache)
            for spec in TELL_SPECS:
                rows = cache.get_prepared(f"Check Tell {spec.identifier}", models)
                self.assertIsNotNone(rows)
                self.assertEqual(rows[0].model_name, "Model")
                getattr(checker, spec.method).assert_called_once()
            cache.invalidate(model)
            self.assertIsNone(cache.get_prepared("Check Tell OC1", models))

    def test_failed_check_is_reported_and_other_checks_continue_and_are_cached(self):
        model, _ = XmlImporter().import_file("models/fmmlx/c13_inst_level_not_lower.xml")
        cache = TellAnalysisCache()
        with patch("src.gui.tell_results.TellChecker") as cls:
            checker = cls.return_value
            for spec in TELL_SPECS:
                getattr(checker, spec.method).return_value = []
            checker.check_assoc_name.side_effect = ValueError("failed")
            rows = analyze_tells("Check All Tells", [("Model", model)], cache=cache)
            self.assertEqual(rows.failures, [("Model", "TO2", "ValueError: failed")])
            self.assertEqual([(row.model_name, row.indicators, row.affected_parts, row.is_placeholder) for row in rows],
                             [("Model", "TO2", "TO2 failed: ValueError: failed", True)])
            checker.check_generalizations.assert_called_once()
            again = analyze_tells("Check Tell TO2", [("Model", model)], cache=cache)
            self.assertEqual(again.failures, rows.failures)
            checker.check_assoc_name.assert_called_once()
            self.assertFalse(analyze_tells("Check Tell TH1", [("Model", model)], cache=cache).failures)


if __name__ == "__main__":
    unittest.main()

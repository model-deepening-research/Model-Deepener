"""Tests for exporting without a constraint check."""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from src.gui.app import ModelDeepenerApp


class UncheckedExportTests(unittest.TestCase):
    """Check confirmation and export dispatch."""

    def test_confirmation_exports_without_validation(self) -> None:
        model = Mock()
        ui = SimpleNamespace(current_model=model, _export_current_xml_model=Mock())
        with patch("src.gui.app.messagebox.askokcancel", return_value=True):
            ModelDeepenerApp._export_without_check(ui)
        ui._export_current_xml_model.assert_called_once_with()
        model.validate_basemlm_integrity.assert_not_called()

    def test_cancel_does_not_export(self) -> None:
        ui = SimpleNamespace(current_model=Mock(), _export_current_xml_model=Mock())
        with patch("src.gui.app.messagebox.askokcancel", return_value=False):
            ModelDeepenerApp._export_without_check(ui)
        ui._export_current_xml_model.assert_not_called()

    def test_missing_model_does_not_prompt(self) -> None:
        ui = SimpleNamespace(current_model=None, _show_information=Mock())
        with patch("src.gui.app.messagebox.askokcancel") as confirm:
            ModelDeepenerApp._export_without_check(ui)
        confirm.assert_not_called()
        ui._show_information.assert_called_once()


if __name__ == "__main__":
    unittest.main()

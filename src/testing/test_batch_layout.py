import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from src.gui.app import ModelDeepenerApp


class BatchLayoutTests(unittest.TestCase):
    """Test batch layout."""
    def test_close_active_batch_returns_to_overview(self):
        """Check close active batch returns to overview."""
        ui = SimpleNamespace(batch_models=[object()], batch_tab=Mock(), active_top_tab='batch',
                             _show_models_overview_page=Mock())
        ModelDeepenerApp._close_top_tab(ui, 'batch')
        self.assertEqual(ui.batch_models, [])
        ui.batch_tab.grid_remove.assert_called_once()
        ui._show_models_overview_page.assert_called_once()

    def test_close_inactive_model_does_not_navigate(self):
        """Check close inactive model does not navigate."""
        ui = SimpleNamespace(current_model=object(), model_tab=Mock(), active_top_tab='batch',
                             _show_models_overview_page=Mock())
        ModelDeepenerApp._close_top_tab(ui, 'model')
        self.assertIsNone(ui.current_model)
        ui.model_tab.grid_remove.assert_called_once()
        ui._show_models_overview_page.assert_not_called()

    def test_columns_follow_nonzero_values_even_when_mean_rounds_to_zero(self):
        """Check columns follow nonzero values even when mean rounds to zero."""
        models = [SimpleNamespace(name=f"Model {i}", file_type="XMI", model=i) for i in range(3)]
        def metrics(model):
            return [("Classes", 2), ("Attributes", 0), ("Objects", int(model == 0))]
        ui = SimpleNamespace(_batch_format=ModelDeepenerApp._batch_format,
                             _display_file_type=ModelDeepenerApp._display_file_type, _model_metrics=metrics)
        counts, means, headers, rows = ModelDeepenerApp._prepare_batch_page(ui, models, lambda *_: None)
        self.assertEqual(headers, ("Model Name", "Format", "Classes", "Objects"))
        self.assertEqual(dict(means)["Objects"], 0.3)
        self.assertEqual(rows[0], ("Model 0", "XMI", 2, 1))
        self.assertEqual(rows[1], ("Model 1", "XMI", 2, 0))
        _, _, narrower_headers, narrower_rows = ModelDeepenerApp._prepare_batch_page(ui, models[1:], lambda *_: None)
        self.assertEqual(narrower_headers, ("Model Name", "Format", "Classes"))
        self.assertEqual(narrower_rows[0], ("Model 1", "XMI", 2))
        self.assertNotIn("Adapted", headers)

    def test_empty_selection_has_only_name_and_format_columns(self):
        """Check empty selection has only name and format columns."""
        ui = SimpleNamespace(_batch_format=ModelDeepenerApp._batch_format)
        counts, means, headers, rows = ModelDeepenerApp._prepare_batch_page(ui, [], lambda *_: None)
        self.assertEqual(headers, ("Model Name", "Format"))
        self.assertEqual((means, rows), ([], []))
        self.assertEqual(dict(counts)["Number of Models"], 0)

    def test_window_and_navigation_symbols_are_utf8(self):
        """Check window and navigation symbols are utf8."""
        source = (Path(__file__).resolve().parents[1] / "gui" / "app.py").read_text(encoding="utf-8")
        for symbol in ("\u2014", "\u25a1", "\u00d7", "\u21c4", "\u2193", "\u2191", "\u2192"):
            self.assertIn(symbol, source)
        for corruption in ("\u00e2\u20ac\u201d", "\u00e2\u2013\u00a1", "\u00c3\u2014", "\u00e2\u2021\u201e"):
            self.assertNotIn(corruption, source)

    def test_tell_column_drag_preserves_total_and_minimum(self):
        """Check tell column drag preserves total and minimum."""
        self.assertEqual(ModelDeepenerApp._move_column_boundary([220, 300, 200], 0, 80, minimum=100),
                         [300, 220, 200])
        self.assertEqual(ModelDeepenerApp._move_column_boundary([220, 300, 200], 0, -999, minimum=100),
                         [100, 420, 200])


if __name__ == '__main__':
    unittest.main()

import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from src.gui.app import ModelDeepenerApp


class ImportDisplayTests(unittest.TestCase):
    """Test import display."""
    def test_fmmlx_display_preserves_internal_type(self):
        """Check fmmlx display preserves internal type."""
        self.assertEqual(ModelDeepenerApp._display_file_type('XML'), 'FMMLx')
        self.assertEqual(ModelDeepenerApp._display_file_type('CSV'), 'CSV')
        labels = dict(ModelDeepenerApp._import_file_types())
        self.assertIn('FMMLx files', labels)
        self.assertIn('*.xml', labels['FMMLx files'])
        self.assertNotIn('XML files', labels)

    def test_column_controls_only_visible_for_csv(self):
        """Check column controls only visible for csv."""
        ui = SimpleNamespace(column_selection_expanded=False, column_selection_description=Mock(),
                             expand_columns_button=Mock())
        ModelDeepenerApp._set_column_selection_enabled(ui, False)
        ui.column_selection_description.grid_remove.assert_called_once()
        ui.expand_columns_button.grid_remove.assert_called_once()
        ModelDeepenerApp._set_column_selection_enabled(ui, True)
        ui.column_selection_description.grid.assert_called_once()
        ui.expand_columns_button.grid.assert_called_once()

    def test_hiding_controls_collapses_expanded_view(self):
        """Check hiding controls collapses expanded view."""
        ui = SimpleNamespace(column_selection_expanded=True, column_selection_description=Mock(),
                             expand_columns_button=Mock(), _toggle_column_selection_size=Mock())
        ModelDeepenerApp._set_column_selection_enabled(ui, False)
        ui._toggle_column_selection_size.assert_called_once()


if __name__ == '__main__':
    unittest.main()

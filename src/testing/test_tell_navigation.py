import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from src.gui.app import ModelDeepenerApp
from src.gui.tell_results import TELL_CHOICES


class TellNavigationTests(unittest.TestCase):
    """Test tell navigation."""
    def test_single_menu_opens_then_closes_without_resetting_selection(self):
        """Check single menu opens then closes without resetting selection."""
        menu = Mock()
        ui = SimpleNamespace(_tell_menu_open={False: False}, _tell_selection={False: 'Check Tell TO3'},
                             _single_tell_menu=menu, action_cards={3: object()}, _open_placeholder_action=Mock())
        ModelDeepenerApp._toggle_tell_menu(ui, False)
        self.assertTrue(ui._tell_menu_open[False])
        menu.pack.assert_called_once()
        ui._open_placeholder_action.assert_called_once_with(3)
        ModelDeepenerApp._toggle_tell_menu(ui, False)
        self.assertFalse(ui._tell_menu_open[False])
        menu.pack_forget.assert_called_once()
        self.assertEqual(ui._tell_selection[False], 'Check Tell TO3')

    def test_batch_action_uses_active_batch_not_open_model(self):
        ui = SimpleNamespace(active_top_tab="batch", _tell_menu_open={True: False},
                             _show_batch_analysis=Mock(), _open_placeholder_action=Mock())
        ModelDeepenerApp._try_open_action(ui, 3)
        ui._show_batch_analysis.assert_called_once()
        ui._open_placeholder_action.assert_not_called()
        self.assertTrue(ui._tell_menu_open[True])

    def test_import_navigation_remains_available_with_an_open_model(self):
        """Check import navigation remains available with an open model."""
        ui = SimpleNamespace(current_model=object(), _is_navigation_item_available=lambda action: True,
                             _show_import_page=Mock())
        self.assertTrue(ModelDeepenerApp._is_navigation_item_available(ui, 1))
        ModelDeepenerApp._try_open_action(ui, 1)
        ui._show_import_page.assert_called_once()

    def test_unchanged_model_metadata_does_not_commit_again(self):
        """Check unchanged model metadata does not commit again."""
        model = object()
        loaded = SimpleNamespace(model=model, last_worked_on="now", last_action="Inspect Model")
        ui = SimpleNamespace(loaded_models=[loaded], current_model=model, _current_timestamp_text=lambda: "now",
                             ACTION_TITLES={2: "Inspect Model"}, _commit_database=Mock())
        ModelDeepenerApp._touch_loaded_model(ui, model)
        ModelDeepenerApp._set_last_action(ui, 2)
        ui._commit_database.assert_not_called()

    def test_selection_routes_to_correct_view(self):
        """Check selection routes to correct view."""
        ui = SimpleNamespace(_tell_selection={False: TELL_CHOICES[0], True: TELL_CHOICES[0]},
                             _show_batch_analysis=Mock(), _open_placeholder_action=Mock())
        ModelDeepenerApp._select_tell(ui, 'Check Tell TO3', True)
        self.assertEqual(ui._tell_selection[True], 'Check Tell TO3')
        ui._show_batch_analysis.assert_called_once()
        ModelDeepenerApp._select_tell(ui, 'Check Tell TH1', False)
        self.assertEqual(ui._tell_selection[False], 'Check Tell TH1')
        ui._open_placeholder_action.assert_called_once_with(3)

    def test_open_model_tab_is_retained_and_restores_model(self):
        """Check open model tab is retained and restores model."""
        model = object()
        tab = Mock()
        ui = SimpleNamespace(model_tab=tab, current_model=model, current_file_path="model.xmi",
                             current_file_type="XMI", current_selected_columns=["name"],
                             _current_model_display_name=lambda: "Example model",
                             _short_tab_text=ModelDeepenerApp._short_tab_text,
                             _show_model_page=Mock())
        ModelDeepenerApp._update_model_tab(ui)
        ui.current_model = None
        ui.current_file_path = "different.csv"
        ui.current_file_type = "CSV"
        ui.current_selected_columns = []
        ModelDeepenerApp._update_model_tab(ui)
        tab.grid_remove.assert_not_called()
        ModelDeepenerApp._reopen_model_tab(ui)
        self.assertIs(ui.current_model, model)
        self.assertEqual((ui.current_file_path, ui.current_file_type, ui.current_selected_columns),
                         ("model.xmi", "XMI", ["name"]))
        ui._show_model_page.assert_called_once()

    def test_close_model_tab_clears_its_retained_state(self):
        """Check close model tab clears its retained state."""
        ui = SimpleNamespace(current_model=object(), _model_tab_state=(object(), None, "", []),
                             model_tab=Mock(), active_top_tab="batch", _show_models_overview_page=Mock())
        ModelDeepenerApp._close_top_tab(ui, "model")
        self.assertIsNone(ui.current_model)
        self.assertIsNone(ui._model_tab_state)
        ui.model_tab.grid_remove.assert_called_once()
        ui._show_models_overview_page.assert_not_called()

    def test_object_details_do_not_offer_operations(self):
        """Check object details do not offer operations."""
        obj = SimpleNamespace(name="Instance", get_regular_slots=lambda: [])
        ui = SimpleNamespace(detail_title=Mock(), detail_subtitle=Mock(), current_model=object(),
                             _links_for_object=Mock(return_value=[]), _render_object_value_table=Mock(),
                             _render_object_link_table=Mock(), _render_detail_option_buttons=Mock(),
                             _render_detail_table=Mock())
        ModelDeepenerApp._render_object_details(ui, obj)
        options = ui._render_detail_option_buttons.call_args.args[0]
        self.assertEqual([option[0] for option in options], ["Slots", "Links"])

    def test_class_details_do_not_offer_operations(self):
        """Check class details do not offer operations."""
        obj = SimpleNamespace(name='Example', operations_list=[object()])
        ui = SimpleNamespace(detail_title=Mock(), detail_subtitle=Mock(), colors={'text': '#000'},
                             _has_attribute_rows=Mock(return_value=False), _has_association_rows=Mock(return_value=False),
                             _generalization_rows=Mock(return_value=[]), _render_class_attribute_table=Mock(),
                             _render_class_association_table=Mock(), _render_class_generalization_table=Mock(),
                             _render_detail_option_buttons=Mock(), _render_detail_table=Mock())
        ModelDeepenerApp._render_class_details(ui, obj)
        options = ui._render_detail_option_buttons.call_args.args[0]
        self.assertEqual([option[0] for option in options], ['Attributes', 'Associations', 'Generalization'])


if __name__ == '__main__':
    unittest.main()

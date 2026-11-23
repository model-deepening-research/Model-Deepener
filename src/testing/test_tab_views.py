"""Tests for cancelled input choosers, remembered tab views, tab overflow and the view loading indicator."""
import sys
import time
import unittest
from types import MethodType, SimpleNamespace
from unittest.mock import Mock, patch

import customtkinter as ctk

from src.gui.app import ModelDeepenerApp, _cancel_widget_timers
from src.gui.view_loading import ViewLoadingIndicator, set_window_redraw

COLORS = {"surface": "#ffffff", "surface_alt": "#f8fafc", "text": "#0f172a", "muted": "#64748b",
          "border": "#e2e8f0", "primary": "#04173D", "primary_hover": "#013897", "primary_soft": "#DFE9FD"}


class TabViewTests(unittest.TestCase):
    """Test tab view."""
    @classmethod
    def setUpClass(cls):
        cls.root = ctk.CTk()
        cls.root.geometry("900x300")
        cls.root.colors = COLORS

    @classmethod
    def tearDownClass(cls):
        for after_id in cls.root.tk.call("after", "info"):
            cls.root.tk.call("after", "cancel", after_id)
        cls.root.destroy()

    def _fill(self, button):
        return button._canvas.itemcget("inner_parts", "fill")

    def test_cancelled_chooser_keeps_previous_mode_and_removes_hover_look(self):
        """Check cancelled chooser keeps previous mode and removes hover look."""
        root = self.root
        frame = ctk.CTkFrame(root)
        frame.pack()
        root._file_input_buttons = {mode: ctk.CTkButton(frame, text=mode) for mode in ("upload", "example", "batch")}
        for button in root._file_input_buttons.values():
            button.pack(side="left")
        root.file_browse_button = ctk.CTkButton(frame, text="Browse...")
        root._file_input_mode = "upload"
        root._browse_file = root._select_example_file = root._add_batch_folder = Mock()
        root._set_file_input_mode = MethodType(ModelDeepenerApp._set_file_input_mode, root)
        root._reset_file_input_hover = MethodType(ModelDeepenerApp._reset_file_input_hover, root)
        root._set_file_input_mode("upload")
        root.update()
        batch = root._file_input_buttons["batch"]
        normal = self._fill(batch)

        def cancelled_chooser():
            # CustomTkinter colors the clicked button with its hover color 100 ms after the click,
            # while the native dialog is still open.
            time.sleep(0.15)
            root.update()
            self.assertNotEqual(self._fill(batch), normal)

        batch.configure(command=lambda: ModelDeepenerApp._activate_file_input(root, "batch", cancelled_chooser))
        with patch.object(root, "winfo_containing", return_value=None):
            batch._mouse_inside = True
            batch._on_release()
            root.update()
        self.assertEqual(root._file_input_mode, "upload")
        self.assertEqual(self._fill(batch), normal)
        self.assertEqual(self._fill(root._file_input_buttons["upload"]),
                         root._apply_appearance_mode(COLORS["primary"]))
        self.assertEqual(root.file_browse_button.cget("text"), "Browse...")
        _cancel_widget_timers(frame)
        frame.destroy()

    def _model_tab_ui(self, width=900):
        root = self.root
        root.geometry(f"{width}x300")
        header = ctk.CTkFrame(root, height=60)
        header.pack(fill="x")
        header.grid_columnconfigure(5, weight=1)
        root.header = header
        root.model_tabs_container = ctk.CTkFrame(header, fg_color="transparent")
        root.model_tabs_container.grid(row=0, column=3)
        root.model_tabs_more = ctk.CTkButton(header, text="+", width=42)
        root.model_tabs_more.grid(row=0, column=5, sticky="w")
        root.model_tabs_more.grid_remove()
        root.batch_tab = ctk.CTkButton(header, text="Batch Process", width=160)
        root.batch_tab.grid(row=0, column=4)
        root._model_tabs = {}
        root._model_tabs_layout = None
        root._active_model_tab = None
        root._tell_selection = {False: "Check All Tells", True: "Check All Tells"}
        root._tell_menu_open = {False: False, True: False}
        root._current_model_display_name = lambda: root.current_model.name
        root._short_tab_text = ModelDeepenerApp._short_tab_text
        root._show_model_page = Mock()
        root._open_placeholder_action = Mock()
        root._show_models_overview_page = Mock()
        root.active_top_tab = "model"
        for name in ("_update_model_tab", "_layout_model_tabs", "_model_tab_space", "_reopen_model_tab",
                     "_close_model_tab"):
            setattr(root, name, MethodType(getattr(ModelDeepenerApp, name), root))
        models = [SimpleNamespace(name=f"Model {index}") for index in range(6)]
        for model in models:
            root.current_model = model
            root.current_file_path = model.name + ".xmi"
            root.current_file_type = "XMI"
            root.current_selected_columns = []
            root._update_model_tab()
            root.update()
            root._layout_model_tabs()
        return header, models

    def _remove_model_tab_ui(self, header):
        _cancel_widget_timers(header)
        header.destroy()
        for name in ("header", "_model_tabs"):
            delattr(self.root, name)

    def test_opening_more_models_keeps_tabs_and_lists_overflow_right_of_all_tabs(self):
        """Check opening more models keeps tabs and lists overflow right of all tabs."""
        root = self.root
        header, models = self._model_tab_ui()
        self.assertEqual(len(root._model_tabs), 6)
        visible = [key for key, state in root._model_tabs.items() if state["button"].winfo_manager()]
        self.assertIn(id(models[-1]), visible)
        self.assertTrue(root._overflow_model_tabs)
        self.assertEqual(set(visible) | set(root._overflow_model_tabs), {id(model) for model in models})
        self.assertTrue(root.model_tabs_more.winfo_ismapped())
        self.assertGreater(root.model_tabs_more.winfo_x(), root.batch_tab.winfo_x())
        # Only "x" closes a tab; the overflow list reopens a hidden one and keeps all tabs open.
        hidden = root._overflow_model_tabs[0]
        root._reopen_model_tab(hidden)
        root.update()
        self.assertEqual(len(root._model_tabs), 6)
        self.assertIs(root.current_model, root._model_tabs[hidden]["model"])
        root._close_model_tab(id(models[0]))
        root.update()
        self.assertEqual(len(root._model_tabs), 5)
        self._remove_model_tab_ui(header)

    def test_all_tabs_fit_without_overflow_button(self):
        """Check all tabs fit without overflow button."""
        root = self.root
        header, _models = self._model_tab_ui(width=2400)
        self.assertEqual(root._overflow_model_tabs, [])
        self.assertFalse(root.model_tabs_more.winfo_ismapped())
        self._remove_model_tab_ui(header)

    def test_each_tab_restores_its_own_view_and_tell(self):
        """Check each tab restores its own view and tell."""
        root = self.root
        header, models = self._model_tab_ui(width=2400)
        analysis, inspect = id(models[0]), id(models[1])
        root._model_tabs[analysis].update(view="analysis", tell="Check Tell OC1")
        root._tell_menu_open[False] = True
        root._reopen_model_tab(inspect)
        self.assertIs(root.current_model, models[1])
        self.assertFalse(root._tell_menu_open[False])
        root._show_model_page.assert_called_once()
        root._open_placeholder_action.assert_not_called()
        root._reopen_model_tab(analysis)
        self.assertIs(root.current_model, models[0])
        self.assertEqual(root._tell_selection[False], "Check Tell OC1")
        self.assertTrue(root._tell_menu_open[False])
        root._open_placeholder_action.assert_called_once_with(3)
        root._show_model_page.assert_called_once()
        self._remove_model_tab_ui(header)

    def test_tab_click_during_running_task_keeps_current_tab(self):
        """Check tab click during running task keeps current tab."""
        model = object()
        ui = SimpleNamespace(_model_task_active=True, _model_tabs={1: {"model": object()}}, _active_model_tab=2,
                             current_model=model, _show_model_page=Mock(), _open_placeholder_action=Mock(),
                             _batch_view="analysis", _show_batch_analysis=Mock(), _show_batch_page=Mock())
        ModelDeepenerApp._reopen_model_tab(ui, 1)
        ModelDeepenerApp._reopen_batch_tab(ui)
        self.assertIs(ui.current_model, model)
        self.assertEqual(ui._active_model_tab, 2)
        ui._show_model_page.assert_not_called()
        ui._show_batch_analysis.assert_not_called()

    def test_batch_tab_restores_analysis_with_open_tell_menu(self):
        """Check batch tab restores analysis with open tell menu."""
        ui = SimpleNamespace(_batch_view="analysis", _tell_menu_open={False: False, True: False},
                             _show_batch_analysis=Mock(), _show_batch_page=Mock())
        ModelDeepenerApp._reopen_batch_tab(ui)
        self.assertTrue(ui._tell_menu_open[True])
        ui._show_batch_analysis.assert_called_once()
        ui._batch_view = "inspect"
        ModelDeepenerApp._reopen_batch_tab(ui)
        ui._show_batch_page.assert_called_once()

    def test_closed_tell_menu_opens_analysis(self):
        """Check closed tell menu opens analysis."""
        ui = SimpleNamespace(_tell_menu_open={False: False, True: False}, _single_tell_menu=Mock(),
                             _batch_tell_menu=Mock(), action_cards={3: object()}, _open_placeholder_action=Mock(),
                             _show_batch_analysis=Mock())
        ModelDeepenerApp._toggle_tell_menu(ui, False)
        ui._open_placeholder_action.assert_called_once_with(3)
        ModelDeepenerApp._toggle_tell_menu(ui, True)
        ui._show_batch_analysis.assert_called_once()


class ViewLoadingTests(unittest.TestCase):
    """Test view loading."""
    def test_hidden_build_starts_and_always_stops_indicator(self):
        """Check hidden build starts and always stops indicator."""
        events = []
        ui = SimpleNamespace(winfo_rootx=lambda: 10, winfo_rooty=lambda: 20, winfo_width=lambda: 800,
                             winfo_height=lambda: 600, update_idletasks=lambda: events.append("idle"),
                             _view_loading=Mock())
        ui._view_loading.stop.side_effect = lambda: events.append("stop")
        with patch("src.gui.app.set_window_redraw", side_effect=lambda _w, enabled: events.append(enabled) or True), \
                patch("src.gui.app.ctk.ScalingTracker.get_widget_scaling", return_value=1.5):
            ModelDeepenerApp._build_view_hidden(ui, lambda: events.append("build"), "Preparing analysis...")
            ui._view_loading.start.assert_called_once_with((10, 20, 800, 600), "Preparing analysis...", 1.5)
            self.assertEqual(events, [False, "build", "idle", True, "stop"])
            events.clear()
            with self.assertRaises(RuntimeError):
                ModelDeepenerApp._build_view_hidden(ui, Mock(side_effect=RuntimeError("failed")))
            self.assertEqual(events, [False, True, "stop"])

    def test_single_and_batch_analysis_are_built_hidden(self):
        """Check single and batch analysis are built hidden."""
        for method, renderer, args in ((ModelDeepenerApp._open_placeholder_action, "_render_single_analysis", (3,)),
                                       (ModelDeepenerApp._show_batch_analysis, "_render_batch_analysis", ())):
            ui = SimpleNamespace(_tell_selection={False: "Check Tell TO2", True: "Check Tell TO2"},
                                 _build_view_hidden=Mock(side_effect=lambda build, message="": build()),
                                 _render_single_analysis=Mock(), _render_batch_analysis=Mock(), _show_error=Mock(),
                                 _current_model_display_name=lambda: "Model", current_model=Mock(), batch_models=[])
            ui._run_model_task = lambda _total, _message, work, success, _failure: success(work(None))
            with patch("src.gui.app.analyze_tells", return_value=[]):
                method(ui, *args)
            ui._build_view_hidden.assert_called_once()
            getattr(ui, renderer).assert_called_once()

    @unittest.skipUnless(sys.platform == "win32", "Windows window painting")
    def test_window_redraw_can_be_stopped_and_resumed(self):
        """Check window redraw can be stopped and resumed."""
        root = ctk.CTk()
        try:
            root.update()
            self.assertTrue(set_window_redraw(root, False))
            self.assertTrue(set_window_redraw(root, True))
        finally:
            _cancel_widget_timers(root)
            root.destroy()

    def test_indicator_appears_only_after_delay_without_percentage(self):
        """Check indicator appears only after delay without percentage."""
        indicator = ViewLoadingIndicator(COLORS)
        try:
            indicator.prepare()
            indicator.start((0, 0, 800, 600), "Preparing analysis...", delay_ms=400)
            time.sleep(0.1)
            indicator.stop()
            self.assertFalse(indicator.shown.wait(0.7))
            indicator.start((0, 0, 800, 600), "Preparing analysis...", delay_ms=100)
            self.assertTrue(indicator.shown.wait(5))
            indicator.stop()
        finally:
            process = indicator._process
            indicator.close()
        self.assertIsNotNone(process)
        self.assertEqual(process.poll(), 0)


if __name__ == "__main__":
    unittest.main()

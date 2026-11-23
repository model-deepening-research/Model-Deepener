import threading
import time
import unittest
from types import MethodType, SimpleNamespace
from unittest.mock import Mock

import customtkinter as ctk

from src.gui.app import ModelDeepenerApp, ModelProgressDialog, DatabaseDialog, _cancel_widget_timers


class OverviewPreparationTests(unittest.TestCase):
    """Test overview preparation."""
    def test_filters_use_original_type_and_cached_counts(self):
        """Check filters use original type and cached counts."""
        loaded = SimpleNamespace(name="Example", source_file="example.xml", file_type="XML", model=object())
        ui = SimpleNamespace(models_search_var=SimpleNamespace(get=lambda: "example"),
                             models_type_filter_var=SimpleNamespace(get=lambda: "XML"),
                             models_min_objects_var=SimpleNamespace(get=lambda: "2"),
                             models_min_attributes_var=SimpleNamespace(get=lambda: "3"),
                             _optional_int_filter=ModelDeepenerApp._optional_int_filter,
                             _overview_counts_for=lambda _loaded: (1, 2, 3, 2))
        self.assertTrue(ModelDeepenerApp._model_matches_overview_filters(ui, loaded))
        ui.models_type_filter_var = SimpleNamespace(get=lambda: "Ecore")
        self.assertFalse(ModelDeepenerApp._model_matches_overview_filters(ui, loaded))


class OverviewWindowTests(unittest.TestCase):
    """Test overview window."""
    @classmethod
    def setUpClass(cls):
        cls.root = ctk.CTk()
        cls.root.geometry("1400x800")
        cls.root.update()

    @classmethod
    def tearDownClass(cls):
        for after_id in cls.root.tk.call("after", "info"):
            cls.root.tk.call("after", "cancel", after_id)
        cls.root.destroy()

    def test_actual_overview_preserves_table_filters_badge_and_sort(self):
        """Check actual overview preserves table filters badge and sort."""
        root = self.root
        root.colors = {"app_bg": "#f8fafc", "surface": "#ffffff", "border": "#e2e8f0", "text": "#0f172a",
                       "muted": "#64748b", "primary": "#04173d", "primary_hover": "#013897",
                       "primary_soft": "#dfe9fd", "danger": "#dc2626", "success": "#16a34a"}
        root.shell = ctk.CTkFrame(root)
        root.shell.pack(fill="both", expand=True)
        root.shell.grid_columnconfigure(1, weight=1)
        root.shell.grid_rowconfigure(0, weight=1)
        root.sidebar = ctk.CTkFrame(root.shell)
        root.sidebar.grid(row=0, column=0)
        root.content = ctk.CTkFrame(root.shell)
        root.content.grid(row=0, column=1, sticky="nsew")
        model_a = SimpleNamespace(get_is_adapted=lambda: True)
        model_b = SimpleNamespace(get_is_adapted=lambda: False)
        earlier = SimpleNamespace(name="Old", source_file="old.xml", file_type="XML", model=model_a,
                                  uploaded="2026-01-01 10:00", last_worked_on="2026-01-01 10:00", last_action="Imported")
        newer = SimpleNamespace(name="New", source_file="new.csv", file_type="CSV", model=model_b,
                                uploaded="2026-03-01 10:00", last_worked_on="2026-03-01 10:00", last_action="Imported")
        root.loaded_models = [earlier, newer]
        root._overview_model_counts = {id(earlier): (1, 2, 3, 4), id(newer): (0, 1, 0, 2)}
        root._set_top_tab = Mock()
        root._export_all_models = Mock()
        root._inspect_all_models = Mock()
        root._delete_loaded_model = Mock()
        root._open_loaded_model = Mock()
        root._show_adapted_tooltip = Mock()
        root._hide_adapted_tooltip = Mock()
        root._display_table_value = ModelDeepenerApp._display_table_value
        root._optional_int_filter = ModelDeepenerApp._optional_int_filter
        root._model_last_action_label = ModelDeepenerApp._model_last_action_label
        for name in ("_hide_workflow_sidebar", "_clear_content", "_card", "_card_title", "_draw_models_table_cell",
                     "_overview_counts_for", "_model_matches_overview_filters", "_populate_models_table",
                     "_draw_visible_models_rows", "_on_models_canvas_scroll", "_cancel_models_canvas_redraw",
                     "_bind_models_scroll_events", "_unbind_models_scroll_events",
                     "_on_models_mousewheel"):
            setattr(root, name, MethodType(getattr(ModelDeepenerApp, name), root))
        ModelDeepenerApp._render_models_overview_page(root)
        root.update_idletasks()
        canvas = root.models_canvas
        self.assertEqual(root.total_models_label.cget("text"), "Total Models: 2")
        self.assertEqual(root.total_models_label.cget("text_color"), "#2563EB")
        header = root.total_models_label.master
        buttons = [widget for widget in header.winfo_children() if isinstance(widget, ctk.CTkButton)]
        self.assertEqual([widget.cget("text") for widget in buttons], ["Export All", "Inspect All"])
        self.assertIsInstance(root.total_models_label, ctk.CTkLabel)
        self.assertGreater(root.total_models_label.cget("font").cget("size"), 13)
        # The total lies between the title and the buttons, centered in the free column.
        self.assertEqual(root.total_models_label.grid_info()["column"], 1)
        self.assertEqual(header.grid_columnconfigure(1)["weight"], 1)
        self.assertEqual({widget.grid_info()["column"] for widget in buttons}, {2, 3})
        self.assertTrue(all(widget.cget("height") == 40 and widget.cget("corner_radius") == 7 for widget in buttons))
        self.assertTrue(all(widget.cget("font").cget("size") == 13 for widget in buttons))
        body = root.models_table_wrapper.master.master
        self.assertEqual(len(body.grid_slaves(row=1)), 0)
        self.assertEqual(body.grid_rowconfigure(0)["weight"], 1)
        self.assertEqual(root.models_table_wrapper.master.grid_info()["sticky"], "nesw")
        texts = [(canvas.itemcget(item, "text"), canvas.coords(item)[1]) for item in canvas.find_all()
                 if canvas.type(item) == "text"]
        self.assertLess(next(y for text, y in texts if text == "New"), next(y for text, y in texts if text == "Old"))
        for header in ("Model Name", "Source File", "Type", "Higher Level Classes", "Last Action", "Last worked on", "Open Model"):
            self.assertIn(header, [text for text, _y in texts])
        def click_text(text):
            item = next(item for item in canvas.find_all()
                        if canvas.type(item) == "text" and canvas.itemcget(item, "text") == text)
            x, y = canvas.coords(item)
            canvas.event_generate("<Motion>", x=int(x), y=int(y))
            canvas.event_generate("<Button-1>", x=int(x), y=int(y))
            root.update_idletasks()
        click_text("New")
        root._open_loaded_model.assert_called_once_with(newer)
        click_text("Delete")
        root._delete_loaded_model.assert_called_once_with(newer)
        badge = next(item for item in canvas.find_all() if canvas.type(item) == "text" and canvas.itemcget(item, "text") == "adapted")
        self.assertEqual(canvas.itemcget(badge, "fill"), "#A34D00")
        root.models_type_filter_var.set("XML")
        root._populate_models_table()
        texts = [canvas.itemcget(item, "text") for item in canvas.find_all() if canvas.type(item) == "text"]
        self.assertIn("Old", texts)
        self.assertNotIn("New", texts)
        self.assertIn("FMMLx", texts)
        _cancel_widget_timers(root.shell)
        root.shell.destroy()

    def test_large_overview_draws_only_visible_rows_and_scrolls(self):
        """Check large overview draws only visible rows and scrolls."""
        root = self.root
        root.colors = {"text": "#000000", "muted": "#666666", "border": "#cccccc", "primary": "#0055aa",
                       "danger": "#dc2626", "success": "#16a34a"}
        model = SimpleNamespace(get_is_adapted=lambda: False)
        root.loaded_models = [SimpleNamespace(name=f"Model {i:04}", source_file=f"{i}.xmi", file_type="XMI",
                                              model=model, uploaded="", last_worked_on="", last_action="Imported")
                              for i in range(3212)]
        root._overview_model_counts = {id(item): (0, 1, 0, 0) for item in root.loaded_models}
        root.models_canvas = __import__("tkinter").Canvas(root, width=1000, height=320)
        root.models_canvas.pack()
        root.models_scrollbar = Mock()
        root.models_search_var = SimpleNamespace(get=lambda: "")
        root.models_type_filter_var = SimpleNamespace(get=lambda: "All")
        root.models_min_objects_var = SimpleNamespace(get=lambda: "")
        root.models_min_attributes_var = SimpleNamespace(get=lambda: "")
        root._optional_int_filter = ModelDeepenerApp._optional_int_filter
        root._model_last_action_label = ModelDeepenerApp._model_last_action_label
        root._display_table_value = ModelDeepenerApp._display_table_value
        root._open_loaded_model = Mock()
        root._delete_loaded_model = Mock()
        root._show_adapted_tooltip = Mock()
        root._hide_adapted_tooltip = Mock()
        for name in ("_draw_models_table_cell", "_overview_counts_for", "_model_matches_overview_filters",
                     "_populate_models_table", "_draw_visible_models_rows", "_on_models_canvas_scroll", "_cancel_models_canvas_redraw"):
            setattr(root, name, MethodType(getattr(ModelDeepenerApp, name), root))
        root.models_canvas.configure(yscrollcommand=root._on_models_canvas_scroll)
        root.models_canvas.bind("<Destroy>", root._cancel_models_canvas_redraw, add="+")
        root.update_idletasks()
        root._populate_models_table()
        root.update_idletasks()
        self.assertLess(len(root.models_canvas.find_all()), 300)
        root.models_canvas.yview_moveto(1.0)
        root.update_idletasks()
        texts = [root.models_canvas.itemcget(item, "text") for item in root.models_canvas.find_all()
                 if root.models_canvas.type(item) == "text"]
        self.assertIn("Model 3211", texts)
        self.assertNotIn("Model 0000", texts)
        self.assertLess(len(root.models_canvas.find_all()), 300)
        root.models_canvas.destroy()

    def test_database_choice_loads_in_worker_and_shows_progress(self):
        """Check database choice loads in worker and shows progress."""
        root = self.root
        root.colors = {"app_bg": "#f8fafc", "surface": "#ffffff", "border": "#e2e8f0", "text": "#0f172a",
                       "muted": "#64748b", "primary": "#04173d", "primary_hover": "#013897",
                       "primary_soft": "#dfe9fd", "danger": "#dc2626", "disabled": "#cbd5e1"}
        thread_ids = []
        result = object()
        def load(_name):
            thread_ids.append(threading.get_ident())
            time.sleep(0.8)
            return result
        folder = SimpleNamespace(get_names=lambda: ["Example"], open_database=load)
        dialog = DatabaseDialog(root, folder)
        dialog.grab_set()
        observed = []
        def inspect():
            observed.append((dialog._error_label.cget("text"), dialog._open_button.cget("state")))
        def poll():
            if dialog.winfo_exists():
                root.after(30, poll)
            else:
                root.quit()
        main_thread = threading.get_ident()
        dialog._open_selected()
        root.after(600, inspect)
        root.after(30, poll)
        timeout = root.after(5000, root.quit)
        root.mainloop()
        root.after_cancel(timeout)
        self.assertEqual(observed, [("Loading database...", "disabled")])
        self.assertEqual(dialog.get_result(), (result, "Example"))
        self.assertNotEqual(thread_ids, [main_thread])

    def test_autosave_runs_without_blocking_the_event_loop(self):
        """Check autosave runs without blocking the event loop."""
        root = self.root
        root._is_closing = True
        root._model_task_active = False
        root._autosave_in_progress = False
        identities = []
        def slow_save():
            identities.append(threading.get_ident())
            time.sleep(0.7)
        root._database = SimpleNamespace(save_if_changed=slow_save)
        root._show_error = Mock()
        main_thread = threading.get_ident()
        started = time.perf_counter()
        ModelDeepenerApp._autosave_models(root)
        self.assertLess(time.perf_counter() - started, 0.2)
        ticks = []
        def tick():
            ticks.append(time.perf_counter())
            if root._autosave_in_progress:
                root.after(30, tick)
            else:
                root.quit()
        timeout = root.after(4000, root.quit)
        root.after(30, tick)
        root.mainloop()
        root.after_cancel(timeout)
        self.assertFalse(root._autosave_in_progress)
        self.assertGreater(len(ticks), 5)
        self.assertNotEqual(identities, [main_thread])
        root._show_error.assert_not_called()

    def test_background_preparation_keeps_loading_window_until_render(self):
        """Check background preparation keeps loading window until render."""
        root = self.root
        root.colors = {"text": "#000000", "muted": "#666666", "border": "#cccccc", "primary": "#0055aa"}
        root._overlay = SimpleNamespace(show=lambda: None, hide=lambda: None)
        main_thread = threading.get_ident()
        worker = []
        model = SimpleNamespace(get_all_flat_classes=lambda: [1], get_all_pure_objects=lambda: [])
        loaded = SimpleNamespace(model=model)
        root.loaded_models = [loaded]
        def count(_model):
            worker.append(threading.get_ident())
            time.sleep(0.65)
            return 0
        root._count_higher_level_classes = count
        root._count_attributes = lambda _model: 0
        root._run_model_task = MethodType(ModelDeepenerApp._run_model_task, root)
        root._show_error = Mock()
        observed = []
        def render():
            progress = root._model_progress_dialog
            observed.append((threading.get_ident(), bool(progress.winfo_ismapped()), root._model_task_active))
            root.after(50, root.quit)
        root._render_models_overview_page = render
        timeout = root.after(5000, root.quit)
        ModelDeepenerApp._show_models_overview_page(root)
        root.mainloop()
        root.after_cancel(timeout)
        self.assertEqual(len(worker), 1)
        self.assertNotEqual(worker[0], main_thread)
        self.assertEqual(observed, [(main_thread, True, True)])
        self.assertEqual(root._overview_model_counts[id(loaded)], (0, 1, 0, 0))
        root._show_error.assert_not_called()


if __name__ == "__main__":
    unittest.main()

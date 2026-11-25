import unittest
import time
import threading
import customtkinter as ctk
from types import SimpleNamespace, MethodType
from tkinter import ttk
from unittest.mock import Mock, patch

from src.gui.app import ModelDeepenerApp, ModelProgressDialog, InlineModelProgress, VirtualModelSelector, BatchProblemDetails, atomic_page, _cancel_widget_timers
from src.importers.import_report import ImportReport, ImportAdaptation


class BatchDialogTests(unittest.TestCase):
    """Test batch dialog."""
    def test_import_progress_closes_before_hints_and_cancel_does_not_save(self):
        """Check import progress closes before hints and cancel does not save."""
        report = ImportReport()
        report.add_adaptation(ImportAdaptation('Interface', 'A', 'Adapted'))
        importer = Mock()
        importer.import_file.return_value = (object(), report)
        def run_task(_total, _message, work, success, _failure, handoff=False):
            result = work(lambda *_args: None)
            if handoff:
                success(result, lambda: None)
            else:
                success(result)
        ui = SimpleNamespace(_importer_for_file=Mock(return_value=importer), _ask_batch_problems=Mock(return_value=False),
                             _store_batch=Mock(), _show_error=Mock(), _run_model_task=run_task, _overlay=Mock())
        ModelDeepenerApp._create_batch(ui, ['a.csv', 'b.csv'])
        ui._ask_batch_problems.assert_called_once()
        ui._store_batch.assert_not_called()
        ui._overlay.show.assert_called_once()
        ui._overlay.hide.assert_called_once()

    def test_bad_file_is_reported_and_remaining_models_are_saved(self):
        """Check bad file is reported and remaining models are saved."""
        importer = Mock()
        report = ImportReport()
        def read(path):
            if path == "bad.csv":
                raise ValueError("bad row")
            return object(), report
        importer.import_file.side_effect = read
        def run(_total, _message, work, success, _failure, handoff=False):
            result = work(lambda *_args: None)
            if handoff:
                success(result, lambda: None)
            else:
                success(result)
        ui = SimpleNamespace(_overlay=Mock(), _importer_for_file=Mock(return_value=importer),
                             _ask_batch_problems=Mock(return_value=True), _store_batch=Mock(),
                             _show_error=Mock(), _run_model_task=run, batch_tab=Mock(), _show_batch_page=Mock())
        ModelDeepenerApp._create_batch(ui, ["first.csv", "bad.csv", "last.csv"])
        self.assertEqual(ui._ask_batch_problems.call_args.args, ([], [("bad.csv", "bad row")]))
        self.assertEqual(ui._ask_batch_problems.call_args.kwargs["prepared_summary"], [])
        saved = ui._store_batch.call_args.args[0]
        self.assertEqual([candidate[0] for candidate in saved], ["first.csv", "last.csv"])
        ui._show_error.assert_not_called()
        ui._show_batch_page.assert_called_once()

    def test_all_files_failing_shows_dialog_without_saving(self):
        """Check all files failing shows dialog without saving."""
        importer = Mock()
        importer.import_file.side_effect = ValueError("broken")
        def run(_total, _message, work, success, _failure, handoff=False):
            result = work(lambda *_args: None)
            if handoff:
                success(result, lambda: None)
            else:
                success(result)
        ui = SimpleNamespace(_overlay=Mock(), _importer_for_file=Mock(return_value=importer),
                             _ask_batch_problems=Mock(return_value=True), _store_batch=Mock(),
                             _show_error=Mock(), _run_model_task=run)
        ModelDeepenerApp._create_batch(ui, ["bad.csv"])
        self.assertEqual(ui._ask_batch_problems.call_args.args, ([], [("bad.csv", "broken")]))
        ui._store_batch.assert_not_called()
        ui._overlay.hide.assert_called_once()

    def test_batch_keeps_one_overlay_across_all_phases(self):
        """Check batch keeps one overlay across all phases."""
        report = ImportReport()
        report.add_adaptation(ImportAdaptation("Interface", "A", "Adapted"))
        importer = Mock()
        importer.import_file.return_value = (object(), report)
        depth = [0]
        events = []
        def show():
            depth[0] += 1
            events.append(("show", depth[0]))
        def hide():
            depth[0] -= 1
            events.append(("hide", depth[0]))
        overlay = SimpleNamespace(show=show, hide=hide)
        def run(_total, _message, work, success, failure, handoff=False):
            overlay.show()
            result = work(lambda *_args: None)
            if handoff:
                success(result, overlay.hide)
            else:
                overlay.hide()
                success(result)
        def ask(_reports, _failures, prepared_summary, on_visible, **_kwargs):
            self.assertGreater(depth[0], 0)
            on_visible()
            return True
        def display():
            self.assertGreater(depth[0], 0)
        ui = SimpleNamespace(_overlay=overlay, _importer_for_file=Mock(return_value=importer),
                             _ask_batch_problems=ask, _store_batch=Mock(), _show_error=Mock(),
                             _run_model_task=run, batch_tab=Mock(), _show_batch_page=display)
        ModelDeepenerApp._create_batch(ui, ["a.csv"])
        self.assertEqual(depth[0], 0)
        self.assertTrue(all(count > 0 for _kind, count in events[:-1]))

    def test_progress_displays_count_and_fraction(self):
        """Check progress displays count and fraction."""
        progress = SimpleNamespace(bar=Mock(), count=Mock(), update_idletasks=Mock())
        ModelProgressDialog.update_progress(progress, 3, 5)
        progress.bar.set.assert_called_once_with(0.6)
        progress.count.configure.assert_called_once_with(text='3 / 5 models')
        progress.update_idletasks.assert_called_once()


class RealProgressWindowTests(unittest.TestCase):
    """Test real progress window."""
    @classmethod
    def setUpClass(cls):
        cls.root = ctk.CTk()

    @classmethod
    def tearDownClass(cls):
        for after_id in cls.root.tk.call("after", "info"):
            cls.root.tk.call("after", "cancel", after_id)
        cls.root.destroy()

    def test_long_task_shows_window_and_progress(self):
        """Check long task shows window and progress."""
        root = self.root
        root.colors = {"text": "#000000", "muted": "#666666", "border": "#cccccc", "primary": "#0055aa"}
        root._overlay = SimpleNamespace(cover=lambda _dialog: None, show=lambda: None, hide=lambda: None)
        seen = []
        finished = []
        def work(progress):
            progress(1, 2)
            time.sleep(2.3)
            return "done"
        try:
            ModelDeepenerApp._run_model_task(root, 2, "Importing models...", work, finished.append, self.fail)
            def inspect():
                for child in root.winfo_children():
                    if isinstance(child, ModelProgressDialog) and hasattr(child, "count"):
                        seen.append(child.count.cget("text"))
                if not finished:
                    root.after(50, inspect)
                else:
                    root.quit()
            root.after(50, inspect)
            timeout = root.after(5000, root.quit)
            root.mainloop()
            root.after_cancel(timeout)
            self.assertEqual(finished, ["done"])
            self.assertIn("1 / 2 models", seen)
        finally:
            pass

    def test_batch_progress_releases_before_report_is_visible(self):
        """Check batch progress releases before report is visible."""
        root = self.root
        root.colors = {"text": "#000000", "muted": "#666666", "border": "#cccccc", "primary": "#0055aa",
                       "primary_hover": "#004488", "surface": "#ffffff", "app_bg": "#ffffff"}
        root._overlay = SimpleNamespace(cover=lambda _dialog: None, show=lambda: None, hide=lambda: None)
        root._run_model_task = MethodType(ModelDeepenerApp._run_model_task, root)
        report = ImportReport()
        report.add_adaptation(ImportAdaptation("Unknown type", "A", "Unknown type replaced by String."))
        importer = Mock()
        def read(_path):
            time.sleep(0.35)
            return object(), report
        importer.import_file.side_effect = read
        root._importer_for_file = lambda _path: importer
        root._store_batch = Mock()
        root.batch_tab = Mock()
        finished = []
        root._show_batch_page = lambda: (finished.append(True), root.after(50, root.quit))
        errors = []
        root._show_error = lambda *args: errors.append(args)
        observed = []
        def ask(reports, failures=(), **kwargs):
            release = kwargs["on_visible"]
            def handed_off():
                progress = root._model_progress_dialog
                dialogs = [w for w in root.winfo_children() if isinstance(w, ctk.CTkToplevel)
                           and not isinstance(w, ModelProgressDialog) and w.title() == "Import Problems"]
                observed.append((bool(progress.winfo_ismapped()), progress.bar.get(), bool(dialogs[0].winfo_ismapped())))
                release()
                dialog = dialogs[0]
                def click_continue():
                    def children(widget):
                        for child in widget.winfo_children():
                            yield child
                            yield from children(child)
                    next(w for w in children(dialog) if isinstance(w, ctk.CTkButton)
                         and w.cget("text") == "Continue Import").invoke()
                dialog.after(150, click_continue)
            kwargs["on_visible"] = handed_off
            return ModelDeepenerApp._ask_batch_problems(root, reports, failures, **kwargs)
        root._ask_batch_problems = ask
        root.deiconify()
        root.update()
        timeout = root.after(6000, root.quit)
        ModelDeepenerApp._create_batch(root, ["a.xmi", "b.xmi"])
        root.mainloop()
        root.after_cancel(timeout)
        self.assertEqual(errors, [])
        self.assertEqual(finished, [True])
        self.assertEqual(len(observed), 1)
        self.assertTrue(observed[0][0])
        self.assertLess(observed[0][1], 1.0)
        self.assertFalse(observed[0][2])
        self.assertEqual(len(root._store_batch.call_args.args[0]), 2)

    def test_large_progress_window_is_visible_and_reused(self):
        """Check large progress window is visible and reused."""
        root = self.root
        root.colors = {"text": "#000000", "muted": "#666666", "border": "#cccccc", "primary": "#0055aa"}
        root._overlay = SimpleNamespace(cover=lambda _dialog: None, show=lambda: None, hide=lambda: None)
        root.deiconify()
        root.update()
        seen = []
        windows = []
        completed = []
        def work(progress):
            for count in range(1, 301):
                progress(count, 864)
            time.sleep(0.9)
        def start():
            ModelDeepenerApp._run_model_task(root, 864, "Importing", work, done, self.fail)
        def done(_value):
            completed.append(True)
            if len(completed) == 1:
                root.after(50, start)
            else:
                root.quit()
        def observe():
            window = getattr(root, "_model_progress_dialog", None)
            if window is not None and window.winfo_exists() and window.winfo_ismapped():
                seen.append(window.count.cget("text"))
                windows.append(window)
            if len(completed) < 2:
                root.after(50, observe)
        root.after(50, observe)
        timeout = root.after(5000, root.quit)
        start()
        root.mainloop()
        root.after_cancel(timeout)
        self.assertEqual(len(completed), 2)
        self.assertIn("300 / 864 models", seen)
        self.assertTrue(all(window is windows[0] for window in windows))
        self.assertEqual(root._model_progress_dialog.state(), "withdrawn")

    def test_writing_database_uses_animated_progress(self):
        """Check writing database uses animated progress."""
        root = self.root
        root.colors = {"text": "#000000", "muted": "#666666", "border": "#cccccc", "primary": "#0055aa"}
        progress = ModelProgressDialog(root, 5, "Preparing models...")
        progress.set_message("Writing database...")
        self.assertEqual(progress.bar.cget("mode"), "indeterminate")
        self.assertEqual(progress.count.winfo_manager(), "")
        progress.bar.stop()
        _cancel_widget_timers(progress)
        progress.destroy()

    def test_detail_buttons_mark_first_and_clicked_view(self):
        """Check detail buttons mark first and clicked view."""
        root = self.root
        root.colors = {"primary": "#0055aa", "primary_soft": "#ddeeff", "border": "#cccccc",
                       "disabled_bg": "#eeeeee"}
        root.detail_card = ctk.CTkFrame(root)
        root.detail_card.pack()
        root._clear_detail_option_bar = MethodType(ModelDeepenerApp._clear_detail_option_bar, root)
        callbacks = [Mock(), Mock()]
        ModelDeepenerApp._render_detail_option_buttons(root, [("Attributes", True, callbacks[0]),
                                                              ("Associations", True, callbacks[1])])
        buttons = root._detail_option_bar.winfo_children()
        self.assertEqual(buttons[0].cget("fg_color"), "#0055aa")
        buttons[1].invoke()
        self.assertEqual(buttons[0].cget("fg_color"), "#FFFFFF")
        self.assertEqual(buttons[1].cget("fg_color"), "#0055aa")
        callbacks[1].assert_called_once()
        root.detail_card.destroy()

    def test_progress_starts_empty_or_runs_without_count(self):
        """Check progress starts empty or runs without count."""
        root = self.root
        root.colors = {"text": "#000000", "muted": "#666666", "border": "#cccccc", "primary": "#0055aa"}
        root._overlay = SimpleNamespace(cover=lambda _dialog: None)
        multi = ModelProgressDialog(root, 5, "Importing")
        self.assertEqual(multi.bar.cget("mode"), "determinate")
        self.assertEqual(multi.bar.get(), 0)
        self.assertEqual(multi.count.cget("text"), "0 / 5 models")
        _cancel_widget_timers(multi)
        multi.destroy()
        single = ModelProgressDialog(root, 1, "Importing")
        self.assertEqual(single.bar.cget("mode"), "indeterminate")
        self.assertEqual(single.count.winfo_manager(), "")
        self.assertTrue(single._indeterminate)
        single.bar.stop()
        _cancel_widget_timers(single)
        single.destroy()

    def test_model_tabs_keep_views_and_overflow_without_closing(self):
        """Check model tabs keep views and overflow without closing."""
        root = self.root
        root.colors = {"surface": "#ffffff", "text": "#000000", "border": "#cccccc", "muted": "#666666",
                       "primary": "#0055aa", "primary_soft": "#dfe9fd", "surface_alt": "#eeeeee"}
        container = ctk.CTkFrame(root)
        container.pack()
        root.model_tabs_container = ctk.CTkFrame(container)
        root.model_tabs_container.grid(row=0, column=0)
        root.model_tabs_more = ctk.CTkButton(container, text="+")
        root.model_tabs_more.grid(row=0, column=1)
        root.model_tabs_more.grid_remove()
        root._model_tabs = {}
        root._active_model_tab = None
        root._tell_selection = {False: "Check All Tells"}
        root._tell_menu_open = {False: False}
        root._current_model_display_name = lambda: root.current_model.name
        root._short_tab_text = ModelDeepenerApp._short_tab_text
        root._show_model_page = Mock()
        root._open_placeholder_action = Mock()
        root._show_models_overview_page = Mock()
        root.active_top_tab = "models"
        for name in ("_layout_model_tabs", "_model_tab_space", "_reopen_model_tab", "_close_model_tab"):
            setattr(root, name, MethodType(getattr(ModelDeepenerApp, name), root))
        models = [SimpleNamespace(name=f"Model {i}") for i in range(3)]
        for model in models:
            root.current_model = model
            root.current_file_path = model.name + ".xmi"
            root.current_file_type = "XMI"
            root.current_selected_columns = []
            ModelDeepenerApp._update_model_tab(root)
        self.assertEqual(len(root._model_tabs), 3)
        self.assertTrue(root._overflow_model_tabs)
        first = root._model_tabs[id(models[0])]
        first.update(view="analysis", tell="Check Tell OC1")
        root._reopen_model_tab(id(models[0]))
        self.assertIs(root.current_model, models[0])
        self.assertEqual(root._tell_selection[False], "Check Tell OC1")
        root._open_placeholder_action.assert_called_once_with(3)
        root._reopen_model_tab(id(models[1]))
        self.assertIs(root.current_model, models[1])
        root._show_model_page.assert_called_once()
        root._close_model_tab(id(models[0]))
        self.assertEqual(len(root._model_tabs), 2)
        self.assertIn(id(models[2]), root._model_tabs)
        _cancel_widget_timers(container)
        container.destroy()
        del root._model_tabs

    def test_batch_reuses_workflow_sidebar_and_card_dimensions(self):
        """Check batch reuses workflow sidebar and card dimensions."""
        root = self.root
        root.colors = {"surface": "#ffffff", "text": "#000000", "border": "#cccccc",
                       "primary": "#0055aa", "primary_soft": "#dfe9fd"}
        root.shell = ctk.CTkFrame(root)
        root.shell.pack(fill="both", expand=True)
        root.sidebar = ctk.CTkFrame(root.shell, width=310)
        root.sidebar.grid(row=0, column=0, sticky="nsw")
        root.sidebar.grid_propagate(False)
        root.content = ctk.CTkFrame(root.shell)
        root.content.grid(row=0, column=1)
        root.action_cards = {}
        root.action_title_labels = {}
        root.ACTION_TITLES = {1: "Upload File or Select Example", 2: "Inspect Model", 3: "Conduct Model Deepening Analysis"}
        root._tell_menu_open = {False: False, True: False}
        root._try_open_action = lambda _action: None
        root._select_tell = lambda *_args: None
        root._show_import_page = lambda: None
        root._show_batch_page = lambda: None
        root._toggle_tell_menu = lambda _batch: None
        root._make_tell_menu = MethodType(ModelDeepenerApp._make_tell_menu, root)
        for action in root.ACTION_TITLES:
            ModelDeepenerApp._build_action_card(root, action)
        root._single_tell_menu = root._make_tell_menu(root.sidebar, batch=False)
        sidebar = root.sidebar
        self.assertNotIsInstance(root._single_tell_menu, ctk.CTkScrollableFrame)
        self.assertEqual(len(root._single_tell_menu.winfo_children()), 10)
        root.current_action = 2
        root._tell_menu_open[False] = True
        ModelDeepenerApp._show_workflow_sidebar(root)
        self.assertEqual(root._single_tell_menu.winfo_manager(), "")
        root.current_action = 3
        ModelDeepenerApp._show_workflow_sidebar(root)
        self.assertEqual(root._single_tell_menu.winfo_manager(), "pack")
        root._tell_menu_open[True] = True
        ModelDeepenerApp._show_batch_sidebar(root, False)
        self.assertEqual(root._batch_tell_menu.winfo_manager(), "")
        root._tell_menu_open[True] = False
        ModelDeepenerApp._show_batch_sidebar(root, True)
        self.assertEqual(root._batch_tell_menu.winfo_manager(), "pack")
        ModelDeepenerApp._show_batch_sidebar(root, False)
        root.active_top_tab = "batch"
        root.current_model = object()
        root._show_batch_analysis = Mock()
        root._open_placeholder_action = Mock()
        root._try_open_action = MethodType(ModelDeepenerApp._try_open_action, root)
        root.update()
        root.action_title_labels[3]._label.event_generate("<Button-1>")
        root.update()
        root._show_batch_analysis.assert_called_once()
        root._open_placeholder_action.assert_not_called()
        self.assertIs(root.sidebar, sidebar)
        self.assertEqual(root.sidebar.cget("width"), 310)
        self.assertTrue(all(card.cget("height") == 58 for card in root.action_cards.values()))
        self.assertEqual([root.action_title_labels[i].cget("text") for i in (1, 2, 3)], list(root.ACTION_TITLES.values()))
        for title in root.action_title_labels.values():
            self.assertLessEqual(title.winfo_reqheight(), 58)
        _cancel_widget_timers(root.shell)
        root.shell.destroy()
        del root._batch_tell_menu

    def test_task_blocks_another_task_and_releases_grab(self):
        """Check task blocks another task and releases grab."""
        root = self.root
        root.colors = {"text": "#000000", "muted": "#666666", "border": "#cccccc", "primary": "#0055aa"}
        root._overlay = SimpleNamespace(cover=lambda _dialog: None, show=Mock(), hide=Mock())
        completed = []
        def work(_progress):
            time.sleep(0.2)
            return "first"
        ModelDeepenerApp._run_model_task(root, 1, "Loading", work, completed.append, self.fail)
        self.assertTrue(root._model_task_active)
        self.assertIsNotNone(root.grab_current())
        ModelDeepenerApp._run_model_task(root, 1, "Loading", lambda _progress: "second", completed.append, self.fail)
        def poll():
            if completed:
                root.quit()
            else:
                root.after(20, poll)
        timeout = root.after(5000, root.quit)
        root.after(20, poll)
        root.mainloop()
        root.after_cancel(timeout)
        self.assertEqual(completed, ["first"])
        self.assertFalse(root._model_task_active)
        self.assertIsNone(root.grab_current())
        root._overlay.show.assert_called_once()
        root._overlay.hide.assert_called_once()

    def test_export_selection_is_virtual_and_displays_inline_progress(self):
        """Check export selection is virtual and displays inline progress."""
        root = self.root
        root.colors = {"text": "#000000", "muted": "#666666", "border": "#cccccc", "primary": "#0055aa",
                       "primary_hover": "#004488", "surface": "#ffffff", "app_bg": "#ffffff"}
        root._overlay = SimpleNamespace(cover=lambda _dialog: None, show=Mock(), hide=Mock())
        root.loaded_models = [SimpleNamespace(name=f"Model {i}") for i in range(3000)]
        root._run_model_task = MethodType(ModelDeepenerApp._run_model_task, root)
        root._show_information = Mock()
        root._show_error = Mock()
        root.deiconify()
        root.update()
        observed = []
        def descendants(widget):
            for child in widget.winfo_children():
                yield child
                yield from descendants(child)
        def start():
            dialog = next(w for w in root.winfo_children() if isinstance(w, ctk.CTkToplevel) and w.title() == "Export All")
            selector = next(w for w in descendants(dialog) if isinstance(w, VirtualModelSelector))
            dialog.update_idletasks()
            observed.append((len(selector.models), len(selector.canvas.find_all())))
            # The click handler is called directly, because a generated event reaches the canvas only
            # after Windows has shown the dialog, and waiting for that can block the whole test run.
            selector._click(SimpleNamespace(y=17))
            observed.append(len(selector.selected_models()))
            next(w for w in descendants(dialog) if isinstance(w, ctk.CTkButton) and w.cget("text") == "Export").invoke()
            def check():
                progress = next(w for w in descendants(dialog) if isinstance(w, InlineModelProgress))
                observed.append((bool(progress.winfo_viewable()), bool(progress.bar.winfo_viewable()),
                                 dialog.grab_current() is dialog))
            root.after(650, check)
        def export(models, _directory, _skip, _progress):
            time.sleep(1.0)
            return [(model.name, None, None) for model in models]
        with patch("src.gui.app.filedialog.askdirectory", return_value="test"), \
             patch("src.gui.app.check_models", side_effect=lambda models, _progress: (list(models), [])), \
             patch("src.gui.app.export_models", side_effect=export):
            root.after(100, start)
            ModelDeepenerApp._select_models_for_batch(root, False)
        self.assertEqual(observed[0][0], 3000)
        self.assertLess(observed[0][1], 100)
        self.assertEqual(observed[1], 2999)
        self.assertEqual(observed[2], (True, True, True))
        root._show_information.assert_called_once()

    def test_slow_analysis_preparation_keeps_old_page_and_shows_progress(self):
        """Check slow analysis preparation keeps old page and shows progress."""
        root = self.root
        root.colors = {"text": "#000000", "muted": "#666666", "border": "#cccccc", "primary": "#0055aa"}
        root._overlay = SimpleNamespace(show=Mock(), hide=Mock())
        root._tell_selection = {False: "Check Tell OC1"}
        root.current_model = object()
        root._current_model_display_name = lambda: "Model"
        root._run_model_task = MethodType(ModelDeepenerApp._run_model_task, root)
        root._render_single_analysis = Mock(side_effect=lambda *_: root.quit())
        root._build_view_hidden = lambda build, message="": build()
        root._show_error = Mock()
        root.deiconify()
        root.update()
        seen = []
        def prepare(_selection, _models, _progress):
            time.sleep(0.8)
            return []
        with patch("src.gui.app.analyze_tells", side_effect=prepare):
            ModelDeepenerApp._open_placeholder_action(root, 3)
            def inspect():
                progress = root._model_progress_dialog
                seen.append((bool(progress.winfo_ismapped()), progress.bar.cget("mode"), root._render_single_analysis.called))
            root.after(650, inspect)
            timeout = root.after(5000, root.quit)
            root.mainloop()
            root.after_cancel(timeout)
        self.assertEqual(seen, [(True, "determinate", False)])
        root._render_single_analysis.assert_called_once_with(3, "Check Tell OC1", [])

    def test_switch_and_close_save_in_background_before_continuing(self):
        """Check switch and close save in background before continuing."""
        root = self.root
        root.colors = {"text": "#000000", "muted": "#666666", "border": "#cccccc", "primary": "#0055aa"}
        root._overlay = SimpleNamespace(show=Mock(), hide=Mock())
        root._run_model_task = MethodType(ModelDeepenerApp._run_model_task, root)
        root._is_closing = False
        root._autosave_in_progress = False
        root._close_wait_scheduled = False
        root._database = SimpleNamespace(commit=Mock(side_effect=lambda: time.sleep(0.8)))
        root._choose_database = Mock(side_effect=lambda **_kwargs: root.quit())
        root._show_error = Mock()
        root.deiconify()
        root.update()
        observed = []
        def check():
            progress = root._model_progress_dialog
            observed.append((bool(progress.winfo_ismapped()), progress.message.cget("text"),
                             root._choose_database.called, root._finish_close.called))
        root._finish_close = Mock(side_effect=lambda: root.quit())
        ModelDeepenerApp._switch_database(root)
        root.after(650, check)
        timeout = root.after(5000, root.quit)
        root.mainloop()
        root.after_cancel(timeout)
        self.assertEqual(observed, [(True, "Saving database...", False, False)])
        root._choose_database.assert_called_once_with(is_startup=False)
        root._database.commit.assert_called_once()
        root._database.commit.reset_mock()
        observed.clear()
        root._choose_database.reset_mock()
        ModelDeepenerApp._close_application(root)
        root.after(650, check)
        timeout = root.after(5000, root.quit)
        root.mainloop()
        root.after_cancel(timeout)
        self.assertEqual(observed, [(True, "Saving database...", False, False)])
        root._finish_close.assert_called_once()
        root._database.commit.assert_called_once()

    def test_loading_inside_dialog_disables_buttons_without_second_popup(self):
        """Check loading inside dialog disables buttons without second popup."""
        root = self.root
        root.colors = {"text": "#000000", "muted": "#666666", "border": "#cccccc", "primary": "#0055aa"}
        root._overlay = SimpleNamespace(cover=lambda _dialog: None, show=Mock(), hide=Mock())
        dialog = ctk.CTkToplevel(root)
        button = ctk.CTkButton(dialog, text="Start")
        button.pack()
        dialog.grab_set()
        done = []
        ModelDeepenerApp._run_model_task(root, 2, "Loading", lambda progress: (progress(1, 2), time.sleep(0.8)),
                                        done.append, self.fail, dialog=dialog)
        self.assertEqual(button.cget("state"), "disabled")
        seen = []
        def inspect():
            seen.append((any(isinstance(w, InlineModelProgress) for w in dialog.winfo_children()),
                         any(isinstance(w, ModelProgressDialog) and w.winfo_ismapped()
                             for w in root.winfo_children())))
        root.after(650, inspect)
        def poll():
            if done:
                root.quit()
            else:
                root.after(20, poll)
        timeout = root.after(5000, root.quit)
        root.after(20, poll)
        root.mainloop()
        root.after_cancel(timeout)
        self.assertEqual(seen, [(True, False)])
        self.assertEqual(button.cget("state"), "normal")
        root._overlay.show.assert_not_called()
        root.after(100, root.quit)
        root.mainloop()
        _cancel_widget_timers(dialog)
        dialog.destroy()

    def test_atomic_page_keeps_old_frame_during_build(self):
        """Check atomic page keeps old frame during build."""
        root = self.root
        shell = ctk.CTkFrame(root)
        shell.pack(fill="both", expand=True)
        old = ctk.CTkFrame(shell)
        old.grid(row=0, column=0)
        owner = SimpleNamespace(content=old, shell=shell, colors={"app_bg": "#ffffff"})
        observations = []
        @atomic_page
        def build(ui):
            observations.append((old.winfo_exists(), ui.content is not old))
            ctk.CTkLabel(ui.content, text="Ready").pack()
        build(owner)
        self.assertEqual(observations, [(1, True)])
        self.assertFalse(old.winfo_exists())
        self.assertEqual(len(owner.content.winfo_children()), 1)
        shell.destroy()

    def test_single_import_reads_and_commits_on_worker_threads(self):
        """Check single import reads and commits on worker threads."""
        root = self.root
        root.colors = {"text": "#000000", "muted": "#666666", "border": "#cccccc", "primary": "#0055aa"}
        root._overlay = SimpleNamespace(cover=lambda _dialog: None, show=lambda: None, hide=lambda: None)
        main = threading.get_ident()
        worker_ids = []
        model = SimpleNamespace(path_name="Example")
        report = ImportReport()
        importer = Mock(FORMAT_NAME="PLANTUML")
        importer.import_file.side_effect = lambda _path: (worker_ids.append(threading.get_ident()) or model, report)
        database = Mock()
        database.commit.side_effect = lambda: worker_ids.append(threading.get_ident())
        root.current_file_path = "source.txt"
        root.current_batch_paths = []
        root._importer_for_file = lambda _path: importer
        root._database = database
        root._unique_model_name = lambda name: name
        root._current_timestamp_text = lambda: "now"
        root.ACTION_TITLES = {2: "Imported"}
        root.loaded_models = []
        root.file_path_var = Mock()
        root.action_completed = {1: False}
        root.action_unlocked = {2: False}
        root._show_error = self.fail
        done = []
        root._show_model_page = lambda: done.append(True)
        root._run_model_task = MethodType(ModelDeepenerApp._run_model_task, root)
        ModelDeepenerApp._create_model(root)
        def poll():
            if done:
                root.quit()
            else:
                root.after(20, poll)
        timeout = root.after(5000, root.quit)
        root.after(20, poll)
        root.mainloop()
        root.after_cancel(timeout)
        self.assertEqual(done, [True])
        self.assertEqual(len(worker_ids), 2)
        self.assertTrue(all(identity != main for identity in worker_ids))
        self.assertIs(root.current_model, model)

    def test_model_tree_expands_groups_lazily(self):
        """Check model tree expands groups lazily."""
        tree = ttk.Treeview(self.root)
        tree.pack()
        objects = [SimpleNamespace(name=f"Object {i}", level=0) for i in range(120)]
        model = SimpleNamespace(path_name="Example", enums=[], mlm_objects=objects)
        ui = SimpleNamespace(model_tree=tree, tree_item_payload={}, tree_item_view={}, current_file_path="",
                             _display_table_value=lambda text: text, _enum_matches_search=lambda *_: True,
                             _object_matches_search=lambda *_: True, _natural_sort_key=lambda name: name,
                             _import_note_tag=lambda _obj: None, _insert_object_search_hits=lambda *_: None,
                             _clear_tree=lambda widget: widget.delete(*widget.get_children()))
        for name in ("_defer_tree_group", "_populate_lazy_tree_group", "_insert_model_tree_object",
                     "_insert_model_tree_load_more", "_open_model_tree_group"):
            setattr(ui, name, MethodType(getattr(ModelDeepenerApp, name), ui))
        ModelDeepenerApp._populate_model_tree(ui, model)
        root_id = tree.get_children()[0]
        level_id = tree.get_children(root_id)[1]
        self.assertEqual(len(tree.get_children(level_id)), 1)
        self.assertEqual(tree.item(tree.get_children(level_id)[0], "text"), "")
        tree.focus(level_id)
        ui._open_model_tree_group(None)
        children = tree.get_children(level_id)
        self.assertEqual(len(children), 101)
        self.assertIn("Load 100 more", tree.item(children[-1], "text"))
        self.assertEqual(len(ui._lazy_tree_groups), 0)
        tree.destroy()

    def test_large_details_list_draws_only_visible_rows_and_expands(self):
        """Check large details list draws only visible rows and expands."""
        root = self.root
        colors = {"surface": "#ffffff"}
        report = ImportReport()
        report.add_adaptation(ImportAdaptation("Interface", "A", "Adapted"))
        details = BatchProblemDetails(root, [(f"path/Model {i}.xmi", report) for i in range(650)], colors)
        details.pack(fill="both", expand=True)
        root.update()
        self.assertEqual(len(details.rows), 650)
        self.assertEqual(details.rows[0][2], "Model 0")
        self.assertLess(len(details.canvas.find_all()), 100)
        details._click(SimpleNamespace(y=10))
        self.assertIn(0, details.expanded)
        self.assertGreater(len(details.rows), 650)
        self.assertLess(len(details.canvas.find_all()), 100)
        details._click(SimpleNamespace(y=10))
        self.assertNotIn(0, details.expanded)
        details.canvas.yview_moveto(1.0)
        root.update()
        self.assertLess(len(details.canvas.find_all()), 100)
        _cancel_widget_timers(details)
        details.destroy()

    def test_empty_column_hint_uses_original_xml_style(self):
        """Check empty column hint uses original xml style."""
        root = self.root
        root.colors = {"muted": "#64748b"}
        root.column_canvas = object()
        root.column_table = ctk.CTkFrame(root)
        root.column_table.pack()
        root._reset_column_table = lambda _height: None
        ModelDeepenerApp._render_empty_preview(root, "Column selection is only available for CSV files.")
        label = root.column_table.winfo_children()[0]
        self.assertEqual(label.cget("anchor"), "w")
        self.assertEqual(label.cget("text_color"), "#64748b")
        self.assertEqual(label.cget("font").cget("size"), 13)
        self.assertEqual(label.cget("font").cget("weight"), "bold")
        self.assertEqual(label.grid_info()["padx"], 0)
        root.column_table.destroy()

    def test_batch_format_tiles_use_metric_colors_and_zero_is_grey(self):
        """Check batch format tiles use metric colors and zero is grey."""
        root = self.root
        root.colors = {"surface": "#ffffff", "border": "#cccccc", "text": "#000000",
                       "muted": "#666666", "primary": "#0055aa", "primary_soft": "#dfe9fd", "app_bg": "#ffffff"}
        root.shell = ctk.CTkFrame(root)
        root.shell.pack(fill="both", expand=True)
        root.content = ctk.CTkFrame(root.shell)
        root.content.grid(row=0, column=0)
        root.batch_models = [SimpleNamespace(name="Example", source_file="example.xmi"),
                             SimpleNamespace(name="Other", source_file="other.csv")]
        root._show_batch_sidebar = lambda analysis: None
        root._tell_menu_open = {False: False, True: True}
        root._set_top_tab = lambda _tab: None
        root._open_loaded_model = lambda _model: None
        root._optional_int_filter = ModelDeepenerApp._optional_int_filter
        for name in ("_card", "_card_title", "_metric_card_no_icon", "_page_header", "_clear_content", "_build_batch_models_table", "_build_batch_filters", "_refresh_batch_filter"):
            setattr(root, name, MethodType(getattr(ModelDeepenerApp, name), root))
        counts = [("Number of Models", 2), ("Number of FMMLx", 0), ("Number of CSV", 1),
                  ("Number of PlantUML", 0), ("Number of XMI", 1), ("Number of Ecore", 0)]
        ModelDeepenerApp._render_batch_page(root, counts, [("Classes", 1)],
                                            ("Model Name", "Format", "Classes", "Attributes", "Objects"),
                                            [("Example", "XMI", 1, 2, 0), ("Other", "CSV", 1, 0, 4)])
        # Inspect Models closes the batch tell menu, so Conduct Analysis opens it again.
        self.assertFalse(root._tell_menu_open[True])
        root.update_idletasks()
        self.assertEqual(root._batch_table_card.master, root._batch_table_host)
        self.assertEqual(root._batch_table_host.grid_info()["row"], 2)
        self.assertTrue(any(isinstance(widget, ctk.CTkLabel) and widget.cget("text") == "Selected Models"
                            for widget in root._batch_table_host.winfo_children()))
        self.assertTrue(any(widget.grid_info().get("row") == 1 for widget in root._batch_table_host.winfo_children()
                            if widget.winfo_manager() == "grid"))
        def descendants(widget):
            for child in widget.winfo_children():
                yield child
                yield from descendants(child)
        labels = [widget for widget in descendants(root.content) if isinstance(widget, ctk.CTkLabel)]
        def number_color(title):
            label = next(widget for widget in labels if widget.cget("text") == title)
            number = next(widget for widget in label.master.winfo_children()
                          if isinstance(widget, ctk.CTkLabel) and widget is not label)
            return number.cget("text_color")
        avg = next(widget for widget in labels if widget.cget("text") == "Avg. Classes")
        self.assertTrue(any(widget.cget("text") == "1.0" for widget in avg.master.winfo_children()
                            if isinstance(widget, ctk.CTkLabel)))
        self.assertEqual(number_color("Number of XMI"), "#EA580C")
        self.assertEqual(number_color("Number of FMMLx"), "#A8B2C1")
        cards_before = root._batch_format_tiles.grid_slaves() + root._batch_metric_tiles.grid_slaves()
        root.batch_type_filter_var.set("XMI")
        self.assertEqual(cards_before, root._batch_format_tiles.grid_slaves() + root._batch_metric_tiles.grid_slaves())
        root.update_idletasks()
        canvas = next(widget for widget in descendants(root._batch_table_card) if type(widget) is __import__("tkinter").Canvas)
        values = [canvas.itemcget(item, "text") for item in canvas.find_all() if canvas.type(item) == "text"]
        self.assertIn("Example", values)
        self.assertNotIn("Other", values)
        self.assertIn("Attributes", values)
        self.assertNotIn("Objects", values)
        root.batch_min_objects_var.set("1")
        root.update_idletasks()
        self.assertEqual(len(root.batch_models), 2)
        labels = [widget for widget in descendants(root._batch_format_tiles) if isinstance(widget, ctk.CTkLabel)]
        number = next(widget for widget in labels if widget.cget("text") == "Number of Models")
        self.assertTrue(any(widget.cget("text") == "0" for widget in number.master.winfo_children()
                            if isinstance(widget, ctk.CTkLabel)))
        _cancel_widget_timers(root.shell)
        root.shell.destroy()

    def test_large_batch_table_reaches_idle_and_draws_visible_rows(self):
        """Check large batch table reaches idle and draws visible rows."""
        root = self.root
        root.colors = {"surface": "#ffffff", "border": "#cccccc", "text": "#000000", "primary": "#0055aa"}
        root.batch_models = [SimpleNamespace(name=f"Model {i}") for i in range(3000)]
        root._card = MethodType(ModelDeepenerApp._card, root)
        root._card_title = MethodType(ModelDeepenerApp._card_title, root)
        root._open_loaded_model = lambda _model: None
        rows = [(item.name, "XMI", 1, 0, 0, "No") for item in root.batch_models]
        table = ModelDeepenerApp._build_batch_models_table(root, root, ("Model Name", "Format", "Classes", "Attributes", "Associations", "Objects"), rows)
        table.pack(fill="both", expand=True)
        root.update_idletasks()
        canvases = []
        def find(widget):
            for child in widget.winfo_children():
                if isinstance(child, __import__("tkinter").Canvas):
                    canvases.append(child)
                find(child)
        find(table)
        batch_canvas = next(canvas for canvas in canvases if canvas.cget("background") == "#FFFFFF")
        self.assertLess(len(batch_canvas.find_all()), 300)
        root.update()
        batch_canvas.event_generate("<MouseWheel>", delta=-40)
        batch_canvas.event_generate("<MouseWheel>", delta=-40)
        batch_canvas.event_generate("<MouseWheel>", delta=-40)
        root.update()
        self.assertGreater(batch_canvas.yview()[0], 0)
        batch_canvas.yview_moveto(0.8)
        root.update()
        values = [batch_canvas.itemcget(item, "text") for item in batch_canvas.find_all()
                  if batch_canvas.type(item) == "text"]
        self.assertTrue(any(value.startswith("Model 24") for value in values))
        header = batch_canvas.find_withtag("sticky_header")
        self.assertTrue(header)
        self.assertAlmostEqual(batch_canvas.coords(header[0])[1], batch_canvas.canvasy(0), delta=2)
        _cancel_widget_timers(table)
        table.destroy()

    def test_folder_panel_has_fixed_height_and_browse_button_style(self):
        """Check folder panel has fixed height and browse button style."""
        root = self.root
        root.colors = {"border": "#cccccc", "primary_soft": "#dfe9fd", "primary": "#0055aa"}
        root._add_batch_folder = Mock()
        parent = ctk.CTkFrame(root)
        parent.pack(fill="x")
        parent.grid_columnconfigure(0, weight=1)
        ModelDeepenerApp._build_batch_folder_panel(root, parent)
        root.batch_folder_panel.grid()
        for index in range(30):
            ctk.CTkLabel(root.batch_folder_list, text=f"Folder {index}").pack()
        root.update_idletasks()
        self.assertEqual(root.batch_folder_panel.cget("height"), 100)
        self.assertFalse(root.batch_folder_panel.grid_propagate())
        self.assertFalse(any(isinstance(w, ctk.CTkButton) for w in root.batch_folder_panel.winfo_children()))
        _cancel_widget_timers(parent)
        parent.destroy()

    def test_file_input_mode_updates_single_browse_button_and_selected_tab(self):
        """Check file input mode updates single browse button and selected tab."""
        root = self.root
        root.colors = {"primary": "#0055aa", "primary_hover": "#004488", "surface_alt": "#eeeeee",
                       "text": "#000000", "border": "#cccccc"}
        root._file_input_buttons = {name: Mock() for name in ("upload", "example", "batch")}
        root.file_browse_button = Mock()
        root._add_batch_folder = Mock()
        root._browse_file = Mock()
        root._select_example_file = Mock()
        ModelDeepenerApp._set_file_input_mode(root, "batch")
        self.assertEqual(root.file_browse_button.configure.call_args.kwargs["text"], "Add Folder")
        self.assertEqual(root.file_browse_button.configure.call_args.kwargs["command"], root._add_batch_folder)
        self.assertEqual(root._file_input_buttons["batch"].configure.call_args.kwargs["fg_color"], "#0055aa")
        self.assertEqual(root._file_input_buttons["upload"].configure.call_args.kwargs["fg_color"], "#eeeeee")
        ModelDeepenerApp._set_file_input_mode(root, "example")
        self.assertEqual(root.file_browse_button.configure.call_args.kwargs["text"], "Select")
        self.assertEqual(root.file_browse_button.configure.call_args.kwargs["command"], root._select_example_file)
        self.assertEqual(root._file_input_buttons["example"].configure.call_args.kwargs["fg_color"], "#0055aa")
        root.current_file_path = "chosen.xmi"
        root._file_selection_mode = "example"
        ModelDeepenerApp._set_file_input_mode(root, "example")
        self.assertEqual(root.file_browse_button.configure.call_args.kwargs["text"], "Change File")
        ModelDeepenerApp._set_file_input_mode(root, "upload")
        self.assertEqual(root.file_browse_button.configure.call_args.kwargs["text"], "Browse...")
        root._file_selection_mode = "upload"
        ModelDeepenerApp._set_file_input_mode(root, "upload")
        self.assertEqual(root.file_browse_button.configure.call_args.kwargs["text"], "Change File")

    def test_folder_list_deduplicates_and_removes_individual_folders(self):
        """Check folder list deduplicates and removes individual folders."""
        root = self.root
        root.colors = {"primary_soft": "#dfe9fd", "primary": "#0055aa"}
        folder_container = ctk.CTkFrame(root)
        folder_container.pack()
        root.batch_folder_panel = ctk.CTkFrame(folder_container)
        root.batch_folder_list = ctk.CTkScrollableFrame(root.batch_folder_panel, height=100)
        root.batch_folder_list.pack(fill="both", expand=True)
        root.file_entry = Mock()
        root.batch_file_list = Mock()
        root.selected_csv_columns = {}
        root._set_column_selection_enabled = Mock()
        root._render_empty_preview = Mock()
        root._set_validation_badge_visible = Mock()
        root._set_validation_rows = Mock()
        root._set_create_button_enabled = Mock()
        root._select_batch_files = MethodType(ModelDeepenerApp._select_batch_files, root)
        root._show_batch_folders = MethodType(ModelDeepenerApp._show_batch_folders, root)
        root._remove_batch_folder = MethodType(ModelDeepenerApp._remove_batch_folder, root)
        root.current_batch_folders = {"first": ("Folder A", ["a.xmi", "shared.xmi"]),
                                      "second": ("Folder B", ["shared.xmi", "b.ecore"])}
        root._show_batch_folders()
        self.assertEqual(root.current_batch_paths, ["a.xmi", "shared.xmi", "b.ecore"])
        rows = root.batch_folder_list.winfo_children()
        self.assertEqual(len(rows), 2)
        label = next(w for w in rows[0].winfo_children() if isinstance(w, ctk.CTkLabel))
        self.assertEqual(label.cget("text"), "Folder A  (2 files)")
        next(w for w in rows[0].winfo_children() if isinstance(w, ctk.CTkButton)).invoke()
        self.assertEqual(root.current_batch_paths, ["shared.xmi", "b.ecore"])
        self.assertEqual(list(root.current_batch_folders), ["second"])
        _cancel_widget_timers(root.batch_folder_panel)
        folder_container.destroy()

    def test_failed_file_dialog_shows_reason_summary_and_controls(self):
        """Check failed file dialog shows reason summary and controls."""
        root = self.root
        root.colors = {"text": "#000000", "muted": "#666666", "border": "#cccccc",
                       "primary": "#0055aa", "primary_hover": "#004488", "surface": "#ffffff", "app_bg": "#ffffff"}
        root._overlay = SimpleNamespace(cover=lambda _dialog: None)
        observed = []
        def descendants(widget):
            for child in widget.winfo_children():
                yield child
                yield from descendants(child)
        def inspect():
            dialog = next(w for w in root.winfo_children() if isinstance(w, ctk.CTkToplevel)
                          and not isinstance(w, ModelProgressDialog))
            dialog.deiconify()
            dialog.update()
            labels = [w.cget("text") for w in descendants(dialog) if isinstance(w, ctk.CTkLabel)]
            texts = [w.get("1.0", "end") for w in descendants(dialog) if isinstance(w, ctk.CTkTextbox)]
            observed.append("Could Not Be Imported" in labels)
            observed.append(not any("Could not be imported: 1 file" in text for text in texts))
            observed.append(any("bad.csv: bad row" in text for text in texts))
            buttons = [w for w in descendants(dialog) if isinstance(w, ctk.CTkButton)]
            observed.append(all(next(w for w in buttons if w.cget("text") == name).winfo_viewable()
                                for name in ("Show Details", "Export Problem List (CSV)", "Continue Import", "Cancel Import")))
            next(w for w in buttons if w.cget("text") == "Cancel Import").invoke()
        root.update()
        root.after(400, inspect)
        self.assertFalse(ModelDeepenerApp._ask_batch_problems(root, [], [("bad.csv", "bad row")]))
        self.assertEqual(observed, [True, True, True, True])

    def test_show_details_expands_the_real_dialog(self):
        """Check show details expands the real dialog."""
        root = self.root
        root.colors = {"text": "#000000", "muted": "#666666", "border": "#cccccc",
                       "primary": "#0055aa", "primary_hover": "#004488", "surface": "#ffffff",
                       "app_bg": "#ffffff"}
        root._overlay = SimpleNamespace(cover=lambda dialog: dialog.deiconify(), show=lambda: None, hide=lambda: None)
        report = ImportReport()
        report.add_adaptation(ImportAdaptation("Interface", "A", "Adapted"))
        observed = []
        def children(widget):
            for child in widget.winfo_children():
                yield child
                yield from children(child)
        def click():
            dialogs = [w for w in root.winfo_children() if isinstance(w, ctk.CTkToplevel)
                       and not isinstance(w, ModelProgressDialog)]
            if not dialogs:
                root.after(20, click)
                return
            dialog = dialogs[0]
            dialog.deiconify()
            button = next(w for w in children(dialog)
                          if isinstance(w, ctk.CTkButton) and w.cget("text") == "Show Details")
            dialog.update()
            heading = next(w for w in children(dialog) if isinstance(w, ctk.CTkLabel)
                           and w.cget("text") == "Details per Model")
            observed.append(bool(heading.winfo_viewable()))
            initial_height = dialog.winfo_height()
            button.invoke()
            dialog.update()
            observed.append(button.cget("text"))
            observed.append(bool(heading.winfo_viewable()))
            observed.append(dialog.winfo_height() > initial_height)
            details = next(w for w in children(dialog) if isinstance(w, BatchProblemDetails))
            self.assertLessEqual(details.canvas.winfo_height(),
                                 round(5 * details.ROW_HEIGHT * ctk.ScalingTracker.get_widget_scaling(details)))
            self.assertLessEqual(dialog.winfo_height(), dialog.winfo_screenheight())
            for label in ("Hide Details", "Export Problem List (CSV)", "Continue Import", "Cancel Import"):
                control = next(w for w in children(dialog) if isinstance(w, ctk.CTkButton) and w.cget("text") == label)
                self.assertLessEqual(control.winfo_rooty() + control.winfo_height(),
                                     dialog.winfo_rooty() + dialog.winfo_height())
            observed.append(all(next(w for w in children(dialog) if isinstance(w, ctk.CTkButton)
                                     and w.cget("text") == label).winfo_viewable()
                                for label in ("Hide Details", "Export Problem List (CSV)", "Continue Import", "Cancel Import")))
            observed.append(dialog.resizable() == (1, 1))
            button.invoke()
            dialog.update()
            observed.append(not bool(heading.winfo_viewable()))
            observed.append(button.cget("text"))
            next(w for w in children(dialog) if isinstance(w, ctk.CTkButton)
                 and w.cget("text") == "Cancel Import").invoke()
        try:
            root.update()
            root.after(400, click)
            ModelDeepenerApp._ask_batch_problems(root, [("example", report)])
            self.assertEqual(observed, [False, "Hide Details", True, True, True, True, True, "Show Details"])
        finally:
            pass


if __name__ == '__main__':
    unittest.main()


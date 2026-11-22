"""Tests for the constraint check of Export All and the check boxes of the model selection."""
import tempfile
import unittest
from types import MethodType, SimpleNamespace
from unittest.mock import Mock, patch

import customtkinter as ctk

from src.gui.app import ModelDeepenerApp, VirtualModelSelector, _cancel_widget_timers
from src.gui.bulk_export import check_models

COLORS = {"text": "#000000", "muted": "#666666", "border": "#cccccc", "primary": "#0055aa",
          "primary_hover": "#004488", "surface": "#ffffff", "app_bg": "#ffffff"}


def stored(name, violations=(), error=None):
    model = Mock(path_name="Root::" + name)
    if error is not None:
        model.validate_basemlm_integrity.side_effect = error
    else:
        model.validate_basemlm_integrity.return_value = list(violations)
    return SimpleNamespace(name=name, model=model)


class CheckModelsTests(unittest.TestCase):
    """Test check models."""
    def test_checks_all_models_without_exporting(self):
        """Check checks all models without exporting."""
        models = [stored("Good"), stored("Bad", ["C12 violated"]), stored("Broken", error=ValueError("check failed"))]
        progress = Mock()
        passed, failures = check_models(models, progress)
        self.assertEqual([loaded.name for loaded in passed], ["Good"])
        self.assertEqual([name for name, _reason in failures], ["Bad", "Broken"])
        self.assertIn("C12 violated", failures[0][1])
        self.assertIn("check failed", failures[1][1])
        self.assertEqual(progress.call_args_list[-1].args, (3, 3))
        for loaded in models:
            loaded.model.export_xml.assert_not_called()


class ExportAllDialogTests(unittest.TestCase):
    """Test export all dialog."""
    @classmethod
    def setUpClass(cls):
        cls.root = ctk.CTk()
        cls.root.colors = COLORS

    @classmethod
    def tearDownClass(cls):
        for after_id in cls.root.tk.call("after", "info"):
            cls.root.tk.call("after", "cancel", after_id)
        cls.root.destroy()

    def _descendants(self, widget):
        for child in widget.winfo_children():
            yield child
            yield from self._descendants(child)

    def _dialog(self):
        return next(w for w in self.root.winfo_children()
                    if isinstance(w, ctk.CTkToplevel) and w.title() == "Export All" and w.winfo_exists())

    def _button(self, dialog, text):
        return next(w for w in self._descendants(dialog) if isinstance(w, ctk.CTkButton) and w.cget("text") == text)

    def _run(self, models, actions, ask_result=None):
        """Open Export All, run actions on the dialog and return the mocks of the following steps."""
        root = self.root
        root._overlay = SimpleNamespace(cover=lambda _dialog: None, show=Mock(), hide=Mock())
        root.loaded_models = models
        root._run_model_task = lambda _total, _message, work, success, _failure, dialog=None: success(work(lambda *_: None))
        root._show_information = Mock()
        root._show_error = Mock()
        root._ask_export_check_result = Mock(return_value=ask_result)
        exports = []

        def export(selected, directory, skip_check, _progress):
            exports.append(([loaded.name for loaded in selected], skip_check))
            return [(loaded.name, directory, None) for loaded in selected]

        def start():
            actions(self._dialog())
        with tempfile.TemporaryDirectory() as folder, \
                patch("src.gui.app.filedialog.askdirectory", return_value=folder) as ask_folder, \
                patch("src.gui.app.export_models", side_effect=export):
            root.after(300, start)
            ModelDeepenerApp._select_models_for_batch(root, False)
        return exports, ask_folder

    def test_run_constraint_check_is_checked_by_default(self):
        """Check run constraint check is checked by default."""
        seen = []

        def actions(dialog):
            box = next(w for w in self._descendants(dialog) if isinstance(w, ctk.CTkCheckBox))
            seen.append((box.cget("text"), box.get()))
            dialog.destroy()
        self._run([stored("A")], actions)
        self.assertEqual(seen, [("Run Constraint Check", True)])

    def test_all_passed_chooses_folder_and_exports_after_the_check(self):
        """Check all passed chooses folder and exports after the check."""
        models = [stored("A"), stored("B")]
        exports, ask_folder = self._run(models, lambda dialog: self._button(dialog, "Export").invoke())
        self.assertEqual(exports, [(["A", "B"], True)])
        ask_folder.assert_called_once()
        self.root._ask_export_check_result.assert_not_called()
        for loaded in models:
            loaded.model.validate_basemlm_integrity.assert_called_once()

    def test_failures_show_result_and_export_only_valid_models(self):
        """Check failures show result and export only valid models."""
        models = [stored("A"), stored("Bad", ["C3"]), stored("C")]
        exports, ask_folder = self._run(models, lambda dialog: self._button(dialog, "Export").invoke(), ask_result=True)
        passed, failures = self.root._ask_export_check_result.call_args.args
        self.assertEqual(passed, 2)
        self.assertEqual([name for name, _reason in failures], ["Bad"])
        self.assertIn("C3", failures[0][1])
        self.assertEqual(exports, [(["A", "C"], True)])
        self.assertIn("Not exported (constraint check): 1", self.root._show_information.call_args.args[1])

    def test_cancelled_result_exports_nothing_and_asks_no_folder(self):
        """Check cancelled result exports nothing and asks no folder."""
        def actions(dialog):
            self._button(dialog, "Export").invoke()
            self.assertTrue(dialog.winfo_exists())
            dialog.destroy()
        exports, ask_folder = self._run([stored("A"), stored("Bad", ["C3"])], actions, ask_result=False)
        self.root._ask_export_check_result.assert_called_once()
        self.assertEqual(exports, [])
        ask_folder.assert_not_called()

    def test_unchecked_box_exports_without_check(self):
        """Check unchecked box exports without check."""
        models = [stored("A"), stored("Bad", ["C3"])]

        def actions(dialog):
            next(w for w in self._descendants(dialog) if isinstance(w, ctk.CTkCheckBox)).deselect()
            self._button(dialog, "Export").invoke()
        exports, _ask_folder = self._run(models, actions)
        self.assertEqual(exports, [(["A", "Bad"], True)])
        for loaded in models:
            loaded.model.validate_basemlm_integrity.assert_not_called()

    def test_result_popup_lists_failures_and_offers_valid_export(self):
        """Check result popup lists failures and offers valid export."""
        root = self.root
        seen = []

        def inspect():
            dialog = next(w for w in root.winfo_children()
                          if isinstance(w, ctk.CTkToplevel) and w.title() == "Constraint Check" and w.winfo_exists())
            texts = [w.cget("text") for w in self._descendants(dialog) if isinstance(w, ctk.CTkLabel)]
            box = next(w for w in self._descendants(dialog) if isinstance(w, ctk.CTkTextbox))
            seen.append(("Passed: 1\nFailed: 2" in texts, box.get("1.0", "end").strip()))
            seen.append([w.cget("text") for w in self._descendants(dialog) if isinstance(w, ctk.CTkButton)])
            self._button(dialog, "Export Valid Models").invoke()
        root.after(300, inspect)
        accepted = ModelDeepenerApp._ask_export_check_result(root, 1, [("Bad", "Constraint violations: C3"),
                                                                       ("Worse", "Constraint violations: C7")])
        self.assertTrue(accepted)
        self.assertEqual(seen[0], (True, "Bad: Constraint violations: C3\nWorse: Constraint violations: C7"))
        self.assertEqual(seen[1], ["Export Valid Models", "Cancel"])

    def test_result_popup_without_valid_models_cannot_export(self):
        """Check result popup without valid models cannot export."""
        root = self.root
        states = []

        def inspect():
            dialog = next(w for w in root.winfo_children()
                          if isinstance(w, ctk.CTkToplevel) and w.title() == "Constraint Check" and w.winfo_exists())
            states.append(self._button(dialog, "Export Valid Models").cget("state"))
            self._button(dialog, "Cancel").invoke()
        root.after(300, inspect)
        self.assertFalse(ModelDeepenerApp._ask_export_check_result(root, 0, [("Bad", "C3")]))
        self.assertEqual(states, ["disabled"])


class SelectorCheckboxTests(unittest.TestCase):
    """Test selector checkbox."""
    def test_checked_rows_draw_blue_box_with_check_mark_and_unchecked_rows_stay_empty(self):
        """Check checked rows draw blue box with check mark and unchecked rows stay empty."""
        root = ctk.CTk()
        try:
            selector = VirtualModelSelector(root, [SimpleNamespace(name=f"Model {i}") for i in range(2000)], COLORS)
            selector.pack()
            root.update()
            canvas = selector.canvas
            self.assertNotIn("?", [canvas.itemcget(item, "text") for item in canvas.find_all()
                                   if canvas.type(item) == "text"])
            boxes = canvas.find_withtag("checkbox")
            marks = canvas.find_withtag("checkmark")
            self.assertTrue(0 < len(boxes) < 30)
            self.assertEqual(len(marks), len(boxes))
            self.assertEqual(canvas.itemcget(boxes[0], "fill"), COLORS["primary"])
            self.assertEqual(canvas.itemcget(marks[0], "fill"), "#FFFFFF")
            canvas.event_generate("<Button-1>", x=20, y=17)
            boxes = canvas.find_withtag("checkbox")
            self.assertEqual(canvas.itemcget(boxes[0], "fill"), COLORS["surface"])
            self.assertEqual(canvas.itemcget(boxes[0], "outline"), COLORS["border"])
            self.assertEqual(len(canvas.find_withtag("checkmark")), len(boxes) - 1)
            self.assertEqual(len(selector.selected_models()), 1999)
        finally:
            _cancel_widget_timers(root)
            root.destroy()


if __name__ == "__main__":
    unittest.main()

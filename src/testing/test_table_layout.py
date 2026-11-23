"""Tests for table scrollbars, the tell table layout, the tell menu and the import marker legend."""
import unittest
from types import MethodType, SimpleNamespace
from unittest.mock import Mock

import customtkinter as ctk
import tkinter as tk

from src.gui.app import ModelDeepenerApp, _cancel_widget_timers
from src.gui.tell_results import TellResultRow

COLORS = {"surface": "#ffffff", "surface_alt": "#f8fafc", "text": "#0f172a", "muted": "#64748b",
          "border": "#e2e8f0", "primary": "#04173D", "primary_hover": "#013897", "primary_soft": "#DFE9FD",
          "app_bg": "#f5f7fb"}


class TableLayoutTests(unittest.TestCase):
    """Test table layout."""
    @classmethod
    def setUpClass(cls):
        cls.root = ctk.CTk()
        cls.root.geometry("1200x700")
        cls.root.colors = COLORS
        for name in ("_card", "_autohide_scroll", "_move_column_boundary", "_balanced_tell_widths",
                     "_prompt_deepening"):
            setattr(cls.root, name, MethodType(getattr(ModelDeepenerApp, name), cls.root)
                    if not isinstance(ModelDeepenerApp.__dict__[name], (staticmethod, classmethod))
                    else getattr(ModelDeepenerApp, name))
        for name in ("TELL_HEADER_HEIGHT", "TELL_ROW_HEIGHT", "TELL_TRANSFORM_WIDTH"):
            setattr(cls.root, name, getattr(ModelDeepenerApp, name))
        cls.root._tell_selection = {False: "Check All Tells", True: "Check All Tells"}

    @classmethod
    def tearDownClass(cls):
        for after_id in cls.root.tk.call("after", "info"):
            cls.root.tk.call("after", "cancel", after_id)
        cls.root.destroy()

    def _tell_table(self, rows, batch=True):
        frame = ctk.CTkFrame(self.root)
        frame.pack(fill="both", expand=True)
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(0, weight=1)
        panel = ModelDeepenerApp._build_tell_results(self.root, frame, batch, row_provider=lambda _selection: rows)
        panel.grid(row=0, column=0, sticky="nsew")
        self.root.update()
        return frame, panel

    def _descendants(self, widget):
        for child in widget.winfo_children():
            yield child
            yield from self._descendants(child)

    def _detail_heights(self):
        """Heights of a header and a row of the Attributes table in Inspect Model, drawn for real."""
        root = self.root
        wrapper = tk.Frame(root)
        wrapper.pack(fill="both", expand=True)
        root.detail_table_wrapper = wrapper
        root.detail_canvas = tk.Canvas(wrapper, width=900, height=300)
        root.detail_canvas.pack(fill="both", expand=True)
        root.detail_table = tk.Frame(root.detail_canvas)
        root.detail_canvas_window = root.detail_canvas.create_window(0, 0, anchor="nw", window=root.detail_table)
        root._reset_detail_canvas_table = lambda: None
        root._standard_detail_column_widths = ModelDeepenerApp._standard_detail_column_widths
        root._fit_column_widths = ModelDeepenerApp._fit_column_widths
        root._display_table_value = ModelDeepenerApp._display_table_value
        root._update_detail_x_scrollbar_visibility = lambda: None
        root._start_detail_column_resize = root._resize_detail_column = root._finish_detail_column_resize = Mock()
        root._show_import_note_tooltip = root._hide_adapted_tooltip = Mock()
        ModelDeepenerApp._render_detail_table(root, ("Attribute", "Type", "Level"), [("name", "String", "1")])
        root.update()
        header = root.detail_table.grid_slaves(row=0, column=0)[0].winfo_height()
        row = root.detail_table.grid_slaves(row=1, column=0)[0].winfo_height()
        _cancel_widget_timers(wrapper)
        wrapper.destroy()
        return header, row

    def test_transformation_button_sits_below_table_card_for_both_views(self):
        """Check transformation button sits below table card for both views."""
        for batch in (False, True):
            with self.subTest(batch=batch):
                frame, panel = self._tell_table([TellResultRow("A", "B", "M")], batch=batch)
                button = next(child for child in panel.winfo_children() if isinstance(child, ctk.CTkButton)
                              and child.cget("text") == "Perform Deepening Transformation")
                card = panel.grid_slaves(row=0, column=0)[0]
                self.assertIs(button.master, panel)
                self.assertIs(card.master, panel)
                self.assertEqual(button.grid_info()["row"], 1)
                self.assertEqual(button.grid_info()["sticky"], "e")
                self.assertGreater(button.winfo_y(), card.winfo_y() + card.winfo_height())
                _cancel_widget_timers(frame)
                frame.destroy()

    def test_tell_result_tooltip_and_single_selection(self):
        """Show tell names on hover and keep Yes and No mutually exclusive."""
        row = TellResultRow("Class", "TO1, OC1", "Model", "TO1: Name of Associated Class\nOC1: Class Name")
        frame, panel = self._tell_table([row], batch=False)
        indicator = next(label for label, _column in panel._tell_text_labels if label.cget("text") == "TO1, OC1")
        self.assertTrue(indicator._label.bind("<Enter>"))
        checkboxes = [widget for widget in self._descendants(panel) if isinstance(widget, ctk.CTkCheckBox)]
        yes, no = checkboxes
        self.assertEqual(panel._transform_choices[0].get(), "No")
        self.assertEqual((yes._check_state, no._check_state), (False, True))
        yes.toggle()
        self.assertEqual((yes._check_state, no._check_state), (True, False))
        no.toggle()
        self.assertEqual(panel._transform_choices[0].get(), "No")
        _cancel_widget_timers(frame)
        frame.destroy()

    def test_empty_tell_table_explains_no_results(self):
        """Show a message when the selected check finds no affected parts."""
        frame, panel = self._tell_table([], batch=True)
        labels = [widget.cget("text") for widget in self._descendants(panel) if isinstance(widget, ctk.CTkLabel)]
        self.assertIn("No affected parts found.", labels)
        _cancel_widget_timers(frame)
        frame.destroy()

    def test_tell_rows_are_as_high_as_attribute_table_rows(self):
        """Check tell rows are as high as attribute table rows."""
        rows = [TellResultRow("Class A", "Tell 3 indicator", "Model 1"),
                TellResultRow("Class B", "Tell 4 indicator", "Model 2")]
        frame, panel = self._tell_table(rows)
        table = panel._tell_text_labels[0][0].master.master
        tell_header = table.grid_slaves(row=0, column=0)[0].winfo_height()
        tell_row = table.grid_slaves(row=1, column=3)[0].winfo_height()
        tell_text_row = table.grid_slaves(row=1, column=0)[0].winfo_height()
        _cancel_widget_timers(frame)
        frame.destroy()
        self.assertEqual((tell_header, tell_row), self._detail_heights())
        self.assertEqual(tell_text_row, tell_row)

    def test_tell_header_dividers_match_row_dividers(self):
        """Check tell header dividers match row dividers."""
        frame, panel = self._tell_table([TellResultRow("A", "B", "Model")])
        table = panel._tell_text_labels[0][0].master.master
        for column in range(1, 4):
            header = table.grid_slaves(row=0, column=column)[0]
            row = table.grid_slaves(row=1, column=column)[0]
            for cell in (header, row):
                self.assertEqual(cell.cget("highlightthickness"), 1)
                self.assertEqual(cell.cget("highlightbackground"), "#AFC1D9")
                self.assertTrue(any(isinstance(child, tk.Frame) and child.cget("background") == "#AFC1D9"
                                    and child.place_info().get("x") == "0" for child in cell.winfo_children()))
        _cancel_widget_timers(frame)
        frame.destroy()

    def test_tell_columns_are_balanced_and_transform_is_narrow(self):
        """Check tell columns are balanced and transform is narrow."""
        widths = ModelDeepenerApp._balanced_tell_widths(4, 1200)
        self.assertEqual(sum(widths), 1200)
        self.assertEqual(widths[3], ModelDeepenerApp.TELL_TRANSFORM_WIDTH)
        self.assertEqual(widths[2], ModelDeepenerApp.TELL_INDICATOR_WIDTH)
        self.assertLessEqual(max(widths[:2]) - min(widths[:2]), 2)
        self.assertGreater(min(widths[:2]), widths[2])
        self.assertGreater(widths[2], widths[3])
        frame, panel = self._tell_table([TellResultRow("A", "B", "M")])
        canvas = next(w for w in self._descendants(panel) if type(w) is tk.Canvas)
        self.assertEqual(sum(panel._tell_widths), canvas.winfo_width())
        scaling = ctk.ScalingTracker.get_widget_scaling(self.root)
        self.assertEqual(panel._tell_widths[-1], round(ModelDeepenerApp.TELL_TRANSFORM_WIDTH * scaling))
        # The Yes and No check boxes fit into the narrow column.
        choices = next(w for w in self._descendants(panel) if isinstance(w, ctk.CTkCheckBox)).master
        self.assertLessEqual(choices.winfo_reqwidth(), panel._tell_widths[-1])
        self.assertEqual(ModelDeepenerApp._balanced_tell_widths(3, 1000, 1.5)[-1], 240)
        _cancel_widget_timers(frame)
        frame.destroy()

    def test_scrollbars_appear_only_when_content_does_not_fit(self):
        """Check scrollbars appear only when content does not fit."""
        frame, panel = self._tell_table([TellResultRow("A", "B", "M")])
        bars = [w for w in self._descendants(panel) if isinstance(w, ctk.CTkScrollbar)]
        self.assertEqual(len(bars), 2)
        self.assertTrue(all(not bar.winfo_ismapped() for bar in bars))
        _cancel_widget_timers(frame)
        frame.destroy()
        many = [TellResultRow(f"Class {i}", "indicator", f"Model {i}") for i in range(40)]
        frame, panel = self._tell_table(many)
        vertical, horizontal = [w for w in self._descendants(panel) if isinstance(w, ctk.CTkScrollbar)]
        self.assertTrue(vertical.winfo_ismapped())
        self.assertFalse(horizontal.winfo_ismapped())
        _cancel_widget_timers(frame)
        frame.destroy()

    def test_autohide_scroll_shows_and_hides_a_gridded_scrollbar(self):
        """Check autohide scroll shows and hides a gridded scrollbar."""
        frame = ctk.CTkFrame(self.root)
        frame.pack()
        bar = ctk.CTkScrollbar(frame)
        bar.grid(row=0, column=1, sticky="ns")
        update = ModelDeepenerApp._autohide_scroll(bar)
        update("0.0", "1.0")
        self.assertEqual(bar.winfo_manager(), "")
        update("0.0", "0.4")
        self.assertEqual(bar.winfo_manager(), "grid")
        self.assertEqual(bar.grid_info()["column"], 1)
        update("0.0", "1.0")
        self.assertEqual(bar.winfo_manager(), "")
        _cancel_widget_timers(frame)
        frame.destroy()

    def test_batch_selected_models_hide_scrollbars_when_all_rows_fit(self):
        """Check batch selected models hide scrollbars when all rows fit."""
        root = self.root
        root._open_loaded_model = Mock()
        frame = ctk.CTkFrame(root)
        frame.pack(fill="both", expand=True)
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(0, weight=1)
        models = [SimpleNamespace(name="A"), SimpleNamespace(name="B")]
        card = ModelDeepenerApp._build_batch_models_table(root, frame, ("Model Name", "Format"),
                                                          [("A", "XMI"), ("B", "CSV")], models)
        card.grid(row=0, column=0, sticky="nsew")
        root.update()
        bars = [w for w in self._descendants(card) if isinstance(w, ctk.CTkScrollbar)]
        self.assertEqual(len(bars), 2)
        self.assertTrue(all(not bar.winfo_ismapped() for bar in bars))
        _cancel_widget_timers(frame)
        frame.destroy()

    def test_tell_menu_entries_have_button_height_without_scrollbar(self):
        """Check tell menu entries have button height without scrollbar."""
        root = self.root
        root._select_tell = Mock()
        menu = ModelDeepenerApp._make_tell_menu(root, root, batch=False)
        buttons = menu.winfo_children()
        self.assertNotIsInstance(menu, ctk.CTkScrollableFrame)
        self.assertEqual(len(buttons), 10)
        self.assertTrue(all(button.cget("height") == 40 for button in buttons))
        root._tell_selection[False] = "Check Tell OC1"
        ModelDeepenerApp._refresh_tell_menu(root, False, menu)
        self.assertEqual(menu._tell_buttons["Check Tell OC1"].cget("fg_color"), COLORS["primary_soft"])
        self.assertEqual(menu._tell_buttons["Check Tell TO3"].cget("fg_color"), COLORS["surface"])
        gap = int(6 * ctk.ScalingTracker.get_widget_scaling(menu))
        self.assertEqual([button.pack_info()["pady"] for button in buttons], [(0, gap)] * 9 + [0])
        holder = ctk.CTkFrame(root, width=300, height=330)
        holder.pack()
        holder.pack_propagate(False)
        menu.pack(in_=holder, fill="both", expand=True)
        root.update()
        self.assertTrue(all(button.cget("height") < 40 for button in buttons))
        self.assertLessEqual(buttons[-1].winfo_y() + buttons[-1].winfo_height(), menu.winfo_height())
        _cancel_widget_timers(holder)
        holder.destroy()
        _cancel_widget_timers(menu)
        menu.destroy()


class LegendTests(unittest.TestCase):
    """Test legend."""
    def test_info_card_explains_both_marker_colors(self):
        """Check info card explains both marker colors."""
        root = ctk.CTk()
        try:
            root.colors = COLORS
            root.ADAPTATION_LEGEND = ModelDeepenerApp.ADAPTATION_LEGEND
            root._hide_adapted_tooltip = MethodType(ModelDeepenerApp._hide_adapted_tooltip, root)
            ModelDeepenerApp._show_adaptation_legend(root, SimpleNamespace(x_root=10, y_root=10))
            card = root._adapted_tooltip
            labels = []
            swatches = []
            stack = [card]
            while stack:
                widget = stack.pop()
                stack.extend(widget.winfo_children())
                if isinstance(widget, tk.Label):
                    labels.append(widget.cget("text"))
                elif isinstance(widget, tk.Frame) and widget.cget("width") == 14:
                    swatches.append(widget.cget("background"))
            text = "\n".join(labels)
            self.assertIn("Orange: Changed during import in a way that may affect the meaning "
                          "(e.g. unknown type replaced by String).", text)
            self.assertIn("Grey-blue: Adjusted automatically (e.g. renamed elements, generated role names).", text)
            self.assertIn("Hover over a marked cell for details.", text)
            self.assertEqual(sorted(swatches), sorted(["#B45309", "#647A94"]))
            ModelDeepenerApp._hide_adapted_tooltip(root)
            self.assertIsNone(root._adapted_tooltip)
        finally:
            _cancel_widget_timers(root)
            root.destroy()


if __name__ == "__main__":
    unittest.main()


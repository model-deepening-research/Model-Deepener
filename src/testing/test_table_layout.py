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
                     "_transform_tell_results", "_export_tell_results"):
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
                buttons = [child for child in self._descendants(panel) if isinstance(child, ctk.CTkButton)]
                self.assertEqual({button.cget("text") for button in buttons}, {"Transform", "Export CSV"})
                card = panel.grid_slaves(row=0, column=0)[0]
                actions = panel.grid_slaves(row=1, column=0)[0]
                self.assertIs(card.master, panel)
                self.assertTrue(all(button.master is actions for button in buttons))
                self.assertGreater(actions.winfo_y(), card.winfo_y() + card.winfo_height())
                _cancel_widget_timers(frame)
                frame.destroy()

    def test_tell_result_tooltip_and_single_selection(self):
        """Show tell names on hover and keep Yes and No mutually exclusive."""
        row = TellResultRow("Class", "TO1, OC1", "Model", "TO1: Name of Associated Class\nOC1: Class Name")
        frame, panel = self._tell_table([row], batch=False)
        indicator = next(label for label, _column in panel._tell_text_labels if label.cget("text") == "TO1, OC1")
        self.assertTrue(indicator.bind("<Enter>"))
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

    def test_no_hit_model_has_no_transform_checkbox(self):
        rows = [TellResultRow("No affected parts found.", "", "Empty", model_format="XMI", is_placeholder=True),
                TellResultRow("Class", "OC1", "Other", model_format="XMI")]
        frame, panel = self._tell_table(rows)
        checkboxes = [widget for widget in self._descendants(panel)
                      if isinstance(widget, ctk.CTkCheckBox) and widget.winfo_ismapped()]
        self.assertEqual(len(checkboxes), 2)
        self.assertEqual(panel._tell_rows[0][1].get(), "No")
        _cancel_widget_timers(frame)
        frame.destroy()

    def test_failed_checks_show_a_warning_above_the_table(self):
        from src.gui.tell_results import TellRows
        rows = TellRows()
        rows.failures.extend([("Model", "TO1", "error"), ("Model", "OC1", "error")])
        frame, panel = self._tell_table(rows)
        labels = [widget.cget("text") for widget in self._descendants(panel) if isinstance(widget, ctk.CTkLabel)]
        self.assertIn("2 checks failed.", labels)
        _cancel_widget_timers(frame)
        frame.destroy()

    def test_tell_rows_are_as_high_as_attribute_table_rows(self):
        """Check tell rows are as high as attribute table rows."""
        rows = [TellResultRow("Class A", "Tell 3 indicator", "Model 1"),
                TellResultRow("Class B", "Tell 4 indicator", "Model 2")]
        frame, panel = self._tell_table(rows)
        table = panel._tell_text_labels[0][0].master.master
        tell_header = table.grid_slaves(row=0, column=0)[0].winfo_height()
        tell_row = table.grid_slaves(row=2, column=3)[0].winfo_height()
        tell_text_row = table.grid_slaves(row=2, column=0)[0].winfo_height()
        _cancel_widget_timers(frame)
        frame.destroy()
        self.assertEqual((tell_header, tell_row), self._detail_heights())
        self.assertEqual(tell_text_row, tell_row)

    def test_tell_header_dividers_match_row_dividers(self):
        """Check tell header dividers match row dividers."""
        frame, panel = self._tell_table([TellResultRow("A", "B", "Model")])
        table = panel._tell_text_labels[0][0].master.master
        for column in range(1, 5):
            header = table.grid_slaves(row=0, column=column)[0]
            row = table.grid_slaves(row=2, column=column)[0]
            for cell in (header, row):
                self.assertEqual(cell.cget("highlightthickness"), 1)
                self.assertEqual(cell.cget("highlightbackground"), "#AFC1D9")
                self.assertTrue(any(isinstance(child, tk.Frame) and child.cget("background") == "#AFC1D9"
                                    and child.place_info().get("x") == "0" for child in cell.winfo_children()))
        _cancel_widget_timers(frame)
        frame.destroy()

    def test_virtual_tell_table_keeps_decisions_when_scrolling(self):
        rows = [TellResultRow(f"Part {index}", "OC1", "Model") for index in range(400)]
        frame, panel = self._tell_table(rows)
        canvas = next(w for w in self._descendants(panel) if type(w) is tk.Canvas)
        self.assertLess(len(panel._tell_text_labels), 100)
        panel._transform_choices[0].set("Yes")
        canvas.yview_moveto(1.0)
        self.root.update()
        self.assertGreater(panel._tell_visible[0], 350)
        self.assertGreater(canvas.yview()[1], 0.99)
        canvas.yview_moveto(0.0)
        self.root.update()
        self.assertEqual(panel._transform_choices[0].get(), "Yes")
        self.assertEqual(len(panel._tell_rows), len(rows))
        _cancel_widget_timers(frame)
        frame.destroy()

    def test_large_tell_table_scrolls_from_cell_and_sticky_header(self):
        rows = [TellResultRow(f"Part {index}", "OC1", "Model") for index in range(3000)]
        frame, panel = self._tell_table(rows)
        canvas = panel._tell_canvas
        label = panel._tell_text_labels[0][0]
        target = getattr(label, "_label", label)
        target.event_generate("<MouseWheel>", delta=-120)
        self.root.update()
        self.assertGreater(canvas.yview()[0], 0)
        canvas.yview_moveto(0.75)
        self.root.update()
        self.assertGreater(panel._tell_visible[0], 2000)
        self.assertTrue(any("Part 22" in label.cget("text") for label, _ in panel._tell_text_labels))
        window = next(item for item in canvas.find_all() if canvas.type(item) == "window"
                      and canvas.itemcget(item, "window") == str(panel._tell_sticky))
        self.assertAlmostEqual(canvas.coords(window)[1], canvas.canvasy(0), delta=2)
        _cancel_widget_timers(frame)
        frame.destroy()

    def test_tell_scroll_position_is_restored_per_tab_and_tell(self):
        root = self.root
        root._batch_tabs = {1: {}, 2: {}}
        root._active_batch_tab = 1
        rows = [TellResultRow(f"Part {i}", "OC1", "Model") for i in range(1000)]
        frame, panel = self._tell_table(rows)
        panel._tell_canvas.yview_moveto(0.7)
        root.update()
        saved = root._batch_tabs[1]["analysis_scroll"]["Check All Tells"][0]
        _cancel_widget_timers(frame)
        frame.destroy()
        root._active_batch_tab = 2
        other_frame, other_panel = self._tell_table(rows)
        self.assertLess(other_panel._tell_canvas.yview()[0], 0.01)
        _cancel_widget_timers(other_frame)
        other_frame.destroy()
        root._active_batch_tab = 1
        frame, panel = self._tell_table(rows)
        self.assertAlmostEqual(panel._tell_canvas.yview()[0], saved, delta=0.01)
        _cancel_widget_timers(frame)
        frame.destroy()
        del root._batch_tabs
        del root._active_batch_tab

    def test_detail_header_remains_visible_and_follows_horizontal_scroll(self):
        root = self.root
        wrapper = tk.Frame(root, width=500, height=250)
        wrapper.pack(fill="both", expand=True)
        root.detail_table_wrapper = wrapper
        root.detail_canvas = tk.Canvas(wrapper, width=500, height=250)
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
        ModelDeepenerApp._render_detail_table(root, ("Name", "Value"), [(str(i), str(i)) for i in range(100)],
                                              column_minsizes=(800, 800))
        root.update()
        header = root._detail_sticky_header
        root.detail_canvas.yview_moveto(0.6)
        root.detail_canvas.xview_moveto(0.3)
        root.update()
        self.assertTrue(header.winfo_ismapped())
        self.assertEqual(header.winfo_rooty(), root.detail_canvas.winfo_rooty())
        self.assertAlmostEqual(header.xview()[0], root.detail_canvas.xview()[0], delta=0.01)
        _cancel_widget_timers(wrapper)
        wrapper.destroy()

    def test_tell_selection_reuses_header_scrollbars_and_rows(self):
        rows = [TellResultRow(f"Part {i}", "OC1", "Model") for i in range(200)]
        frame, panel = self._tell_table(rows)
        canvas = panel._tell_canvas
        header = panel._tell_sticky
        before_slots = [tuple(slot["cells"]) for slot in panel._tell_slots]
        before_scrollbars = [widget for widget in self._descendants(panel) if isinstance(widget, ctk.CTkScrollbar)]
        other = [TellResultRow(f"Other {i}", "OC2", "Model") for i in range(200)]
        panel._set_rows("Check Tell OC2", other)
        self.root.update()
        self.assertIs(panel._tell_canvas, canvas)
        self.assertIs(panel._tell_sticky, header)
        self.assertEqual(before_scrollbars, [widget for widget in self._descendants(panel) if isinstance(widget, ctk.CTkScrollbar)])
        self.assertEqual(before_slots, [tuple(slot["cells"]) for slot in panel._tell_slots])
        self.assertTrue(any(label.cget("text") == "Other 0" for label, _ in panel._tell_text_labels))
        _cancel_widget_timers(frame)
        frame.destroy()

    def test_cached_tell_click_updates_the_existing_panel(self):
        root = self.root
        rows = [TellResultRow(f"Part {i}", "OC1", "Model") for i in range(100)]
        frame, panel = self._tell_table(rows)
        root.active_top_tab = "batch"
        root._active_batch_tab = 17
        root._batch_tabs = {17: {}}
        root.batch_models = []
        root._tell_cache = Mock()
        root._tell_cache.get_prepared.return_value = [TellResultRow("New", "OC2", "Model")]
        root._show_batch_analysis = Mock()
        panel._tell_owner = (True, 17)
        panel._tell_header = Mock()
        panel._tell_header.grid_slaves.return_value = [Mock()]
        root._active_tell_panel = panel
        original = panel._tell_canvas
        ModelDeepenerApp._select_tell(root, "Check Tell OC2", True)
        root.update()
        root._show_batch_analysis.assert_not_called()
        self.assertIs(panel._tell_canvas, original)
        self.assertEqual(panel._tell_rows[0][0].affected_parts, "New")
        _cancel_widget_timers(frame)
        frame.destroy()
        for name in ("_batch_tabs", "_active_batch_tab", "_active_tell_panel", "_tell_cache"):
            delattr(root, name)
        root._tell_selection[True] = "Check All Tells"

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


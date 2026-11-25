# External packages for this project belong to the Python 3.12 environment in .venv312.
# Keeping one shared environment makes the GUI use the same library versions on every start.
# noinspection PyPackageRequirements
import csv
import textwrap
import ctypes
import math
import os
import pickle
import queue
import threading
import random
import re
import sys
import tkinter as tk
import customtkinter as ctk
from dataclasses import dataclass, field
from datetime import datetime
from functools import partial, wraps
from PIL import Image
from tkinter import filedialog, messagebox, ttk
from tkinter import font as tk_font
from typing import Any, Callable, Dict, List, Optional

from src.basemlm.basemlm_association import BaseMlmAssociation
from src.basemlm.basemlm_attribute import BaseMlmAttribute
from src.basemlm.basemlm_enum_type import BaseMlmEnumType
from src.basemlm.basemlm_link import BaseMlmLink
from src.basemlm.basemlm_model import BaseMlmModel
from src.basemlm.basemlm_object import BaseMlmObject
from src.basemlm.basemlm_slot import BaseMlmSlot
from src.gui.bulk_export import check_models, export_models, models_newest_first
from src.gui.batch_reports import (batch_problem_summary, batch_report_rows, write_batch_problem_list,
                                   visible_import_report, visible_import_notes)
from src.gui.deepening import export_tell_table, save_deepened_models
from src.gui.folder_dialog import choose_windows_folders
from src.gui.tell_results import TELL_CHOICES, TellAnalysisCache, TellDecision, analyze_tells, tell_columns, tell_description
from src.gui.view_loading import ViewLoadingIndicator, set_window_redraw
from src.importers import CsvImporter, EcoreImporter, PlantUmlImporter, XmiImporter, XmlImporter, importer_for, supported_extensions
from src.importers.csv_import.csv_reader import CsvReader
from src.importers.import_report import ImportReport
from src.importers.model_importer import ModelImporter, supported_formats_text, supported_importers
from src.object_database.database import Database
from src.object_database.folder import DatabaseFolder, IncompatibleDatabaseError
from src.object_database.persistent import Persistent

# app.py lies in src/gui/, so the project folder is three folders above this file.
PROJECT_FOLDER_PATH = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATABASE_FOLDER_PATH = os.path.join(PROJECT_FOLDER_PATH, "databases")
# GWLP_HWNDPARENT in the Windows application programming interface (API): the index that sets
# the owner window of a window.
OWNER_WINDOW_INDEX = -8
FONT_FAMILY = "Segoe UI"
WHITE = "#FFFFFF"
LIGHT_BUTTON_HOVER = "#EEF2F7"
DANGER_BUTTON_HOVER = "#b91c1c"
DIALOG_PADDING = 18
BUTTON_HEIGHT = 36
BUTTON_WIDTH = 100
# A popup is centered a second time, because the window system can still change its size at first.
RECENTER_DELAY_MILLISECONDS = 200
SAVE_ERRORS = (OSError, pickle.PickleError, RecursionError, TypeError, AttributeError)


def save_error_message(error: Exception) -> str:
    """Return the text shown to the user when saving failed."""
    if isinstance(error, RecursionError):
        return ("The model is too deeply nested to be stored in the database. "
                "The last saved state of the database is unchanged.")
    return str(error)


def center_popup(dialog: ctk.CTkToplevel, parent: Optional[tk.Misc] = None) -> None:
    """Position a popup using its final size, in physical screen pixels.

    At startup use the monitor work area where the main window will open
    maximized. Later dialogs use the visible owner's center. CTk scales sizes
    but leaves screen positions alone.
    """
    dialog.update_idletasks()
    scaling = ctk.ScalingTracker.get_window_scaling(dialog)
    width = max(dialog.winfo_width(), dialog.winfo_reqwidth())
    height = max(dialog.winfo_height(), dialog.winfo_reqheight())
    dialog.geometry(f"{round(width / scaling)}x{round(height / scaling)}")
    dialog.update_idletasks()
    width, height = dialog.winfo_width(), dialog.winfo_height()
    if parent is not None and parent.winfo_viewable():
        x = parent.winfo_rootx() + (parent.winfo_width() - width) // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - height) // 2
    else:
        try:
            _, left, top, area_width, area_height = parent.current_monitor_work_area()
        except (AttributeError, OSError):
            left, top = 0, 0
            area_width, area_height = dialog.winfo_screenwidth(), dialog.winfo_screenheight()
        x = left + (area_width - width) // 2
        y = top + (area_height - height) // 2
    if sys.platform == "win32" and dialog.winfo_ismapped():
        # Tk reports the content size; include the Windows border and title bar.
        from ctypes import wintypes
        rectangle = wintypes.RECT()
        handle = ctypes.windll.user32.GetParent(dialog.winfo_id())
        if ctypes.windll.user32.GetWindowRect(handle, ctypes.byref(rectangle)):
            x -= (rectangle.right - rectangle.left - width) // 2
            y -= (rectangle.bottom - rectangle.top - height) // 2
    dialog.geometry(f"+{x}+{y}")


def _add_dialog_heading(dialog: ctk.CTkToplevel, title: str, colors: Dict[str, str]) -> None:
    """Add the bold first line of a dialog."""
    ctk.CTkLabel(dialog, text=title, anchor="w", text_color=colors["text"],
                 font=ctk.CTkFont(family=FONT_FAMILY, size=16, weight="bold")).pack(
                     fill="x", padx=DIALOG_PADDING, pady=(DIALOG_PADDING, 6))


def _add_dialog_button_row(dialog: ctk.CTkToplevel) -> ctk.CTkFrame:
    """Add the empty row that holds the buttons of a dialog."""
    row = ctk.CTkFrame(dialog, fg_color="transparent")
    row.pack(fill="x", padx=DIALOG_PADDING, pady=(0, DIALOG_PADDING))
    return row


def _show_dialog_and_wait(dialog: ctk.CTkToplevel, parent: tk.Misc) -> None:
    """Center the dialog, block all other windows, and wait until the dialog is closed."""
    center_popup(dialog, parent)
    dialog.after(RECENTER_DELAY_MILLISECONDS, center_popup, dialog, parent)
    dialog.grab_set()
    parent.wait_window(dialog)


def popup_message(parent: tk.Misc, title: str, message: str, confirm: bool = False,
                  accept_text: str = "Yes", cancel_text: str = "No") -> bool:
    """Show a consistently styled message. Destructive actions require an explicit Yes."""
    result = False
    previous_grab = parent.grab_current()
    dialog = ctk.CTkToplevel(parent)
    dialog.title(title)
    dialog.resizable(False, False)
    dialog.transient(parent)
    colors = parent.colors
    dialog.configure(fg_color=colors["app_bg"])
    _add_dialog_heading(dialog, title, colors)
    ctk.CTkLabel(dialog, text=message, wraplength=480, justify="left", anchor="w",
                 text_color=colors["text"],
                 font=ctk.CTkFont(family=FONT_FAMILY, size=13)).pack(
                     fill="x", padx=DIALOG_PADDING, pady=(0, DIALOG_PADDING))
    row = _add_dialog_button_row(dialog)

    def close() -> None:
        """Close the dialog without accepting."""
        dialog.destroy()

    def accept() -> None:
        """Close the dialog and remember that the user accepted."""
        nonlocal result
        result = True
        dialog.destroy()

    def close_with_key(_event: tk.Event) -> None:
        """Close the dialog without accepting, for a key that was pressed."""
        close()

    if confirm:
        _add_accept_button(row, accept_text, colors, accept)
        close_text = cancel_text
    else:
        close_text = "OK"
    ctk.CTkButton(row, text=close_text, width=BUTTON_WIDTH, height=BUTTON_HEIGHT,
                  fg_color=WHITE, hover_color=LIGHT_BUTTON_HOVER, border_width=1,
                  border_color=colors["border"], text_color=colors["text"],
                  command=close).pack(side="right", padx=(0, 8))
    dialog.protocol("WM_DELETE_WINDOW", close)
    dialog.bind("<Escape>", close_with_key)
    dialog.bind("<Return>", close_with_key)
    _show_dialog_and_wait(dialog, parent)
    if previous_grab is not None and previous_grab.winfo_exists():
        previous_grab.grab_set()
    return result


def _add_accept_button(row: ctk.CTkFrame, accept_text: str, colors: Dict[str, str],
                       command: Callable[[], None]) -> None:
    """Add the button that accepts a question. A plain Yes is red, because it confirms a destructive action."""
    if accept_text == "Yes":
        button_color = colors["danger"]
        hover_color = DANGER_BUTTON_HOVER
    else:
        button_color = colors["primary"]
        hover_color = colors["primary_hover"]
    ctk.CTkButton(row, text=accept_text, width=BUTTON_WIDTH, height=BUTTON_HEIGHT, fg_color=button_color,
                  hover_color=hover_color, text_color=WHITE, command=command).pack(side="right")


def ask_database_conversion(parent: tk.Misc, name: str) -> str:
    """Offer conversion, deletion or another selection; closing chooses another database."""
    result = "other"
    dialog = ctk.CTkToplevel(parent)
    dialog.title("Database version")
    dialog.transient(parent)
    dialog.resizable(False, False)
    colors = parent.colors
    dialog.configure(fg_color=colors["app_bg"])
    _add_dialog_heading(dialog, "This database uses an older model format", colors)
    ctk.CTkLabel(dialog,
                 text=f"Database '{name}' cannot be opened directly.\n"
                      "Convert this database to the current format, delete it, "
                      "or select another one.\nConversion updates this database and keeps a backup.",
                 text_color=colors["text"], justify="left", wraplength=480,
                 font=ctk.CTkFont(family=FONT_FAMILY, size=13)).pack(
                     fill="x", padx=DIALOG_PADDING, pady=(0, DIALOG_PADDING))
    row = _add_dialog_button_row(dialog)

    def close(choice: str = "other") -> None:
        """Close the dialog and remember the choice of the user."""
        nonlocal result
        result = choice
        dialog.destroy()

    def close_with_key(_event: tk.Event) -> None:
        """Close the dialog for a key that was pressed, which chooses another database."""
        close()

    ctk.CTkButton(row, text="Convert", fg_color=colors["primary"],
                  hover_color=colors["primary_hover"], text_color=WHITE,
                  command=partial(close, "convert")).pack(side="left", padx=(0, 8))
    ctk.CTkButton(row, text="Delete", width=BUTTON_WIDTH, fg_color=colors["danger"],
                  hover_color=DANGER_BUTTON_HOVER, text_color=WHITE,
                  command=partial(close, "delete")).pack(side="left", padx=(0, 8))
    ctk.CTkButton(row, text="Select another", fg_color=WHITE, hover_color=LIGHT_BUTTON_HOVER,
                  border_width=1, border_color=colors["border"], text_color=colors["text"],
                  command=close).pack(side="left")
    dialog.protocol("WM_DELETE_WINDOW", close)
    dialog.bind("<Escape>", close_with_key)
    _show_dialog_and_wait(dialog, parent)
    parent.grab_set()
    return result


@dataclass
class CsvImportPreview:
    file_path: str
    delimiter: str
    header: List[str]
    data_rows: List[List[str]]
    row_count: int
    column_count: int
    header_detected: bool
    warnings: List[str]
    errors: List[str]


@dataclass
class XmlImportPreview:
    file_path: str
    errors: List[str]
    warnings: List[str] = field(default_factory=list)
    model: Optional[BaseMlmModel] = None
    report: Optional[ImportReport] = None


@dataclass
class LoadedModel(Persistent):
    name: str
    source_file: str
    file_type: str
    model: BaseMlmModel
    source_path: str = ""
    selected_columns: List[str] = field(default_factory=list)
    uploaded: str = ""
    last_worked_on: str = ""
    last_action: str = "Imported"

    def __post_init__(self):
        """Give the model an empty OID.

        The __init__ that the dataclass creates does not call Persistent.__init__, so it is
        called here.
        """
        Persistent.__init__(self)


# noinspection PyAttributeOutsideInit,PyUnresolvedReferences,PyTypeChecker,SpellCheckingInspection
def atomic_page(build):
    """Keep the previous content above a new page until construction finishes."""
    @wraps(build)
    def wrapped(self, *args, **kwargs):
        old = self.content
        layout = old.grid_info()
        new = ctk.CTkFrame(self.shell, fg_color=self.colors["app_bg"], corner_radius=0)
        new.grid_columnconfigure(0, weight=1)
        new.grid_rowconfigure(1, weight=1)
        new.grid(**layout)
        old.lift()
        self.content = new
        try:
            result = build(self, *args, **kwargs)
        except Exception:
            self.content = old
            _cancel_widget_timers(new)
            new.destroy()
            raise
        new.lift()
        _cancel_widget_timers(old)
        old.destroy()
        return result
    return wrapped


class ModelDeepenerApp(ctk.CTk):
    """
    Main window of the Model Deepener desktop application.

    The file is organized in the same order as the user works through the app:
    1. App setup and navigation create the window, top tabs, and workflow sidebar.
    2. New Model / Upload File validates CSV or XML input and shows Column Selection.
    3. Create and Save Model creates the model, stores it, reloads it, and exports it.
    4. Inspect Model shows the model tree, overview table, and detail tables.
    5. Models Overview lists all imported models and opens or deletes them.
    6. Shared helpers create repeated UI elements such as cards, headers, and table cells.
    """

    # The application draws its own title bar; avoid CTk mapping a temporary Windows window during setup.
    _deactivate_windows_window_header_manipulation = True

    ASSOCIATION_TABLE_HEADERS = ("Associationname", "Source", "Target", "Multiplicity")

    COLUMN_WIDTH_INCLUDE = 100
    COLUMN_WIDTH_NAME = 280
    COLUMN_WIDTH_TYPE = 220
    COLUMN_WIDTH_EXAMPLES = 600
    TABLE_HEADER_HEIGHT = 46
    TABLE_ROW_HEIGHT = 50

    VALIDATION_ICON_WIDTH = 34
    VALIDATION_LABEL_WIDTH = 170
    VALIDATION_VALUE_WIDTH = 170
    VALIDATION_ROW_HEIGHT = 42

    ACTION_TITLES = {
        1: "Import Models",
        2: "Inspect Model",
        3: "Conduct Model Deepening Analysis",
    }

    def __init__(self) -> None:
        """
        Builds the application window and initializes its complete GUI state.

        Native minimization is tracked until Windows restores the window, and
        closing is guarded so the shutdown procedure cannot run twice.
        The window stays hidden while its layout, taskbar entry, and icon are
        prepared. It is shown in a maximized state when setup is complete.
        """
        super().__init__()
        # The hidden setup prevents an empty icon from flashing in the taskbar.
        self.withdraw()
        ctk.set_appearance_mode("light")
        ctk.set_default_color_theme("blue")

        self.title("Model Deepener")
        self.geometry("1500x900")
        self.minsize(800, 500)
        # The standard Windows frame is hidden because the tool draws its own
        # top row with its logo and window-control buttons.
        self.overrideredirect(True)
        # Operating-system close requests use the same complete shutdown as
        # the visible X button.
        self.protocol("WM_DELETE_WINDOW", self._close_application)

        self.colors = {
            "app_bg": "#f5f7fb",
            "surface": "#ffffff",
            "surface_alt": "#f8fafc",
            "border": "#e2e8f0",
            "text": "#0f172a",
            "muted": "#64748b",
            "primary": "#04173D",
            "primary_hover": "#013897",
            "primary_soft": "#DFE9FD",
            "success": "#16a34a",
            "success_soft": "#ecfdf3",
            "disabled": "#cbd5e1",
            "disabled_bg": "#f1f5f9",
            "danger": "#dc2626",
            "danger_soft": "#fff1f2",
        }
        self.configure(fg_color=self.colors["app_bg"])

        self.current_model: Optional[BaseMlmModel] = None
        self.current_file_path: Optional[str] = None
        self.current_file_type: str = ""
        self.current_selected_columns: List[str] = []
        self._file_input_mode = "upload"
        self._file_selection_mode = None
        self.csv_preview: Optional[CsvImportPreview] = None
        self.xml_preview: Optional[XmlImportPreview] = None
        self.selected_csv_columns: Dict[str, tk.BooleanVar] = {}
        self.tree_item_payload: Dict[str, object] = {}
        self.tree_item_view: Dict[str, str] = {}
        self.loaded_models: List[LoadedModel] = []
        # Set in _open_database().
        self._database: Database
        self._database_folder = DatabaseFolder(DATABASE_FOLDER_PATH)
        self._database_name = ""
        self._database_name_label: ctk.CTkLabel | None = None
        self.action_unlocked = {1: True, 2: False, 3: False}
        self.action_completed = {1: False, 2: False, 3: False}
        self.current_action = 1
        self.active_top_tab = "new"
        self._tell_menu_open = {False: False, True: False}
        self._tell_selection = {False: TELL_CHOICES[0], True: TELL_CHOICES[0]}
        self._tell_cache = TellAnalysisCache()
        self.model_tab = None
        self._model_tab_state = None
        self._model_tabs = {}
        self._active_model_tab = None
        self._batch_view = "inspect"
        self.batch_models = []
        self.batch_tab = None
        self._batch_tabs = {}
        self._active_batch_tab = None
        self._next_batch_number = 1
        self.logo_image = None
        self.titlebar_logo_image = None
        # These values remember how the user moves and resizes the window.
        self._window_drag_offset = (0, 0)
        self._window_maximized = False
        self._window_restore_binding_id = None
        self._window_is_minimized = False
        # This flag prevents the close procedure from running twice.
        self._is_closing = False
        self._detail_load_token = 0
        self._detail_batch_after_id = None
        self._detail_loading_panel = None
        self.column_selection_expanded = False
        self.all_columns_selected_var = tk.BooleanVar(value=True)

        if not self._choose_database(is_startup=True):
            self._close_application()
            return
        self._configure_ttk_style()
        self._build_layout()
        self._overlay = Overlay(self)
        self._view_loading = ViewLoadingIndicator(self.colors)
        self._show_import_page()
        self.after_idle(self._show_configured_window)
        self.after(1500, self._view_loading.prepare)
        self.after(2000, self._autosave_models)

    def _configure_ttk_style(self):
        """
        Defines the look of standard Tk tables and trees.

        This is part of the app setup. The methods around it build the main
        window, the top navigation, and the workflow sidebar on the left.
        """
        self.style = ttk.Style(self)
        self.style.theme_use("clam")

        # Segoe UI is the native, highly readable Windows interface font.
        self.style.configure(
            "Treeview",
            background="#ffffff",
            fieldbackground="#ffffff",
            foreground="#0f172a",
            rowheight=32,
            relief="flat",
            borderwidth=0,
            font=("Segoe UI", 11),
        )
        self.style.configure(
            "Treeview.Heading",
            background="#f8fafc",
            foreground="#334155",
            relief="flat",
            borderwidth=0,
            font=("Segoe UI", 12, "bold"),
            padding=(10, 8),
        )
        self.style.map(
            "Treeview",
            background=[("selected", "#dbeafe")],
            foreground=[("selected", "#0f172a")],
        )
        self.style.map(
            "Treeview.Heading",
            background=[("active", "#eef2f7")],
        )

        # Removes the heavy classic Tk border around the table body.
        # noinspection PyTypeChecker
        self.style.layout(
            "Treeview",
            [("Treeview.treearea", {"sticky": "nswe"})],
        )

    def _build_custom_title_bar(self):
        """
        Creates the narrow row at the very top of the application window.

        The row contains Logo.png, the text "Model Deepener", and the three
        buttons on the right that minimize, resize, or close the window.
        """
        self.title_bar = ctk.CTkFrame(
            self,
            height=38,
            corner_radius=0,
            fg_color="#ffffff",
        )
        self.title_bar.grid(row=0, column=0, sticky="ew")
        self.title_bar.grid_propagate(False)
        self.title_bar.grid_columnconfigure(2, weight=1)

        logo_path = os.path.join(os.path.dirname(__file__), "Logo.png")
        if os.path.exists(logo_path):
            try:
                source_image = Image.open(logo_path)
                self.titlebar_logo_image = ctk.CTkImage(
                    light_image=source_image,
                    dark_image=source_image,
                    size=(24, 24),
                )
            except (OSError, ValueError):
                self.titlebar_logo_image = None

        logo_label = ctk.CTkLabel(
            self.title_bar,
            text="",
            image=self.titlebar_logo_image,
            width=28,
        )
        logo_label.grid(row=0, column=0, padx=(10, 4), pady=5)

        title_label = ctk.CTkLabel(
            self.title_bar,
            text="Model Deepener",
            text_color="#5f6368",
            font=ctk.CTkFont(size=13),
        )
        title_label.grid(row=0, column=1, sticky="w")

        minimize_button = self._title_bar_button("—", self._minimize_window)
        minimize_button.grid(row=0, column=3, sticky="nsew")
        maximize_button = self._title_bar_button("□", self._toggle_maximize_window)
        maximize_button.grid(row=0, column=4, sticky="nsew")
        close_button = self._title_bar_button("×", self._close_application, hover_color="#e81123")
        close_button.grid(row=0, column=5, sticky="nsew")

        for widget in (self.title_bar, logo_label, title_label):
            widget.bind("<ButtonPress-1>", self._start_window_drag)
            widget.bind("<B1-Motion>", self._drag_window)
            widget.bind("<Double-Button-1>", lambda _event: self._toggle_maximize_window())

    def _title_bar_button(self, text: str, command, hover_color: str = "#e5e7eb"):
        """Creates one of the three matching buttons in the top window row."""
        return ctk.CTkButton(
            self.title_bar,
            text=text,
            command=command,
            width=46,
            height=38,
            corner_radius=0,
            border_width=0,
            fg_color="transparent",
            hover_color=hover_color,
            text_color="#334155",
            font=ctk.CTkFont(size=16),
        )

    def _start_window_drag(self, event):
        """Remembers where the user grabbed the top row to move the window."""
        if self._window_maximized:
            return
        self._window_drag_offset = (event.x_root - self.winfo_x(), event.y_root - self.winfo_y())

    def _drag_window(self, event):
        """Moves the window while the user drags its top row with the mouse."""
        if self._window_maximized:
            return
        offset_x, offset_y = self._window_drag_offset
        self.geometry(f"+{event.x_root - offset_x}+{event.y_root - offset_y}")

    def current_monitor_work_area(self) -> tuple:
        """
        Returns the usable size and position of the window's current monitor.

        The returned area leaves out space occupied by the Windows taskbar.
        It is used to size the window correctly on different screens.
        """
        from ctypes import wintypes

        class MonitorInfo(ctypes.Structure):
            """Stores the full and usable monitor areas reported by Windows."""

            _fields_ = [
                ("cbSize", wintypes.DWORD),
                ("rcMonitor", wintypes.RECT),
                ("rcWork", wintypes.RECT),
                ("dwFlags", wintypes.DWORD),
            ]

        # Windows identifies each open window by a number called a handle.
        # The handle lets the tool ask which monitor contains this window.
        hwnd = int(self.frame(), 0)
        monitor_default_to_nearest = 2
        monitor = ctypes.windll.user32.MonitorFromWindow(hwnd, monitor_default_to_nearest)
        monitor_info = MonitorInfo()
        monitor_info.cbSize = ctypes.sizeof(MonitorInfo)
        if not ctypes.windll.user32.GetMonitorInfoW(monitor, ctypes.byref(monitor_info)):
            raise OSError("Could not determine the monitor work area")

        work_area = monitor_info.rcWork
        return (
            hwnd,
            work_area.left,
            work_area.top,
            work_area.right - work_area.left,
            work_area.bottom - work_area.top,
        )

    def _toggle_maximize_window(self) -> None:
        """
        Switches between the maximized and normal window sizes.

        The maximized size uses the available area of the current monitor, so
        the window fits different screens and leaves the Windows taskbar free.
        """
        if self._window_maximized:
            self._shrink_window()
            return

        try:
            hwnd, left, top, width, height = self.current_monitor_work_area()
            keep_window_order = 0x0004
            show_window = 0x0040
            ctypes.windll.user32.SetWindowPos(
                hwnd,
                None,
                left,
                top,
                width,
                height,
                keep_window_order | show_window,
            )
            self._window_maximized = True
        except (AttributeError, OSError):
            # Tk's normal maximize mode is used if Windows cannot provide the
            # monitor information.
            self.state("zoomed")
            self._window_maximized = True

    def _minimize_window(self):
        """
        Hides the application window and keeps it available in the taskbar.

        Restoring the minimized window turns the tool's own top row back on,
        because Windows temporarily needs its standard frame for minimizing.
        """
        self._window_is_minimized = True
        if self._window_restore_binding_id is None:
            self._window_restore_binding_id = self.bind(
                "<Map>",
                self._restore_custom_window_after_minimize,
                add="+",
            )
        self.overrideredirect(False)
        self.update_idletasks()
        self.after_idle(self.iconify)

    def _restore_custom_window_after_minimize(self, _event=None):
        """Restores the custom frame after Windows leaves the minimized state."""
        def restore_when_visible():
            """Waits for native restoration before replacing the Windows frame."""
            if not self._window_is_minimized or self.state() == "iconic":
                return
            self._window_is_minimized = False
            if self._window_restore_binding_id is not None:
                self.unbind("<Map>", self._window_restore_binding_id)
                self._window_restore_binding_id = None
            self.overrideredirect(True)
            self._configure_custom_window()

        self.after(100, restore_when_visible)

    def _shrink_window(self) -> None:
        """
        Reduces the window to 60 percent and centers it on its current monitor.

        The available area excludes the Windows taskbar, so the smaller window
        remains fully visible on laptops and external monitors.
        """
        self.state("normal")
        try:
            hwnd, left, top, width, height = self.current_monitor_work_area()
            target_width = round(width * 0.60)
            target_height = round(height * 0.60)
            target_left = left + ((width - target_width) // 2)
            target_top = top + ((height - target_height) // 2)
            keep_window_order = 0x0004
            show_window = 0x0040
            ctypes.windll.user32.SetWindowPos(
                hwnd,
                None,
                target_left,
                target_top,
                target_width,
                target_height,
                keep_window_order | show_window,
            )
            self._window_maximized = False
        except (AttributeError, OSError):
            screen_width = self.winfo_screenwidth()
            screen_height = self.winfo_screenheight()
            target_width = round(screen_width * 0.60)
            target_height = round(screen_height * 0.60)
            target_left = (screen_width - target_width) // 2
            target_top = (screen_height - target_height) // 2
            tk.Tk.geometry(
                self,
                f"{target_width}x{target_height}+{target_left}+{target_top}",
            )
            self._window_maximized = False

    def _close_application(self) -> None:
        """
        Closes the complete application when the user selects the X button.

        Scheduled interface tasks are cancelled before the window and its
        event loop are stopped, so the application does not remain active in
        the background. If saving fails, the user decides whether to close without
        saving. The database file then keeps its last saved state.
        """
        if self._is_closing or getattr(self, "_model_task_active", False):
            return
        if getattr(self, "_autosave_in_progress", False):
            if not getattr(self, "_close_wait_scheduled", False):
                self._close_wait_scheduled = True
                def retry_close():
                    self._close_wait_scheduled = False
                    self._close_application()
                self.after(50, retry_close)
            return
        database = getattr(self, "_database", None)
        if database is None:
            self._finish_close()
            return
        def failed(error):
            close_without_saving = popup_message(
                self, "Save failed", f"Saving failed. Close without saving?\n\n{save_error_message(error)}", confirm=True)
            if close_without_saving:
                self._finish_close()
        self._run_model_task(1, "Saving database...", lambda _progress: database.commit(),
                             lambda _result: self._finish_close(), failed)

    def _finish_close(self) -> None:
        """Cancel pending callbacks and destroy the application window."""
        self._is_closing = True
        try:
            for after_id in self.tk.call("after", "info"):
                try:
                    # Cancel on the Tcl level, so the Python callbacks stay registered and
                    # destroy() can remove them together with their widgets.
                    self.tk.call("after", "cancel", after_id)
                except tk.TclError:
                    pass
        except tk.TclError:
            pass
        view_loading = getattr(self, "_view_loading", None)
        if view_loading is not None:
            view_loading.close()
        self.quit()
        self.destroy()

    def is_running(self) -> bool:
        """Return False once the tool is closed.

        This is the case, for example, after the database dialog was cancelled at startup.
        """
        return not self._is_closing

    def _show_information(self, title: str, message: str) -> None:
        """Show an information message over the darkened main window."""
        self._overlay.show()
        try:
            messagebox.showinfo(title, message, parent=self)
        finally:
            self._overlay.hide()

    def _show_warning(self, title: str, message: str) -> None:
        """Show a warning message over the darkened main window."""
        self._overlay.show()
        try:
            messagebox.showwarning(title, message, parent=self)
        finally:
            self._overlay.hide()

    def _show_error(self, title: str, message: str) -> None:
        """Show an error message over the darkened main window."""
        self._overlay.show()
        try:
            messagebox.showerror(title, message, parent=self)
        finally:
            self._overlay.hide()

    def _ask_open_file(self, file_types: list[tuple[str, str]]) -> str:
        """Ask for a file to open over the darkened main window.

        Returns the chosen path, or an empty string if the user cancels.
        """
        self._overlay.show()
        try:
            return filedialog.askopenfilename(parent=self, filetypes=file_types)
        finally:
            self._overlay.hide()

    def _ask_save_file(
            self,
            title: str,
            initial_file: str,
            default_extension: str,
            file_types: list[tuple[str, str]],
    ) -> str:
        """Ask where a file should be saved, over the darkened main window.

        Returns the chosen path, or an empty string if the user cancels.
        """
        self._overlay.show()
        try:
            return filedialog.asksaveasfilename(
                parent=self,
                title=title,
                initialfile=initial_file,
                defaultextension=default_extension,
                filetypes=file_types,
            )
        finally:
            self._overlay.hide()

    def _show_configured_window(self):
        """
        Displays the finished application window in its maximized size.

        The taskbar entry and icon are prepared while the window is hidden.
        They are checked again after it becomes visible because Windows creates
        the final taskbar entry at that point.
        """
        self.update_idletasks()
        self._apply_windows_icons()
        self._configure_custom_window()
        self.deiconify()
        self.update_idletasks()
        if not self._window_maximized:
            self._toggle_maximize_window()
        self._configure_custom_window()
        self._apply_windows_icons()
        self.lift()

    def _configure_custom_window(self):
        """
        Tells Windows to show Model Deepener as a normal taskbar application.

        The tool hides the standard Windows frame because it draws its own top
        row. These Windows settings make sure the open tool still receives its
        own entry in the taskbar.
        """
        try:
            # This is the hidden Windows wrapper around the visible Tk window.
            hwnd = ctypes.windll.user32.GetParent(self.winfo_id())
            # These values remove the "small utility window" marker and add
            # the "normal application" marker used by the Windows taskbar.
            gwl_exstyle = -20
            ws_ex_toolwindow = 0x00000080
            ws_ex_appwindow = 0x00040000
            style = ctypes.windll.user32.GetWindowLongW(hwnd, gwl_exstyle)
            style = (style & ~ws_ex_toolwindow) | ws_ex_appwindow
            ctypes.windll.user32.SetWindowLongW(hwnd, gwl_exstyle, style)
            # Windows refreshes only the window type. Size, position, and the
            # order among other open windows stay unchanged.
            swp_no_size = 0x0001
            swp_no_move = 0x0002
            swp_no_zorder = 0x0004
            swp_frame_changed = 0x0020
            ctypes.windll.user32.SetWindowPos(
                hwnd,
                None,
                0,
                0,
                0,
                0,
                swp_no_size | swp_no_move | swp_no_zorder | swp_frame_changed,
            )
        except (AttributeError, OSError):
            pass

    def _build_layout(self):
        """
        Places the main visible sections inside the application window.

        From top to bottom these are the tool's own top row, the navigation
        header, and the workspace containing the sidebar and page content.
        """
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        self._build_custom_title_bar()

        self.header = ctk.CTkFrame(
            self,
            fg_color=self.colors["surface"],
            corner_radius=0,
            height=82,
        )
        self.header.grid(row=1, column=0, sticky="ew")
        self.header.grid_propagate(False)
        self.header.grid_columnconfigure(5, weight=1)

        self._build_database_area()

        self.new_model_tab = ctk.CTkButton(
            self.header,
            text="+  New Model",
            width=122,
            height=42,
            corner_radius=8,
            fg_color="transparent",
            hover_color=self.colors["surface_alt"],
            text_color=self.colors["text"],
            font=ctk.CTkFont(size=14),
            command=self._show_import_page,
        )
        self.new_model_tab.grid(row=0, column=1, padx=(0, 8), pady=12)

        self.models_tab = ctk.CTkButton(
            self.header,
            text="Models Overview",
            width=158,
            height=42,
            corner_radius=8,
            fg_color="transparent",
            hover_color=self.colors["surface_alt"],
            text_color=self.colors["text"],
            font=ctk.CTkFont(size=14),
            command=self._show_models_overview_page,
        )
        self.models_tab.grid(row=0, column=2, padx=(0, 8), pady=12)
        self._new_models_separator = tk.Frame(self.header, bg=self.colors["border"], width=1, height=30)
        self._models_tabs_separator = tk.Frame(self.header, bg=self.colors["border"], width=1, height=30)
        self.header.bind("<Configure>", self._position_header_separators, add="+")

        # An empty CTkFrame requests 200 x 200 pixels. That would make the header row taller than
        # the header and push all header buttons out of view, so the container has the tab height
        # and is only shown while model tabs exist.
        self.model_tabs_container = ctk.CTkFrame(self.header, fg_color="transparent", width=1, height=42)
        self.model_tabs_container.grid(row=0, column=3, pady=12)
        self.model_tabs_container.grid_remove()
        self.header.bind("<Configure>", lambda _event: self._layout_model_tabs(), add="+")
        self.model_tab = None
        self.model_tab_close = None
        # The overflow button lies right of all tabs and lists the model tabs that do not fit.
        self.model_tabs_more = ctk.CTkButton(
            self.header, text="+", width=42, height=42, corner_radius=8, fg_color="transparent",
            hover_color=self.colors["surface_alt"], text_color=self.colors["text"], border_width=1,
            border_color=self.colors["border"], font=ctk.CTkFont(size=18), command=self._show_more_model_tabs)
        self.model_tabs_more.grid(row=0, column=5, sticky="w", pady=12)
        self.model_tabs_more.grid_remove()

        self.batch_tab = ctk.CTkButton(
            self.header, text="  Batch Process", width=160, height=42, corner_radius=8, anchor="w",
            fg_color="transparent", hover_color=self.colors["surface_alt"],
            text_color=self.colors["text"], font=ctk.CTkFont(size=14),
            command=self._reopen_batch_tab,
        )
        self.batch_tab.grid(row=0, column=4, padx=(0, 8), pady=12)
        self.batch_tab.grid_remove()
        # Showing or hiding the batch tab changes the space that is left for the model tabs.
        for event in ("<Map>", "<Unmap>"):
            self.batch_tab.bind(event, lambda _event: self.after_idle(self._layout_model_tabs), add="+")
        self.batch_tab_close = ctk.CTkButton(self.batch_tab, text="x", width=18, height=18,
            fg_color="transparent", hover_color=self.colors["border"], text_color=self.colors["muted"],
            font=ctk.CTkFont(size=12), command=lambda: self._close_top_tab("batch"))
        self.batch_tab_close.place(relx=1, x=-7, y=5, anchor="ne")

        self.logo_label = ctk.CTkLabel(self.header, text="", width=1)
        self.logo_label.grid(row=0, column=6, sticky="e", padx=(8, 24), pady=8)
        self._load_header_logo()

        self.shell = ctk.CTkFrame(
            self,
            fg_color=self.colors["app_bg"],
            corner_radius=0,
        )
        self.shell.grid(row=2, column=0, sticky="nsew")
        self.shell.grid_columnconfigure(1, weight=1)
        self.shell.grid_rowconfigure(0, weight=1)

        self.sidebar = ctk.CTkFrame(
            self.shell,
            width=310,
            fg_color=self.colors["surface"],
            corner_radius=0,
        )
        self.sidebar.grid(row=0, column=0, sticky="nsw")
        self.sidebar.grid_propagate(False)

        self.workflow_title = ctk.CTkLabel(
            self.sidebar,
            text="New Model Workflow",
            anchor="w",
            text_color=self.colors["text"],
            font=ctk.CTkFont(size=15, weight="bold"),
        )
        self.workflow_title.pack(fill="x", padx=20, pady=(24, 14))

        self.action_cards: Dict[int, ctk.CTkFrame] = {}
        self.action_title_labels: Dict[int, ctk.CTkLabel] = {}

        for action in self.ACTION_TITLES:
            self._build_action_card(action)
        self._single_tell_menu = self._make_tell_menu(self.sidebar, batch=False)
        self._single_tell_menu.pack_forget()

        self.content = ctk.CTkFrame(
            self.shell,
            fg_color=self.colors["app_bg"],
            corner_radius=0,
        )
        self.content.grid(row=0, column=1, sticky="nsew", padx=24, pady=22)
        self.content.grid_columnconfigure(0, weight=1)
        self.content.grid_rowconfigure(1, weight=1)

    def _load_header_logo(self):
        """
        Loads the logo shown in the top-right header.

        The header uses the wide logo with the product name. The taskbar icon is
        loaded separately.
        """
        gui_dir = os.path.dirname(__file__)
        logo_path = os.path.join(gui_dir, "Logo und Name (+ Kontur).png")
        if not os.path.exists(logo_path):
            return
        try:
            source_image = Image.open(logo_path)
            max_height = 62
            ratio = max_height / source_image.height
            image_size = (max(1, int(source_image.width * ratio)), max_height)
            self.logo_image = ctk.CTkImage(
                light_image=source_image,
                dark_image=source_image,
                size=image_size,
            )
            self.logo_label.configure(image=self.logo_image)
        except (OSError, tk.TclError, ValueError):
            self.logo_image = None

    def _apply_windows_icons(self):
        """
        Uses Logo + Kontur.ico as the Windows icon for Model Deepener.

        An ICO is a Windows icon file that contains several display sizes. The
        file is assigned to every icon slot so the taskbar does not show a
        generic Python or empty application symbol.
        """
        gui_dir = os.path.dirname(__file__)
        taskbar_icon_path = os.path.join(gui_dir, "Logo + Kontur.ico")
        if not os.path.exists(taskbar_icon_path):
            return
        try:
            self.update_idletasks()
            try:
                # The outer Windows handle owns the taskbar entry. The visible
                # Tk handle is used only if that outer handle is unavailable.
                hwnd = int(self.frame(), 0)
            except (tk.TclError, TypeError, ValueError):
                hwnd = self.winfo_id()
            # These values tell Windows to load an icon file and assign it to
            # every icon size it may request for the open application.
            image_icon = 1
            lr_load_from_file = 0x00000010
            wm_seticon = 0x0080
            icon_small = 0
            icon_big = 1
            icon_small2 = 2
            user32 = ctypes.windll.user32
            user32.LoadImageW.restype = ctypes.c_void_p
            user32.LoadImageW.argtypes = [
                ctypes.c_void_p,
                ctypes.c_wchar_p,
                ctypes.c_uint,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_uint,
            ]
            user32.SendMessageW.restype = ctypes.c_void_p
            user32.SendMessageW.argtypes = [
                ctypes.c_void_p,
                ctypes.c_uint,
                ctypes.c_void_p,
                ctypes.c_void_p,
            ]
            # Tk receives the icon first; Windows then receives the same file
            # for its large and small taskbar representations.
            self.iconbitmap(taskbar_icon_path)
            taskbar_icon = user32.LoadImageW(None, taskbar_icon_path, image_icon, 0, 0, lr_load_from_file)
            if taskbar_icon:
                user32.SendMessageW(hwnd, wm_seticon, icon_big, taskbar_icon)
                user32.SendMessageW(hwnd, wm_seticon, icon_small, taskbar_icon)
                user32.SendMessageW(hwnd, wm_seticon, icon_small2, taskbar_icon)
            self._windows_icon_handles = (taskbar_icon,)
        except (AttributeError, OSError, tk.TclError):
            self._windows_icon_handles = ()

    def _build_action_card(self, action: int):
        card = ctk.CTkFrame(
            self.sidebar,
            fg_color=self.colors["surface"],
            corner_radius=10,
            border_width=1,
            border_color=self.colors["border"],
            height=58,
        )
        card.pack(fill="x", padx=14, pady=6)
        card.pack_propagate(False)
        card.grid_columnconfigure(0, weight=1)

        title = ctk.CTkLabel(
            card,
            text=self.ACTION_TITLES[action],
            justify="left",
            anchor="w",
            wraplength=250,
            text_color=self.colors["text"],
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
        )
        title.grid(row=0, column=0, sticky="ew", padx=16, pady=16)

        for widget in (card, title):
            widget.configure(cursor="hand2")
            widget.bind(
                "<Button-1>",
                lambda _event, selected_action=action: self._try_open_action(selected_action),
            )

        self.action_cards[action] = card
        self.action_title_labels[action] = title

    TELL_MENU_ENTRY_HEIGHT = 40
    TELL_MENU_ENTRY_GAP = 6

    def _make_tell_menu(self, parent, batch):
        """Build the tell list and fit its entries into the available height."""
        count = len(TELL_CHOICES)
        menu = ctk.CTkFrame(parent, fg_color=self.colors["surface"], corner_radius=8,
                            height=count * ModelDeepenerApp.TELL_MENU_ENTRY_HEIGHT + (count - 1) * ModelDeepenerApp.TELL_MENU_ENTRY_GAP)
        menu.pack_propagate(False)
        buttons = []
        for index, choice in enumerate(TELL_CHOICES):
            button = ctk.CTkButton(menu, text=choice, anchor="w", height=ModelDeepenerApp.TELL_MENU_ENTRY_HEIGHT, corner_radius=8,
                                   fg_color=self.colors["surface"], border_width=1, border_color=self.colors["border"],
                                   hover_color=self.colors["primary_soft"], text_color=self.colors["text"],
                                   font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
                                   command=lambda value=choice: self._select_tell(value, batch))
            button.pack(fill="x", padx=0, pady=(0, ModelDeepenerApp.TELL_MENU_ENTRY_GAP if index < count - 1 else 0))
            buttons.append(button)
            description = tell_description(choice)[0]
            button.bind("<Enter>", lambda event, text=description: self._show_import_note_tooltip(event, [(text, False)]), add="+")
            button.bind("<Leave>", lambda _event: self._hide_adapted_tooltip(), add="+")
        def fit(event):
            scaling = ctk.ScalingTracker.get_widget_scaling(menu)
            available = event.height / scaling - (count - 1) * ModelDeepenerApp.TELL_MENU_ENTRY_GAP
            height = max(1, min(ModelDeepenerApp.TELL_MENU_ENTRY_HEIGHT, int(available // count)))
            for button in buttons:
                if button.cget("height") != height:
                    button.configure(height=height)
        menu.bind("<Configure>", fit, add="+")
        menu._tell_buttons = dict(zip(TELL_CHOICES, buttons))
        ModelDeepenerApp._refresh_tell_menu(self, batch, menu)
        return menu

    def _refresh_tell_menu(self, batch: bool, menu=None) -> None:
        """Highlight the currently selected tell in its sidebar menu."""
        if menu is None:
            menu = getattr(self, "_batch_tell_menu" if batch else "_single_tell_menu", None)
        if menu is None or not hasattr(menu, "_tell_buttons"):
            return
        selection = getattr(self, "_tell_selection", {}).get(batch, TELL_CHOICES[0])
        for name, button in menu._tell_buttons.items():
            active = name == selection
            button.configure(fg_color=self.colors["primary_soft"] if active else self.colors["surface"],
                             border_color=self.colors["primary"] if active else self.colors["border"],
                             text_color=self.colors["primary"] if active else self.colors["text"])

    def _select_tell(self, selection, batch):
        self._tell_selection[batch] = selection
        if batch:
            state = getattr(self, "_batch_tabs", {}).get(getattr(self, "_active_batch_tab", None))
            if state is not None:
                state["tell"] = selection
        ModelDeepenerApp._refresh_tell_menu(self, batch)
        if ModelDeepenerApp._show_cached_tell(self, selection, batch):
            return
        if batch:
            self._show_batch_analysis()
        else:
            self._open_placeholder_action(3)

    def _show_cached_tell(self, selection, batch):
        panel = getattr(self, "_active_tell_panel", None)
        cache = getattr(self, "_tell_cache", None)
        active = "batch" if batch else "model"
        key = getattr(self, "_active_batch_tab" if batch else "_active_model_tab", None)
        if (panel is None or cache is None or getattr(self, "active_top_tab", None) != active
                or getattr(panel, "_tell_owner", None) != (batch, key) or not panel.winfo_exists()):
            return False
        if batch:
            models = [(loaded.name, loaded.model, self._batch_format(loaded)) for loaded in self.batch_models]
        else:
            model = self.current_model
            loaded = next((item for item in self.loaded_models if item.model is model), None)
            models = [(self._current_model_display_name(), model, self._batch_format(loaded) if loaded else "")]
        rows = cache.get_prepared(selection, models)
        if rows is None:
            return False
        ModelDeepenerApp._update_tell_panel(self, panel, selection, rows, batch)
        return True

    def _update_tell_panel(self, panel, selection, rows, batch):
        panel._set_rows(selection, rows)
        title, subtitle = tell_description(selection)
        panel._tell_header.grid_slaves(row=0, column=0)[0].configure(text=title)
        panel._tell_header.grid_slaves(row=1, column=0)[0].configure(text=subtitle)
        if not batch:
            state = getattr(self, "_model_tabs", {}).get(getattr(self, "_active_model_tab", None))
            if state is not None:
                state["tell"] = selection

    def _present_tell_results(self, batch, selection, rows, render):
        panel = getattr(self, "_active_tell_panel", None)
        active = "batch" if batch else "model"
        key = getattr(self, "_active_batch_tab" if batch else "_active_model_tab", None)
        if (panel is not None and getattr(self, "active_top_tab", None) == active
                and getattr(panel, "_tell_owner", None) == (batch, key) and panel.winfo_exists()):
            ModelDeepenerApp._update_tell_panel(self, panel, selection, rows, batch)
        else:
            self._build_view_hidden(render)

    def _toggle_tell_menu(self, batch):
        self._tell_menu_open[batch] = not self._tell_menu_open[batch]
        if batch:
            if self._tell_menu_open[batch]:
                self._show_batch_analysis()
            else:
                self._batch_tell_menu.pack_forget()
        else:
            if self._tell_menu_open[batch]:
                self._single_tell_menu.pack(fill="both", expand=True, padx=14, pady=(0, 6), after=self.action_cards[3])
                self._open_placeholder_action(3)
            else:
                self._single_tell_menu.pack_forget()

    def _clear_content(self):
        for child in self.content.winfo_children():
            child.destroy()

    @staticmethod
    def _autohide_scroll(scrollbar) -> Callable[[str, str], None]:
        """Return a scroll command that shows a gridded scrollbar only while the content does not fit."""
        def update(first, last):
            scrollbar._autohide_pending = (first, last)
            if getattr(scrollbar, "_autohide_busy", False):
                return
            scrollbar._autohide_busy = True
            try:
                while scrollbar._autohide_pending is not None:
                    position = scrollbar._autohide_pending
                    scrollbar._autohide_pending = None
                    visible = float(position[0]) > 0.0 or float(position[1]) < 1.0
                    if visible and not scrollbar.winfo_manager():
                        scrollbar.grid()
                    elif not visible and scrollbar.winfo_manager():
                        scrollbar.grid_remove()
                    if getattr(scrollbar, "_autohide_position", None) != position:
                        scrollbar._autohide_position = position
                        scrollbar.set(*position)
            finally:
                scrollbar._autohide_busy = False
        return update

    def _show_workflow_sidebar(self):
        self.sidebar.grid(row=0, column=0, sticky="nsw")
        self.content.grid_configure(row=0, column=1, columnspan=1, sticky="nsew", padx=18, pady=18)
        if hasattr(self, "_batch_tell_menu"):
            self._batch_tell_menu.pack_forget()
        if self.current_action == 3 and self._tell_menu_open[False]:
            ModelDeepenerApp._refresh_tell_menu(self, False)
            self._single_tell_menu.pack(fill="both", expand=True, padx=14, pady=(0, 6), after=self.action_cards[3])
        else:
            self._single_tell_menu.pack_forget()

    def _hide_workflow_sidebar(self):
        if hasattr(self, "batch_sidebar"):
            self.batch_sidebar.grid_remove()
        self.sidebar.grid_remove()
        self.content.grid_configure(row=0, column=0, columnspan=2, sticky="nsew", padx=18, pady=18)

    def _set_top_tab(self, active: str):
        if active != getattr(self, "active_top_tab", None):
            ModelDeepenerApp._save_model_view(self)
        self.active_top_tab = active
        for button, is_active in (
                (self.new_model_tab, active == "new"),
                (self.models_tab, active == "models"),
                (self.batch_tab, active == "batch"),
        ):
            if button is None:
                continue
            button.configure(
                fg_color=self.colors["primary_soft"] if is_active else "transparent",
                hover_color=self.colors["primary_soft"] if is_active else self.colors["surface_alt"],
                text_color=self.colors["primary"] if is_active else self.colors["text"],
                border_width=1 if is_active else 0,
                border_color="#bfdbfe" if is_active else self.colors["surface"],
            )
        for key, state in getattr(self, "_batch_tabs", {}).items():
            button = state["button"]
            selected = active == "batch" and key == self._active_batch_tab
            button.configure(fg_color=self.colors["primary_soft"] if selected else "transparent",
                             hover_color=self.colors["primary_soft"] if selected else self.colors["surface_alt"],
                             text_color=self.colors["primary"] if selected else self.colors["text"],
                             border_width=1 if selected else 0, border_color="#bfdbfe" if selected else self.colors["surface"])
            state["close"].lift()
        for key, state in getattr(self, "_model_tabs", {}).items():
            button = state["button"]
            selected = active == "model" and key == self._active_model_tab
            button.configure(fg_color=self.colors["primary_soft"] if selected else "transparent",
                             hover_color=self.colors["primary_soft"] if selected else self.colors["surface_alt"],
                             text_color=self.colors["primary"] if selected else self.colors["text"],
                             border_width=1 if selected else 0, border_color="#bfdbfe" if selected else self.colors["surface"])
            state["close"].lift()
        if getattr(self, "_batch_tabs", None):
            self._layout_model_tabs()
        for name in ("model_tab_close", "batch_tab_close"):
            close = getattr(self, name, None)
            if close is not None:
                close.lift()

    def _close_top_tab(self, tab: str) -> None:
        """Close a model-specific tab without deleting its saved models."""
        if tab == "batch" and getattr(self, "_batch_tabs", None):
            self._close_batch_tab(self._active_batch_tab)
            return
        if tab == "batch":
            cache = getattr(self, "_tell_cache", None)
            if cache is not None:
                for loaded in self.batch_models:
                    cache.invalidate(loaded.model)
            self.batch_models = []
            self.batch_tab.grid_remove()
        elif tab == "model" and getattr(self, "_model_tabs", None):
            self._close_model_tab(self._active_model_tab)
            return
        elif tab == "model":
            self.current_model = None
            self._model_tab_state = None
            self.model_tab.grid_remove()
        else:
            return
        if self.active_top_tab == tab:
            self._show_models_overview_page()

    def _show_batch_sidebar(self, analysis: bool) -> None:
        """Use the workflow sidebar for batch actions and the batch tell menu."""
        self.sidebar.grid(row=0, column=0, sticky="nsw")
        self.content.grid_configure(row=0, column=1, columnspan=1, sticky="nsew", padx=18, pady=18)
        self._single_tell_menu.pack_forget()
        if not hasattr(self, "_batch_tell_menu"):
            self._batch_tell_menu = self._make_tell_menu(self.sidebar, batch=True)
        if analysis:
            ModelDeepenerApp._refresh_tell_menu(self, True)
            self._batch_tell_menu.pack(fill="both", expand=True, padx=14, pady=(0, 6), after=self.action_cards[3])
        else:
            self._batch_tell_menu.pack_forget()
        for action, card in self.action_cards.items():
            selected = action == (3 if analysis else 2)
            card.configure(fg_color=self.colors["primary_soft"] if selected else self.colors["surface"],
                           border_color=self.colors["primary"] if selected else self.colors["border"],
                           border_width=1, cursor="hand2")
            title = self.action_title_labels[action]
            title.configure(text=self.ACTION_TITLES[action],
                            text_color=self.colors["primary"] if selected else self.colors["text"], cursor="hand2")

    def _refresh_actions(self):
        for action, card in self.action_cards.items():
            is_current = action == self.current_action
            is_unlocked = self._is_navigation_item_available(action)
            card.configure(cursor="hand2" if is_unlocked else "arrow")
            self.action_title_labels[action].configure(cursor="hand2" if is_unlocked else "arrow")

            if is_current:
                card.configure(
                    fg_color=self.colors["primary_soft"],
                    border_color=self.colors["primary"],
                    border_width=1,
                )
                self.action_title_labels[action].configure(text_color=self.colors["primary"])
            elif is_unlocked:
                card.configure(
                    fg_color=self.colors["surface"],
                    border_color=self.colors["border"],
                    border_width=1,
                )
                self.action_title_labels[action].configure(text_color=self.colors["text"])
            else:
                card.configure(
                    fg_color=self.colors["disabled_bg"],
                    border_color=self.colors["border"],
                    border_width=1,
                )
                self.action_title_labels[action].configure(text_color="#94a3b8")

    def _try_open_action(self, action: int):
        if action != 2:
            ModelDeepenerApp._save_model_view(self)
        if getattr(self, "active_top_tab", None) == "batch":
            if action == 1:
                self._show_import_page()
            elif action == 2:
                self._show_batch_page()
            else:
                self._tell_menu_open[True] = True
                self._show_batch_analysis()
            return
        if not self._is_navigation_item_available(action):
            return
        if action == 1:
            self._show_import_page()
        elif action == 2:
            self._show_model_page()
        else:
            self._toggle_tell_menu(False)

    def _is_navigation_item_available(self, action: int) -> bool:
        if action == 1:
            return True
        if action != 1:
            return self.current_model is not None
        return True

    def _update_model_tab(self):
        """Create or update the tab belonging to the current model."""
        if self.current_model is None:
            return
        if not hasattr(self, "_model_tabs"):
            if self.model_tab is not None:
                self._model_tab_state = (self.current_model, self.current_file_path, self.current_file_type,
                                         list(self.current_selected_columns))
                self.model_tab.configure(text="  " + self._short_tab_text(self._current_model_display_name(), 18))
                self.model_tab.grid()
            return
        key = id(self.current_model)
        state = self._model_tabs.get(key)
        if state is None:
            button = ctk.CTkButton(self.model_tabs_container, text="", width=180, height=42, corner_radius=8,
                                   anchor="w", fg_color="transparent", text_color=self.colors["text"],
                                   font=ctk.CTkFont(size=14), command=lambda tab=key: self._reopen_model_tab(tab))
            close = ctk.CTkButton(button, text="x", width=18, height=18, fg_color="transparent",
                                  hover_color=self.colors["border"], text_color=self.colors["muted"],
                                  font=ctk.CTkFont(size=12), command=lambda tab=key: self._close_model_tab(tab))
            close.place(relx=1, x=-7, y=5, anchor="ne")
            state = {"button": button, "close": close, "view": "inspect", "tell": "Check All Tells"}
            self._model_tabs[key] = state
        state.update(model=self.current_model, path=self.current_file_path, file_type=self.current_file_type,
                     columns=list(self.current_selected_columns), name=self._current_model_display_name())
        state["button"].configure(text="  " + self._short_tab_text(state["name"], 18))
        self._active_model_tab = key
        self.model_tab = state["button"]
        self.model_tab_close = state["close"]
        self._model_tab_state = (self.current_model, self.current_file_path, self.current_file_type,
                                 list(self.current_selected_columns))
        self._layout_model_tabs()

    def _position_header_separators(self, _event=None) -> None:
        """Align navigation separators with the tab buttons."""
        if not hasattr(self, "_new_models_separator"):
            return
        y = self.new_model_tab.winfo_y() + max(0, (self.new_model_tab.winfo_height() - 30) // 2)
        self._new_models_separator.place(x=self.new_model_tab.winfo_x() + self.new_model_tab.winfo_width() + 3, y=y)
        if self._model_tabs or getattr(self, "_batch_tabs", {}) or (self.batch_tab is not None and self.batch_tab.winfo_manager()):
            self._models_tabs_separator.place(x=self.models_tab.winfo_x() + self.models_tab.winfo_width() + 3, y=y)
        else:
            self._models_tabs_separator.place_forget()

    def _layout_model_tabs(self):
        """Show the tabs that fit and put the remaining tabs in the overflow menu."""
        if not hasattr(self, "model_tabs_container"):
            return
        ModelDeepenerApp._position_header_separators(self)
        batches = getattr(self, "_batch_tabs", {})
        entries = [("model", key, state) for key, state in self._model_tabs.items()]
        entries += [("batch", key, state) for key, state in batches.items()]
        gap = round(8 * ctk.ScalingTracker.get_widget_scaling(self))
        tab_width = max((state["button"].winfo_reqwidth() for _, _, state in entries), default=0) + gap
        space = self._model_tab_space()
        available = len(entries)
        if tab_width * len(entries) > space:
            more_width = self.model_tabs_more.winfo_reqwidth() + gap
            available = max(1, (space - more_width) // tab_width)
        visible = entries[:available]
        active = (("batch", getattr(self, "_active_batch_tab", None)) if self.active_top_tab == "batch"
                  else ("model", self._active_model_tab))
        current = next((entry for entry in entries if entry[:2] == active), None)
        if current is not None and current not in visible:
            visible[-1:] = [current]
        overflow = [entry for entry in entries if entry not in visible]
        self._overflow_model_tabs = [key for kind, key, _ in overflow if kind == "model"]
        self._overflow_batch_tabs = [key for kind, key, _ in overflow if kind == "batch"]
        layout = (tuple(str(state["button"]) for _, _, state in visible), bool(overflow))
        if getattr(self, "_model_tabs_layout", None) == layout:
            return
        self._model_tabs_layout = layout
        for _, _, state in entries:
            state["button"].pack_forget()
        for _, _, state in visible:
            state["button"].pack(side="left", padx=(0, gap))
        if overflow:
            self.model_tabs_more.grid()
        else:
            self.model_tabs_more.grid_remove()
        if visible:
            self.model_tabs_container.grid()
        else:
            self.model_tabs_container.grid_remove()

    def _model_tab_space(self) -> int:
        """Return the header width in pixels that remains for the model tabs."""
        header = getattr(self, "header", None)
        if header is None or header.winfo_width() <= 1:
            return self.winfo_width()
        padding = round(32 * ctk.ScalingTracker.get_widget_scaling(self))
        # The tabs start right of Models Overview; the hidden container has no position of its own.
        models_tab = getattr(self, "models_tab", None)
        if models_tab is not None:
            used = models_tab.winfo_x() + models_tab.winfo_width() + round(8 * ctk.ScalingTracker.get_widget_scaling(self))
        else:
            used = self.model_tabs_container.winfo_x()
        for widget in (getattr(self, "batch_tab", None), getattr(self, "logo_label", None)):
            if widget is not None and widget.winfo_manager():
                used += widget.winfo_reqwidth() + padding
        return header.winfo_width() - used

    def _show_more_model_tabs(self):
        """List the model tabs that do not fit into the header."""
        menu = tk.Menu(self, tearoff=False, font=("Segoe UI", 11), activebackground=self.colors["primary_soft"],
                       activeforeground=self.colors["primary"])
        for key in self._overflow_model_tabs:
            menu.add_command(label=self._model_tabs[key]["name"], command=lambda tab=key: self._reopen_model_tab(tab))
        for key in getattr(self, "_overflow_batch_tabs", []):
            menu.add_command(label=self._batch_tabs[key]["name"], command=lambda tab=key: self._reopen_batch_tab(tab))
        menu.tk_popup(self.model_tabs_more.winfo_rootx(), self.model_tabs_more.winfo_rooty() + self.model_tabs_more.winfo_height())

    def _close_model_tab(self, key):
        state = self._model_tabs.pop(key, None)
        if state is None:
            return
        cache = getattr(self, "_tell_cache", None)
        if cache is not None and not any(loaded.model is state["model"]
                                         for batch in getattr(self, "_batch_tabs", {}).values()
                                         for loaded in batch["models"]):
            cache.invalidate(state["model"])
        state["button"].destroy()
        if self._active_model_tab == key:
            self._active_model_tab = None
            self.current_model = None
            self.model_tab = None
            self.model_tab_close = None
            self._model_tab_state = None
            if self.active_top_tab == "model":
                self._show_models_overview_page()
        self._layout_model_tabs()

    def _save_model_view(self):
        if getattr(self, "active_top_tab", None) != "model":
            return
        state = getattr(self, "_model_tabs", {}).get(getattr(self, "_active_model_tab", None))
        if state is None or state.get("view") != "inspect":
            return
        try:
            state["search"] = self.model_search_var.get()
            state["tree_scroll"] = self.model_tree.yview()[0]
            state["detail_scroll"] = (self.detail_canvas.yview()[0], self.detail_canvas.xview()[0])
            bar = getattr(self, "_detail_option_bar", None)
            if bar is not None and bar.winfo_exists():
                active = next((button for button in bar.winfo_children()
                               if isinstance(button, ctk.CTkButton)
                               and button.cget("fg_color") == self.colors["primary"]), None)
                state["detail_option"] = active.cget("text") if active is not None else None
            else:
                state["detail_option"] = None
            selected = self.model_tree.selection()
            if selected:
                state["selected_payload"] = self.tree_item_payload.get(selected[0])
                state["selected_view"] = self.tree_item_view.get(selected[0], "")
        except (AttributeError, tk.TclError):
            pass

    def _reopen_model_tab(self, key=None) -> None:
        """Restore a model tab and its last selected view."""
        if getattr(self, "_model_task_active", False):
            return
        if hasattr(self, "_model_tabs"):
            ModelDeepenerApp._save_model_view(self)
            key = self._active_model_tab if key is None else key
            state = self._model_tabs.get(key)
            if state is None:
                return
            self._active_model_tab = key
            self.current_model, self.current_file_path = state["model"], state["path"]
            self.current_file_type, self.current_selected_columns = state["file_type"], list(state["columns"])
            self._tell_selection[False] = state["tell"]
            # The tell menu belongs to the analysis view, so each tab shows it only there.
            self._tell_menu_open[False] = state["view"] == "analysis"
            if state["view"] == "analysis":
                self._open_placeholder_action(3)
            else:
                self._show_model_page()
            return
        if self._model_tab_state is not None:
            model, path, file_type, columns = self._model_tab_state
            self.current_model, self.current_file_path, self.current_file_type = model, path, file_type
            self.current_selected_columns = list(columns)
            self._show_model_page()

    def _save_batch_state(self):
        key = getattr(self, "_active_batch_tab", None)
        state = getattr(self, "_batch_tabs", {}).get(key)
        if state is None or self.active_top_tab != "batch":
            return
        state.update(models=list(self.batch_models), view=self._batch_view,
                     tell=self._tell_selection[True], menu=self._tell_menu_open[True])
        names = ("batch_search_var", "batch_type_filter_var", "batch_min_objects_var", "batch_min_attributes_var")
        if self._batch_view == "inspect" and all(hasattr(self, name) for name in names):
            state["filters"] = tuple(getattr(self, name).get() for name in names)

    def _new_batch_tab(self, models, preserve_current=True):
        if preserve_current:
            self._save_batch_state()
        number = self._next_batch_number
        self._next_batch_number += 1
        button = ctk.CTkButton(self.model_tabs_container, text=f"  Batch Process {number}", width=180,
                               height=42, corner_radius=8, anchor="w", fg_color="transparent",
                               text_color=self.colors["text"], font=ctk.CTkFont(size=14),
                               command=lambda: self._reopen_batch_tab(number))
        close = ctk.CTkButton(button, text="x", width=18, height=18, fg_color="transparent",
                              hover_color=self.colors["border"], text_color=self.colors["muted"],
                              font=ctk.CTkFont(size=12), command=lambda: self._close_batch_tab(number))
        close.place(relx=1, x=-7, y=5, anchor="ne")
        self._batch_tabs[number] = {"button": button, "close": close, "name": f"Batch Process {number}",
                                    "models": list(models), "view": "inspect", "tell": TELL_CHOICES[0],
                                    "menu": False, "filters": ("", "All", "", "")}
        self._active_batch_tab = number
        self.batch_models = list(models)
        self._batch_view = "inspect"
        self._tell_selection[True] = TELL_CHOICES[0]
        self._tell_menu_open[True] = False
        self._layout_model_tabs()

    def _close_batch_tab(self, key):
        state = self._batch_tabs.pop(key, None)
        if state is None:
            return
        state["button"].destroy()
        other_models = [loaded.model for other in self._batch_tabs.values() for loaded in other["models"]]
        other_models += [tab["model"] for tab in self._model_tabs.values() if "model" in tab]
        for loaded in state["models"]:
            if not any(loaded.model is model for model in other_models):
                self._tell_cache.invalidate(loaded.model)
        if key == self._active_batch_tab:
            self._active_batch_tab = None
            self.batch_models = []
            if self.active_top_tab == "batch":
                self._show_models_overview_page()
        self._layout_model_tabs()

    def _reopen_batch_tab(self, key=None):
        if getattr(self, "_model_task_active", False):
            return
        if getattr(self, "_batch_tabs", None):
            ModelDeepenerApp._save_model_view(self)
            key = self._active_batch_tab if key is None else key
            state = self._batch_tabs.get(key)
            if state is None:
                return
            if key != self._active_batch_tab:
                self._save_batch_state()
            self._active_batch_tab = key
            self.batch_models = list(state["models"])
            self._batch_view = state["view"]
            self._tell_selection[True] = state["tell"]
            self._tell_menu_open[True] = state["menu"]
            self._layout_model_tabs()
        if self._batch_view == "analysis":
            self._tell_menu_open[True] = True
            self._show_batch_analysis()
        else:
            self._show_batch_page()

    def _current_model_display_name(self) -> str:
        """
        Returns the model name shown in the top tab.

        A stored model shows its name from the Models Overview, for example "examMgmt (2)".
        Otherwise the path name of the model is used, or the file name if the model has no path
        name.
        """
        if self.current_model is None:
            return "Model"
        for loaded in self.loaded_models:
            if loaded.model is self.current_model:
                return self._display_table_value(loaded.name)
        name = self.current_model.path_name.split("::")[-1] if self.current_model.path_name else ""
        if not name and self.current_file_path:
            name = os.path.splitext(os.path.basename(self.current_file_path))[0]
        return self._display_table_value(name or "Model")

    @staticmethod
    def _short_tab_text(text: str, max_length: int = 28) -> str:
        """
        Shortens long model names so the top navigation keeps its shape.
        """
        if len(text) <= max_length:
            return text
        return f"{text[:max_length - 3]}..."

    @atomic_page
    def _show_import_page(self) -> None:
        """
        Shows the New Model page.

        This page contains Upload File, Select Example, Validation Results,
        Column Selection, and the Create Model and Continue button.
        """
        if self.current_model is not None:
            self._update_model_tab()
        self._reset_current_import_state()
        self.current_action = 1
        self._set_last_action(1)
        self._show_workflow_sidebar()
        self._set_top_tab("new")
        self._refresh_actions()
        self._clear_content()

        self._page_header(
            "Import Models",
            "Import a CSV, FMMLx, PlantUML, Ecore or UML-XMI file. Validation starts automatically after a file is selected.",
        )

        body = ctk.CTkFrame(self.content, fg_color="transparent")
        body.grid(row=1, column=0, sticky="nsew")
        body.grid_columnconfigure(0, weight=1)
        body.grid_columnconfigure(1, weight=1)
        body.grid_rowconfigure(1, weight=1)

        # -------------------------------------------------------------
        # File input card
        # -------------------------------------------------------------
        self.file_card = self._card(body)
        file_card = self.file_card
        file_card.grid(row=0, column=0, sticky="nsew", padx=(0, 10), pady=(0, 12))
        file_card.grid_columnconfigure(0, weight=1)

        self._card_title(file_card, "File Input").grid(
            row=0, column=0, sticky="w", padx=16, pady=(14, 10)
        )

        tab_row = ctk.CTkFrame(file_card, fg_color="transparent")
        tab_row.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 12))
        tab_row.grid_columnconfigure((0, 1, 2), weight=1)

        self._file_input_buttons = {}
        for column, (mode, label, action) in enumerate((
                ("upload", "Upload File", self._browse_file),
                ("example", "Select Example", self._select_example_file),
                ("batch", "Batch Import", self._browse_batch))):
            button = ctk.CTkButton(
                tab_row, text=label, height=38, corner_radius=7, border_width=1,
                font=ctk.CTkFont(family="Segoe UI", size=12),
                command=lambda value=mode, callback=action: self._activate_file_input(value, callback))
            button.grid(row=0, column=column, sticky="ew", padx=(0 if column == 0 else 5, 5 if column == 0 else 0))
            self._file_input_buttons[mode] = button

        self._card_title(file_card, "Selected File").grid(
            row=2, column=0, sticky="w", padx=16, pady=(0, 7)
        )

        file_row = ctk.CTkFrame(file_card, fg_color="transparent")
        file_row.grid(row=3, column=0, sticky="ew", padx=16, pady=(0, 14))
        file_row.grid_columnconfigure(0, weight=1)

        self.file_path_var = tk.StringVar(value=self.current_file_path or "")
        self.file_entry = ctk.CTkEntry(
            file_row,
            textvariable=self.file_path_var,
            height=40,
            corner_radius=7,
            border_color=self.colors["border"],
            fg_color="#F8FAFC",
            font=ctk.CTkFont(family="Segoe UI", size=13),
        )
        self.file_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))

        self.batch_file_list = ctk.CTkTextbox(
            file_row, height=100, corner_radius=7, border_width=1,
            border_color=self.colors["border"], fg_color="#F8FAFC",
            font=ctk.CTkFont(family="Segoe UI", size=13),
        )
        self.batch_file_list.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.batch_file_list.grid_remove()
        self._build_batch_folder_panel(file_row)

        self.file_browse_button = ctk.CTkButton(
            file_row,
            text="Browse...",
            width=105,
            height=40,
            corner_radius=7,
            fg_color=self.colors["primary_soft"],
            hover_color=self.colors["primary_soft"],
            text_color=self.colors["primary"],
            border_width=1,
            border_color="#AFCBFF",
            command=self._browse_file,
        )
        self.file_browse_button.grid(row=0, column=1)
        self._set_file_input_mode(self._file_input_mode)

        # -------------------------------------------------------------
        # Validation card
        # -------------------------------------------------------------
        self.validation_card = self._card(body)
        validation_card = self.validation_card
        validation_card.grid(row=0, column=1, sticky="nsew", padx=(10, 0), pady=(0, 12))
        validation_card.grid_columnconfigure(0, weight=1)

        validation_header = ctk.CTkFrame(validation_card, fg_color="transparent")
        validation_header.grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 8))

        self._card_title(validation_header, "Validation Results").pack(
            side="left"
        )
        self.validation_status_badge = ctk.CTkLabel(
            validation_header,
            text="Not validated",
            height=26,
            corner_radius=13,
            fg_color=self.colors["disabled_bg"],
            text_color=self.colors["muted"],
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
        )
        self.validation_status_badge.pack(side="right")

        self.validation_rows_frame = ctk.CTkFrame(
            validation_card,
            fg_color="transparent",
        )
        self.validation_rows_frame.grid(
            row=1, column=0, sticky="nsew", padx=16, pady=(0, 12)
        )
        self.validation_rows_frame.grid_columnconfigure(2, weight=1)

        # -------------------------------------------------------------
        # Column selection card
        # -------------------------------------------------------------
        selection_card = self._card(body)
        selection_card.grid(
            row=1, column=0, columnspan=2, sticky="nsew", pady=(0, 0)
        )
        selection_card.grid_columnconfigure(0, weight=1)
        selection_card.grid_rowconfigure(2, weight=1)

        selection_header = ctk.CTkFrame(selection_card, fg_color="transparent")
        selection_header.grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 2))
        selection_header.grid_columnconfigure(0, weight=1)

        self._card_title(selection_header, "Column Selection").grid(
            row=0, column=0, sticky="w"
        )

        self.expand_columns_button = ctk.CTkButton(
            selection_header,
            text="Expand",
            width=112,
            height=32,
            corner_radius=7,
            fg_color="#F8FAFC",
            hover_color="#EEF2F7",
            text_color=self.colors["primary"],
            border_width=1,
            border_color="#B8D2FF",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            command=self._toggle_column_selection_size,
        )
        self.expand_columns_button.grid(row=0, column=1, sticky="e")
        self._update_expand_columns_button()

        self.column_selection_description = ctk.CTkLabel(
            selection_card,
            text="Selected columns become attributes of the generated class.",
            anchor="w",
            text_color=self.colors["muted"],
            font=ctk.CTkFont(family="Segoe UI", size=13),
        )
        self.column_selection_description.grid(row=1, column=0, sticky="w", padx=16, pady=(0, 10))

        # One shared grid for header and all data cells.
        # This keeps every value exactly aligned under its column heading.
        self.column_table_wrapper = ctk.CTkFrame(
            selection_card,
            fg_color="#FFFFFF",
            corner_radius=0,
            border_width=0,
        )
        self.column_table_wrapper.grid(
            row=2,
            column=0,
            sticky="nsew",
            padx=16,
            pady=(0, 14),
        )
        self.column_table_wrapper.grid_columnconfigure(0, weight=1)
        self.column_table_wrapper.grid_rowconfigure(0, weight=1)

        self.column_canvas = tk.Canvas(
            self.column_table_wrapper,
            background="#FFFFFF",
            highlightthickness=0,
            bd=0,
            height=290,
        )
        self.column_canvas.grid(row=0, column=0, sticky="nsew")

        self.column_scrollbar = ctk.CTkScrollbar(
            self.column_table_wrapper,
            orientation="vertical",
            command=self.column_canvas.yview,
            width=14,
            button_color="#AFCBFF",
            button_hover_color=self.colors["primary"],
        )
        self.column_scrollbar.grid(row=0, column=1, sticky="ns", padx=(4, 0))
        self.column_canvas.configure(yscrollcommand=ModelDeepenerApp._autohide_scroll(self.column_scrollbar))

        # Mouse wheel / touchpad scrolling while the pointer is over
        # the Column Selection area.
        self.column_canvas.bind("<Enter>", self._bind_column_scroll_events)
        self.column_canvas.bind("<Leave>", self._unbind_column_scroll_events)

        self.column_table = None
        self.column_canvas_window = None
        self._reset_column_table(self.TABLE_HEADER_HEIGHT + 76)

        actions = ctk.CTkFrame(self.content, fg_color="transparent")
        actions.grid(row=2, column=0, sticky="ew", pady=(14, 0))
        actions.grid_columnconfigure(0, weight=1)

        self.create_button = ctk.CTkButton(
            actions,
            text="Create Model and Continue",
            width=240,
            height=44,
            corner_radius=8,
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            command=self._create_model,
        )
        self.create_button.grid(row=0, column=1, sticky="e")
        self._set_create_button_enabled(False)

        if self.current_file_path:
            self._validate_current_file()
        else:
            self._set_column_selection_enabled(False)
            self._render_empty_preview("Select a file to start.")

    def _reset_current_import_state(self):
        self.current_model = None
        self.current_file_path = None
        self._file_selection_mode = None
        self.current_batch_paths = []
        self.current_batch_folders = {}
        self.current_file_type = ""
        self.current_selected_columns = []
        self.csv_preview = None
        self.xml_preview = None
        self.selected_csv_columns.clear()
        self.action_completed = {1: False, 2: False, 3: False}

    def _show_model_page(self):
        if self.current_model is None:
            return
        model = self.current_model
        self._run_model_task(1, "Preparing model...",
                             lambda progress: self._model_metrics(model),
                             lambda metrics: self._render_model_page(model, metrics),
                             lambda error: self._show_error("Inspect Model", str(error)))

    @atomic_page
    def _render_model_page(self, model, metrics):
        """
        Shows the Inspect Model page.

        This page shows the model metrics, the Model Structure tree on the left,
        the Details area on the right, and the action buttons below.
        """
        if self.current_model is None:
            return
        self._set_last_action(2)
        self._touch_loaded_model(self.current_model)

        self.current_action = 2
        self.action_completed[2] = True
        self._tell_menu_open[False] = False
        self._show_workflow_sidebar()
        self._update_model_tab()
        if getattr(self, "_model_tabs", None):
            self._model_tabs[self._active_model_tab]["view"] = "inspect"
        self._set_top_tab("model")
        self._refresh_actions()
        self._clear_content()

        header = self._page_header(
            "Inspect Model",
            "Review the imported or generated model structure and content.",
        )
        if self.current_model.get_is_adapted():
            title_widget = header.grid_slaves(row=0, column=0)[0]
            info = ctk.CTkLabel(header, text="i", width=20, height=20, corner_radius=10,
                                fg_color=self.colors["primary_soft"], text_color=self.colors["primary"],
                                font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"), cursor="hand2")
            info.place(in_=title_widget, relx=1, x=8, rely=0.5, anchor="w")
            info.bind("<Enter>", self._show_adaptation_legend)
            info.bind("<Leave>", self._hide_adapted_tooltip)

        if getattr(self.current_model, "get_is_deepened", lambda: False)():
            title_widget = header.grid_slaves(row=0, column=0)[0]
            badge = ctk.CTkLabel(header, text="deepened", height=20, corner_radius=8,
                                 fg_color="#DDF3EE", text_color="#08765E",
                                 font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"), cursor="hand2")
            badge.place(in_=title_widget, relx=1, x=34 if self.current_model.get_is_adapted() else 8,
                        rely=0.5, anchor="w")
            badge.bind("<Enter>", self._show_deepened_tooltip)
            badge.bind("<Leave>", self._hide_adapted_tooltip)

        model = self.current_model
        self._attach_active_model_reference(model)

        body = ctk.CTkFrame(self.content, fg_color="transparent")
        body.grid(row=1, column=0, sticky="nsew")
        body.grid_columnconfigure(0, weight=0, minsize=390)
        body.grid_columnconfigure(1, weight=1)
        body.grid_rowconfigure(1, weight=1)

        # -------------------------------------------------------------
        # Summary metrics in the requested order.
        # -------------------------------------------------------------
        summary = ctk.CTkFrame(body, fg_color="transparent")
        summary.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 14))

        metric_colors = ("#315D9B", "#2563EB", "#7C3AED", "#F59E0B", "#E11D48",
                         "#64748B", "#16A34A", "#EA580C", "#0891B2")
        summary_items = [(label, value, color) for (label, value), color in zip(metrics, metric_colors)]

        for index, (label, value, value_color) in enumerate(summary_items):
            summary.grid_columnconfigure(index, weight=1)
            self._metric_card_no_icon(
                summary,
                label,
                value,
                value_color,
            ).grid(
                row=0,
                column=index,
                sticky="ew",
                padx=(0 if index == 0 else 5, 0 if index == len(summary_items) - 1 else 5),
            )

        # -------------------------------------------------------------
        # Model structure
        # -------------------------------------------------------------
        tree_card = self._card(body)
        tree_card.grid(
            row=1,
            column=0,
            sticky="nsew",
            padx=(0, 14),
        )
        tree_card.grid_columnconfigure(0, weight=1)
        tree_card.grid_rowconfigure(2, weight=1)

        self._card_title(tree_card, "Model Structure").grid(
            row=0,
            column=0,
            sticky="w",
            padx=16,
            pady=(14, 8),
        )

        search_row = ctk.CTkFrame(tree_card, fg_color="transparent")
        search_row.grid(
            row=1,
            column=0,
            sticky="ew",
            padx=16,
            pady=(0, 10),
        )
        search_row.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            search_row,
            text="Search",
            text_color=self.colors["text"],
            font=ctk.CTkFont(family="Segoe UI", size=12),
        ).grid(row=0, column=0, sticky="w", padx=(0, 10))

        model_state = getattr(self, "_model_tabs", {}).get(getattr(self, "_active_model_tab", None), {})
        self.model_search_var = tk.StringVar(value=model_state.get("search", ""))
        self.model_search_entry = ctk.CTkEntry(
            search_row,
            textvariable=self.model_search_var,
            placeholder_text="Search Model...",
            height=38,
            corner_radius=7,
            border_width=1,
            border_color="#CBD8EA",
            fg_color="#FFFFFF",
            text_color=self.colors["text"],
            placeholder_text_color="#94A3B8",
            font=ctk.CTkFont(
                family="Segoe UI",
                size=12,
            ),
        )
        self.model_search_entry.grid(
            row=0,
            column=1,
            sticky="ew",
        )
        self.model_search_var.trace_add(
            "write",
            lambda *_args: self._filter_model_tree(),
        )

        tree_container = ctk.CTkFrame(
            tree_card,
            fg_color="#FFFFFF",
            corner_radius=0,
            border_width=0,
        )
        tree_container.grid(
            row=2,
            column=0,
            sticky="nsew",
            padx=16,
            pady=(0, 16),
        )
        tree_container.grid_columnconfigure(0, weight=1)
        tree_container.grid_rowconfigure(0, weight=1)

        self.model_tree = self._tree(
            tree_container,
            show="tree",
            height=18,
        )
        self.model_tree.tag_configure(
            "model_root",
            font=("Segoe UI", 12, "bold"),
            foreground="#0F172A",
        )
        self.model_tree.tag_configure(
            "level_class",
            font=("Segoe UI", 11, "bold"),
            foreground="#2563EB",
        )
        self.model_tree.tag_configure(
            "level_object",
            font=("Segoe UI", 11, "bold"),
            foreground="#16A34A",
        )
        self.model_tree.tag_configure(
            "enum_group",
            font=("Segoe UI", 11, "bold"),
            foreground="#F59E0B",
        )
        self.model_tree.tag_configure(
            "class_item",
            font=("Segoe UI", 10),
            foreground="#0F172A",
        )
        self.model_tree.tag_configure(
            "enum_item",
            font=("Segoe UI", 10),
            foreground="#0F172A",
        )
        self.model_tree.tag_configure(
            "object_item",
            font=("Segoe UI", 10),
            foreground="#0F172A",
        )
        self.model_tree.tag_configure("serious_adaptation", font=("Segoe UI", 10), foreground="#B45309")
        self.model_tree.tag_configure("automatic_adaptation", font=("Segoe UI", 10), foreground="#647A94")
        self.model_tree.bind("<Motion>", self._show_tree_import_notes)
        self.model_tree.bind("<Leave>", self._hide_adapted_tooltip)
        self.model_tree.grid(
            row=0,
            column=0,
            sticky="nsew",
        )
        self.model_tree.bind("<<TreeviewOpen>>", self._open_model_tree_group)
        self.model_tree.bind(
            "<<TreeviewSelect>>",
            self._show_selected_details,
        )

        self.model_tree_scrollbar = ctk.CTkScrollbar(
            tree_container,
            orientation="vertical",
            command=self.model_tree.yview,
            width=14,
            button_color="#AFCBFF",
            button_hover_color=self.colors["primary"],
        )
        self.model_tree_scrollbar.grid(
            row=0,
            column=1,
            sticky="ns",
            padx=(4, 0),
        )
        self.model_tree.configure(
            yscrollcommand=ModelDeepenerApp._autohide_scroll(self.model_tree_scrollbar),
        )

        # -------------------------------------------------------------
        # Details panel in the same visual language as the Upload page.
        # -------------------------------------------------------------
        detail_card = self._card(body)
        self.detail_card = detail_card
        detail_card.grid(
            row=1,
            column=1,
            sticky="nsew",
        )
        detail_card.grid_columnconfigure(0, weight=1)
        detail_card.grid_rowconfigure(2, weight=1)

        self.detail_title = self._card_title(
            detail_card,
            "Details",
        )
        self.detail_title.grid(
            row=0,
            column=0,
            sticky="w",
            padx=16,
            pady=(14, 4),
        )

        self.detail_subtitle = ctk.CTkLabel(
            detail_card,
            text="Select a class or object to inspect its attributes and slots.",
            anchor="w",
            text_color=self.colors["muted"],
            font=ctk.CTkFont(family="Segoe UI", size=11),
        )
        self.detail_subtitle.grid(
            row=1,
            column=0,
            sticky="w",
            padx=16,
            pady=(0, 10),
        )

        self.detail_table_wrapper = ctk.CTkFrame(
            detail_card,
            fg_color="#FFFFFF",
            corner_radius=0,
            border_width=0,
        )
        self.detail_table_wrapper.grid(
            row=2,
            column=0,
            sticky="nsew",
            padx=16,
            pady=(0, 16),
        )
        self.detail_table_wrapper.grid_columnconfigure(0, weight=1)
        self.detail_table_wrapper.grid_rowconfigure(0, weight=1)

        self.detail_canvas = tk.Canvas(
            self.detail_table_wrapper,
            background="#FFFFFF",
            highlightthickness=0,
            bd=0,
        )
        self.detail_canvas.grid(row=0, column=0, sticky="nsew")

        self.detail_scrollbar = ctk.CTkScrollbar(
            self.detail_table_wrapper,
            orientation="vertical",
            command=self._detail_canvas_yview,
            width=14,
            button_color="#AFCBFF",
            button_hover_color=self.colors["primary"],
        )
        self.detail_scrollbar.grid(
            row=0,
            column=1,
            sticky="ns",
            padx=(4, 0),
        )

        self.detail_x_scrollbar = ctk.CTkScrollbar(
            self.detail_table_wrapper,
            orientation="horizontal",
            command=self._detail_canvas_xview,
            height=14,
            button_color="#AFCBFF",
            button_hover_color=self.colors["primary"],
        )
        self.detail_x_scrollbar.grid(
            row=1,
            column=0,
            sticky="ew",
            pady=(4, 0),
        )
        self.detail_x_scrollbar.grid_remove()

        self.detail_canvas.configure(
            xscrollcommand=self.detail_x_scrollbar.set,
            yscrollcommand=ModelDeepenerApp._autohide_scroll(self.detail_scrollbar),
        )
        self.detail_canvas.bind("<Enter>", self._bind_detail_scroll_events)
        self.detail_canvas.bind("<Leave>", self._unbind_detail_scroll_events)

        self.detail_table = tk.Frame(
            self.detail_canvas,
            background="#FFFFFF",
            bd=0,
            highlightthickness=0,
        )
        self.detail_canvas_window = self.detail_canvas.create_window(
            (0, 0),
            window=self.detail_table,
            anchor="nw",
        )
        self.detail_table.bind(
            "<Configure>",
            lambda _event: self.detail_canvas.configure(
                scrollregion=self.detail_canvas.bbox("all")
            ),
        )
        self.detail_canvas.bind(
            "<Configure>",
            self._resize_detail_canvas_window,
        )

        # -------------------------------------------------------------
        # Navigation
        # -------------------------------------------------------------
        actions = ctk.CTkFrame(
            self.content,
            fg_color="transparent",
        )
        actions.grid(
            row=2,
            column=0,
            sticky="ew",
            pady=(14, 0),
        )
        actions.grid_columnconfigure(1, weight=1)

        ctk.CTkButton(
            actions,
            text="Back to Import",
            width=150,
            height=42,
            corner_radius=8,
            fg_color="#FFFFFF",
            hover_color=self.colors["primary_soft"],
            border_width=1,
            border_color="#C7D2E3",
            text_color=self.colors["text"],
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            command=self._show_import_page,
        ).grid(
            row=0,
            column=0,
            sticky="w",
        )

        ctk.CTkButton(
            actions,
            text="Check Constraints",
            width=180,
            height=42,
            corner_radius=8,
            fg_color="#FFFFFF",
            hover_color=self.colors["primary_soft"],
            border_width=1,
            border_color="#C7D2E3",
            text_color=self.colors["text"],
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            command=self._check_current_constraints,
        ).grid(
            row=0,
            column=2,
            sticky="e",
            padx=(0, 10),
        )

        ctk.CTkButton(
            actions,
            text="Export Model",
            width=170,
            height=42,
            corner_radius=8,
            fg_color=self.colors["primary"],
            hover_color=self.colors["primary_hover"],
            text_color="#FFFFFF",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            command=self._export_current_model_placeholder,
        ).grid(
            row=0,
            column=3,
            sticky="e",
        )

        self._add_export_without_check_button(actions)
        self._populate_model_tree(model, query=self.model_search_var.get())
        self._show_model_overview_load_options(model)
        saved = model_state
        saved_tree, saved_canvas = self.model_tree, self.detail_canvas
        def restore_model_view():
            if self.model_tree is not saved_tree or not saved_tree.winfo_exists():
                return
            payload = saved.get("selected_payload")
            view = saved.get("selected_view", "")
            if payload is not None:
                def same_payload(value):
                    if value is payload:
                        return True
                    return (isinstance(value, tuple) and isinstance(payload, tuple) and len(value) == len(payload)
                            and all(left is right or (isinstance(left, (str, int)) and left == right)
                                    for left, right in zip(value, payload)))
                item = next((key for key, value in self.tree_item_payload.items()
                             if same_payload(value) and self.tree_item_view.get(key, "") == view), None)
                if item is not None:
                    self.model_tree.selection_set(item)
            self.model_tree.yview_moveto(saved.get("tree_scroll", 0.0))
            def restore_detail():
                if self.detail_canvas is not saved_canvas or not saved_canvas.winfo_exists():
                    return
                option = saved.get("detail_option")
                bar = getattr(self, "_detail_option_bar", None)
                if option and bar is not None and bar.winfo_exists():
                    button = next((item for item in bar.winfo_children() if isinstance(item, ctk.CTkButton)
                                   and item.cget("text") == option and item.cget("state") == "normal"), None)
                    if button is not None:
                        button.invoke()
                y, x = saved.get("detail_scroll", (0.0, 0.0))
                self.detail_canvas.yview_moveto(y)
                self.detail_canvas.xview_moveto(x)
            self.after(1, restore_detail)
        self.after_idle(restore_model_view)

    def _bind_detail_scroll_events(self, _event=None):
        """
        Enables scrolling inside the Inspect Model detail area.

        The methods below belong to the same technical block. They keep large
        detail tables and the model overview table usable when many rows or
        columns are displayed.
        """
        self.bind_all("<MouseWheel>", self._on_detail_mousewheel)
        self.bind_all("<Shift-MouseWheel>", self._on_detail_shift_mousewheel)

    def _unbind_detail_scroll_events(self, _event=None):
        self.unbind_all("<MouseWheel>")
        self.unbind_all("<Shift-MouseWheel>")

    def _on_detail_mousewheel(self, event):
        delta = int(-1 * (event.delta / 120)) if event.delta else 0
        if delta:
            self.detail_canvas.yview_scroll(delta, "units")
            self._sync_model_overview_sticky_items()

    def _on_detail_shift_mousewheel(self, event):
        delta = int(-1 * (event.delta / 120)) if event.delta else 0
        if delta:
            self.detail_canvas.xview_scroll(delta, "units")
            self._sync_model_overview_sticky_items()

    def _detail_canvas_yview(self, *args):
        self.detail_canvas.yview(*args)
        self._sync_model_overview_sticky_items()

    def _detail_canvas_xview(self, *args):
        self.detail_canvas.xview(*args)
        self._sync_model_overview_sticky_items()

    def _update_detail_x_scrollbar_visibility(self):
        # The left-right bar is only useful when the table is wider than the visible area.
        if not hasattr(self, "detail_canvas") or not hasattr(self, "detail_x_scrollbar"):
            return
        bbox = self.detail_canvas.bbox("all")
        if bbox is None:
            self.detail_x_scrollbar.grid_remove()
            return
        content_width = bbox[2] - bbox[0]
        visible_width = self.detail_canvas.winfo_width()
        if content_width > visible_width + 2:
            self.detail_x_scrollbar.grid()
        else:
            self.detail_x_scrollbar.grid_remove()

    def _resize_detail_canvas_window(self, event):
        window_id: Optional[int] = getattr(self, "detail_canvas_window", None)
        if window_id is None:
            context = getattr(self, "_overview_resize_context", None)
            if context is not None:
                token, model_name, attributes, rows, widths = context
                fitted = self._fit_column_widths(widths, event.width)
                if fitted != widths:
                    self._begin_prepared_model_overview_render(token, model_name, attributes, rows, fitted)
            return
        try:
            widths = getattr(self, "_detail_column_widths", [])
            if widths:
                widths = self._fit_column_widths(widths, event.width)
                self._detail_column_widths = widths
                for column, width in enumerate(widths):
                    self.detail_table.grid_columnconfigure(column, weight=0, minsize=width)
                key = getattr(self, "_detail_width_key", None)
                if key is not None:
                    self._table_column_widths[key] = list(widths)
                width = sum(widths)
            else:
                width = event.width
            self.detail_canvas.itemconfigure(window_id, width=width)
            self.detail_canvas.configure(scrollregion=self.detail_canvas.bbox("all"))
            self._update_detail_x_scrollbar_visibility()
            ModelDeepenerApp._refresh_detail_sticky_header(self)
        except tk.TclError:
            pass

    def _reset_detail_canvas_table(self):
        old_header = getattr(self, "_detail_sticky_header", None)
        if old_header is not None and old_header.winfo_exists():
            old_header.destroy()
        self._detail_sticky_header = None
        self.detail_canvas.delete("all")
        self._detail_column_widths = []
        self._detail_width_key = None
        self._overview_resize_context = None
        self.detail_table = tk.Frame(
            self.detail_canvas,
            background="#FFFFFF",
            bd=0,
            highlightthickness=0,
        )
        self.detail_canvas_window = self.detail_canvas.create_window(
            (0, 0),
            window=self.detail_table,
            anchor="nw",
        )
        self.detail_table.bind(
            "<Configure>",
            lambda _event: self.detail_canvas.configure(
                scrollregion=self.detail_canvas.bbox("all")
            ),
        )
        self.detail_canvas.configure(scrollregion=(0, 0, 0, 0))
        self._update_detail_x_scrollbar_visibility()

    @staticmethod
    def _natural_sort_key(text: str):
        """
        Sorts names with numbers in a human-readable order.

        This starts the shared formatting helper block. The methods here prepare
        names and values before they are shown in tables or labels.
        """
        return [
            int(part) if part.isdigit() else part.lower()
            for part in re.split(r"(\d+)", text)
        ]

    @staticmethod
    def _model_overview_display_name(model: BaseMlmModel) -> str:
        """Prefer the first attributed class name, falling back to the model path or a generic label."""
        class_objects = [
            obj
            for obj in model.mlm_objects
            if obj.level > 0 and obj.get_regular_attributes()
        ]
        if class_objects:
            return class_objects[0].name
        if model.path_name:
            return model.path_name.split("::")[-1]
        return "Model"


    def _open_placeholder_action(self, action: int):
        """Prepare the single-model analysis before displaying it."""
        selection = self._tell_selection[False]
        model = self.current_model
        model_name = self._current_model_display_name()
        loaded = next((item for item in getattr(self, "loaded_models", []) if item.model is model), None) if isinstance(model, BaseMlmModel) else None
        model_format = self._batch_format(loaded) if loaded is not None else ""
        self._run_model_task(1, "Preparing analysis...",
                             lambda progress: analyze_tells(selection, [(model_name, model, model_format)], progress, self._tell_cache)
                             if isinstance(model, BaseMlmModel) else analyze_tells(selection, [(model_name, model)], progress),
                             lambda rows: ModelDeepenerApp._present_tell_results(
                                 self, False, selection, rows, lambda: self._render_single_analysis(action, selection, rows)),
                             lambda error: self._show_error("Analysis", str(error)))

    def _build_view_hidden(self, build: Callable[[], None], message: str = "Preparing analysis...") -> None:
        """Build a view while the screen still shows the previous one.

        Building the analysis widgets blocks Tk. If it takes longer than half a second, a large
        loading window with a running bar appears until the new view is complete.
        """
        geometry = (self.winfo_rootx(), self.winfo_rooty(), self.winfo_width(), self.winfo_height())
        self._view_loading.start(geometry, message, ctk.ScalingTracker.get_widget_scaling(self))
        frozen = set_window_redraw(self, False)
        try:
            build()
            self.update_idletasks()
        finally:
            if frozen:
                set_window_redraw(self, True)
            self._view_loading.stop()

    @atomic_page
    def _render_single_analysis(self, action, selection, rows):
        """Display the selected tell analysis for the current model."""
        self.current_action = action
        self._set_last_action(action)
        self._show_workflow_sidebar()
        self._update_model_tab()
        if getattr(self, "_model_tabs", None):
            self._model_tabs[self._active_model_tab].update(view="analysis", tell=self._tell_selection[False])
        self._set_top_tab("model")
        self._refresh_actions()
        self._clear_content()
        header = self._page_header(*tell_description(selection))
        body = ctk.CTkFrame(self.content, fg_color="transparent")
        body.grid(row=1, column=0, sticky="nsew")
        body.grid_columnconfigure(0, weight=1)
        body.grid_rowconfigure(0, weight=1)

        panel = self._build_tell_results(body, batch=False, row_provider=lambda _selection: rows)
        panel._tell_owner = (False, getattr(self, "_active_model_tab", None))
        panel._tell_header = header
        self._active_tell_panel = panel
        panel.grid(row=0, column=0, sticky="nsew")

    # The same heights as the header and rows of the detail tables in Inspect Model.
    TELL_HEADER_HEIGHT = 42
    TELL_ROW_HEIGHT = 46
    # Unscaled widths of the indicator IDs and the Yes/No choices.
    TELL_INDICATOR_WIDTH = 260
    TELL_TRANSFORM_WIDTH = 160

    @classmethod
    def _balanced_tell_widths(cls, count: int, total: int, scaling: float = 1.0) -> list[int]:
        """Give name columns the available space while keeping the last columns compact."""
        wide = count - 2
        indicators = round(cls.TELL_INDICATOR_WIDTH * scaling)
        transform = round(cls.TELL_TRANSFORM_WIDTH * scaling)
        each = max(round(200 * scaling), (total - indicators - transform) // wide)
        widths = [each] * wide + [indicators, transform]
        widths[wide - 1] += max(0, total - sum(widths))
        return widths

    @staticmethod
    def _bind_table_wheel(widget, canvas):
        """Route wheel events from a table's child widgets to its canvas."""
        def wheel(event):
            delta = getattr(event, "delta", 0)
            if getattr(event, "num", 0) in (4, 5):
                delta = 120 if event.num == 4 else -120
            accumulated = getattr(canvas, "_wheel_remainder", 0) + delta
            steps = int(accumulated / 120)
            canvas._wheel_remainder = accumulated - steps * 120
            if steps:
                canvas.yview_scroll(-steps, "units")
            return "break"
        for event in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            try:
                widget.bind(event, wheel)
            except (tk.TclError, ValueError):
                pass
        for child in widget.winfo_children():
            ModelDeepenerApp._bind_table_wheel(child, canvas)

    def _build_tell_results(self, parent, batch: bool, row_provider=None):
        """Display results in a resizable table and retain each displayed decision."""
        provider = row_provider or (lambda _selection: [])
        panel = ctk.CTkFrame(parent, fg_color="transparent")
        panel.grid_columnconfigure(0, weight=1)
        panel.grid_rowconfigure(0, weight=1)
        card = self._card(panel)
        card.grid(row=0, column=0, sticky="nsew")
        card.grid_columnconfigure(0, weight=1)
        card.grid_rowconfigure(1, weight=1)
        selected = tk.StringVar(value=self._tell_selection[batch])
        panel._tell_choice = selected
        panel._transform_choices = []
        panel._tell_rows = []
        columns = tell_columns(batch)
        tab_state = (getattr(self, "_batch_tabs", {}).get(getattr(self, "_active_batch_tab", None)) if batch
                     else getattr(self, "_model_tabs", {}).get(getattr(self, "_active_model_tab", None)))
        scroll_state = tab_state.setdefault("analysis_scroll", {}) if tab_state is not None else None
        saved_scroll = scroll_state.get(selected.get(), (0.0, 0.0)) if scroll_state is not None else (0.0, 0.0)
        scaling = ctk.ScalingTracker.get_widget_scaling(self)
        panel._tell_widths = self._balanced_tell_widths(len(columns), 1000, scaling)
        panel._tell_resized = False
        wrapper = ctk.CTkFrame(card, fg_color="#FFFFFF", corner_radius=0)
        wrapper.grid(row=1, column=0, sticky="nsew", padx=16, pady=(14, 16))
        wrapper.grid_columnconfigure(0, weight=1)
        wrapper.grid_rowconfigure(0, weight=1)
        canvas = tk.Canvas(wrapper, background="#FFFFFF", highlightthickness=0)
        canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar = ctk.CTkScrollbar(wrapper, orientation="vertical", command=canvas.yview, width=14,
                                     button_color="#AFCBFF", button_hover_color=self.colors["primary"])
        scrollbar.grid(row=0, column=1, sticky="ns", padx=(4, 0))
        horizontal = ctk.CTkScrollbar(wrapper, orientation="horizontal", command=canvas.xview, height=14,
                                      button_color="#AFCBFF", button_hover_color=self.colors["primary"])
        horizontal.grid(row=1, column=0, sticky="ew", pady=(4, 0))
        horizontal_scroll = ModelDeepenerApp._autohide_scroll(horizontal)
        def on_horizontal(first, last):
            horizontal_scroll(first, last)
            if scroll_state is not None:
                scroll_state[selected.get()] = (canvas.yview()[0], float(first))
        canvas.configure(yscrollcommand=ModelDeepenerApp._autohide_scroll(scrollbar),
                         xscrollcommand=on_horizontal)
        table = tk.Frame(canvas, bg="#FFFFFF")
        table_window = canvas.create_window(0, 0, anchor="nw", window=table)

        panel._tell_text_labels = []
        sticky = tk.Frame(canvas, bg="#DFE9FD")
        sticky_window = canvas.create_window(0, 0, anchor="nw", window=sticky)
        panel._tell_canvas = canvas
        panel._tell_sticky = sticky

        def apply_widths():
            for index, width in enumerate(panel._tell_widths):
                table.grid_columnconfigure(index, minsize=width, weight=0)
                sticky.grid_columnconfigure(index, minsize=width, weight=0)
            # CTkLabel scales its wrap length itself, while the column widths are screen pixels.
            scaling = ctk.ScalingTracker.get_widget_scaling(self)
            for label, column in panel._tell_text_labels:
                label.configure(wraplength=max(40, panel._tell_widths[column] - 24))
            width = sum(panel._tell_widths)
            if getattr(panel, "_tell_applied_width", None) != width:
                panel._tell_applied_width = width
                canvas.itemconfigure(table_window, width=width)
                canvas.itemconfigure(sticky_window, width=width)
            region = (0, 0, width, self.TELL_HEADER_HEIGHT + max(1, len(panel._tell_rows)) * self.TELL_ROW_HEIGHT)
            if getattr(panel, "_tell_region", None) != region:
                panel._tell_region = region
                canvas.configure(scrollregion=region)

        def fit_to_canvas(event):
            # Until the user drags a column, the columns share the visible width.
            if not panel._tell_resized and event.width > 1:
                panel._tell_widths = self._balanced_tell_widths(len(columns), event.width, scaling)
                apply_widths()

        canvas.bind("<Configure>", fit_to_canvas)

        def start_resize(event, column):
            panel._tell_resize = (column, event.x_root, list(panel._tell_widths))

        def resize(event):
            column, start_x, original = panel._tell_resize
            panel._tell_resized = True
            panel._tell_widths = self._move_column_boundary(original, column, event.x_root - start_x, minimum=100)
            apply_widths()

        def render(selection):
            # Cells keep fixed heights like the tables of Inspect Model, so their content is placed, not packed.
            for child in table.winfo_children():
                child.destroy()
            panel._transform_choices = []
            panel._tell_rows = []
            panel._tell_text_labels = []
            header_bg = "#DFE9FD"
            for index, title in enumerate(columns):
                cell = tk.Frame(table, bg=header_bg, bd=0, highlightthickness=1, highlightbackground="#AFC1D9", highlightcolor="#AFC1D9", height=self.TELL_HEADER_HEIGHT)
                cell.grid(row=0, column=index, sticky="nsew")
                cell.grid_propagate(False)
                if index > 0:
                    tk.Frame(cell, width=1, background="#AFC1D9").place(x=0, y=0, width=1, relheight=1)
                ctk.CTkLabel(cell, text=title, text_color="#04173D",
                             font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold")).place(
                                 relx=0.5, rely=0.5, anchor="center")
                fixed_cell = tk.Frame(sticky, bg=header_bg, bd=0, highlightthickness=1,
                                      highlightbackground="#AFC1D9", height=self.TELL_HEADER_HEIGHT)
                fixed_cell.grid(row=0, column=index, sticky="nsew")
                fixed_cell.grid_propagate(False)
                ctk.CTkLabel(fixed_cell, text=title, text_color="#04173D",
                             font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold")).place(
                                 relx=0.5, rely=0.5, anchor="center")
                if index < len(columns) - 1:
                    fixed_handle = tk.Frame(fixed_cell, bg=header_bg, width=8, cursor="sb_h_double_arrow")
                    fixed_handle.place(relx=1, rely=0, relheight=1, anchor="ne")
                    fixed_handle.bind("<ButtonPress-1>", lambda event, col=index: start_resize(event, col))
                    fixed_handle.bind("<B1-Motion>", resize)
                if index < len(columns) - 1:
                    handle = tk.Frame(cell, bg=header_bg, width=8, cursor="sb_h_double_arrow")
                    handle.place(relx=1, rely=0, relheight=1, anchor="ne")
                    handle.bind("<ButtonPress-1>", lambda event, col=index: start_resize(event, col))
                    handle.bind("<B1-Motion>", resize)
            result_rows = []
            cache = getattr(self, "_tell_cache", None)
            top_space = tk.Frame(table, height=1, bg="#FFFFFF")
            top_space.grid(row=1, column=0, columnspan=len(columns), sticky="ew")
            bottom_space = tk.Frame(table, height=1, bg="#FFFFFF")
            bottom_space.grid(row=2, column=0, columnspan=len(columns), sticky="ew")
            empty = tk.Frame(table, bg="#FFFFFF", height=self.TELL_ROW_HEIGHT, highlightthickness=1,
                             highlightbackground="#AFC1D9")
            empty.grid_propagate(False)
            ctk.CTkLabel(empty, text="No affected parts found.", text_color=self.colors["muted"]).place(
                relx=0.5, rely=0.5, anchor="center")
            warning = ctk.CTkLabel(card, text="", text_color="#B45309", anchor="w")
            slots = []
            panel._tell_slots = slots

            def make_slot(index):
                slot = {"cells": [], "labels": [], "decision": None, "details": ""}
                for column in range(len(columns)):
                    cell = tk.Frame(table, bg="#FFFFFF", bd=0, highlightthickness=1,
                                    highlightbackground="#AFC1D9", highlightcolor="#AFC1D9",
                                    height=self.TELL_ROW_HEIGHT)
                    cell.grid(row=index + 2, column=column, sticky="nsew")
                    cell.grid_propagate(False)
                    slot["cells"].append(cell)
                    if column > 0:
                        tk.Frame(cell, width=1, background="#AFC1D9").place(x=0, y=0, width=1, relheight=1)
                    if column < len(columns) - 1:
                        label = tk.Label(cell, foreground=self.colors["text"], background="#FFFFFF",
                                         justify="center", font=("Segoe UI", 12), borderwidth=0)
                        label.place(relx=0.5, rely=0.5, anchor="center")
                        if column == len(columns) - 2:
                            def show_details(event, current=slot):
                                if current["details"]:
                                    self._show_import_note_tooltip(event, [(current["details"], False)])
                            label.bind("<Enter>", show_details)
                            label.bind("<Leave>", lambda _event: self._hide_adapted_tooltip())
                        slot["labels"].append(label)
                    else:
                        variable = tk.StringVar(value="No")
                        def changed(*_args, current=slot, var=variable):
                            if current["decision"] is not None:
                                current["decision"].set(var.get())
                        variable.trace_add("write", changed)
                        slot["variable"] = variable
                        choices = tk.Frame(cell, bg="#FFFFFF")
                        slot["choices"] = choices
                        for text in ("Yes", "No"):
                            ctk.CTkCheckBox(choices, text=text, variable=variable, onvalue=text,
                                            offvalue="No" if text == "Yes" else "Yes",
                                            bg_color="#FFFFFF", width=60).pack(side="left", padx=6)
                        dash = tk.Label(cell, text="?", foreground=self.colors["muted"],
                                        background="#FFFFFF", borderwidth=0)
                        slot["dash"] = dash
                ModelDeepenerApp._bind_table_wheel(table, canvas)
                return slot

            def draw_visible():
                if not table.winfo_exists():
                    return
                top = max(0, int((canvas.canvasy(0) - self.TELL_HEADER_HEIGHT) // self.TELL_ROW_HEIGHT) - 1)
                bottom = min(len(result_rows), int((canvas.canvasy(canvas.winfo_height()) - self.TELL_HEADER_HEIGHT) // self.TELL_ROW_HEIGHT) + 3)
                top = min(top, len(result_rows))
                if getattr(panel, "_tell_visible", None) == (top, bottom):
                    return
                panel._tell_visible = (top, bottom)
                count = max(0, bottom - top)
                while len(slots) < count:
                    slots.append(make_slot(len(slots)))
                panel._tell_text_labels = []
                panel._tell_visible_vars = []
                canvas.coords(table_window, 0, top * self.TELL_ROW_HEIGHT)
                bottom_space.grid_configure(row=count + 2)
                for index, slot in enumerate(slots):
                    if index >= count:
                        for cell in slot["cells"]:
                            cell.grid_remove()
                        continue
                    result = result_rows[top + index]
                    color = "#FFFFFF" if (top + index) % 2 == 0 else "#F3F7FD"
                    values = [result.model_name, result.model_format, result.affected_parts, result.indicators]
                    color_changed = slot.get("color") != color
                    for cell in slot["cells"]:
                        if color_changed:
                            cell.configure(bg=color)
                        if not cell.winfo_manager():
                            cell.grid()
                    for column, (label, value) in enumerate(zip(slot["labels"], values)):
                        text = str(value)
                        if label.cget("text") != text or color_changed:
                            label.configure(text=text, background=color)
                        panel._tell_text_labels.append((label, column))
                    slot["details"] = result.indicator_details
                    slot["decision"] = None
                    decision_value = panel._transform_choices[top + index].get()
                    if slot["variable"].get() != decision_value:
                        slot["variable"].set(decision_value)
                    slot["decision"] = panel._transform_choices[top + index]
                    if color_changed:
                        slot["choices"].configure(bg=color)
                        for checkbox in slot["choices"].winfo_children():
                            checkbox.configure(bg_color=color)
                        slot["dash"].configure(background=color)
                        slot["color"] = color
                    if result.is_placeholder:
                        slot["choices"].place_forget()
                        slot["dash"].place(relx=0.5, rely=0.5, anchor="center")
                    else:
                        slot["dash"].place_forget()
                        slot["choices"].place(relx=0.5, rely=0.5, anchor="center")
                        panel._tell_visible_vars.append(slot["variable"])
                apply_widths()

            vertical_scroll = ModelDeepenerApp._autohide_scroll(scrollbar)
            def on_scroll(first, last):
                vertical_scroll(first, last)
                canvas.coords(sticky_window, 0, canvas.canvasy(0))
                canvas.tag_raise(sticky_window)
                if scroll_state is not None:
                    scroll_state[selected.get()] = (float(first), canvas.xview()[0])
                if not getattr(panel, "_tell_redraw_pending", False):
                    panel._tell_redraw_pending = True
                    def redraw():
                        panel._tell_redraw_pending = False
                        draw_visible()
                    canvas.after_idle(redraw)
            canvas.configure(yscrollcommand=on_scroll)
            canvas.bind("<Configure>", lambda event: (fit_to_canvas(event), draw_visible()))
            ModelDeepenerApp._bind_table_wheel(canvas, canvas)
            ModelDeepenerApp._bind_table_wheel(sticky, canvas)

            def set_rows(new_selection, new_rows):
                nonlocal result_rows
                position = scroll_state.get(new_selection, (0.0, 0.0)) if scroll_state is not None else (0.0, 0.0)
                result_rows = new_rows
                selected.set(new_selection)
                panel._transform_choices = [TellDecision(cache, result.key) for result in result_rows]
                panel._tell_rows = list(zip(result_rows, panel._transform_choices))
                failures = getattr(result_rows, "failures", ())
                if failures:
                    warning.configure(text=f"{len(failures)} checks failed.")
                    warning.grid(row=0, column=0, sticky="ew", padx=16, pady=(12, 0))
                else:
                    warning.grid_remove()
                if result_rows:
                    empty.grid_remove()
                else:
                    empty.grid(row=1, column=0, columnspan=len(columns), sticky="nsew")
                panel._tell_visible = None
                apply_widths()
                if abs(canvas.yview()[0] - position[0]) > 1e-6:
                    canvas.yview_moveto(position[0])
                if abs(canvas.xview()[0] - position[1]) > 1e-6:
                    canvas.xview_moveto(position[1])
                draw_visible()
            panel._set_rows = set_rows
            set_rows(selection, provider(selection))
            def restore_scroll():
                if canvas.winfo_exists():
                    canvas.yview_moveto(saved_scroll[0])
                    canvas.xview_moveto(saved_scroll[1])
                    draw_visible()
            canvas.after_idle(restore_scroll)

        render(selected.get())
        actions = ctk.CTkFrame(panel, fg_color="transparent")
        actions.grid(row=1, column=0, sticky="e", pady=(14, 0))
        ctk.CTkButton(actions, text="Transform", width=170, height=42, corner_radius=8,
                      fg_color=self.colors["primary"], hover_color=self.colors["primary_hover"], text_color="#FFFFFF",
                      font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
                      command=lambda: self._transform_tell_results(panel, batch)).pack(side="left", padx=(0, 10))
        ctk.CTkButton(actions, text="Export CSV", width=170, height=42, corner_radius=8,
                      fg_color=self.colors["primary"], hover_color=self.colors["primary_hover"], text_color="#FFFFFF",
                      font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
                      command=lambda: self._export_tell_results(panel, batch)).pack(side="left")
        return panel

    def _transform_tell_results(self, panel, batch: bool) -> None:
        originals = list(self.batch_models) if batch else [item for item in self.loaded_models if item.model is self.current_model]
        rows = [(result, choice.get()) for result, choice in panel._tell_rows]
        if not originals:
            self._show_error("Deepening", "No saved model is selected.")
            return
        if not any(decision == "Yes" for _, decision in rows):
            self._show_information("Deepening", "Nothing to transform: all rows are set to No.")
            return
        def work(progress):
            return save_deepened_models(self._database, self.loaded_models, originals, rows, batch, LoadedModel, progress)
        def finished(result):
            saved, unavailable, selected_count = result
            message = f"{unavailable} of {selected_count} changes not available yet."
            if saved:
                message += f" Saved {len(saved)} model(s)."
            self._show_information("Deepening", message)
        self._run_model_task(len(originals), "Transforming models...", work, finished,
                             lambda error: self._show_error("Deepening failed", str(error)))

    def _export_tell_results(self, panel, batch: bool) -> None:
        path = filedialog.asksaveasfilename(parent=self, title="Export analysis table",
                                             defaultextension=".csv", filetypes=[("CSV files", "*.csv")])
        if not path:
            return
        rows = [(result, choice.get()) for result, choice in panel._tell_rows]
        try:
            export_tell_table(path, rows, batch)
        except (OSError, csv.Error) as error:
            self._show_error("Export CSV", str(error))
        else:
            self._show_information("Export CSV", f"Table exported to:\n{path}")

    def _add_export_without_check_button(self, actions) -> None:
        """Add the unchecked XML export action to an action bar."""
        ctk.CTkButton(
            actions, text="Export without check", width=190, height=42,
            corner_radius=8, fg_color="#FFFFFF", hover_color="#FFF1E3",
            border_width=1, border_color="#D18132", text_color="#9A4C00",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            command=self._export_without_check,
        ).grid(row=0, column=4, sticky="e", padx=(10, 0))

    def _export_without_check(self) -> None:
        """Export XML after confirming that constraints are not checked."""
        if self.current_model is None:
            self._show_information("Export Model", "Create or open a model before exporting.")
            return
        if messagebox.askokcancel(
            "Export without check",
            "The model is exported without constraint check and may not be valid.",
            icon="warning", parent=self,
        ):
            self._export_current_xml_model()

    def _check_current_constraints(self) -> None:
        """Check the current model and show whether BaseMLM constraints are valid."""
        if self.current_model is None:
            self._show_information(
                "Check Constraints",
                "Create or open a model before checking constraints.",
            )
            return

        model = self.current_model

        def checked(violations):
            if not violations:
                self._show_information("Check Constraints", "The model is valid according to the constraints.")
            else:
                details = "\n".join(f"- {violation}" for violation in violations)
                self._show_warning("Check Constraints",
                                   "The model is not valid. The following constraints are violated:\n\n" + details)

        def failed(error):
            self._show_warning("Check Constraints",
                               "The model could not be checked. "
                               "It remains saved, but export is blocked until the constraint check succeeds.\n\n"
                               + str(error))
        self._run_model_task(1, "Checking constraints...",
                             lambda _progress: model.validate_basemlm_integrity(), checked, failed)

    def _export_current_model_placeholder(self):
        """Export the current model only when all constraints are satisfied."""
        if self.current_model is None:
            self._show_information("Export Model", "Create or open a model before exporting.")
            return

        model = self.current_model

        def checked(violations):
            if violations:
                details = "\n".join(f"- {violation}" for violation in violations)
                self._show_warning("Export Model", "The model cannot be exported because it is not valid.\n\n" + details)
                return
            file_type = (self.current_file_type or os.path.splitext(self.current_file_path or "")[1].lstrip(".")).upper()
            if file_type in ("XML", PlantUmlImporter.FORMAT_NAME.upper(), EcoreImporter.FORMAT_NAME.upper(), XmiImporter.FORMAT_NAME.upper()):
                self._export_current_xml_model()
            elif file_type == "CSV":
                self._export_current_csv_model()
            else:
                self._show_error("Export Model", "Only CSV and FMMLx models can be exported.")
        def failed(error):
            self._show_warning("Check Constraints", "The model could not be checked. It remains saved, "
                                                    "but export is blocked until the constraint check succeeds.\n\n"
                               + str(error))
        self._run_model_task(1, "Checking constraints...", lambda _progress: model.validate_basemlm_integrity(), checked, failed)

    def _export_current_xml_model(self):
        """
        Saves the currently loaded model as a newly generated XML file.

        Export uses the model already loaded in memory, so the original file
        may have been moved or deleted. Its path is only used to suggest a
        filename in the save dialog. If no path is set, "model.xml" is suggested.
        This file does not need to exist; export creates it at the chosen path.

        The model's internal project path (e.g. "Root::MyModel") is kept
        so classes, slots, links, and diagram references remain valid.
        """
        if self.current_model is None:
            self._show_error("Export Model", "No model is loaded.")
            return
        export_options = self._ask_instances_per_class()
        if export_options is None:
            return
        instances_per_class, diagram_mode = export_options
        # Suggest the name of the source file as XML, or "model.xml" if no source path is set.
        # The export creates the file after the user chooses where to save it.
        source_name = "model.xml"
        if self.current_file_path:
            source_stem = os.path.splitext(os.path.basename(self.current_file_path))[0]
            if source_stem:
                source_name = f"{source_stem}.xml"
        target_path = self._ask_save_file(
            title="Export Model",
            initial_file=source_name,
            default_extension=".xml",
            file_types=[("FMMLx files", "*.xml"), ("All files", "*.*")],
        )
        if not target_path:
            return
        model = self.current_model
        self._run_model_task(1, "Exporting model...",
                             lambda _progress: model.export_xml(target_path, project_name=model.path_name,
                                                                max_instances_per_class=instances_per_class,
                                                                diagram_mode=diagram_mode),
                             lambda _result: self._show_information("Export Model", f"Model exported to:\n{target_path}"),
                             lambda error: self._show_error("Export Model", f"Could not export FMMLx: {error}"))

    def _ask_instances_per_class(self):
        """
        Shows the instance-limit question in the same style as the main tool.

        The dialog accepts whole numbers from zero upward. Closing it or using
        Cancel returns no value and stops the export without creating a file.
        The completed dialog is centered inside the current application window.
        """
        result = {"value": None}
        dialog = ctk.CTkToplevel(self)
        dialog.title("Export Model")
        dialog.geometry("500x410")
        dialog.resizable(False, False)
        dialog.transient(self)
        dialog.grab_set()
        dialog.configure(fg_color=self.colors["app_bg"])
        dialog.grid_columnconfigure(0, weight=1)
        self._apply_logo_to_export_dialog(dialog)

        ctk.CTkLabel(
            dialog,
            text="Export Model",
            anchor="w",
            text_color=self.colors["text"],
            font=ctk.CTkFont(family="Segoe UI", size=20, weight="bold"),
        ).grid(row=0, column=0, sticky="ew", padx=28, pady=(26, 8))
        ctk.CTkLabel(
            dialog,
            text="Choose the diagram type and how many Level 0 instances\nshould be exported per class.",
            anchor="w",
            justify="left",
            text_color=self.colors["muted"],
            font=ctk.CTkFont(family="Segoe UI", size=13),
        ).grid(row=1, column=0, sticky="ew", padx=28, pady=(0, 14))

        ctk.CTkLabel(
            dialog,
            text="Diagram type",
            anchor="w",
            text_color=self.colors["text"],
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
        ).grid(row=2, column=0, sticky="ew", padx=28, pady=(0, 6))
        diagram_var = tk.StringVar(value="both")
        diagram_row = ctk.CTkFrame(dialog, fg_color="transparent")
        diagram_row.grid(row=3, column=0, sticky="ew", padx=28)
        diagram_row.grid_columnconfigure((0, 1, 2), weight=1)
        diagram_buttons = {}

        def select_diagram_mode(value):
            """Highlights the diagram type that will be included in the XML."""
            diagram_var.set(value)
            for button_value, button in diagram_buttons.items():
                selected = button_value == value
                button.configure(
                    fg_color=self.colors["primary"] if selected else "#FFFFFF",
                    hover_color=self.colors["primary_hover"] if selected else self.colors["surface_alt"],
                    text_color="#FFFFFF" if selected else self.colors["text"],
                    border_color=self.colors["primary"] if selected else self.colors["border"],
                )

        for column, (label, value) in enumerate((("FMMLx", "fmmlx"), ("UML++", "uml"), ("Both", "both"))):
            button = ctk.CTkButton(
                diagram_row, text=label, height=40, corner_radius=8, border_width=1,
                font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
                command=lambda selected_value=value: select_diagram_mode(selected_value),
            )
            button.grid(row=0, column=column, sticky="ew", padx=4)
            diagram_buttons[value] = button
        select_diagram_mode("both")

        ctk.CTkLabel(
            dialog,
            text="Instances per class (0 exports classes only)",
            anchor="w",
            text_color=self.colors["text"],
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
        ).grid(row=4, column=0, sticky="ew", padx=28, pady=(18, 6))
        value_var = tk.StringVar(value="0")
        value_entry = ctk.CTkEntry(
            dialog,
            textvariable=value_var,
            height=42,
            corner_radius=8,
            border_color=self.colors["border"],
            fg_color="#FFFFFF",
            text_color=self.colors["text"],
            font=ctk.CTkFont(family="Segoe UI", size=14),
        )
        value_entry.grid(row=5, column=0, sticky="ew", padx=28)
        error_label = ctk.CTkLabel(
            dialog,
            text="",
            anchor="w",
            text_color="#dc2626",
            font=ctk.CTkFont(family="Segoe UI", size=12),
        )
        error_label.grid(row=6, column=0, sticky="ew", padx=28, pady=(4, 0))

        button_row = ctk.CTkFrame(dialog, fg_color="transparent")
        button_row.grid(row=7, column=0, sticky="e", padx=28, pady=(14, 24))

        def confirm():
            """Accepts the entry only when it is a whole number of zero or more."""
            try:
                value = int(value_var.get().strip())
            except ValueError:
                error_label.configure(text="Please enter a whole number.")
                return
            if value < 0:
                error_label.configure(text="The number cannot be negative.")
                return
            result["value"] = value, diagram_var.get()
            dialog.destroy()

        ctk.CTkButton(
            button_row,
            text="Cancel",
            width=105,
            height=38,
            corner_radius=8,
            fg_color="#FFFFFF",
            hover_color=self.colors["surface_alt"],
            border_width=1,
            border_color=self.colors["border"],
            text_color=self.colors["text"],
            command=dialog.destroy,
        ).grid(row=0, column=0, padx=(0, 10))
        ctk.CTkButton(
            button_row,
            text="Continue",
            width=115,
            height=38,
            corner_radius=8,
            fg_color=self.colors["primary"],
            hover_color=self.colors["primary_hover"],
            text_color="#FFFFFF",
            command=confirm,
        ).grid(row=0, column=1)

        dialog.bind("<Return>", lambda _event: confirm())
        dialog.bind("<Escape>", lambda _event: dialog.destroy())
        self._overlay.cover(dialog)
        dialog.after(100, value_entry.focus_set)
        self.wait_window(dialog)
        return result["value"]

    def _apply_logo_to_export_dialog(self, dialog):
        """Uses Logo.png after CustomTkinter has finished creating a dialog."""
        logo_path = os.path.join(os.path.dirname(__file__), "Logo.png")
        if not os.path.exists(logo_path):
            return
        try:
            dialog.logo_icon_image = tk.PhotoImage(file=logo_path)
            dialog.iconphoto(False, dialog.logo_icon_image)
            dialog.after(
                300,
                lambda: dialog.iconphoto(False, dialog.logo_icon_image)
                if dialog.winfo_exists() else None,
            )
        except tk.TclError:
            dialog.logo_icon_image = None

    def _ask_csv_export_options(self):
        """
        Asks for the CSV model's target format and number of instances.

        CSV keeps the selected columns and limits its data rows. XML uses the
        same complete model exporter as an imported XML model. Zero produces
        either a header-only CSV or an XML containing only its model class.
        The completed dialog is centered inside the current tool window.
        """
        result = {"value": None}
        dialog = ctk.CTkToplevel(self)
        dialog.title("Export Model")
        dialog.geometry("500x500")
        dialog.resizable(False, False)
        dialog.transient(self)
        dialog.grab_set()
        dialog.configure(fg_color=self.colors["app_bg"])
        dialog.grid_columnconfigure(0, weight=1)
        self._apply_logo_to_export_dialog(dialog)

        ctk.CTkLabel(
            dialog,
            text="Export Model",
            anchor="w",
            text_color=self.colors["text"],
            font=ctk.CTkFont(family="Segoe UI", size=20, weight="bold"),
        ).grid(row=0, column=0, sticky="ew", padx=28, pady=(26, 8))
        ctk.CTkLabel(
            dialog,
            text="Choose the file format and the maximum number of Level 0\ninstances exported from the CSV model.",
            anchor="w",
            justify="left",
            text_color=self.colors["muted"],
            font=ctk.CTkFont(family="Segoe UI", size=13),
        ).grid(row=1, column=0, sticky="ew", padx=28, pady=(0, 18))

        ctk.CTkLabel(
            dialog,
            text="File format",
            anchor="w",
            text_color=self.colors["text"],
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
        ).grid(row=2, column=0, sticky="ew", padx=28, pady=(0, 6))
        format_var = tk.StringVar(value="CSV")
        format_row = ctk.CTkFrame(dialog, fg_color="transparent")
        format_row.grid(row=3, column=0, sticky="ew", padx=28)
        format_row.grid_columnconfigure((0, 1), weight=1)
        format_buttons = {}

        def select_format(value):
            """Highlights the selected format with readable white text."""
            format_var.set(value)
            for button_value, button in format_buttons.items():
                selected = button_value == value
                button.configure(
                    fg_color=self.colors["primary"] if selected else "#FFFFFF",
                    hover_color=self.colors["primary_hover"] if selected else self.colors["surface_alt"],
                    text_color="#FFFFFF" if selected else self.colors["text"],
                    border_color=self.colors["primary"] if selected else self.colors["border"],
                )

        for column, value in enumerate(("CSV", "XML")):
            button = ctk.CTkButton(
                format_row,
                text="FMMLx" if value == "XML" else value,
                height=42,
                corner_radius=8,
                border_width=1,
                font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
                command=lambda selected_value=value: select_format(selected_value),
            )
            button.grid(row=0, column=column, sticky="ew", padx=(0, 4) if column == 0 else (4, 0))
            format_buttons[value] = button
        select_format("CSV")

        ctk.CTkLabel(
            dialog,
            text="FMMLx Diagram Type",
            anchor="w",
            text_color=self.colors["text"],
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
        ).grid(row=4, column=0, sticky="ew", padx=28, pady=(18, 6))
        diagram_var = tk.StringVar(value="both")
        diagram_row = ctk.CTkFrame(dialog, fg_color="transparent")
        diagram_row.grid(row=5, column=0, sticky="ew", padx=28)
        diagram_row.grid_columnconfigure((0, 1, 2), weight=1)
        diagram_buttons = {}

        def select_diagram_mode(value):
            """Highlights the diagram type used when XML is selected."""
            diagram_var.set(value)
            for button_value, button in diagram_buttons.items():
                selected = button_value == value
                button.configure(
                    fg_color=self.colors["primary"] if selected else "#FFFFFF",
                    hover_color=self.colors["primary_hover"] if selected else self.colors["surface_alt"],
                    text_color="#FFFFFF" if selected else self.colors["text"],
                    border_color=self.colors["primary"] if selected else self.colors["border"],
                )

        for column, (label, value) in enumerate((("FMMLx", "fmmlx"), ("UML++", "uml"), ("Both", "both"))):
            button = ctk.CTkButton(
                diagram_row, text=label, height=40, corner_radius=8, border_width=1,
                font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
                command=lambda selected_value=value: select_diagram_mode(selected_value),
            )
            button.grid(row=0, column=column, sticky="ew", padx=4)
            diagram_buttons[value] = button
        select_diagram_mode("both")

        ctk.CTkLabel(
            dialog,
            text="Instances per class",
            anchor="w",
            text_color=self.colors["text"],
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
        ).grid(row=6, column=0, sticky="ew", padx=28, pady=(18, 6))
        value_var = tk.StringVar(value="0")
        value_entry = ctk.CTkEntry(
            dialog,
            textvariable=value_var,
            height=42,
            corner_radius=8,
            border_color=self.colors["border"],
            fg_color="#FFFFFF",
            text_color=self.colors["text"],
            font=ctk.CTkFont(family="Segoe UI", size=14),
        )
        value_entry.grid(row=7, column=0, sticky="ew", padx=28)
        error_label = ctk.CTkLabel(
            dialog,
            text="",
            anchor="w",
            text_color=self.colors["danger"],
            font=ctk.CTkFont(family="Segoe UI", size=12),
        )
        error_label.grid(row=8, column=0, sticky="ew", padx=28, pady=(4, 0))

        button_row = ctk.CTkFrame(dialog, fg_color="transparent")
        button_row.grid(row=9, column=0, sticky="e", padx=28, pady=(12, 24))

        def confirm():
            """Accepts a supported format and a non-negative whole number."""
            try:
                instance_limit = int(value_var.get().strip())
            except ValueError:
                error_label.configure(text="Please enter a whole number.")
                return
            if instance_limit < 0:
                error_label.configure(text="The number cannot be negative.")
                return
            result["value"] = format_var.get(), instance_limit, diagram_var.get()
            dialog.destroy()

        ctk.CTkButton(
            button_row,
            text="Cancel",
            width=105,
            height=38,
            corner_radius=8,
            fg_color="#FFFFFF",
            hover_color=self.colors["surface_alt"],
            border_width=1,
            border_color=self.colors["border"],
            text_color=self.colors["text"],
            command=dialog.destroy,
        ).grid(row=0, column=0, padx=(0, 10))
        ctk.CTkButton(
            button_row,
            text="Continue",
            width=115,
            height=38,
            corner_radius=8,
            fg_color=self.colors["primary"],
            hover_color=self.colors["primary_hover"],
            text_color="#FFFFFF",
            command=confirm,
        ).grid(row=0, column=1)

        dialog.bind("<Return>", lambda _event: confirm())
        dialog.bind("<Escape>", lambda _event: dialog.destroy())
        self._overlay.cover(dialog)
        dialog.after(100, value_entry.focus_set)
        self.wait_window(dialog)
        return result["value"]

    def _export_current_csv_model(self):
        """Exports an imported CSV model as a limited CSV or XML document."""
        if not self.current_file_path or not os.path.exists(self.current_file_path):
            self._show_error("Export Model", "The source CSV file is missing.")
            return
        selected_columns = self.current_selected_columns or [
            column
            for column, selected in self.selected_csv_columns.items()
            if selected.get()
        ]
        if not selected_columns:
            self._show_error("Export Model", "No CSV columns were selected.")
            return
        export_options = self._ask_csv_export_options()
        if export_options is None:
            return
        export_format, instances_per_class, diagram_mode = export_options
        extension = export_format.lower()
        source_name = os.path.splitext(os.path.basename(self.current_file_path))[0] + f".{extension}"
        target_path = self._ask_save_file(
            title="Export Model",
            initial_file=source_name,
            default_extension=f".{extension}",
            file_types=[(f"{self._display_file_type(export_format)} files", f"*.{extension}"), ("All files", "*.*")],
        )
        if not target_path:
            return
        model = self.current_model
        source_path = self.current_file_path
        def export(_progress):
            if export_format == "XML":
                model.export_xml(target_path, project_name=model.path_name,
                                 max_instances_per_class=instances_per_class, diagram_mode=diagram_mode)
            else:
                self._write_selected_csv_columns(source_path, target_path, selected_columns,
                                                 max_instances=instances_per_class)
        self._run_model_task(1, "Exporting model...", export,
                             lambda _result: self._show_information("Export Model", f"Model exported to:\n{target_path}"),
                             lambda error: self._show_error("Export Model", f"Could not export {self._display_file_type(export_format)}: {error}"))

    def _write_selected_csv_columns(self, source_path: str, target_path: str,
                                    selected_columns: List[str], max_instances: Optional[int] = None):
        """Writes selected columns and at most the requested number of data rows."""
        with open(source_path, "r", newline="", encoding="utf-8-sig") as source_file:
            dialect = self._detect_csv_dialect(source_file)
            reader = csv.reader(source_file, dialect, skipinitialspace=True)
            rows = [[value.strip().strip('"') for value in row] for row in reader if row]
        if not rows:
            raise ValueError("CSV file is empty.")
        header = rows[0]
        selected_indexes = []
        missing_columns = []
        for selected_column in selected_columns:
            try:
                selected_indexes.append(header.index(selected_column))
            except ValueError:
                missing_columns.append(selected_column)
        if missing_columns:
            raise ValueError(f"Selected columns were not found: {missing_columns}")
        with open(target_path, "w", newline="", encoding="utf-8-sig") as target_file:
            writer = csv.writer(target_file, dialect)
            rows_to_write = rows if max_instances is None else rows[:max_instances + 1]
            for row in rows_to_write:
                writer.writerow([
                    row[index] if index < len(row) else ""
                    for index in selected_indexes
                ])
        os.utime(target_path, None)

    def _export_all_models(self) -> None:
        """Select models and export them to a single chosen directory."""
        self._select_models_for_batch(inspect=False)

    def _inspect_all_models(self) -> None:
        self._select_models_for_batch(inspect=True)

    def _select_models_for_batch(self, inspect: bool) -> None:
        title = "Inspect All" if inspect else "Export All"
        if not self.loaded_models:
            self._show_information(title, "There are no models to select.")
            return
        dialog = _styled_dialog(self, title)
        _dialog_heading(dialog, "Select Models to Inspect" if inspect else "Select Models to Export", self.colors)
        listing = VirtualModelSelector(dialog, self.loaded_models, self.colors)
        listing.pack(fill="both", expand=True, padx=18, pady=(6, 10))
        run_check = tk.BooleanVar(master=dialog, value=True)
        if not inspect:
            _dialog_checkbox(dialog, "Run Constraint Check", run_check, self.colors).pack(anchor="w", padx=18, pady=(0, 10))
        row = ctk.CTkFrame(dialog, fg_color="transparent")
        row.pack(fill="x", padx=18, pady=(8, 18))
        dialog._progress_anchor = row
        def close_dialog():
            _cancel_widget_timers(dialog)
            dialog.destroy()

        def start():
            selected_models = listing.selected_models()
            if not selected_models:
                messagebox.showwarning(title, "Select at least one model.", parent=dialog)
                return
            if inspect:
                def prepared(result):
                    if hasattr(self, "_batch_tabs"):
                        self._new_batch_tab(selected_models)
                    else:
                        self.batch_models = selected_models
                        self.batch_tab.grid()
                    close_dialog()
                    self._render_batch_page(*result)
                self._run_model_task(len(selected_models), "Preparing models...",
                                     lambda progress: self._prepare_batch_page(selected_models, progress),
                                     prepared, lambda error: self._show_error("Inspect All", str(error)),
                                     dialog=dialog)
                return
            if not run_check.get():
                export_to_folder(selected_models)
                return

            def checked(result):
                passed, failures = result
                if not failures:
                    export_to_folder(passed)
                elif self._ask_export_check_result(len(passed), failures):
                    export_to_folder(passed, len(failures))

            # All selected models are checked before anything is exported.
            self._run_model_task(len(selected_models), "Checking constraints...",
                                 lambda progress: check_models(selected_models, progress),
                                 checked, lambda error: self._show_error("Export All", str(error)), dialog=dialog)

        def export_to_folder(models, not_valid=0):
            """Choose the export folder and export the models without checking them again."""
            directory = filedialog.askdirectory(parent=self, title="Choose export folder")
            if not directory:
                return
            def exported(results):
                close_dialog()
                failures = [(name, error) for name, _, error in results if error is not None]
                text = f"Successful: {len(results) - len(failures)}\nFailed: {len(failures)}"
                if not_valid:
                    text += f"\nNot exported (constraint check): {not_valid}"
                if failures:
                    text += "\n\n" + "\n".join(f"{name}: {error}" for name, error in failures)
                self._show_information("Export All", text)

            self._run_model_task(len(models), "Exporting models...",
                                 lambda progress: export_models(models, directory, True, progress),
                                 exported, lambda error: self._show_error("Export All", str(error)), dialog=dialog)

        _dialog_primary_button(row, "Inspect" if inspect else "Export", start, self.colors).pack(side="right")
        _dialog_plain_button(row, "Cancel", close_dialog, self.colors).pack(side="right", padx=(0, 8))
        dialog.bind("<Return>", lambda _event: start())
        dialog.bind("<Escape>", lambda _event: close_dialog())
        self._overlay.cover(dialog)
        dialog.grab_set()
        self.wait_window(dialog)

    def _ask_export_check_result(self, passed: int, failures: list[tuple[str, str]]) -> bool:
        """Show the constraint check result of Export All; True exports the valid models."""
        result = False
        previous_grab = self.grab_current()
        dialog = _styled_dialog(self, "Constraint Check")
        _add_dialog_heading(dialog, "Constraint Check", self.colors)
        ctk.CTkLabel(dialog, text=f"Passed: {passed}\nFailed: {len(failures)}", justify="left", anchor="w",
                     text_color=self.colors["text"], font=ctk.CTkFont(family=FONT_FAMILY, size=13)).pack(
                         fill="x", padx=DIALOG_PADDING, pady=(0, 10))
        ctk.CTkLabel(dialog, text="Failed Models", anchor="w", text_color=self.colors["text"],
                     font=ctk.CTkFont(family=FONT_FAMILY, size=14, weight="bold")).pack(
                         fill="x", padx=DIALOG_PADDING, pady=(0, 4))
        failed_list = ctk.CTkTextbox(dialog, width=520, height=180, wrap="word", text_color=self.colors["text"],
                                     font=ctk.CTkFont(family=FONT_FAMILY, size=12))
        failed_list.pack(fill="both", expand=True, padx=DIALOG_PADDING, pady=(0, DIALOG_PADDING))
        failed_list.insert("1.0", "\n".join(f"{name}: {reason}" for name, reason in failures))
        failed_list.configure(state="disabled")
        row = _add_dialog_button_row(dialog)

        def close(accepted: bool) -> None:
            """Close the dialog and remember whether the valid models are exported."""
            nonlocal result
            result = accepted
            _cancel_widget_timers(dialog)
            dialog.destroy()

        export_button = ctk.CTkButton(row, text="Export Valid Models", height=BUTTON_HEIGHT,
                                      fg_color=self.colors["primary"], hover_color=self.colors["primary_hover"],
                                      text_color=WHITE, command=lambda: close(True))
        export_button.pack(side="right")
        if not passed:
            export_button.configure(state="disabled")
        ctk.CTkButton(row, text="Cancel", width=BUTTON_WIDTH, height=BUTTON_HEIGHT, fg_color=WHITE,
                      hover_color=LIGHT_BUTTON_HOVER, border_width=1, border_color=self.colors["border"],
                      text_color=self.colors["text"], command=lambda: close(False)).pack(side="right", padx=(0, 8))
        dialog.protocol("WM_DELETE_WINDOW", lambda: close(False))
        dialog.bind("<Escape>", lambda _event: close(False))
        _show_dialog_and_wait(dialog, self)
        if previous_grab is not None and previous_grab.winfo_exists():
            previous_grab.grab_set()
        return result and passed > 0

    def _show_models_overview_page(self) -> None:
        """Prepare the overview model data before displaying the page."""
        models = list(self.loaded_models)
        def prepare(progress):
            values = {}
            for index, loaded in enumerate(models, 1):
                model = loaded.model
                values[id(loaded)] = (self._count_higher_level_classes(model),
                                      len(model.get_all_flat_classes()),
                                      self._count_attributes(model),
                                      len(model.get_all_pure_objects()))
                progress(index, len(models))
            return values
        def ready(values, release):
            self._overview_model_counts = values
            try:
                self._render_models_overview_page()
            finally:
                release()
        self._run_model_task(len(models), "Loading models...", prepare, ready,
                             lambda error: self._show_error("Models Overview", str(error)), handoff=True)

    @atomic_page
    def _render_models_overview_page(self) -> None:
        """
        Shows the Models Overview page.

        This page lists all imported models, provides filters, shows model
        metrics, and lets the user open or delete a stored model.
        """
        self._hide_workflow_sidebar()
        self._set_top_tab("models")
        self._clear_content()

        header = ctk.CTkFrame(self.content, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 16))
        ctk.CTkLabel(header, text="Models Overview", anchor="w", font=ctk.CTkFont(size=22, weight="bold")).grid(
            row=0, column=0, sticky="w"
        )
        ctk.CTkLabel(
            header,
            text="View and manage all imported or generated models.",
            anchor="w",
            text_color="#64748b",
            font=ctk.CTkFont(size=12),
        ).grid(row=1, column=0, sticky="w", pady=(2, 0))
        # The total lies centered in the free space between the title and the two buttons.
        header.grid_columnconfigure(1, weight=1)
        self.total_models_label = ctk.CTkLabel(
            header, text=f"Total Models: {len(self.loaded_models)}", text_color="#2563EB",
            font=ctk.CTkFont(family="Segoe UI", size=18, weight="bold"),
        )
        self.total_models_label.grid(row=0, column=1, rowspan=2)
        for column, (label, command) in enumerate((("Export All", self._export_all_models),
                                                    ("Inspect All", self._inspect_all_models)), start=2):
            ctk.CTkButton(header, text=label, width=130, height=40, corner_radius=7,
                          fg_color=self.colors["primary"], hover_color=self.colors["primary_hover"],
                          text_color="#FFFFFF", font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
                          command=command).grid(row=0, column=column, rowspan=2, padx=16 if column == 2 else 0)

        body = ctk.CTkFrame(self.content, fg_color="transparent")
        body.grid(row=1, column=0, sticky="nsew")
        body.grid_columnconfigure(0, weight=1)
        body.grid_rowconfigure(0, weight=1)

        list_card = self._card(body)
        list_card.grid(row=0, column=0, sticky="nsew")
        list_card.grid_columnconfigure(0, weight=1)
        list_card.grid_rowconfigure(2, weight=1)
        self._card_title(list_card, "Your Models").grid(row=0, column=0, sticky="w", padx=16, pady=(14, 8))

        filters = ctk.CTkFrame(list_card, fg_color="transparent")
        filters.grid(row=1, column=0, sticky="ew", padx=22, pady=(0, 18))
        filters.grid_columnconfigure(1, weight=1)
        filters.grid_columnconfigure(3, weight=0)

        self.models_search_var = tk.StringVar()
        self.models_search_var.trace_add("write", lambda *_args: self._populate_models_table())
        ctk.CTkLabel(filters, text="Search", text_color=self.colors["text"], font=ctk.CTkFont(size=12)).grid(row=0, column=0, sticky="w", padx=(0, 14), pady=10)
        ctk.CTkEntry(
            filters,
            textvariable=self.models_search_var,
            placeholder_text="Search Model or File ...",
            placeholder_text_color="#94A3B8",
            height=44,
            corner_radius=7,
            border_color="#CBD8EA",
            fg_color="#FFFFFF",
            font=ctk.CTkFont(size=13),
        ).grid(row=0, column=1, sticky="ew", padx=(0, 44), pady=10)

        self.models_type_filter_var = tk.StringVar(value="All")
        ctk.CTkLabel(filters, text="Type", text_color=self.colors["text"], font=ctk.CTkFont(size=12)).grid(row=0, column=2, sticky="w", padx=(0, 14), pady=10)
        ctk.CTkComboBox(
            filters,
            variable=self.models_type_filter_var,
            values=["All", "FMMLx", "CSV", "PlantUML", "XMI", "Ecore"],
            width=190,
            height=44,
            corner_radius=7,
            fg_color="#FFFFFF",
            button_color="#FFFFFF",
            button_hover_color=self.colors["primary_soft"],
            border_color="#CBD8EA",
            border_width=1,
            text_color=self.colors["text"],
            dropdown_fg_color="#FFFFFF",
            dropdown_hover_color=self.colors["primary_soft"],
            dropdown_text_color=self.colors["text"],
            command=lambda _value: self._populate_models_table(),
            state="readonly",
        ).grid(row=0, column=3, sticky="w", padx=(0, 44), pady=10)

        self.models_min_objects_var = tk.StringVar()
        self.models_min_attributes_var = tk.StringVar()
        for var in (self.models_min_objects_var, self.models_min_attributes_var):
            var.trace_add("write", lambda *_args: self._populate_models_table())
        ctk.CTkLabel(filters, text="Min objects", text_color=self.colors["text"], font=ctk.CTkFont(size=12)).grid(row=0, column=4, sticky="w", padx=(0, 14), pady=10)
        ctk.CTkEntry(filters, textvariable=self.models_min_objects_var, placeholder_text="e.g. 100", width=116, height=44, corner_radius=7, border_color="#CBD8EA", fg_color="#FFFFFF").grid(row=0, column=5, sticky="w", padx=(0, 44), pady=10)
        ctk.CTkLabel(filters, text="Min attributes", text_color=self.colors["text"], font=ctk.CTkFont(size=12)).grid(row=0, column=6, sticky="w", padx=(0, 14), pady=10)
        ctk.CTkEntry(filters, textvariable=self.models_min_attributes_var, placeholder_text="e.g. 10", width=116, height=44, corner_radius=7, border_color="#CBD8EA", fg_color="#FFFFFF").grid(row=0, column=7, sticky="w", padx=(0, 0), pady=10)

        self.models_table_wrapper = ctk.CTkFrame(
            list_card,
            fg_color="#FFFFFF",
            corner_radius=0,
            border_width=0,
        )
        self.models_table_wrapper.grid(row=2, column=0, sticky="nsew", padx=22, pady=(0, 22))
        self.models_table_wrapper.grid_columnconfigure(0, weight=1)
        self.models_table_wrapper.grid_rowconfigure(0, weight=1)

        self.models_canvas = tk.Canvas(
            self.models_table_wrapper,
            background="#FFFFFF",
            highlightthickness=0,
            bd=0,
        )
        self.models_canvas.grid(row=0, column=0, sticky="nsew")
        self.models_scrollbar = ctk.CTkScrollbar(
            self.models_table_wrapper,
            orientation="vertical",
            command=self.models_canvas.yview,
            width=14,
            button_color="#AFCBFF",
            button_hover_color=self.colors["primary"],
        )
        self.models_scrollbar.grid(row=0, column=1, sticky="ns", padx=(4, 0))
        self.models_canvas.configure(
            yscrollcommand=self._on_models_canvas_scroll,
        )
        ModelDeepenerApp._bind_table_wheel(self.models_canvas, self.models_canvas)
        self.models_canvas.bind("<Destroy>", self._cancel_models_canvas_redraw, add="+")
        self.models_canvas.bind("<Enter>", self._bind_models_scroll_events)
        self.models_canvas.bind("<Leave>", self._unbind_models_scroll_events)
        self.models_canvas.bind("<Configure>", lambda _event: self._populate_models_table())

        self._populate_models_table()

    def _select_example_file(self):
        """
        Opens the Select Example dialog.

        The example tree includes CSV, XML, PlantUML, Ecore and XMI models.
        """
        roots = [("CSV", os.path.join(PROJECT_FOLDER_PATH, "models", "csv")),
                 ("FMMLx", os.path.join(PROJECT_FOLDER_PATH, "models", "fmmlx")),
                 ("PlantUML", os.path.join(PROJECT_FOLDER_PATH, "models", "plantuml")),
                 ("XMI", os.path.join(PROJECT_FOLDER_PATH, "models", "xmi")),
                 ("Ecore", os.path.join(PROJECT_FOLDER_PATH, "models", "ecore"))]
        examples = [(label, root, self._collect_example_files(root)) for label, root in roots
                    if os.path.isdir(root)]
        if not any(files for _label, _root, folders in examples for _folder, files in folders):
            self._show_information(
                "No examples found",
                "No example files were found in the model example folders.",
            )
            return

        dialog = ctk.CTkToplevel(self)
        dialog.title("Select Example")
        dialog.geometry("620x520")
        dialog.transient(self)
        dialog.grab_set()
        dialog.grid_columnconfigure(0, weight=1)
        dialog.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(
            dialog,
            text="Select an example",
            anchor="w",
            text_color=self.colors["text"],
            font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"),
        ).grid(row=0, column=0, sticky="ew", padx=18, pady=(18, 10))

        tree_frame = ctk.CTkFrame(dialog, fg_color="#FFFFFF", corner_radius=0)
        tree_frame.grid(row=1, column=0, sticky="nsew", padx=18, pady=(0, 14))
        tree_frame.grid_columnconfigure(0, weight=1)
        tree_frame.grid_rowconfigure(0, weight=1)

        tree = self._tree(tree_frame, show="tree")
        tree.grid(row=0, column=0, sticky="nsew")
        scrollbar = ctk.CTkScrollbar(tree_frame, orientation="vertical", command=tree.yview)
        scrollbar.grid(row=0, column=1, sticky="ns", padx=(4, 0))
        tree.configure(yscrollcommand=scrollbar.set)

        path_by_item = {}
        folder_items = set()
        for label, examples_root, example_files in examples:
            root_id = tree.insert("", "end", text=label, open=False)
            folder_items.add(root_id)
            folder_ids = {examples_root: root_id}
            for folder_path, file_names in example_files:
                parent_path = os.path.dirname(folder_path)
                if folder_path == examples_root:
                    folder_id = root_id
                else:
                    parent_id = folder_ids.get(parent_path, root_id)
                    folder_id = tree.insert(parent_id, "end", text=os.path.basename(folder_path), open=False)
                    folder_items.add(folder_id)
                    folder_ids[folder_path] = folder_id
                for file_name in file_names:
                    full_path = os.path.join(folder_path, file_name)
                    item_id = tree.insert(folder_id, "end", text=file_name, open=False)
                    path_by_item[item_id] = full_path

        def choose_selected():
            selected = tree.selection()
            if not selected:
                return
            selected_path = path_by_item.get(selected[0])
            if not selected_path:
                return
            self.file_path_var.set(selected_path)
            self.current_file_path = selected_path
            self._file_selection_mode = "example"
            dialog.destroy()
            self._validate_current_file()
            self._set_file_input_mode("example")

        def toggle_folder(event) -> None:
            item = tree.identify_row(event.y)
            if item in folder_items and tree.identify("element", event.x, event.y) != "Treeitem.indicator":
                tree.item(item, open=not tree.item(item, "open"))

        tree.bind("<ButtonRelease-1>", toggle_folder)
        tree.bind("<Double-1>", lambda _event: choose_selected())

        actions = ctk.CTkFrame(dialog, fg_color="transparent")
        actions.grid(row=2, column=0, sticky="ew", padx=18, pady=(0, 18))
        actions.grid_columnconfigure(0, weight=1)
        ctk.CTkButton(
            actions,
            text="Cancel",
            width=100,
            height=36,
            fg_color="#FFFFFF",
            hover_color="#EEF2F7",
            border_width=1,
            border_color=self.colors["border"],
            text_color=self.colors["text"],
            command=dialog.destroy,
        ).grid(row=0, column=1, padx=(0, 8))
        ctk.CTkButton(
            actions,
            text="Select",
            width=100,
            height=36,
            fg_color=self.colors["primary"],
            hover_color=self.colors["primary_hover"],
            text_color="#FFFFFF",
            command=choose_selected,
        ).grid(row=0, column=2)
        self._overlay.cover(dialog)
        self.wait_window(dialog)

    @staticmethod
    def _collect_example_files(examples_root: str) -> list[tuple[str, list[str]]]:
        """List supported example files by folder while omitting Python cache directories."""
        rows = []
        for folder_path, subfolders, file_names in os.walk(examples_root):
            visible_folders = []
            for folder in subfolders:
                if folder != "__pycache__":
                    visible_folders.append(folder)
            subfolders[:] = sorted(visible_folders)
            supported_files = []
            for file_name in file_names:
                path = os.path.join(folder_path, file_name)
                try:
                    importer_for(path)
                except (OSError, ValueError):
                    continue
                supported_files.append(file_name)
            supported_files.sort()
            if supported_files or folder_path == examples_root:
                rows.append((folder_path, supported_files))
        return rows

    def _build_batch_folder_panel(self, parent) -> None:
        """Build the fixed-height scrollable folder selection."""
        self.batch_folder_panel = ctk.CTkFrame(parent, fg_color="transparent", height=100)
        self.batch_folder_panel.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.batch_folder_panel.grid_propagate(False)
        self.batch_folder_panel.grid_columnconfigure(0, weight=1)
        self.batch_folder_panel.grid_rowconfigure(0, weight=1)
        self.batch_folder_panel.grid_remove()
        self.batch_folder_list = ctk.CTkScrollableFrame(self.batch_folder_panel, height=70, fg_color="#F8FAFC")
        self.batch_folder_list.grid(row=0, column=0, sticky="nsew", padx=(0, 8))

    def _activate_file_input(self, mode: str, callback: Callable[[], None]) -> None:
        """Open the chooser of an input mode; the mode changes only when the chooser selects something."""
        callback()
        self._reset_file_input_hover()

    def _reset_file_input_hover(self) -> None:
        """Remove the hover look that a closed chooser left on the clicked input button.

        CustomTkinter restores the hover color 100 ms after a click. A native file dialog keeps the
        pointer away from the button, so no leave event follows and a cancelled chooser would leave
        the button looking selected.
        """
        x, y = self.winfo_pointerxy()
        under = self.winfo_containing(x, y)
        for button in self._file_input_buttons.values():
            if not button.winfo_exists():
                continue
            button._click_animation_running = False
            inside = under is not None and (str(under) + ".").startswith(str(button) + ".")
            if inside:
                button._on_enter()
            else:
                button._on_leave()

    def _set_file_input_mode(self, mode: str) -> None:
        """Update the selected input button and the adjacent browse action."""
        self._file_input_mode = mode
        for name, button in self._file_input_buttons.items():
            selected = name == mode
            button.configure(fg_color=self.colors["primary"] if selected else self.colors["surface_alt"],
                             hover_color=self.colors["primary_hover"] if selected else "#EEF2F7",
                             text_color="#FFFFFF" if selected else self.colors["text"],
                             border_width=0 if selected else 1,
                             border_color=self.colors["border"],
                             font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold" if selected else "normal"))
        selected = bool(getattr(self, "current_file_path", None)) and getattr(self, "_file_selection_mode", None) == mode
        text = "Add Folder" if mode == "batch" else "Change File" if selected else "Select" if mode == "example" else "Browse..."
        self.file_browse_button.configure(text=text,
                                          command=(self._add_batch_folder if mode == "batch" else
                                                   self._select_example_file if mode == "example" else self._browse_file))

    def _ask_batch_source(self) -> str | None:
        """Ask whether a batch is selected as files or as a folder."""
        dialog = _styled_dialog(self, "Batch Import")
        _dialog_heading(dialog, "Choose What to Import", self.colors)
        row = ctk.CTkFrame(dialog, fg_color="transparent")
        row.pack(fill="x", padx=18, pady=18)
        result = [None]
        def choose(value):
            result[0] = value
            dialog.destroy()
        _dialog_primary_button(row, "Select Files", lambda: choose("files"), self.colors).pack(side="left", padx=(0, 8))
        _dialog_primary_button(row, "Select Folder", lambda: choose("folder"), self.colors).pack(side="left", padx=(0, 8))
        _dialog_plain_button(row, "Cancel", lambda: choose(None), self.colors).pack(side="right")
        dialog.bind("<Escape>", lambda _event: choose(None))
        self._overlay.cover(dialog)
        dialog.grab_set()
        self.wait_window(dialog)
        return result[0]

    @staticmethod
    def _collect_batch_folder(folder: str) -> list[str]:
        """Return supported files in a folder and its subfolders."""
        extensions = {ext.lower() for ext in supported_extensions()}
        paths = []
        for root, directories, files in os.walk(folder):
            directories.sort()
            paths.extend(os.path.join(root, name) for name in sorted(files)
                         if os.path.splitext(name)[1].lower() in extensions)
        return paths

    def _choose_batch_folders(self, title: str) -> list[str]:
        """Choose folders with native multiple selection on Windows."""
        if sys.platform == "win32":
            self.update_idletasks()
            get_parent = ctypes.windll.user32.GetParent
            get_parent.argtypes = [ctypes.c_void_p]
            get_parent.restype = ctypes.c_void_p
            owner = get_parent(self.winfo_id()) or self.winfo_id()
            return choose_windows_folders(owner)
        folder = filedialog.askdirectory(parent=self, title=title)
        return [folder] if folder else []

    def _browse_batch(self) -> None:
        """Select batch files or folders for the import page."""
        choice = self._ask_batch_source()
        if choice is None:
            return
        self._overlay.show()
        try:
            if choice == "folder":
                folders = self._choose_batch_folders("Select Folder")
                paths = None
            else:
                paths = filedialog.askopenfilenames(parent=self, filetypes=self._import_file_types())
                folders = []
        except OSError as error:
            self._show_error("Batch Import", str(error))
            return
        finally:
            self._overlay.hide()
        if folders:
            self._set_file_input_mode("batch")
            self._scan_batch_folders(folders, replace=True)
        elif paths:
            self._set_file_input_mode("batch")
            if len(paths) == 1:
                self.file_path_var.set(paths[0])
                self._validate_current_file()
            else:
                self._select_batch_files(paths)

    def _add_batch_folder(self) -> None:
        """Add folders selected in the native picker."""
        self._overlay.show()
        try:
            folders = self._choose_batch_folders("Add Folder")
        except OSError as error:
            self._show_error("Batch Import", str(error))
            return
        finally:
            self._overlay.hide()
        if folders:
            self._scan_batch_folders(folders)

    def _scan_batch_folders(self, folders: list[str], replace: bool = False) -> None:
        """Find supported files in selected folders before updating the selection."""
        def scan(progress):
            results = []
            for index, folder in enumerate(folders, 1):
                results.append((folder, self._collect_batch_folder(folder)))
                progress(index, len(folders))
            return results
        def selected(results):
            if replace:
                self.current_batch_folders = {}
            for folder, files in results:
                key = os.path.normcase(os.path.abspath(folder))
                self.current_batch_folders[key] = (folder, files)
            self._show_batch_folders()
            if not any(files for _folder, files in results):
                self._show_information("Batch Import", "No supported files were found in the selected folders.")
        self._run_model_task(len(folders), "Finding files...", scan, selected,
                             lambda error: self._show_error("Batch Import", str(error)))

    def _remove_batch_folder(self, key: str) -> None:
        """Remove one folder and update the batch selection."""
        self.current_batch_folders.pop(key, None)
        self._show_batch_folders()

    def _show_batch_folders(self) -> None:
        """Show selected folders and retain each supported file at most once."""
        paths = []
        seen = set()
        for _folder, files in self.current_batch_folders.values():
            for path in files:
                key = os.path.normcase(os.path.abspath(path))
                if key not in seen:
                    seen.add(key)
                    paths.append(path)
        self._select_batch_files(paths, folders=True)
        for child in self.batch_folder_list.winfo_children():
            child.destroy()
        for key, (folder, files) in self.current_batch_folders.items():
            row = ctk.CTkFrame(self.batch_folder_list, fg_color="transparent")
            row.pack(fill="x", pady=2)
            ctk.CTkButton(row, text="x", width=28, height=28, corner_radius=7,
                          fg_color=self.colors["primary_soft"], hover_color=self.colors["primary_soft"],
                          text_color=self.colors["primary"], border_width=1, border_color="#AFCBFF",
                          command=lambda value=key: self._remove_batch_folder(value)).pack(side="right")
            ctk.CTkLabel(row, text=f"{folder}  ({len(files)} files)", anchor="w", justify="left", wraplength=360).pack(
                side="left", fill="x", expand=True, padx=(4, 8))

    def _select_batch_files(self, paths, folder=None, folders=False) -> None:
        self.current_batch_paths = list(paths)
        self.current_file_path = None
        self.csv_preview = None
        self.xml_preview = None
        self.selected_csv_columns.clear()
        self.file_entry.grid_remove()
        if folders:
            self.batch_file_list.grid_remove()
            self.batch_folder_panel.grid()
        else:
            self.current_batch_folders = {}
            self.batch_folder_panel.grid_remove()
            self.batch_file_list.configure(state="normal")
            self.batch_file_list.delete("1.0", "end")
            display = f"{folder}\n{len(paths)} files found" if folder else "\n".join(paths)
            self.batch_file_list.insert("1.0", display)
            self.batch_file_list.configure(state="disabled")
            self.batch_file_list.grid()
        self._set_column_selection_enabled(False)
        self._render_empty_preview("Column selection is only available when importing a single file.")
        self._set_validation_badge_visible(False)
        unsupported = [] if folder or folders else [path for path in paths if self._importer_for_file(path) is None]
        self._set_validation_rows([("Files", str(len(paths))),
                                   ("Status", "Unsupported file type" if unsupported else "Ready to import" if paths else "Select files or folders")])
        self._set_create_button_enabled(bool(paths) and not unsupported)

    def _run_model_task(self, total, message, work, on_success, on_error, dialog=None, handoff=False):
        """Run model work outside Tk and deliver progress and results on the UI thread."""
        if getattr(self, "_model_task_active", False):
            return
        self._model_task_active = True
        blocker = None
        buttons = []
        if dialog is None:
            blocker = tk.Frame(self, width=1, height=1, takefocus=True)
            blocker.place(x=0, y=0)
            blocker.grab_set()
            self._overlay.show()
        else:
            original_close = dialog.protocol("WM_DELETE_WINDOW")
            original_keys = {key: dialog.bind(key) for key in ("<Return>", "<Escape>")}
            dialog.protocol("WM_DELETE_WINDOW", lambda: None)
            for key in original_keys:
                dialog.bind(key, lambda _event: "break")
            def disable_buttons(widget):
                for child in widget.winfo_children():
                    if isinstance(child, ctk.CTkButton):
                        buttons.append((child, child.cget("state")))
                        child.configure(state="disabled")
                    disable_buttons(child)
            disable_buttons(dialog)
        events = queue.Queue()
        worker_done = threading.Event()
        state = {"dialog": None, "count": 0, "done": False, "opening": False, "message": message, "fraction": None}

        def run():
            try:
                result = work(lambda count, size, phase=None, fraction=None: events.put(("progress", count, size, phase, fraction)))
                events.put(("result", result))
            except Exception as error:
                events.put(("error", error))
            finally:
                worker_done.set()

        def show_progress():
            if not state["done"] and not worker_done.is_set():
                state["opening"] = True
                if dialog is None:
                    progress_window = getattr(self, "_model_progress_dialog", None)
                    if progress_window is None or not progress_window.winfo_exists():
                        progress_window = ModelProgressDialog(self, total, state["message"])
                        self._model_progress_dialog = progress_window
                    else:
                        progress_window.prepare(total, state["message"])
                    progress_window.show()
                    state["dialog"] = progress_window
                else:
                    state["dialog"] = InlineModelProgress(dialog, total, state["message"], self.colors)
                state["opening"] = False
                state["dialog"].update_progress(state["count"], total, state["fraction"])

        def poll():
            if state["opening"]:
                self.after(30, poll)
                return
            latest = None
            terminal = None
            try:
                while True:
                    event = events.get_nowait()
                    if event[0] == "progress":
                        latest = event
                    else:
                        terminal = event
                        break
            except queue.Empty:
                pass
            if latest is not None:
                state["count"] = latest[1]
                if latest[3] is not None:
                    state["message"] = latest[3]
                state["fraction"] = latest[4]
                if state["dialog"]:
                    state["dialog"].set_message(state["message"])
                    state["dialog"].update_progress(latest[1], latest[2], latest[4])
            if terminal is None:
                self.after(30, poll)
                return
            state["done"] = True
            self.after_cancel(timer)
            released = [False]
            def release():
                if released[0]:
                    return
                released[0] = True
                if state["dialog"]:
                    if state["dialog"]._indeterminate:
                        state["dialog"].bar.stop()
                    if dialog is None:
                        state["dialog"].hide()
                    else:
                        _cancel_widget_timers(state["dialog"])
                        state["dialog"].destroy()
                if blocker is not None:
                    blocker.grab_release()
                    blocker.destroy()
                    self._overlay.hide()
                else:
                    dialog.protocol("WM_DELETE_WINDOW", original_close)
                    for key, binding in original_keys.items():
                        dialog.tk.call("bind", dialog._w, key, binding)
                    for button, previous in buttons:
                        if button.winfo_exists():
                            button.configure(state=previous)
                self._model_task_active = False
            if handoff and terminal[0] == "result":
                def finish_handoff():
                    if state["dialog"]:
                        state["dialog"].update_progress(total, total, 1.0)
                    release()
                try:
                    on_success(terminal[1], finish_handoff)
                finally:
                    release()
            else:
                release()
                (on_success if terminal[0] == "result" else on_error)(terminal[1])

        timer = self.after(500, show_progress)
        threading.Thread(target=run, daemon=True).start()
        self.after(30, poll)

    def _start_batch_import(self) -> None:
        self._create_batch(list(self.current_batch_paths))

    def _create_batch(self, paths) -> None:
        """Read all candidates, ask once about their reports, then save them together."""
        if hasattr(self, "_batch_tabs"):
            self._save_batch_state()
        self._overlay.show()
        def read(progress):
            candidates = []
            failures = []
            reports = []
            total = len(paths)
            work_units = max(1, 2 * total + 1)
            for index, path in enumerate(paths, 1):
                try:
                    importer = self._importer_for_file(path)
                    if importer is None:
                        raise ValueError(f"Unsupported file: {path}")
                    model, report = importer.import_file(path)
                    if isinstance(importer, XmiImporter) and not model.get_objects():
                        raise ValueError("No objects found")
                    candidates.append((path, importer, model, report))
                except Exception as error:
                    failures.append((path, str(error) or type(error).__name__))
                progress(index, total, "Importing models...", index / work_units)
            for index, (path, _importer, _model, report) in enumerate(candidates, 1):
                visible = visible_import_report(report)
                if visible.has_problems():
                    reports.append((os.path.basename(path), visible))
                progress(index, total, "Preparing report...", (total + index) / work_units)
            summary = batch_problem_summary(reports, failures)
            rows = batch_report_rows(reports)
            failure_text = "\n".join(f"{name}: {reason}" for name, reason in failures)
            progress(total, total, "Preparing report...", (2 * total) / work_units)
            return candidates, failures, reports, summary, rows, failure_text

        def failed(error):
            try:
                self._show_error("Batch import failed", str(error))
            finally:
                self._overlay.hide()

        def read_done(result, release):
            candidates, failures, reports, summary, rows, failure_text = result
            if reports or failures:
                accepted = self._ask_batch_problems(reports, failures, prepared_summary=summary,
                                                    prepared_rows=rows, prepared_failure_text=failure_text,
                                                    on_visible=release)
            else:
                release()
                accepted = True
            if not accepted or not candidates:
                self._overlay.hide()
                return

            def saved(_result):
                if hasattr(self, "_batch_tabs"):
                    self._new_batch_tab(self.batch_models, preserve_current=False)
                else:
                    self.batch_tab.grid()
                self._show_batch_page()
                self._overlay.hide()

            self._run_model_task(len(candidates), "Saving models...",
                                 lambda progress: self._store_batch(candidates, progress), saved, failed)

        self._run_model_task(len(paths), "Importing models...", read, read_done, failed, handoff=True)

    def _ask_batch_problems(self, reports, failures=(), prepared_summary=None, prepared_rows=None,
                            prepared_failure_text=None, on_visible=None) -> bool:
        if prepared_summary is None:
            reports = [(name, visible_import_report(report)) for name, report in reports]
            reports = [(name, report) for name, report in reports if report.has_problems()]
            prepared_summary = batch_problem_summary(reports, failures)
        if prepared_rows is None:
            prepared_rows = batch_report_rows(reports)
        if prepared_failure_text is None:
            prepared_failure_text = "\n".join(f"{name}: {reason}" for name, reason in failures)
        if not reports and not failures:
            return True
        dialog = _styled_dialog(self, "Import Problems", resizable=True)
        dialog.withdraw()
        scaling = ctk.ScalingTracker.get_window_scaling(dialog)
        screen_width = max(1, int((dialog.winfo_screenwidth() - 40) / scaling))
        screen_height = max(1, int((dialog.winfo_screenheight() - 80) / scaling))
        width = min(800, screen_width)
        collapsed_height = min(460 if failures else 360, screen_height)
        dialog.minsize(min(760, screen_width), min(440 if failures else 340, screen_height))
        dialog.maxsize(screen_width, screen_height)
        dialog.geometry(f"{width}x{collapsed_height}")
        _dialog_heading(dialog, "Import Problems", self.colors)
        ctk.CTkLabel(dialog, text="Summary", anchor="w",
                     text_color=self.colors["muted"], font=ctk.CTkFont(family="Segoe UI", size=13)).pack(
                         fill="x", padx=18, pady=(0, 10))
        summary = ctk.CTkTextbox(dialog, width=680, height=90 if failures else 160, wrap="word", text_color=self.colors["text"],
                                 font=ctk.CTkFont(family="Segoe UI", size=13))
        summary.pack(fill="both", padx=18)
        summary.insert("1.0", "\n".join(prepared_summary))
        summary.configure(state="disabled")
        if failures:
            ctk.CTkLabel(dialog, text="Could Not Be Imported", anchor="w", text_color=self.colors["text"],
                         font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold")).pack(fill="x", padx=18, pady=(8, 2))
            failed_list = ctk.CTkTextbox(dialog, width=680, height=85, wrap="word", text_color=self.colors["text"],
                                          font=ctk.CTkFont(family="Segoe UI", size=12))
            failed_list.pack(fill="x", padx=18)
            failed_list.insert("1.0", prepared_failure_text)
            failed_list.configure(state="disabled")
        status = ctk.CTkLabel(dialog, text="", anchor="w", text_color=self.colors["muted"],
                              font=ctk.CTkFont(family="Segoe UI", size=12))
        status.pack(side="bottom", fill="x", padx=18, pady=(0, 4))
        row = ctk.CTkFrame(dialog, fg_color="transparent")
        row.pack(side="bottom", fill="x", padx=18, pady=(8, 18))
        details_panel = ctk.CTkFrame(dialog, fg_color="transparent")
        ctk.CTkLabel(details_panel, text="Details per Model", anchor="w", text_color=self.colors["text"],
                     font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold")).pack(fill="x", pady=(8, 4))
        details = BatchProblemDetails(details_panel, reports, self.colors, prepared=True, initial_rows=prepared_rows)
        details.pack(fill="x")
        result = [False]
        def finish(accepted):
            result[0] = accepted
            _cancel_widget_timers(dialog)
            dialog.destroy()
        def toggle_details():
            if details_panel.winfo_manager():
                details_panel.pack_forget()
                details_button.configure(text="Show Details")
                dialog.geometry(f"{width}x{collapsed_height}")
                dialog.update_idletasks()
                center_popup(dialog, self)
            else:
                details_panel.pack(fill="x", padx=18, pady=(0, 4))
                details_button.configure(text="Hide Details")
                dialog.geometry(f"{min(screen_width, max(width, dialog.winfo_width()))}x{min(screen_height, 620 if failures else 520)}")
                dialog.update_idletasks()
                center_popup(dialog, self)
        def export_list():
            path = filedialog.asksaveasfilename(parent=self, title="Export Problem List (CSV)",
                                                 initialfile="import_problems.csv", defaultextension=".csv",
                                                 filetypes=[("CSV files", "*.csv"), ("All files", "*.*")])
            if not path:
                return
            try:
                write_batch_problem_list(path, reports, failures)
            except (OSError, csv.Error) as error:
                status.configure(text=f"The list could not be saved: {error}")
            else:
                status.configure(text=f"List saved: {path}")
        details_button = _dialog_plain_button(row, "Show Details", toggle_details, self.colors)
        details_button.pack(side="left")
        _dialog_plain_button(row, "Export Problem List (CSV)", export_list, self.colors).pack(side="left", padx=(8, 0))
        _dialog_primary_button(row, "Continue Import", lambda: finish(True), self.colors).pack(side="right")
        _dialog_plain_button(row, "Cancel Import", lambda: finish(False), self.colors).pack(side="right", padx=(0, 8))
        dialog.bind("<Return>", lambda _event: finish(True))
        dialog.bind("<Escape>", lambda _event: finish(False))
        dialog.protocol("WM_DELETE_WINDOW", lambda: finish(False))
        if on_visible is not None:
            on_visible()
        self._overlay.cover(dialog)
        def show_dialog():
            dialog.update_idletasks()
            dialog.deiconify()
            dialog.update_idletasks()
            center_popup(dialog, self)
            dialog.lift()
            dialog.focus_force()
            dialog.grab_set()
        dialog.after(50, show_dialog)
        dialog.wait_visibility()
        self.wait_window(dialog)
        return result[0]

    def _store_batch(self, candidates, progress=None) -> None:
        """Commit the complete batch once, removing staged objects if saving fails."""
        staged = []
        used = {item.name for item in self.loaded_models}
        next_numbers = {}
        try:
            for index, (path, importer, model, _report) in enumerate(candidates, 1):
                source_file = os.path.basename(path)
                base_name = model.path_name.split("::")[-1] if model.path_name else os.path.splitext(source_file)[0]
                name, number = base_name, next_numbers.get(base_name, 2)
                while name in used:
                    name = f"{base_name} ({number})"
                    number += 1
                next_numbers[base_name] = number
                used.add(name)
                loaded = LoadedModel(name=name, source_file=source_file, file_type=importer.FORMAT_NAME.upper(),
                                     model=model, source_path=path,
                                     selected_columns=CsvReader(path).get_header() if isinstance(importer, CsvImporter) else [],
                                     uploaded=datetime.now().strftime("%Y-%m-%d %H:%M"),
                                     last_worked_on=self._current_timestamp_text(), last_action=self.ACTION_TITLES[2])
                self._database.store(loaded)
                staged.append(loaded)
                if progress:
                    progress(index, len(candidates), "Preparing models...", 0.5 * index / len(candidates))
            if progress:
                progress(len(candidates), len(candidates), "Writing database...", 0.5)
            self._database.commit()
            if progress:
                progress(len(candidates), len(candidates), "Writing database...", 1.0)
        except Exception:
            for loaded in staged:
                self._database.delete(loaded.get_oid())
            raise
        self.loaded_models.extend(staged)
        self.batch_models = staged

    @staticmethod
    def _batch_format(loaded: LoadedModel) -> str:
        """Use the stored import format, falling back to the source name for older models."""
        file_type = (getattr(loaded, "file_type", "") or "").upper()
        aliases = {"XML": "FMMLx", "FMMLX": "FMMLx", "CSV": "CSV", "PLANTUML": "PlantUML",
                   "XMI": "XMI", "UML-XMI": "XMI", "ECORE": "Ecore"}
        if file_type in aliases:
            return aliases[file_type]
        source = getattr(loaded, "source_file", "") or getattr(loaded, "source_path", "")
        extension = os.path.splitext(source)[1].lower()
        return {".xml": "FMMLx", ".csv": "CSV", ".puml": "PlantUML", ".plantuml": "PlantUML",
                ".txt": "PlantUML", ".xmi": "XMI", ".ecore": "Ecore"}.get(extension, "")

    def _prepare_batch_page(self, models, progress):
        """Prepare batch counts, means, visible columns and row values."""
        metrics = []
        for index, loaded in enumerate(models, 1):
            metrics.append(self._model_metrics(loaded.model))
            progress(index, len(models))
        counts = [("Number of Models", len(models))]
        counts.extend(("Number of " + name, sum(self._batch_format(item) == name for item in models))
                      for name in ("FMMLx", "CSV", "PlantUML", "XMI", "Ecore"))
        means = ([(label, ((20 * sum(row[index][1] for row in metrics) + len(models)) // (2 * len(models))) / 10)
                  for index, (label, _) in enumerate(metrics[0])] if metrics else [])
        active = [index for index in range(len(metrics[0]))
                  if any(row[index][1] > 0 for row in metrics)] if metrics else []
        headers = ("Model Name", "Format") + tuple(metrics[0][index][0] for index in active) if metrics else ("Model Name", "Format")
        rows = [(loaded.name, self._batch_format(loaded) or self._display_file_type(loaded.file_type))
                + tuple(values[index][1] for index in active)
                for loaded, values in zip(models, metrics)]
        return counts, means, headers, rows

    def _show_batch_page(self) -> None:
        models = list(self.batch_models)
        self._run_model_task(len(models), "Preparing models...",
                             lambda progress: self._prepare_batch_page(models, progress),
                             lambda result: self._render_batch_page(*result),
                             lambda error: self._show_error("Inspect Models", str(error)))

    @atomic_page
    def _render_batch_page(self, counts, means, headers, rows) -> None:
        self._batch_view = "inspect"
        self._tell_menu_open[True] = False
        state = getattr(self, "_batch_tabs", {}).get(getattr(self, "_active_batch_tab", None))
        if state is not None:
            state.update(view="inspect", menu=False)
        self._show_batch_sidebar(analysis=False)
        self._set_top_tab("batch")
        self._clear_content()
        self._page_header("Inspect Models", "Review the selected models.")
        body = ctk.CTkFrame(self.content, fg_color="transparent")
        body.grid(row=1, column=0, sticky="nsew")
        body.grid_columnconfigure(0, weight=1)
        body.grid_rowconfigure(2, weight=1)
        colors = {"Higher Level Classes": "#315D9B", "Classes": "#2563EB", "Attributes": "#7C3AED",
                  "Enumeration Types": "#F59E0B", "Generalizations": "#E11D48", "Associations": "#64748B",
                  "Objects": "#16A34A", "Slots": "#EA580C", "Links": "#0891B2"}
        formats = ctk.CTkFrame(body, fg_color="transparent")
        formats.grid(row=0, column=0, sticky="ew", pady=(0, 14))
        format_colors = {"Number of Models": "#315D9B", "Number of FMMLx": "#2563EB",
                         "Number of CSV": "#16A34A", "Number of PlantUML": "#7C3AED",
                         "Number of XMI": "#EA580C", "Number of Ecore": "#0891B2"}
        for index, (label, value) in enumerate(counts):
            formats.grid_columnconfigure(index, weight=1, uniform="formats")
            self._metric_card_no_icon(formats, label, value, format_colors[label]).grid(
                row=0, column=index, sticky="ew", padx=(0 if index == 0 else 5, 0 if index == len(counts)-1 else 5))
        metrics = ctk.CTkFrame(body, fg_color="transparent")
        metrics.grid(row=1, column=0, sticky="ew", pady=(0, 28))
        for index, (label, value) in enumerate(means):
            metrics.grid_columnconfigure(index, weight=1, uniform="means")
            self._metric_card_no_icon(metrics, "Avg. " + label, value, colors.get(label, self.colors["primary"]), average=True).grid(
                row=0, column=index, sticky="ew", padx=(0 if index == 0 else 5, 0 if index == len(means)-1 else 5))
        self._batch_filter_models = list(self.batch_models)
        self._batch_filter_rows = list(rows)
        self._batch_filter_headers = headers
        self._batch_filter_mean_labels = [label for label, _ in means]
        self._batch_filter_colors = colors
        self._batch_filter_format_colors = format_colors
        self._batch_format_tiles = formats
        self._batch_metric_tiles = metrics
        card = self._card(body)
        card.grid(row=2, column=0, sticky="nsew")
        card.grid_columnconfigure(0, weight=1)
        card.grid_rowconfigure(2, weight=1)
        self._card_title(card, "Selected Models").grid(row=0, column=0, sticky="w", padx=16, pady=(14, 8))
        self._batch_table_host = card
        self._batch_table_card = self._build_batch_models_table(card, headers, rows, self._batch_filter_models, embedded=True)
        self._batch_table_card.grid(row=2, column=0, sticky="nsew")
        self._build_batch_filters(card)


    def _build_batch_filters(self, parent) -> None:
        """Create overview-style filters without changing the batch selection."""
        filters = ctk.CTkFrame(parent, fg_color="transparent")
        filters.grid(row=1, column=0, sticky="ew", padx=22, pady=(0, 18))
        filters.grid_columnconfigure(1, weight=1)
        state = getattr(self, "_batch_tabs", {}).get(getattr(self, "_active_batch_tab", None), {})
        search, kind, objects, attributes = state.get("filters", ("", "All", "", ""))
        self.batch_search_var = tk.StringVar(master=self, value=search)
        self.batch_type_filter_var = tk.StringVar(master=self, value=kind)
        self.batch_min_objects_var = tk.StringVar(master=self, value=objects)
        self.batch_min_attributes_var = tk.StringVar(master=self, value=attributes)
        ctk.CTkLabel(filters, text="Search", text_color=self.colors["text"], font=ctk.CTkFont(size=12)).grid(row=0, column=0, sticky="w", padx=(0, 14), pady=10)
        ctk.CTkEntry(filters, textvariable=self.batch_search_var, placeholder_text="Search Model or File ...",
                     placeholder_text_color="#94A3B8", height=44, corner_radius=7, border_color="#CBD8EA",
                     fg_color="#FFFFFF", font=ctk.CTkFont(size=13)).grid(row=0, column=1, sticky="ew", padx=(0, 44), pady=10)
        ctk.CTkLabel(filters, text="Type", text_color=self.colors["text"], font=ctk.CTkFont(size=12)).grid(row=0, column=2, sticky="w", padx=(0, 14), pady=10)
        ctk.CTkComboBox(filters, variable=self.batch_type_filter_var,
                        values=["All", "FMMLx", "CSV", "PlantUML", "XMI", "Ecore"], width=190, height=44,
                        corner_radius=7, fg_color="#FFFFFF", button_color="#FFFFFF",
                        button_hover_color=self.colors["primary_soft"], border_color="#CBD8EA", border_width=1,
                        text_color=self.colors["text"], dropdown_fg_color="#FFFFFF", dropdown_hover_color=self.colors["primary_soft"],
                        dropdown_text_color=self.colors["text"], state="readonly").grid(row=0, column=3, sticky="w", padx=(0, 44), pady=10)
        for column, (label, variable, placeholder) in enumerate((("Min objects", self.batch_min_objects_var, "e.g. 100"),
                                                                 ("Min attributes", self.batch_min_attributes_var, "e.g. 10"))):
            ctk.CTkLabel(filters, text=label, text_color=self.colors["text"], font=ctk.CTkFont(size=12)).grid(row=0, column=4 + 2 * column, sticky="w", padx=(0, 14), pady=10)
            ctk.CTkEntry(filters, textvariable=variable, placeholder_text=placeholder, width=116, height=44,
                         corner_radius=7, border_color="#CBD8EA", fg_color="#FFFFFF").grid(row=0, column=5 + 2 * column, sticky="w", padx=(0, 44 if column == 0 else 0), pady=10)
        for variable in (self.batch_search_var, self.batch_type_filter_var, self.batch_min_objects_var, self.batch_min_attributes_var):
            variable.trace_add("write", lambda *_: self._refresh_batch_filter())
        if (search, kind, objects, attributes) != ("", "All", "", ""):
            self._refresh_batch_filter()

    def _refresh_batch_filter(self) -> None:
        """Update tiles and visible columns from cached data for the filtered batch."""
        headers = self._batch_filter_headers
        query = self.batch_search_var.get().strip().lower()
        kind = self.batch_type_filter_var.get()
        min_objects = self._optional_int_filter(self.batch_min_objects_var.get())
        min_attributes = self._optional_int_filter(self.batch_min_attributes_var.get())
        state = getattr(self, "_batch_tabs", {}).get(getattr(self, "_active_batch_tab", None))
        if state is not None:
            state["filters"] = (self.batch_search_var.get(), self.batch_type_filter_var.get(),
                                self.batch_min_objects_var.get(), self.batch_min_attributes_var.get())
        def value(row, label):
            return row[headers.index(label)] if label in headers else 0
        selected = [(model, row) for model, row in zip(self._batch_filter_models, self._batch_filter_rows)
                    if (not query or query in model.name.lower() or query in model.source_file.lower())
                    and (kind == "All" or row[1] == kind)
                    and (min_objects is None or value(row, "Objects") >= min_objects)
                    and (min_attributes is None or value(row, "Attributes") >= min_attributes)]
        models = [model for model, _ in selected]
        original_rows = [row for _, row in selected]
        active = [index for index in range(2, len(headers)) if any(row[index] > 0 for row in original_rows)]
        display_headers = headers[:2] + tuple(headers[index] for index in active)
        display_rows = [row[:2] + tuple(row[index] for index in active) for row in original_rows]
        counts = [("Number of Models", len(models))] + [("Number of " + name, sum(row[1] == name for row in original_rows))
                   for name in ("FMMLx", "CSV", "PlantUML", "XMI", "Ecore")]
        means = [(label, ((20 * sum(value(row, label) for row in original_rows) + len(models)) // (2 * len(models))) / 10 if models else 0.0)
                 for label in self._batch_filter_mean_labels]
        for frame, entries, palette in ((self._batch_format_tiles, counts, self._batch_filter_format_colors),
                                        (self._batch_metric_tiles, means, self._batch_filter_colors)):
            for card, (label, number) in zip(frame.grid_slaves(row=0)[::-1], entries):
                labels = [child for child in card.winfo_children() if isinstance(child, ctk.CTkLabel)]
                title, value_label = labels
                value_text = f"{number:.1f}" if frame is self._batch_metric_tiles else str(number)
                size = 17 if len(value_text) >= 7 else 18 if len(value_text) >= 6 else 20 if len(value_text) >= 5 else 22
                title.configure(text_color="#A8B2C1" if number == 0 else self.colors["text"])
                value_label.configure(text=value_text, text_color="#A8B2C1" if number == 0 else palette.get(label, self.colors["primary"]))
                value_label.cget("font").configure(size=size)
        _cancel_widget_timers(self._batch_table_card)
        self._batch_table_card.destroy()
        self._batch_table_card = self._build_batch_models_table(self._batch_table_host, display_headers, display_rows, models, embedded=True)
        self._batch_table_card.grid(row=2, column=0, sticky="nsew")

    def _build_batch_models_table(self, parent, headers, rows, models=None, embedded=False):
        models = list(self.batch_models if models is None else models)
        card = ctk.CTkFrame(parent, fg_color="transparent") if embedded else self._card(parent)
        card.grid_columnconfigure(0, weight=1)
        card.grid_rowconfigure(1, weight=1)
        area = ctk.CTkFrame(card, fg_color="#FFFFFF", corner_radius=0)
        area.grid(row=1, column=0, sticky="nsew", padx=22, pady=(0, 22))
        area.grid_columnconfigure(0, weight=1)
        area.grid_rowconfigure(0, weight=1)
        canvas = tk.Canvas(area, background="#FFFFFF", highlightthickness=0, bd=0)
        canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar = ctk.CTkScrollbar(area, orientation="vertical", command=canvas.yview,
                                     width=14, button_color="#AFCBFF", button_hover_color=self.colors["primary"])
        scrollbar.grid(row=0, column=1, sticky="ns", padx=(4, 0))
        horizontal = ctk.CTkScrollbar(area, orientation="horizontal", command=canvas.xview,
                                      height=14, button_color="#AFCBFF", button_hover_color=self.colors["primary"])
        horizontal.grid(row=1, column=0, sticky="ew", pady=(4, 0))
        horizontal_scroll = ModelDeepenerApp._autohide_scroll(horizontal)
        def on_horizontal(first, last):
            horizontal_scroll(first, last)
            if batch_state is not None:
                batch_state["inspect_scroll"] = (canvas.yview()[0], float(first))
        canvas.configure(xscrollcommand=on_horizontal)
        vertical_scroll = ModelDeepenerApp._autohide_scroll(scrollbar)
        batch_state = getattr(self, "_batch_tabs", {}).get(getattr(self, "_active_batch_tab", None))
        saved_position = batch_state.get("inspect_scroll", (0.0, 0.0)) if batch_state is not None else (0.0, 0.0)
        def draw(_event=None):
            canvas.delete("all")
            minimum_widths = [220, 120] + [130] * (len(headers) - 2)
            width = max(canvas.winfo_width(), sum(minimum_widths))
            extra = width - sum(minimum_widths)
            widths = [value + extra // len(headers) for value in minimum_widths]
            widths[-1] += width - sum(widths)
            def cell(x, y, w, height, text, background, foreground, font):
                rect = canvas.create_rectangle(x, y, x+w, y+height, fill=background, outline="#AFC1D9", width=1)
                label = canvas.create_text(x+w/2, y+height/2, text=str(text), fill=foreground,
                                           font=font, anchor="center", justify="center", width=max(20, w-18))
                return rect, label
            header_items = []
            x = 0
            for header, column_width in zip(headers, widths):
                header_items.extend(cell(x, canvas.canvasy(0), column_width, 58, header,
                                         "#DFE9FD", "#04173D", ("Segoe UI", 12, "bold")))
                x += column_width
            first = max(0, int((canvas.canvasy(0) - 58) // 64) - 1)
            last = min(len(models), int((canvas.canvasy(canvas.winfo_height()) - 58) // 64) + 2)
            for index in range(first, last):
                loaded = models[index]
                y = 58 + index * 64
                background = "#FFFFFF" if index % 2 == 0 else "#F3F7FD"
                x = 0
                for value, column_width in zip(rows[index], widths):
                    for item in cell(x, y, column_width, 64, value, background, self.colors["text"], ("Segoe UI", 12)):
                        canvas.tag_bind(item, "<Button-1>", lambda _event, target=loaded: self._open_loaded_model(target))
                        canvas.tag_bind(item, "<Enter>", lambda _event: canvas.configure(cursor="hand2"))
                        canvas.tag_bind(item, "<Leave>", lambda _event: canvas.configure(cursor=""))
                    x += column_width
            canvas.create_rectangle(0, 0, max(1, width - 1), 58 + max(1, len(models)) * 64 - 1, outline="#AFC1D9", width=1)
            for item in header_items:
                canvas.addtag_withtag("sticky_header", item)
            canvas.tag_raise("sticky_header")
            region = (0, 0, width, 58 + max(1, len(models)) * 64)
            if getattr(canvas, "_last_scrollregion", None) != region:
                canvas._last_scrollregion = region
                canvas.configure(scrollregion=region)
        def on_scroll(first, last):
            vertical_scroll(first, last)
            if batch_state is not None:
                batch_state["inspect_scroll"] = (float(first), canvas.xview()[0])
            position = (first, last)
            if position == getattr(canvas, "_last_scroll_position", None):
                return
            canvas._last_scroll_position = position
            if not getattr(canvas, "_redraw_pending", False):
                canvas._redraw_pending = True
                def redraw():
                    canvas._redraw_pending = False
                    if canvas.winfo_exists():
                        draw()
                canvas._redraw_after = canvas.after_idle(redraw)
        def cancel_redraw(event):
            if event.widget is canvas and getattr(canvas, "_redraw_pending", False):
                canvas.after_cancel(canvas._redraw_after)
                canvas._redraw_pending = False
        canvas.bind("<Destroy>", cancel_redraw, add="+")
        canvas.configure(yscrollcommand=on_scroll)
        canvas.bind("<Configure>", draw)
        ModelDeepenerApp._bind_table_wheel(canvas, canvas)
        def restore_position():
            if canvas.winfo_exists():
                canvas.yview_moveto(saved_position[0])
                canvas.xview_moveto(saved_position[1])
                draw()
        canvas.after_idle(restore_position)
        card._batch_canvas = canvas
        return card

    def _show_batch_analysis(self) -> None:
        """Prepare the batch analysis before displaying it."""
        selection = self._tell_selection[True]
        models = [(loaded.name, loaded.model, self._batch_format(loaded)) for loaded in self.batch_models]
        self._run_model_task(len(models), "Preparing analysis...", lambda progress: analyze_tells(selection, models, progress, getattr(self, "_tell_cache", None)),
                             lambda rows: ModelDeepenerApp._present_tell_results(
                                 self, True, selection, rows, lambda: self._render_batch_analysis(selection, rows)),
                             lambda error: self._show_error("Analysis", str(error)))

    @atomic_page
    def _render_batch_analysis(self, selection, rows) -> None:
        self._batch_view = "analysis"
        self._tell_menu_open[True] = True
        state = getattr(self, "_batch_tabs", {}).get(getattr(self, "_active_batch_tab", None))
        if state is not None:
            state.update(view="analysis", menu=True, tell=selection)
        self._show_batch_sidebar(analysis=True)
        self._set_top_tab("batch")
        self._clear_content()
        header = self._page_header(*tell_description(selection))
        panel = self._build_tell_results(self.content, batch=True, row_provider=lambda _selection: rows)
        panel._tell_owner = (True, getattr(self, "_active_batch_tab", None))
        panel._tell_header = header
        self._active_tell_panel = panel
        panel.grid(row=1, column=0, sticky="nsew")

    def _browse_file(self) -> None:
        """Ask for a supported model file and validate its selection.

        If the user cancels the file dialog, nothing changes.
        """
        file_path = self._ask_open_file(
            file_types=self._import_file_types()
        )
        if file_path:
            self.file_path_var.set(file_path)
            self.current_file_path = file_path
            self._file_selection_mode = "upload"
            self._validate_current_file()
            self._set_file_input_mode("upload")

    @staticmethod
    def _display_file_type(file_type: str) -> str:
        return {"XML": "FMMLx", "FMMLX": "FMMLx", "CSV": "CSV", "PLANTUML": "PlantUML",
                "XMI": "XMI", "UML-XMI": "XMI", "ECORE": "Ecore"}.get(file_type.upper(), file_type)

    @staticmethod
    def _import_file_types() -> list[tuple[str, str]]:
        """Returns the entries of the file dialog for all formats that can be imported."""
        all_patterns = []
        for extension in supported_extensions():
            all_patterns.append(f"*{extension}")
        file_types = [("Supported files", " ".join(all_patterns))]
        for importer_class in supported_importers():
            patterns = []
            for extension in importer_class.EXTENSIONS:
                patterns.append(f"*{extension}")
            file_types.append((f"{ModelDeepenerApp._display_file_type(importer_class.FORMAT_NAME)} files", " ".join(patterns)))
        file_types.append(("All files", "*.*"))
        return file_types

    @staticmethod
    def _importer_for_file(file_path: str) -> Optional[ModelImporter]:
        """Returns the importer for the file, or None if no importer reads its file ending."""
        try:
            return importer_for(file_path)
        except ValueError:
            return None

    def _validate_current_file(self) -> None:
        """Validate the chosen format and enable creation only when its selection is usable."""
        self.current_batch_paths = []
        self.current_batch_folders = {}
        self.batch_file_list.grid_remove()
        self.batch_folder_panel.grid_remove()
        self.file_entry.grid()
        file_path = self.file_path_var.get().strip()
        self.current_file_path = file_path or None
        self.csv_preview = None
        self.xml_preview = None
        self.selected_csv_columns.clear()

        if not file_path:
            self._set_column_selection_enabled(False)
            self._set_validation_badge_visible(True)
            self.validation_status_badge.configure(
                text="Not validated",
                fg_color=self.colors["disabled_bg"],
                text_color=self.colors["muted"],
            )
            self._set_validation_rows([("File", "No file selected")])
            self._render_empty_preview("Select a file to start.")
            self._set_create_button_enabled(False)
            return

        self._set_validation_badge_visible(False)
        extension = os.path.splitext(file_path)[1].lower()
        importer = self._importer_for_file(file_path)
        self._set_column_selection_enabled(isinstance(importer, CsvImporter))
        if isinstance(importer, (CsvImporter, XmlImporter)):
            self._set_create_button_enabled(False)
            is_csv = isinstance(importer, CsvImporter)
            def prepared(preview):
                if is_csv:
                    self.csv_preview = preview
                    self._render_csv_validation(preview)
                    self._render_csv_mapping(preview)
                    can_create = not preview.errors and preview.header_detected
                else:
                    self.xml_preview = preview
                    self._render_xml_validation(preview)
                    self._render_empty_preview("Column selection is only available for CSV files.")
                    can_create = not preview.errors
                self._set_create_button_enabled(can_create and self._can_create_current_file())
            self._run_model_task(1, "Validating file...",
                                 lambda _progress: self._build_csv_preview(file_path) if is_csv else self._build_xml_preview(file_path),
                                 prepared, lambda error: self._show_error("Validation", str(error)))
            return
        elif isinstance(importer, (PlantUmlImporter, EcoreImporter, XmiImporter)):
            self._set_validation_rows([
                ("File type", importer.FORMAT_NAME),
                ("Status", "Not Validated"),
                ("Errors", "None"),
            ])
            self._render_empty_preview("Column selection is only available for CSV files.")
            can_create = True
        else:
            self._set_validation_rows([
                ("File type", extension or "unknown"),
                ("Errors", "Unsupported file type"),
            ])
            self._render_empty_preview("Column selection is only available for CSV files.")
            can_create = False

        self._set_create_button_enabled(can_create and self._can_create_current_file())

    def _set_column_selection_enabled(self, enabled: bool) -> None:
        """Only a single CSV offers the column controls and expand action."""
        if not enabled and self.column_selection_expanded:
            self._toggle_column_selection_size()
        for widget in (self.column_selection_description, self.expand_columns_button):
            if enabled:
                widget.grid()
            else:
                widget.grid_remove()

    def _set_create_button_enabled(self, enabled: bool):
        """
        Enables or disables Create Model and Continue.

        This block controls the visible validation state: the create button,
        the Validation Results badge, and the expanded/collapsed Column Selection area.
        """
        self.create_button.configure(
            state="normal" if enabled else "disabled",
            fg_color=self.colors["primary"] if enabled else "#cbd5e1",
            hover_color=self.colors["primary_hover"] if enabled else "#cbd5e1",
            text_color="#ffffff" if enabled else "#f8fafc",
        )

    def _set_validation_badge_visible(self, visible: bool):
        # The badge is only useful before a file has been checked.
        # After a check, the table below already tells the user what happened.
        if visible:
            if not self.validation_status_badge.winfo_ismapped():
                self.validation_status_badge.pack(side="right")
        else:
            self.validation_status_badge.pack_forget()

    def _update_expand_columns_button(self):
        # The arrow shows whether the column table can be opened larger or folded back.
        label = "Collapse ↓" if self.column_selection_expanded else "Expand ↑"
        self.expand_columns_button.configure(text=label)

    @staticmethod
    def _display_table_value(value) -> str:
        """
        Converts raw values into readable table text.

        This starts the parsing helper block. The methods here detect CSV
        separators, infer simple CSV attribute types, detect headers, and load
        XML files far enough to show validation feedback.
        """
        # Empty cells are easier to read as "-" than as a blank space.
        if value is None or value == "":
            return "-"
        return ModelDeepenerApp._clean_display_value(value)

    @staticmethod
    def _clean_display_value(value) -> str:
        text = str(value)
        date_match = re.search(r"(?:Root::)?Auxiliary::Date::createDate\(([^)]*)\)", text)
        if date_match:
            return ", ".join(part.strip() for part in date_match.group(1).split(","))
        datetime_match = re.search(r"(?:Root::)?Auxiliary::DateTime::createDateTime\(([^)]*)\)", text)
        if datetime_match:
            return ", ".join(part.strip() for part in datetime_match.group(1).split(","))
        if "::" in text:
            return text.split("::")[-1]
        return text

    @staticmethod
    def _detect_csv_dialect(csv_file):
        # Look at the beginning of the CSV file to guess how columns are separated.
        # If the automatic guess is unsure, the most common separator is used.
        sample = csv_file.read(2048)
        csv_file.seek(0)
        try:
            return csv.Sniffer().sniff(sample, delimiters=",;\t|")
        except csv.Error:
            dialect = csv.excel
            delimiter_counts = {
                delimiter: sample.count(delimiter)
                for delimiter in [",", ";", "\t", "|"]
            }
            dialect.delimiter = max(delimiter_counts, key=delimiter_counts.get)
            return dialect

    @classmethod
    def _build_csv_preview(cls, file_path: str) -> CsvImportPreview:
        """Read CSV metadata and collect blocking errors before showing the column selection."""
        # Build a small summary before importing the CSV for real.
        # The GUI uses this summary to explain what the selected file contains.
        warnings: List[str] = []
        errors: List[str] = []

        try:
            csv_reader = CsvReader(file_path)
            delimiter = csv_reader.get_delimiter()
        except FileNotFoundError:
            return CsvImportPreview(file_path, "", [], [], 0, 0, False, warnings, [f"File not found: {file_path}"])
        except (OSError, UnicodeError, csv.Error) as exc:
            # File and CSV reading problems become readable messages in the GUI.
            return CsvImportPreview(file_path, "", [], [], 0, 0, False, warnings, [f"Could not read CSV: {exc}"])

        if csv_reader.is_empty():
            return CsvImportPreview(file_path, delimiter, [], [], 0, 0, False, warnings, ["CSV file is empty."])

        header = csv_reader.get_header()
        data_rows = csv_reader.get_data_rows()
        column_count = len(header)
        header_detected = csv_reader.first_row_looks_like_header()

        if column_count == 0:
            errors.append("CSV header must contain at least one column.")
        if not header_detected:
            errors.append("No valid header was detected. The first row looks like data, not attribute names.")

        for row_number, row in enumerate(data_rows, start=2):
            if len(row) != column_count:
                errors.append(f"Row {row_number} has {len(row)} values, but the header has {column_count} values.")
                break

        if len(data_rows) == 0:
            warnings.append("CSV has a header but no data rows.")

        return CsvImportPreview(
            file_path=file_path,
            delimiter=delimiter,
            header=header,
            data_rows=data_rows,
            row_count=len(data_rows),
            column_count=column_count,
            header_detected=header_detected,
            warnings=warnings,
            errors=errors,
        )

    @staticmethod
    def _build_xml_preview(file_path: str) -> XmlImportPreview:
        """Import XML once so validation and creation can share its model and problem report."""
        # Try to open the XML model once so the GUI can report problems before the real import.
        try:
            model, report = importer_for(file_path).import_file(file_path)
            warnings = []
            if ModelDeepenerApp._count_attributes(model) == 0:
                warnings.append(
                    "No attributes were attached to model classes. The FMMLx file may not contain addAttribute entries, "
                    "or its attribute class names may not match the class names in the model."
                )
            return XmlImportPreview(file_path=file_path, errors=[], warnings=warnings, model=model, report=report)
        except Exception as exc:
            # Expected import problems are kept as readable messages for the user.
            return XmlImportPreview(file_path=file_path, errors=[str(exc)], model=None)

    def _render_csv_validation(self, preview: CsvImportPreview):
        """
        Shows CSV validation results in the Validation Results card.

        The methods in this block convert CSV/XML preview results into the
        rows the user sees after selecting a file.
        """
        is_ready = not preview.errors and preview.header_detected
        delimiter_name = {";": "Semicolon (;)", ",": "Comma (,)", "\t": "Tab", "|": "Pipe (|)"}.get(
            preview.delimiter, preview.delimiter
        )
        self._set_validation_rows(
            [
                ("File type", "CSV"),
                ("Status", "Ready" if is_ready else "Blocked"),
                ("Delimiter", delimiter_name),
                ("Rows", str(preview.row_count)),
                ("Columns", str(preview.column_count)),
                ("Errors", "; ".join(preview.errors) if preview.errors else "None"),
            ]
        )

    def _render_xml_validation(self, preview: XmlImportPreview):
        is_ready = not preview.errors
        rows = [
            ("File type", "FMMLx"),
            ("Status", "Not Validated" if is_ready else "Blocked"),
            ("Errors", "; ".join(preview.errors) if preview.errors else "None"),
        ]
        self._set_validation_rows(rows)

    def _bind_column_scroll_events(self, _event=None):
        self.bind_all("<MouseWheel>", self._on_column_mousewheel)
        self.bind_all("<Shift-MouseWheel>", self._on_column_shift_mousewheel)

    def _unbind_column_scroll_events(self, _event=None):
        self.unbind_all("<MouseWheel>")
        self.unbind_all("<Shift-MouseWheel>")

    def _on_column_mousewheel(self, event):
        # Windows/macOS touchpads usually send MouseWheel events.
        if not hasattr(self, "column_canvas"):
            return
        delta = int(-1 * (event.delta / 120)) if event.delta else 0
        if delta:
            self.column_canvas.yview_scroll(delta, "units")

    def _on_column_shift_mousewheel(self, event):
        # Kept for future horizontal scrolling if the table ever grows wider.
        if not hasattr(self, "column_canvas"):
            return
        delta = int(-1 * (event.delta / 120)) if event.delta else 0
        if delta:
            self.column_canvas.xview_scroll(delta, "units")


    def _set_validation_rows(self, rows: List[tuple]):
        for child in self.validation_rows_frame.winfo_children():
            child.destroy()

        icons = {
            "File type": "□",
            "Status": "✓",
            "Delimiter": "↔",
            "Rows": "#",
            "Columns": "▥",
            "Errors": "!",
            "Path": "⌂",
            "Classes": "◇",
            "Objects": "●",
            "Associations": "↔",
            "Links": "↗",
            "Enums": "≡",
            "File": "□",
            "Warnings": "!",
        }

        icon_width = 38
        label_width = 165
        divider_x = icon_width + label_width

        for row_index, (key, value) in enumerate(rows):
            row_bg = "#FFFFFF" if row_index % 2 == 0 else "#F5F8FC"

            # pack(fill="x") makes every row span the full Validation card.
            row_frame = tk.Frame(
                self.validation_rows_frame,
                height=self.VALIDATION_ROW_HEIGHT,
                background=row_bg,
                bd=0,
                highlightthickness=0,
            )
            row_frame.pack(
                fill="x",
                expand=False,
            )
            row_frame.pack_propagate(False)

            icon_cell = tk.Frame(
                row_frame,
                width=icon_width,
                height=self.VALIDATION_ROW_HEIGHT,
                background=row_bg,
                bd=0,
                highlightthickness=0,
            )
            icon_cell.place(
                x=0,
                y=0,
                width=icon_width,
                height=self.VALIDATION_ROW_HEIGHT,
            )

            status_is_ready = key == "Status" and str(value) == "Ready"
            status_is_not_validated = key == "Status" and str(value) == "Not Validated"
            status_is_blocked = key == "Status" and str(value) == "Blocked"

            ctk.CTkLabel(
                icon_cell,
                text=icons.get(str(key), "-"),
                text_color=(
                    self.colors["success"]
                    if status_is_ready
                    else self.colors["muted"]
                    if status_is_not_validated
                    else self.colors["danger"]
                    if status_is_blocked
                    else self.colors["primary"]
                ),
                font=ctk.CTkFont(
                    family="Segoe UI Symbol",
                    size=13,
                    weight="bold",
                ),
            ).place(relx=0.5, rely=0.5, anchor="center")

            label_cell = tk.Frame(
                row_frame,
                width=label_width,
                height=self.VALIDATION_ROW_HEIGHT,
                background=row_bg,
                bd=0,
                highlightthickness=0,
            )
            label_cell.place(
                x=icon_width,
                y=0,
                width=label_width,
                height=self.VALIDATION_ROW_HEIGHT,
            )

            ctk.CTkLabel(
                label_cell,
                text=str(key),
                anchor="w",
                justify="left",
                text_color=self.colors["text"],
                font=ctk.CTkFont(
                    family="Segoe UI",
                    size=12,
                    weight="bold",
                ),
            ).place(x=8, rely=0.5, anchor="w")

            # One light divider between label and value.
            tk.Frame(
                row_frame,
                width=1,
                height=self.VALIDATION_ROW_HEIGHT,
                background="#DCE6F2",
                bd=0,
                highlightthickness=0,
            ).place(
                x=divider_x,
                y=0,
                width=1,
                height=self.VALIDATION_ROW_HEIGHT,
            )

            # Value area stretches from the divider to the right edge.
            value_cell = tk.Frame(
                row_frame,
                height=self.VALIDATION_ROW_HEIGHT,
                background=row_bg,
                bd=0,
                highlightthickness=0,
            )
            value_cell.place(
                x=divider_x + 1,
                y=0,
                relwidth=1.0,
                width=-(divider_x + 1),
                height=self.VALIDATION_ROW_HEIGHT,
            )

            is_error = key == "Errors" and str(value) != "None"
            ctk.CTkLabel(
                value_cell,
                text=str(value),
                anchor="w",
                justify="left",
                text_color=(
                    self.colors["danger"]
                    if is_error or status_is_blocked
                    else self.colors["success"]
                    if status_is_ready
                    else self.colors["muted"]
                    if status_is_not_validated
                    else self.colors["text"]
                ),
                font=ctk.CTkFont(
                    family="Segoe UI",
                    size=12,
                    weight="bold" if key == "Status" else "normal",
                ),
            ).place(
                x=12,
                rely=0.5,
                anchor="w",
            )

    def _reset_column_table(self, total_height: int):
        """
        Clears and rebuilds the Column Selection table.

        The methods in this block draw the CSV columns, inferred types, example
        values, Include checkboxes, and Select All behavior.
        """
        old_header = getattr(self, "_column_sticky_header", None)
        if old_header is not None and old_header.winfo_exists():
            old_header.destroy()
        self._column_sticky_header = None
        if self.column_table is not None:
            self.column_table.destroy()

        self.column_canvas.update_idletasks()
        total_width = max(
            self.column_canvas.winfo_width(),
            self.COLUMN_WIDTH_INCLUDE
            + self.COLUMN_WIDTH_NAME
            + self.COLUMN_WIDTH_TYPE
            + 360,
            )

        self.column_table = tk.Frame(
            self.column_canvas,
            background="#FFFFFF",
            height=total_height,
            bd=0,
            highlightthickness=0,
        )

        # Stable first columns; Example Slots receives the remaining width.
        self.column_table.grid_columnconfigure(
            0,
            weight=0,
            minsize=self.COLUMN_WIDTH_INCLUDE,
        )
        self.column_table.grid_columnconfigure(
            1,
            weight=0,
            minsize=self.COLUMN_WIDTH_NAME,
        )
        self.column_table.grid_columnconfigure(
            2,
            weight=0,
            minsize=self.COLUMN_WIDTH_TYPE,
        )
        self.column_table.grid_columnconfigure(
            3,
            weight=1,
            minsize=360,
        )

        self.column_canvas.delete("all")
        self.column_canvas_window = self.column_canvas.create_window(
            (0, 0),
            window=self.column_table,
            anchor="nw",
            width=total_width,
            height=total_height,
        )

        self.column_canvas.configure(
            scrollregion=(0, 0, total_width, total_height)
        )
        self.column_canvas.yview_moveto(0)

        def _fit_table_to_canvas(event):
            fitted_width = max(
                event.width,
                self.COLUMN_WIDTH_INCLUDE
                + self.COLUMN_WIDTH_NAME
                + self.COLUMN_WIDTH_TYPE
                + 360,
                )
            self.column_canvas.itemconfigure(
                self.column_canvas_window,
                width=fitted_width,
            )
            self.column_canvas.configure(
                scrollregion=(0, 0, fitted_width, total_height)
            )

        self.column_canvas.bind("<Configure>", _fit_table_to_canvas)

    def _make_table_cell(
            self,
            row: int,
            column: int,
            height: int,
            background: str,
            border_left: bool = False,
    ):
        cell = tk.Frame(
            self.column_table,
            height=height,
            background=background,
            highlightthickness=1,
            highlightbackground="#AFC1D9",
            highlightcolor="#AFC1D9",
            bd=0,
        )
        cell.grid(row=row, column=column, sticky="nsew")
        cell.grid_propagate(False)

        if border_left:
            separator = tk.Frame(
                cell,
                width=1,
                background="#AFC1D9",
                bd=0,
                highlightthickness=0,
            )
            separator.place(x=0, y=0, width=1, height=height)

        return cell

    def _build_column_table_header(self):
        header_bg = "#DFE9FD"
        specs = (
            (0, "include", "All"),
            (1, "label", "Column Name"),
            (2, "label", "Detected Data Type"),
            (3, "label", "Example Slots"),
        )

        self.column_table.grid_rowconfigure(
            0,
            weight=0,
            minsize=self.TABLE_HEADER_HEIGHT,
        )

        for column, cell_type, text in specs:
            cell = self._make_table_cell(
                row=0,
                column=column,
                height=self.TABLE_HEADER_HEIGHT,
                background=header_bg,
                border_left=column > 0,
            )

            if cell_type == "include":
                # A separate checkbox and label are placed in one centered
                # group. This avoids CTkCheckBox centering only its text.
                all_group = tk.Frame(
                    cell,
                    background=header_bg,
                    bd=0,
                    highlightthickness=0,
                )
                all_group.place(
                    relx=0.5,
                    rely=0.5,
                    anchor="center",
                )

                self.select_all_columns_checkbox = ctk.CTkCheckBox(
                    all_group,
                    text="",
                    variable=self.all_columns_selected_var,
                    width=21,
                    height=21,
                    checkbox_width=21,
                    checkbox_height=21,
                    corner_radius=4,
                    border_width=2,
                    border_color="#315D9B",
                    fg_color=self.colors["primary"],
                    hover_color=self.colors["primary_hover"],
                    command=self._toggle_all_columns,
                )
                self.select_all_columns_checkbox.pack(
                    side="left",
                    padx=(0, 6),
                )

                all_label = ctk.CTkLabel(
                    all_group,
                    text="All",
                    text_color="#04173D",
                    font=ctk.CTkFont(
                        family="Segoe UI",
                        size=12,
                        weight="bold",
                    ),
                )
                all_label.pack(side="left")
                all_label.bind(
                    "<Button-1>",
                    lambda _event: self._toggle_all_columns_from_label(),
                )
            else:
                ctk.CTkLabel(
                    cell,
                    text=text,
                    anchor="center",
                    justify="center",
                    text_color="#04173D",
                    font=ctk.CTkFont(
                        family="Segoe UI",
                        size=12,
                        weight="bold",
                    ),
                ).place(
                    relx=0.5,
                    rely=0.5,
                    anchor="center",
                )

    def _pin_column_table_header(self):
        """Keep the CSV column-selection header visible while rows scroll."""
        header = tk.Canvas(self.column_table_wrapper, background="#DFE9FD", highlightthickness=0)
        header.place(in_=self.column_canvas, x=0, y=0, relwidth=1, height=self.TABLE_HEADER_HEIGHT)
        self._column_sticky_header = header
        frame = tk.Frame(header, bg="#DFE9FD")
        window = header.create_window(0, 0, anchor="nw", window=frame)
        widths = [self.COLUMN_WIDTH_INCLUDE, self.COLUMN_WIDTH_NAME, self.COLUMN_WIDTH_TYPE, 360]
        for index, text in enumerate(("All", "Column Name", "Detected Data Type", "Example Slots")):
            frame.grid_columnconfigure(index, minsize=widths[index], weight=1 if index == 3 else 0)
            cell = tk.Frame(frame, bg="#DFE9FD", height=self.TABLE_HEADER_HEIGHT,
                            highlightthickness=1, highlightbackground="#AFC1D9")
            cell.grid(row=0, column=index, sticky="nsew")
            cell.grid_propagate(False)
            if index == 0:
                group = tk.Frame(cell, bg="#DFE9FD")
                group.place(relx=0.5, rely=0.5, anchor="center")
                ctk.CTkCheckBox(group, text="", variable=self.all_columns_selected_var,
                                width=21, height=21, checkbox_width=21, checkbox_height=21,
                                command=self._toggle_all_columns).pack(side="left", padx=(0, 6))
                label = ctk.CTkLabel(group, text=text, text_color="#04173D",
                                     font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"))
                label.pack(side="left")
                label.bind("<Button-1>", lambda _event: self._toggle_all_columns_from_label())
            else:
                ctk.CTkLabel(cell, text=text, text_color="#04173D",
                             font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold")).place(
                                 relx=0.5, rely=0.5, anchor="center")
        def fit(_event=None):
            if not header.winfo_exists():
                return
            region = self.column_canvas.cget("scrollregion").split()
            width = max(sum(widths), int(float(region[2])) if len(region) == 4 else 0)
            header.itemconfigure(window, width=width)
            header.configure(scrollregion=(0, 0, width, self.TABLE_HEADER_HEIGHT))
            header.xview_moveto(self.column_canvas.xview()[0])
        header.bind("<Configure>", fit)
        self.column_canvas.configure(xscrollcommand=lambda first, _last: header.xview_moveto(float(first)) if header.winfo_exists() else None)
        ModelDeepenerApp._bind_table_wheel(header, self.column_canvas)
        ModelDeepenerApp._bind_table_wheel(frame, self.column_canvas)
        fit()

    def _render_csv_mapping(self, preview: CsvImportPreview) -> None:
        """Build the column selection and sample rows for the validated CSV preview."""
        self.selected_csv_columns.clear()
        self.all_columns_selected_var.set(True)

        row_count = len(preview.header)
        total_height = (
                self.TABLE_HEADER_HEIGHT
                + row_count * self.TABLE_ROW_HEIGHT
        )

        self._reset_column_table(total_height)
        self._build_column_table_header()
        self._pin_column_table_header()

        for column_index, column_name in enumerate(preview.header):
            values = [
                row[column_index]
                for row in preview.data_rows
                if column_index < len(row)
            ]
            data_type = CsvReader.column_type(values)
            selected = tk.BooleanVar(value=True)
            self.selected_csv_columns[column_name] = selected

            row_number = column_index + 1
            row_color = "#FFFFFF" if column_index % 2 == 0 else "#F3F7FD"

            self.column_table.grid_rowconfigure(
                row_number,
                weight=0,
                minsize=self.TABLE_ROW_HEIGHT,
            )

            include_cell = self._make_table_cell(
                row=row_number,
                column=0,
                height=self.TABLE_ROW_HEIGHT,
                background=row_color,
            )
            checkbox = ctk.CTkCheckBox(
                include_cell,
                text="",
                variable=selected,
                width=22,
                height=22,
                checkbox_width=20,
                checkbox_height=20,
                corner_radius=4,
                border_width=2,
                border_color="#4F78B8",
                fg_color=self.colors["primary"],
                hover_color=self.colors["primary_hover"],
                command=self._on_column_checkbox_changed,
            )
            checkbox.place(relx=0.5, rely=0.5, anchor="center")

            name_cell = self._make_table_cell(
                row=row_number,
                column=1,
                height=self.TABLE_ROW_HEIGHT,
                background=row_color,
                border_left=True,
            )
            ctk.CTkLabel(
                name_cell,
                text=column_name,
                anchor="center",
                justify="center",
                text_color=self.colors["text"],
                font=ctk.CTkFont(family="Segoe UI", size=13),
            ).place(relx=0.5, rely=0.5, anchor="center")

            type_cell = self._make_table_cell(
                row=row_number,
                column=2,
                height=self.TABLE_ROW_HEIGHT,
                background=row_color,
                border_left=True,
            )
            ctk.CTkLabel(
                type_cell,
                text=data_type,
                height=26,
                corner_radius=13,
                fg_color=self.colors["primary_soft"],
                text_color="#013897",
                font=ctk.CTkFont(
                    family="Segoe UI",
                    size=11,
                    weight="bold",
                ),
            ).place(relx=0.5, rely=0.5, anchor="center")

            examples_cell = self._make_table_cell(
                row=row_number,
                column=3,
                height=self.TABLE_ROW_HEIGHT,
                background=row_color,
                border_left=True,
            )
            ctk.CTkLabel(
                examples_cell,
                text=self._format_example_values(values),
                anchor="center",
                justify="center",
                text_color="#334155",
                font=ctk.CTkFont(family="Segoe UI", size=13),
            ).place(
                relx=0.5,
                rely=0.5,
                anchor="center",
                relwidth=0.94,
            )

        self.column_canvas.update_idletasks()
        fitted_width = max(
            self.column_canvas.winfo_width(),
            self.COLUMN_WIDTH_INCLUDE
            + self.COLUMN_WIDTH_NAME
            + self.COLUMN_WIDTH_TYPE
            + 360,
            )
        self.column_canvas.itemconfigure(
            self.column_canvas_window,
            width=fitted_width,
            height=total_height,
        )
        self.column_canvas.configure(
            scrollregion=(0, 0, fitted_width, total_height)
        )
        self.column_canvas.yview_moveto(0)
        ModelDeepenerApp._bind_table_wheel(self.column_table, self.column_canvas)

    @staticmethod
    def _format_example_values(
            values: List[str],
            max_chars: int = 58,
    ) -> str:
        # Fit a few example values into one table cell.
        # Long text is shortened so the column preview stays readable.
        cleaned_values = [
            str(value).strip()
            for value in values
            if str(value).strip()
        ]

        if not cleaned_values:
            return "-"

        selected_values: List[str] = []
        current_length = 0

        for value in cleaned_values:
            separator_length = 2 if selected_values else 0
            remaining = max_chars - current_length - separator_length

            if remaining <= 0:
                break

            # A single long value is shortened so that every populated
            # column still shows at least one example.
            if not selected_values and len(value) > remaining:
                shortened = value[: max(1, remaining - 3)].rstrip()
                selected_values.append(shortened + "...")
                break

            if len(value) > remaining:
                break

            selected_values.append(value)
            current_length += separator_length + len(value)

        if not selected_values:
            first_value = cleaned_values[0]
            return (
                first_value
                if len(first_value) <= max_chars
                else first_value[: max(1, max_chars - 3)].rstrip() + "..."
            )

        result = ", ".join(selected_values)
        if len(selected_values) < len(cleaned_values) and not result.endswith("..."):
            if len(result) + 3 <= max_chars:
                result += ", ..."
            else:
                result = result[: max(1, max_chars - 3)].rstrip(" ,") + "..."

        return result

    def _toggle_all_columns_from_label(self):
        self.all_columns_selected_var.set(
            not self.all_columns_selected_var.get()
        )
        self._toggle_all_columns()

    def _toggle_all_columns(self):
        selected = self.all_columns_selected_var.get()
        for variable in self.selected_csv_columns.values():
            variable.set(selected)
        self._set_create_button_enabled(self._has_selected_columns())

    def _toggle_column_selection_size(self):
        self.column_selection_expanded = not self.column_selection_expanded

        if self.column_selection_expanded:
            self.file_card.grid_remove()
            self.validation_card.grid_remove()
            self.column_canvas.configure(height=560)
        else:
            self.file_card.grid()
            self.validation_card.grid()
            self.column_canvas.configure(height=290)
        self._update_expand_columns_button()


    def _on_column_checkbox_changed(self):
        values = [var.get() for var in self.selected_csv_columns.values()]
        self.all_columns_selected_var.set(bool(values) and all(values))
        self._set_create_button_enabled(self._has_selected_columns())


    def _can_create_current_file(self) -> bool:
        """Return True if the chosen file can be imported as it is selected on the page."""
        file_path = self.current_file_path
        if not file_path:
            file_path = ""
        importer = self._importer_for_file(file_path)
        if isinstance(importer, CsvImporter):
            return self._has_selected_columns()
        if isinstance(importer, XmlImporter):
            return self.xml_preview is not None and not self.xml_preview.errors
        return isinstance(importer, (PlantUmlImporter, EcoreImporter, XmiImporter))

    def _has_selected_columns(self) -> bool:
        if self.csv_preview is None or self.csv_preview.errors or not self.csv_preview.header_detected:
            return False
        return any(var.get() for var in self.selected_csv_columns.values())

    def _render_empty_preview(self, text: str):
        """Show a single message without a column table header."""
        if not hasattr(self, "column_canvas"):
            return
        self._reset_column_table(118)
        self.column_table.grid_columnconfigure(0, weight=1)
        self.column_table.grid_rowconfigure(0, minsize=118)
        ctk.CTkLabel(self.column_table, text=text, anchor="w", justify="left",
                     text_color=self.colors["muted"], font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold")).grid(
                         row=0, column=0, sticky="new", padx=0, pady=18)

    def _create_model(self) -> None:
        """Import a model and display the candidate only after it is saved.

        Cancellation and database failures leave the previous model and workflow state in place.
        """
        if getattr(self, "current_batch_paths", []):
            self._start_batch_import()
            return
        if not self.current_file_path:
            self._show_error("Import blocked", "Select a file first.")
            return
        source_path = self.current_file_path
        importer = self._importer_for_file(source_path)
        if importer is None:
            self._show_error("Import failed", f"Only {supported_formats_text(' and ').replace('XML', 'FMMLx')} files are supported.")
            return
        selected_columns = []
        if isinstance(importer, CsvImporter):
            selected_columns = [column for column, selected in self.selected_csv_columns.items() if selected.get()]
            if not selected_columns:
                self._show_error("Import failed", "Select at least one CSV column.")
                return
            importer.select_columns(selected_columns)
        preview = self.xml_preview if isinstance(importer, XmlImporter) else None
        file_type = importer.FORMAT_NAME.upper()

        def read(_progress):
            if preview and preview.model:
                return preview.model, preview.report
            return importer.import_file(source_path)

        def failed(error):
            self._show_error("Import failed", f"The model could not be imported or saved. {save_error_message(error)}")

        def imported(result):
            model, report = result
            if report.has_problems() and not ask_import_problems(self, report, self._overlay):
                return
            if isinstance(importer, XmiImporter) and not model.get_objects():
                return
            source_file = os.path.basename(source_path)
            name = model.path_name.split("::")[-1] if model.path_name else os.path.splitext(source_file)[0]
            loaded = LoadedModel(name=self._unique_model_name(name), source_file=source_file,
                                 file_type=file_type, model=model, source_path=source_path,
                                 selected_columns=list(selected_columns),
                                 uploaded=datetime.now().strftime("%Y-%m-%d %H:%M"),
                                 last_worked_on=self._current_timestamp_text(), last_action=self.ACTION_TITLES[2])

            def save(_progress):
                self._database.store(loaded)
                try:
                    self._database.commit()
                except Exception:
                    self._database.delete(loaded.get_oid())
                    raise
                return loaded

            def saved(record):
                self.loaded_models.append(record)
                self.current_model = model
                self.current_selected_columns = selected_columns
                self.current_file_path = source_path
                self.current_file_type = file_type
                self.file_path_var.set(source_path)
                self.action_completed[1] = True
                self.action_unlocked[2] = True
                self._show_model_page()

            self._run_model_task(1, "Saving model...", save, saved, failed)

        self._run_model_task(1, "Importing model...", read, imported, failed)

    def _read_import_candidate(self, importer: ModelImporter) -> tuple[BaseMlmModel, ImportReport, List[str]]:
        """Build a candidate without replacing the active model, reusing an available XML preview."""
        selected_columns = []
        if isinstance(importer, CsvImporter):
            for column, selected in self.selected_csv_columns.items():
                if selected.get():
                    selected_columns.append(column)
            if not selected_columns:
                raise ValueError("Select at least one CSV column.")
            importer.select_columns(selected_columns)
        elif isinstance(importer, XmlImporter):
            if self.xml_preview and self.xml_preview.model:
                return self.xml_preview.model, self.xml_preview.report, selected_columns
        model, report = importer.import_file(self.current_file_path)
        return model, report, selected_columns

    def forget_deleted_database(self, name: str) -> bool:
        """Stop using a database that was deleted. Return True if it was the active database."""
        if name != self._database_name:
            return False
        self._database = None
        self._database_name = ""
        self.loaded_models = []
        self._reset_current_import_state()
        self._active_database_deleted = True
        return True

    def _unique_model_name(self, name: str) -> str:
        """Return the name, or the name with the next free number if a model already has it.

        The second model with the name "examMgmt" is called "examMgmt (2)", the third
        "examMgmt (3)", and so on. The number is part of the stored name.
        """
        used_names = [loaded.name for loaded in self.loaded_models]
        if name not in used_names:
            return name
        number = 2
        while f"{name} ({number})" in used_names:
            number = number + 1
        return f"{name} ({number})"

    def _switch_database(self) -> None:
        """Save the current database in the background before opening the chooser."""
        database = getattr(self, "_database", None)
        if database is None:
            self._choose_database(is_startup=False)
            return
        self._run_model_task(1, "Saving database...", lambda _progress: database.commit(),
                             lambda _result: self._choose_database(is_startup=False),
                             lambda error: self._show_error("Save failed", "Cannot switch databases before saving:\n" + save_error_message(error)))

    def _choose_database(self, is_startup: bool) -> bool:
        """Ask the user which database to open, open it and return True.

        Startup and the "Switch" button use the same dialog. At startup the main window is
        hidden, so the dialog has no overlay; when switching, the main window is darkened. If the
        user cancels, False is returned: at startup the caller then ends the tool, when switching
        the current database stays open. After a switch the New Model page is shown again.

        Changes are saved before switching, without checking constraints. Two running
        instances that open the same database overwrite each
        other's commits; there is no lock file against this.
        """
        overlay = None if is_startup else self._overlay
        result = ask_for_database(self, self._database_folder, overlay)
        while result is None and getattr(self, "_active_database_deleted", False):
            # Keep the UI covered and grabbed until another database is selected
            # or the user ends the application. Cancel and X mean "Close application".
            if overlay is not None:
                overlay.show()
            try:
                reopen = popup_message(
                    self, "Database deleted",
                    "The active database was deleted. Please open or create another "
                    "database to continue, or close the application.",
                    confirm=True, accept_text="Open / create database",
                    cancel_text="Close application",
                )
                if not reopen:
                    self._close_application()
                    return False
                result = ask_for_database(self, self._database_folder, overlay)
            finally:
                if overlay is not None and not self._is_closing:
                    overlay.hide()
        if result is None:
            return False
        database, name = result
        self._open_database(database, name)
        if not is_startup:
            self._show_import_page()
        return True

    def _open_database(self, database: Database, name: str) -> None:
        """Make the given database the current one and load its models.

        The open model and an unfinished import are reset, because they belong to the old
        database.
        """
        for state in getattr(self, "_batch_tabs", {}).values():
            state["button"].destroy()
        self._batch_tabs = {}
        self._active_batch_tab = None
        self._database = database
        self._active_database_deleted = False
        self._database_name = name
        self.loaded_models = database.get_all()
        self.batch_models = []
        if self.batch_tab is not None:
            self.batch_tab.grid_remove()
        for state in getattr(self, "_model_tabs", {}).values():
            state["button"].destroy()
        self._model_tabs = {}
        self._active_model_tab = None
        if hasattr(self, "model_tabs_more"):
            self.model_tabs_more.grid_remove()
        if hasattr(self, "model_tabs_container"):
            self.model_tabs_container.grid_remove()
        self._model_tabs_layout = None
        self.model_tab = None
        self._model_tab_state = None
        self._reset_current_import_state()
        self._show_database_name()

    def _show_database_name(self) -> None:
        """Show the name of the open database in the window title and in the navigation row.

        The window title is what Windows shows in the taskbar. Long names are shortened in the
        navigation row. At startup the label does not exist yet; _build_database_area() calls
        this method again after creating it.
        """
        self.title(f"Model Deepener – {self._database_name}")
        if self._database_name_label is not None:
            self._database_name_label.configure(text=self._short_tab_text(self._database_name))

    def _build_database_area(self) -> None:
        """Create the left part of the navigation row: database name, "Switch" and a divider.

        The name is only a hint and cannot be clicked. It sits on the same soft background as
        the selected tab. The "Switch" button next to it opens the database dialog.
        """
        area = ctk.CTkFrame(self.header, fg_color="transparent")
        area.grid(row=0, column=0, padx=(24, 0), pady=12)

        name_box = ctk.CTkFrame(
            area,
            height=42,
            corner_radius=8,
            fg_color=self.colors["primary_soft"],
        )
        name_box.grid(row=0, column=0)
        # The labels are lower than the box, so they do not cover its round corners.
        ctk.CTkLabel(
            name_box,
            text="Database",
            height=30,
            text_color=self.colors["muted"],
            font=ctk.CTkFont(size=11),
        ).grid(row=0, column=0, padx=(14, 6), pady=6)
        self._database_name_label = ctk.CTkLabel(
            name_box,
            text="",
            height=30,
            text_color=self.colors["primary"],
            font=ctk.CTkFont(size=14, weight="bold"),
        )
        self._database_name_label.grid(row=0, column=1, padx=(0, 14), pady=6)

        ctk.CTkButton(
            area,
            text="⇄  Switch",
            width=86,
            height=32,
            corner_radius=8,
            fg_color=self.colors["surface"],
            hover_color=self.colors["surface_alt"],
            border_width=1,
            border_color=self.colors["border"],
            text_color=self.colors["text"],
            font=ctk.CTkFont(size=13),
            command=self._switch_database,
        ).grid(row=0, column=1, padx=(8, 0))

        # A plain tk.Frame, because CustomTkinter does not draw a CTkFrame that is 1 pixel wide.
        tk.Frame(
            area,
            width=1,
            height=28,
            background=self.colors["border"],
        ).grid(row=0, column=2, padx=16)

        self._show_database_name()

    @staticmethod
    def _current_timestamp_text() -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M")

    def _commit_database(self) -> bool:
        """Save the open database. Show a message and return False if saving failed."""
        try:
            self._database.commit()
        except SAVE_ERRORS as error:
            self._show_error("Save failed", save_error_message(error))
            return False
        return True

    def _autosave_models(self) -> None:
        """Compare and save a database snapshot in a background worker."""
        database = getattr(self, "_database", None)
        if (database is not None and not getattr(self, "_model_task_active", False)
                and not getattr(self, "_autosave_in_progress", False)):
            self._autosave_in_progress = True
            results = queue.Queue()
            def save():
                try:
                    database.save_if_changed()
                    results.put(None)
                except Exception as error:
                    results.put(error)
            def finish():
                try:
                    error = results.get_nowait()
                except queue.Empty:
                    self.after(50, finish)
                    return
                self._autosave_in_progress = False
                if database is not getattr(self, "_database", None):
                    return
                if error is None:
                    self._autosave_error = None
                else:
                    message = save_error_message(error)
                    if message != getattr(self, "_autosave_error", None):
                        self._autosave_error = message
                        self._show_error("Automatic save failed", message)
            threading.Thread(target=save, daemon=True).start()
            self.after(50, finish)
        if not self._is_closing:
            self.after(2000, self._autosave_models)

    def _touch_loaded_model(self, model: Optional[BaseMlmModel]) -> None:
        """Set "Last worked on" of the stored model to the current time.

        Nothing happens if the model is None or does not belong to a stored model.
        """
        if model is None:
            return
        for loaded in self.loaded_models:
            if loaded.model is model:
                timestamp = self._current_timestamp_text()
                if loaded.last_worked_on != timestamp:
                    loaded.last_worked_on = timestamp
                break

    def _set_last_action(self, action: int) -> None:
        """Set the title of the given workflow step as the last action.

        The title is stored in last_action_label and, if a stored model is open, in its
        last_action.
        """
        self.last_action_label = self.ACTION_TITLES.get(action, "Imported")
        if self.current_model is None:
            return
        for loaded in self.loaded_models:
            if loaded.model is self.current_model:
                if loaded.last_action != self.last_action_label:
                    loaded.last_action = self.last_action_label
                break

    def _populate_model_tree(
            self,
            model: BaseMlmModel,
            query: str = "",
    ):
        """
        Fills the Model Structure tree in Inspect Model.

        The methods in this block insert classes, objects, enums, and search
        hits into the tree and open the matching Details view when the user
        selects an entry.
        """
        self.tree_item_payload.clear()
        self.tree_item_view.clear()
        self._lazy_tree_groups = {}
        self._clear_tree(self.model_tree)

        normalized_query = query.strip().lower()

        root_text = self._display_table_value(model.path_name or os.path.basename(
            self.current_file_path or "Model"
        ))
        root_id = self.model_tree.insert(
            "",
            "end",
            text=f"Model: {root_text}",
            open=True,
            tags=("model_root",),
        )
        self.tree_item_payload[root_id] = model
        self.tree_item_view[root_id] = "model"

        enumerations = [
            enum
            for enum in model.enums
            if self._enum_matches_search(enum, normalized_query)
        ]

        enum_id = self.model_tree.insert(
            root_id,
            "end",
            text=f"Enumeration Types ({len(enumerations)})",
            open=bool(normalized_query),
            tags=("enum_group",),
        )
        self.tree_item_payload[enum_id] = None
        self.tree_item_view[enum_id] = "group"

        sorted_enums = sorted(enumerations, key=lambda item: self._natural_sort_key(item.name))
        if normalized_query:
            self._populate_lazy_tree_group(enum_id, ("enums", model, sorted_enums, normalized_query))
        elif sorted_enums:
            self._defer_tree_group(enum_id, ("enums", model, sorted_enums, ""))

        levels = sorted({obj.level for obj in model.mlm_objects}, reverse=True)
        for level in levels:
            level_objects = [
                obj
                for obj in model.mlm_objects
                if obj.level == level and self._object_matches_search(model, obj, normalized_query)
            ]
            level_id = self.model_tree.insert(
                root_id,
                "end",
                text=f"Level {level} ({len(level_objects)})",
                open=bool(normalized_query),
                tags=("level_object" if level == 0 else "level_class",),
            )
            self.tree_item_payload[level_id] = None
            self.tree_item_view[level_id] = "group"

            sorted_objects = sorted(
                level_objects,
                key=lambda item: self._natural_sort_key(item.name),
            )
            group = ("objects", model, sorted_objects, normalized_query)
            if normalized_query:
                self._populate_lazy_tree_group(level_id, group)
            elif sorted_objects:
                self._defer_tree_group(level_id, group)

        self.model_tree.selection_remove(
            self.model_tree.selection()
        )
        self.model_tree.yview_moveto(0)

    def _defer_tree_group(self, item_id: str, data: tuple) -> None:
        """Add an expansion marker for a group whose children are not yet displayed."""
        self._lazy_tree_groups[item_id] = data
        self.model_tree.insert(item_id, "end", text="")

    def _open_model_tree_group(self, _event) -> None:
        """Create a group's children when it is first expanded."""
        item_id = self.model_tree.focus()
        group = self._lazy_tree_groups.pop(item_id, None)
        if group is not None:
            self.model_tree.delete(*self.model_tree.get_children(item_id))
            self._populate_lazy_tree_group(item_id, group)

    def _populate_lazy_tree_group(self, parent_id: str, group: tuple) -> None:
        kind, model, items, query = group
        if kind == "enums":
            for enum in items:
                item_id = self.model_tree.insert(parent_id, "end", text=enum.name, open=False,
                                                 tags=(self._import_note_tag(enum) or "enum_item",))
                self.tree_item_payload[item_id] = enum
                self.tree_item_view[item_id] = "enumeration"
                self._insert_enum_search_hits(item_id, enum, query)
            return
        visible = items[:100] if items and items[0].level == 0 and not query else items
        for obj in visible:
            self._insert_model_tree_object(parent_id, model, obj, query)
        if len(visible) < len(items):
            self._insert_model_tree_load_more(parent_id, model, items, len(visible))

    def _insert_model_tree_object(self, parent_id: str, model: BaseMlmModel,
                                  obj: BaseMlmObject, query: str):
        """Adds one class or object to the structure tree with its search hits."""
        obj_id = self.model_tree.insert(
            parent_id,
            "end",
            text=obj.name,
            open=bool(query),
            tags=(self._import_note_tag(obj) or ("object_item" if obj.level == 0 else "class_item"),),
        )
        self.tree_item_payload[obj_id] = obj
        self.tree_item_view[obj_id] = "object" if obj.level == 0 else "class"
        self._insert_object_search_hits(obj_id, model, obj, query)

    def _insert_model_tree_load_more(self, parent_id: str, model: BaseMlmModel,
                                     objects: List[BaseMlmObject], next_index: int):
        """Adds a tree entry that loads the next 100 Level 0 objects on demand."""
        remaining = len(objects) - next_index
        item_id = self.model_tree.insert(
            parent_id,
            "end",
            text=f"Load 100 more objects... ({remaining} remaining)",
            tags=("enum_group",),
        )
        self.tree_item_payload[item_id] = (
            "load_more_objects",
            model,
            objects,
            next_index,
            parent_id,
        )
        self.tree_item_view[item_id] = "load_more"

    def _load_more_model_tree_objects(self, item_id: str, payload: tuple):
        """Replaces the load-more entry with the next object batch and a new entry."""
        _, model, objects, start_index, parent_id = payload
        self.model_tree.delete(item_id)
        self.tree_item_payload.pop(item_id, None)
        self.tree_item_view.pop(item_id, None)
        end_index = min(start_index + 100, len(objects))
        for obj in objects[start_index:end_index]:
            self._insert_model_tree_object(parent_id, model, obj, "")
        if end_index < len(objects):
            self._insert_model_tree_load_more(parent_id, model, objects, end_index)
        self.model_tree.item(parent_id, open=True)

    def _object_matches_search(self, model: BaseMlmModel, obj: BaseMlmObject, query: str) -> bool:
        """Search names, properties and relationships to decide whether an object matches the query."""
        if not query:
            return True
        values = [obj.name, obj.full_name]
        for attr in obj.get_regular_attributes():
            values.append(attr.name)
            values.append(attr.attr_type_str_short)
        object_operations = self._operations_for_object(obj)
        for operation in object_operations:
            values.append(operation.operation_name)
            values.append(operation.return_type)
        for slot in obj.get_regular_slots():
            values.append(slot.name)
            values.append(slot.get_value_as_text())
        for parent in obj.parent_classes:
            values.append(parent.name)
        for candidate in model.mlm_objects:
            if obj in candidate.parent_classes:
                values.append(candidate.name)
        for association in self._associations_for_class(model, obj):
            values.append("association")
            values.extend(
                [
                    association.name,
                    self._name(association.source_object),
                    self._name(association.target_object),
                    association.get_source_access_name(),
                    association.get_target_access_name(),
                    self._association_multiplicity_text(association),
                ]
            )
        for link in self._links_for_object(model, obj):
            values.append("link")
            values.extend(
                [
                    link.name,
                    self._name(link.source_object),
                    self._name(link.target_object),
                    *self._link_access_names(link),
                ]
            )
        if object_operations:
            values.append("operation")
        if self._generalization_rows(obj):
            values.extend(["generalization", "superclass", "subclass"])
        for value in values:
            if value is not None and query in str(value).lower():
                return True
        return False

    def _insert_object_search_hits(self, parent_id: str, model: BaseMlmModel, obj: BaseMlmObject, query: str) -> None:
        """Add matching properties and relationships below an object in the search tree."""
        if not query:
            return
        hit_groups = [
            ("Attributes", "attribute", [
                attr for attr in obj.get_regular_attributes()
                if self._query_matches_values(query, attr.name, attr.attr_type_str_short, attr.inst_level)
            ]),
            ("Slots", "slot", [
                slot for slot in obj.get_regular_slots()
                if self._query_matches_values(query, slot.name, slot.get_value_as_text(), self._slot_type(slot))
            ]),
            ("Associations", "association", [
                association for association in self._associations_for_class(model, obj)
                if query == "association" or self._query_matches_values(
                    query,
                    association.name,
                    self._name(association.source_object),
                    self._name(association.target_object),
                    association.get_source_access_name(),
                    association.get_target_access_name(),
                    self._association_multiplicity_text(association),
                )
            ]),
            ("Links", "link", [
                link for link in self._links_for_object(model, obj)
                if query == "link" or self._query_matches_values(
                    query,
                    link.name,
                    self._name(link.source_object),
                    self._name(link.target_object),
                    *self._link_access_names(link),
                )
            ]),
            ("Operations", "operation", [
                operation for operation in self._operations_for_object(obj)
                if query == "operation" or self._query_matches_values(query, operation.operation_name, operation.return_type)
            ]),
            ("Generalization", "generalization", [
                row for row in self._generalization_rows(obj)
                if query in {"generalization", "superclass", "subclass"} or self._query_matches_values(query, *row)
            ]),
        ]
        for group_label, view_name, hits in hit_groups:
            if obj.level == 0 and view_name == "operation":
                continue
            if not hits:
                continue
            group_id = self.model_tree.insert(parent_id, "end", text=f"{group_label} ({len(hits)})", open=True)
            self.tree_item_payload[group_id] = None
            self.tree_item_view[group_id] = "group"
            for hit in hits:
                text = self._search_hit_text(view_name, hit)
                tag = self._import_note_tag(hit)
                item_id = self.model_tree.insert(group_id, "end", text=text, open=False,
                                                 tags=(tag,) if tag else ())
                self.tree_item_payload[item_id] = (view_name, obj, hit)
                self.tree_item_view[item_id] = view_name

    def _insert_enum_search_hits(self, parent_id: str, enum: BaseMlmEnumType, query: str):
        if not query:
            return
        matching_values = [
            value
            for value in enum.enum_values
            if self._query_matches_values(query, value)
        ]
        if not matching_values:
            return
        group_id = self.model_tree.insert(parent_id, "end", text=f"Slots ({len(matching_values)})", open=True)
        self.tree_item_payload[group_id] = None
        self.tree_item_view[group_id] = "group"
        for value in matching_values:
            notes = enum.get_import_notes_for(f"value:{value}")
            tag = "serious_adaptation" if any(serious for _text, serious in notes) else "automatic_adaptation"
            item_id = self.model_tree.insert(group_id, "end", text=str(value), open=False,
                                             tags=(tag,) if notes else ())
            self.tree_item_payload[item_id] = ("enum_value", enum, value)
            self.tree_item_view[item_id] = "enum_value"

    @staticmethod
    def _query_matches_values(query: str, *values: Any) -> bool:
        """Accept a search hit when any nonempty display value contains the query."""
        for value in values:
            if value is not None and query in str(value).lower():
                return True
        return False

    def _search_hit_text(self, view_name: str, hit: Any) -> str:
        """Format the selected kind of search hit for its tree label."""
        if view_name == "attribute":
            return f"{hit.name}: {hit.attr_type_str_short}"
        if view_name == "slot":
            return f"{hit.name}: {self._display_table_value(hit.get_value_as_text())}"
        if view_name == "association":
            return f"{hit.name}: {self._name(hit.source_object)} → {self._name(hit.target_object)}"
        if view_name == "link":
            return f"{hit.name}: {self._name(hit.source_object)} → {self._name(hit.target_object)}"
        if view_name == "operation":
            return f"{hit.operation_name}: {self._short_type_name(hit.return_type)}"
        if view_name == "generalization":
            return f"{hit[0]} → {hit[1]}"
        return str(hit)

    @staticmethod
    def _enum_matches_search(enum: BaseMlmEnumType, query: str) -> bool:
        if not query:
            return True
        values = [enum.name] + list(enum.enum_values)
        return any(query in str(value).lower() for value in values)

    def _filter_model_tree(self, _event=None):
        if self.current_model is None:
            return

        query = self.model_search_var.get()
        self._cancel_detail_loading()
        self._populate_model_tree(
            self.current_model,
            query=query,
        )
        self._render_empty_detail_state()

    def _show_selected_details(self, _event):
        selected = self.model_tree.selection()
        if not selected:
            self._cancel_detail_loading()
            self._render_empty_detail_state()
            return

        payload = self.tree_item_payload.get(selected[0])
        selected_view = self.tree_item_view.get(selected[0], "")
        self._cancel_detail_loading()

        if isinstance(payload, tuple) and payload and payload[0] == "load_more_objects":
            self._load_more_model_tree_objects(selected[0], payload)
            self._render_empty_detail_state()
        elif isinstance(payload, BaseMlmModel):
            self._start_model_overview_loading(payload)
        elif isinstance(payload, BaseMlmObject):
            if selected_view == "class":
                self._render_class_details(payload)
            elif selected_view == "object":
                self._render_object_details(payload)
            else:
                self._render_empty_detail_state()
        elif isinstance(payload, BaseMlmEnumType):
            self._render_enum_details(payload)
        elif isinstance(payload, tuple):
            self._render_search_hit_details(payload)
        else:
            self._render_empty_detail_state()

    def _render_search_hit_details(self, payload: tuple) -> None:
        """Show the detail view belonging to the selected property or relationship search hit."""
        view_name = payload[0] if payload else ""
        if view_name == "attribute":
            _view, obj, attr = payload
            self.detail_title.configure(text=f"Attribute: {attr.name}", text_color="#7C3AED")
            self.detail_subtitle.configure(text=f"Defined on {obj.name}.")
            self._render_detail_table(
                ("Attribute", "Type", "Slot"),
                [(attr.name, attr.attr_type_str_short, "-")],
            )
        elif view_name == "slot":
            _view, obj, slot = payload
            self.detail_title.configure(text=f"Slot: {slot.name}", text_color="#16A34A")
            self.detail_subtitle.configure(text=f"Defined on {obj.name}.")
            self._render_detail_table(
                ("Attribute", "Type", "Slot"),
                [(slot.name, self._slot_type(slot), slot.get_value_as_text())],
            )
        elif view_name == "association":
            _view, _obj, association = payload
            self.detail_title.configure(text=f"Association: {association.name}", text_color="#64748B")
            self.detail_subtitle.configure(text="Matching association.")
            self._render_detail_table(
                self.ASSOCIATION_TABLE_HEADERS,
                [self._association_table_row(association)],
                highlight_column=self.ASSOCIATION_TABLE_HEADERS.index("Multiplicity"),
            )
        elif view_name == "link":
            _view, _obj, link = payload
            self.detail_title.configure(text=f"Link: {link.name}", text_color="#0891B2")
            self.detail_subtitle.configure(text="Matching link.")
            self._render_detail_table(
                ("Linkname", "Source", "Target", "Multiplicity"),
                [(link.name, self._name(link.source_object), self._name(link.target_object), "-")],
                highlight_column=3,
            )
        elif view_name == "operation":
            _view, obj, operation = payload
            self.detail_title.configure(text=f"Operation: {operation.operation_name}", text_color="#0D9488")
            self.detail_subtitle.configure(text=f"Defined for {obj.name}.")
            slot_by_name = {slot.name: slot.get_value_as_text() for slot in obj.get_regular_slots()}
            self._render_detail_table(
                ("Operation", "Type", "Slot"),
                [(operation.operation_name, self._short_type_name(operation.return_type), slot_by_name.get(operation.operation_name, "-"))],
            )
        elif view_name == "generalization":
            _view, _obj, row = payload
            self.detail_title.configure(text="Generalization", text_color="#E11D48")
            self.detail_subtitle.configure(text="Matching generalization.")
            self._render_detail_table(("Superclass", "Subclass"), [row])
        elif view_name == "enum_value":
            _view, enum, value = payload
            self.detail_title.configure(text=f"Enumeration Type: {enum.name}", text_color="#F59E0B")
            self.detail_subtitle.configure(text="Matching enumeration type slot.")
            self._render_detail_table(("Enumeration Type", "Slot", "Index"),
                                      [(enum.name, value, enum.enum_values.index(value) + 1)],
                                      cell_elements=[[(enum, "name"), (enum, f"value:{value}"), None]])
        else:
            self._render_empty_detail_state()

    def _cancel_detail_loading(self):
        # Stop any background-like loading work that is still scheduled in Tk.
        # This prevents old loading jobs from drawing into a view the user has already left.
        self._detail_load_token = getattr(self, "_detail_load_token", 0) + 1
        self._clear_detail_option_bar()

        batch_id = getattr(self, "_detail_batch_after_id", None)
        if batch_id is not None:
            try:
                self.after_cancel(batch_id)
            except tk.TclError:
                # Tk can complain if the scheduled job has already disappeared. That is harmless here.
                pass
            self._detail_batch_after_id = None

        progress_id = getattr(self, "_detail_progress_after_id", None)
        if progress_id is not None:
            try:
                self.after_cancel(progress_id)
            except tk.TclError:
                pass
            self._detail_progress_after_id = None

        staging_table = getattr(self, "_detail_staging_table", None)
        staging_was_current = (
            staging_table is not None
            and getattr(self, "detail_table", None) is staging_table
        )
        if staging_table is not None and staging_table.winfo_exists():
            staging_table.destroy()
        self._detail_staging_table = None
        staging_window = getattr(self, "_detail_staging_window", None)
        if staging_window is not None and hasattr(self, "detail_canvas"):
            try:
                self.detail_canvas.delete(staging_window)
            except tk.TclError:
                # The temporary canvas item may already be gone after a screen refresh.
                pass
        self._detail_staging_window = None
        self._pending_overview_rows = []

        panel = getattr(self, "_detail_loading_panel", None)
        if panel is not None and panel.winfo_exists():
            try:
                if hasattr(self, "detail_loading_bar"):
                    self.detail_loading_bar.stop()
            except tk.TclError:
                # The progress bar may already have been destroyed while the screen was changing.
                pass
            panel.destroy()
        self._detail_loading_panel = None
        toolbar = getattr(self, "_detail_overview_toolbar", None)
        if toolbar is not None and toolbar.winfo_exists():
            toolbar.destroy()
        self._detail_overview_toolbar = None
        self._detail_progress_determinate = False
        overview_canvas_was_current = getattr(
            self,
            "_detail_canvas_overview_loading",
            False,
        )
        self._detail_canvas_overview_loading = False
        if staging_was_current or overview_canvas_was_current or (
            hasattr(self, "detail_table")
            and not self.detail_table.winfo_exists()
        ):
            self._reset_detail_canvas_table()

    def _schedule_detail_batch(self, token: int, delay_ms: int, callback):
        if token != getattr(self, "_detail_load_token", None):
            return
        self._detail_batch_after_id = self.after(delay_ms, callback)

    def _start_model_overview_loading(self, model: BaseMlmModel):
        """
        Starts loading the large Model Overview table in Inspect Model.

        This block asks how many objects should be shown, prepares the values,
        shows progress, and draws the large object/value table in batches.
        """
        self._show_model_overview_load_options(model)

    @staticmethod
    def _attach_active_model_reference(model: BaseMlmModel):
        for obj in model.mlm_objects:
            obj._active_model = model

    def _show_model_overview_load_options(self, model: BaseMlmModel) -> None:
        """Build the attribute and object selection controls before loading an overview."""
        self._detail_load_token = getattr(self, "_detail_load_token", 0) + 1

        self.detail_title.configure(
            text="Model Overview",
            text_color=self.colors["text"],
        )
        self.detail_subtitle.configure(
            text="Choose how many objects should be loaded into the overview."
        )

        class_objects = [
            obj
            for obj in model.mlm_objects
            if obj.level > 0 and obj.get_regular_attributes()
        ]
        attributes = class_objects[0].get_regular_attributes() if class_objects else []
        objects = [
            obj
            for obj in model.mlm_objects
            if obj.level == 0
        ]
        objects = sorted(
            objects,
            key=lambda item: self._natural_sort_key(item.name),
        )
        if not objects:
            self._render_model_structure_overview(model)
            return

        self._reset_detail_canvas_table()
        previous_header = getattr(self, "_detail_sticky_header", None)
        if previous_header is not None and previous_header.winfo_exists():
            previous_header.destroy()
        self._detail_sticky_header = None
        for child in self.detail_table.winfo_children():
            child.destroy()

        panel = ctk.CTkFrame(
            self.detail_table,
            fg_color=self.colors["surface_alt"],
            corner_radius=8,
            border_width=1,
            border_color="#D8E3F5",
        )
        panel.grid(row=0, column=0, sticky="new", padx=18, pady=18)
        panel.grid_columnconfigure(1, weight=1)

        total_objects = len(objects)
        total_cells = (total_objects + 1) * (len(attributes) + 1)

        ctk.CTkLabel(
            panel,
            text="Load model overview",
            text_color=self.colors["text"],
            anchor="w",
            font=ctk.CTkFont(family="Segoe UI", size=15, weight="bold"),
        ).grid(row=0, column=0, columnspan=2, sticky="ew", padx=18, pady=(16, 6))

        ctk.CTkLabel(
            panel,
            text=f"The model contains {total_objects} objects and {total_cells} cells if fully loaded.",
            text_color=self.colors["muted"],
            anchor="w",
            font=ctk.CTkFont(family="Segoe UI", size=12),
        ).grid(row=1, column=0, columnspan=2, sticky="ew", padx=18, pady=(0, 16))

        ctk.CTkLabel(
            panel,
            text="Number of objects",
            text_color=self.colors["text"],
            anchor="w",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
        ).grid(row=2, column=0, sticky="w", padx=(18, 14), pady=(0, 12))

        self.model_overview_count_var = tk.StringVar(value="")
        count_buttons = ctk.CTkFrame(
            panel,
            fg_color="transparent",
        )
        count_buttons.grid(row=2, column=1, sticky="w", padx=(0, 18), pady=(0, 12))
        self._model_overview_count_buttons = {}
        object_count_options = (5, 10, 15, 20, 50, 100)
        default_count = None
        for count in object_count_options:
            if total_objects >= count:
                default_count = count
                break
        for index, count in enumerate(object_count_options):
            enabled = total_objects >= count
            button = ctk.CTkButton(
                count_buttons,
                text=str(count),
                width=54,
                height=32,
                corner_radius=7,
                border_width=1,
                font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
                state="normal" if enabled else "disabled",
                command=lambda value=count: self._set_model_overview_count(value),
            )
            button.grid(row=0, column=index, padx=(0 if index == 0 else 8, 0))
            self._model_overview_count_buttons[count] = button
        if default_count is not None:
            self._set_model_overview_count(default_count)
        else:
            self._refresh_model_overview_count_buttons()

        ctk.CTkLabel(
            panel,
            text="Selection",
            text_color=self.colors["text"],
            anchor="w",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
        ).grid(row=3, column=0, sticky="w", padx=(18, 14), pady=(0, 18))

        self.model_overview_selection_var = tk.StringVar(value="From start")
        selection_frame = ctk.CTkFrame(
            panel,
            fg_color="transparent",
        )
        selection_frame.grid(row=3, column=1, sticky="w", padx=(0, 18), pady=(0, 18))
        self._model_overview_mode_buttons = {}
        for index, label in enumerate(("From start", "From end", "Random")):
            button = ctk.CTkButton(
                selection_frame,
                text=label,
                width=92,
                height=32,
                corner_radius=7,
                border_width=1,
                font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
                command=lambda value=label: self._set_model_overview_selection_mode(value),
            )
            button.grid(row=0, column=index, padx=(0 if index == 0 else 8, 0))
            self._model_overview_mode_buttons[label] = button
        self._set_model_overview_selection_mode("From start")

        ctk.CTkButton(
            panel,
            text="Load Overview",
            width=150,
            height=38,
            corner_radius=8,
            fg_color=self.colors["primary"],
            hover_color=self.colors["primary_hover"],
            text_color="#FFFFFF",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            state="normal" if default_count is not None else "disabled",
            command=lambda: self._start_model_overview_loading_with_options(
                model=model,
                attributes=attributes,
                objects=objects,
            ),
        ).grid(row=4, column=1, sticky="w", padx=(0, 18), pady=(0, 18))

        self.detail_table.update_idletasks()
        self.detail_canvas.itemconfigure(
            self.detail_canvas_window,
            width=max(self.detail_canvas.winfo_width(), 700),
        )
        self.detail_canvas.configure(scrollregion=self.detail_canvas.bbox("all"))
        self._update_detail_x_scrollbar_visibility()
        self.detail_canvas.xview_moveto(0)
        self.detail_canvas.yview_moveto(0)

    def _render_model_structure_overview(self, model: BaseMlmModel):
        self._clear_detail_option_bar()
        self.detail_title.configure(
            text="Model Overview",
            text_color=self.colors["text"],
        )
        self.detail_subtitle.configure(
            text="Complete model structure grouped by level."
        )
        rows = []
        for obj in sorted(
                model.mlm_objects,
                key=lambda item: (-item.level, self._natural_sort_key(item.name)),
        ):
            rows.append(
                (
                    f"Level {obj.level}",
                    obj.name,
                    self._name(obj.class_of_object),
                    self._model_structure_content_text(model, obj),
                )
            )
        self._render_detail_table(
            ("Level", "Element", "Type", "Content"),
            rows,
            highlight_column=0,
            column_weights=[1, 2, 1, 5],
            column_minsizes=[110, 180, 150, 520],
        )

    def _model_structure_content_text(self, model: BaseMlmModel, obj: BaseMlmObject) -> str:
        """Summarize the properties and relationships available on one model object."""
        parts = [f"{len(obj.get_regular_attributes())} attributes"]
        associations = self._associations_for_class(model, obj)
        if associations:
            parts.append(f"{len(associations)} associations")
        links = self._links_for_object(model, obj)
        if links:
            parts.append(f"{len(links)} links")
        if obj.get_regular_slots():
            parts.append(f"{len(obj.get_regular_slots())} slots")
        return ", ".join(parts)

    def _set_model_overview_count(self, count: int):
        self.model_overview_count_var.set(str(count))
        self._refresh_model_overview_count_buttons()

    def _refresh_model_overview_count_buttons(self):
        selected = self.model_overview_count_var.get()
        for count, button in getattr(self, "_model_overview_count_buttons", {}).items():
            if str(count) == selected:
                button.configure(
                    fg_color=self.colors["primary"],
                    hover_color=self.colors["primary_hover"],
                    border_color=self.colors["primary"],
                    text_color="#FFFFFF",
                )
            else:
                button.configure(
                    fg_color="#FFFFFF",
                    hover_color=self.colors["primary_soft"],
                    border_color="#BBD0F4",
                    text_color=self.colors["text"],
                )

    def _set_model_overview_selection_mode(self, value: str):
        self.model_overview_selection_var.set(value)
        buttons = getattr(self, "_model_overview_mode_buttons", {})
        for label, button in buttons.items():
            if label == value:
                button.configure(
                    fg_color=self.colors["primary"],
                    hover_color=self.colors["primary_hover"],
                    border_color=self.colors["primary"],
                    text_color="#FFFFFF",
                )
            else:
                button.configure(
                    fg_color="#FFFFFF",
                    hover_color=self.colors["primary_soft"],
                    border_color="#BBD0F4",
                    text_color=self.colors["text"],
                )

    def _start_model_overview_loading_with_options(
            self,
            model: BaseMlmModel,
            attributes: List[BaseMlmAttribute],
            objects: List[BaseMlmObject],
    ):
        try:
            requested_count = int(self.model_overview_count_var.get().strip())
        except ValueError:
            self._show_error(
                "Invalid object count",
                "Enter a whole number of objects to load.",
            )
            return

        if requested_count <= 0:
            self._show_error(
                "Invalid object count",
                "Enter at least 1 object to load.",
            )
            return

        selected_objects = self._select_model_overview_objects(
            objects=objects,
            count=min(requested_count, len(objects)),
            mode={
                "From start": "from_start",
                "From end": "from_end",
                "Random": "random",
            }.get(self.model_overview_selection_var.get(), "from_start"),
        )
        self._current_overview_model = model
        self._current_overview_attributes = attributes
        self._current_overview_objects = objects

        self._detail_load_token = getattr(self, "_detail_load_token", 0) + 1
        token = self._detail_load_token

        self.detail_title.configure(
            text="Model Overview",
            text_color=self.colors["text"],
        )
        self.detail_subtitle.configure(
            text="Preparing the complete model overview."
        )

        self._reset_detail_canvas_table()
        self._pending_overview_rows = []
        self._pending_overview_model_name = self._model_overview_display_name(model)
        self._pending_overview_attributes = attributes
        self._detail_progress_loaded = 0
        self._detail_progress_total = len(selected_objects)
        self._detail_progress_work_loaded = 0
        self._detail_progress_work_total = max(
            1,
            (len(selected_objects) + 1) * (len(attributes) + 1),
        )
        self._detail_progress_determinate = True
        self._detail_progress_phase = "preparing"

        self._detail_progress_after_id = self.after(
            500,
            lambda: self._show_model_loading_progress(
                token=token,
                total=self._detail_progress_work_total,
            ),
        )

        self._schedule_detail_batch(
            token,
            1,
            lambda: self._prepare_model_overview_batch(
                token=token,
                attributes=attributes,
                objects=selected_objects,
                start_index=0,
            ),
        )

    def _select_model_overview_objects(
            self,
            objects: List[BaseMlmObject],
            count: int,
            mode: str,
    ) -> List[BaseMlmObject]:
        if mode == "from_end":
            return objects[-count:]
        if mode == "random":
            return sorted(
                random.sample(objects, count),
                key=lambda item: self._natural_sort_key(item.name),
            )
        return objects[:count]

    def _show_model_loading_progress(self, token: int, total: int):
        if token != getattr(self, "_detail_load_token", None):
            return
        self._detail_progress_after_id = None

        existing = getattr(self, "_detail_loading_panel", None)
        if existing is not None and existing.winfo_exists():
            existing.destroy()

        panel = ctk.CTkFrame(
            self.detail_table_wrapper,
            fg_color="#FFFFFF",
            corner_radius=0,
            border_width=0,
        )
        panel.place(x=0, y=0, relwidth=1, relheight=1)
        panel.grid_columnconfigure(0, weight=1)
        panel.grid_rowconfigure(0, weight=1)

        loading_panel = ctk.CTkFrame(
            panel,
            fg_color="#FFFFFF",
            corner_radius=12,
            border_width=1,
            border_color=self.colors["border"],
            height=230,
        )
        loading_panel.place(
            relx=0.5,
            rely=0.5,
            anchor="center",
            relwidth=0.68,
        )
        loading_panel.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            loading_panel,
            text="Loading Data...",
            text_color=self.colors["text"],
            font=ctk.CTkFont(
                family="Segoe UI",
                size=17,
                weight="bold",
            ),
        ).grid(
            row=0,
            column=0,
            pady=(26, 6),
        )

        self.detail_loading_message_label = ctk.CTkLabel(
            loading_panel,
            text="Preparing the complete model overview. Please wait...",
            text_color=self.colors["muted"],
            font=ctk.CTkFont(
                family="Segoe UI",
                size=12,
            ),
        )
        self.detail_loading_message_label.grid(
            row=1,
            column=0,
            pady=(0, 18),
        )

        progress_row = ctk.CTkFrame(
            loading_panel,
            fg_color="transparent",
        )
        progress_row.grid(
            row=2,
            column=0,
            sticky="ew",
            padx=34,
        )
        progress_row.grid_columnconfigure(0, weight=1)

        self.detail_loading_bar = ctk.CTkProgressBar(
            progress_row,
            mode="determinate",
            height=13,
            corner_radius=7,
            progress_color=self.colors["primary"],
        )
        self.detail_loading_bar.grid(
            row=0,
            column=0,
            sticky="ew",
            padx=(0, 14),
        )
        self.detail_loading_bar.set(0)

        self.detail_loading_total_label = ctk.CTkLabel(
            progress_row,
            text=f"Total: {total} cells",
            text_color=self.colors["muted"],
            font=ctk.CTkFont(
                family="Segoe UI",
                size=11,
                weight="bold",
            ),
        )
        self.detail_loading_total_label.grid(
            row=0,
            column=1,
            sticky="e",
        )

        self.detail_loading_count_label = ctk.CTkLabel(
            loading_panel,
            text=f"0 of {total} cells loaded",
            text_color=self.colors["muted"],
            font=ctk.CTkFont(
                family="Segoe UI",
                size=12,
            ),
        )
        self.detail_loading_count_label.grid(
            row=3,
            column=0,
            pady=(12, 0),
        )

        ctk.CTkButton(
            loading_panel,
            text="Cancel Loading",
            width=146,
            height=36,
            corner_radius=8,
            fg_color="#FFFFFF",
            hover_color="#FEF2F2",
            border_width=1,
            border_color="#FCA5A5",
            text_color="#DC2626",
            font=ctk.CTkFont(
                family="Segoe UI",
                size=11,
                weight="bold",
            ),
            command=self._cancel_model_overview_loading,
        ).grid(
            row=4,
            column=0,
            pady=(18, 20),
        )

        self._detail_loading_panel = panel
        panel.lift()
        self._refresh_determinate_progress_display(token)

        # Force Tk to paint the loading layer before the first data batch starts.
        self.update_idletasks()

    def _refresh_determinate_progress_display(self, token: int):
        if token != getattr(self, "_detail_load_token", None):
            return
        if not getattr(self, "_detail_progress_determinate", False):
            return

        panel = getattr(self, "_detail_loading_panel", None)
        if panel is None or not panel.winfo_exists():
            return

        loaded = getattr(self, "_detail_progress_loaded", 0)
        total = getattr(self, "_detail_progress_total", 0)
        work_loaded = getattr(self, "_detail_progress_work_loaded", loaded)
        work_total = getattr(self, "_detail_progress_work_total", total)
        fraction = 1.0 if work_total == 0 else min(1.0, work_loaded / work_total)
        # "phase" tells the user whether the app is still preparing data or already drawing it.
        phase = getattr(self, "_detail_progress_phase", "loading")
        message = (
            "Preparing the complete model overview. Please wait..."
            if phase == "preparing"
            else "Loading the complete model overview. Please wait..."
        )
        self.detail_loading_bar.set(fraction)
        self.detail_loading_message_label.configure(
                text=message
        )
        self.detail_loading_count_label.configure(
            text=f"{work_loaded} of {work_total} cells loaded"
        )

    def _cancel_model_overview_loading(self):
        self._cancel_detail_loading()
        self.detail_title.configure(
            text="Loading cancelled",
            text_color=self.colors["text"],
        )
        self.detail_subtitle.configure(
            text="Select the model again to restart loading."
        )

        for child in self.detail_table.winfo_children():
            child.destroy()

        ctk.CTkLabel(
            self.detail_table,
            text="Model overview loading was cancelled.",
            text_color=self.colors["muted"],
            font=ctk.CTkFont(
                family="Segoe UI",
                size=13,
                weight="bold",
            ),
        ).grid(
            row=0,
            column=0,
            padx=30,
            pady=40,
        )

    def _update_model_loading_progress(
            self,
            token: int,
            loaded: int,
            total: int,
            phase: str = "loading",
            work_loaded: Optional[int] = None,
            work_total: Optional[int] = None,
    ):
        # Store the latest loading numbers so the progress bar and message stay in sync.
        if token != getattr(self, "_detail_load_token", None):
            return

        self._detail_progress_total = total
        if work_loaded is None:
            work_loaded = loaded
        if work_total is None:
            work_total = max(1, total)
        self._detail_progress_work_loaded = min(work_loaded, work_total)
        self._detail_progress_work_total = max(1, work_total)
        self._detail_progress_loaded = loaded
        self._detail_progress_phase = phase
        self._refresh_determinate_progress_display(token)

    def _prepare_model_overview_batch(
            self,
            token: int,
            attributes: List[BaseMlmAttribute],
            objects: List[BaseMlmObject],
            start_index: int,
    ) -> None:
        """Prepare one bounded batch of slot rows and schedule the next batch without blocking the UI."""
        self._detail_batch_after_id = None
        if token != getattr(self, "_detail_load_token", None):
            return

        batch_size = 40
        end_index = min(start_index + batch_size, len(objects))

        for object_index in range(start_index, end_index):
            obj = objects[object_index]
            slot_by_name = {
                slot.name: slot.get_value_as_text()
                for slot in obj.get_regular_slots()
            }
            row_values = [
                slot_by_name.get(attr.name, "-")
                for attr in attributes
            ]
            self._pending_overview_rows.append(
                (obj.name, row_values)
            )

        self._update_model_loading_progress(
            token=token,
            loaded=end_index,
            total=len(objects),
            phase="preparing",
            work_loaded=min(
                getattr(self, "_detail_progress_work_total", len(objects)),
                (end_index + 1) * (len(attributes) + 1),
            ),
            work_total=getattr(self, "_detail_progress_work_total", len(objects)),
        )

        if end_index < len(objects):
            self._schedule_detail_batch(
                token,
                1,
                partial(self._prepare_model_overview_batch,
                    token=token,
                    attributes=attributes,
                    objects=objects,
                    start_index=end_index,
                ),
            )
        else:
            self._finish_preparing_model_overview(token)

    def _finish_preparing_model_overview(self, token: int):
        if token != getattr(self, "_detail_load_token", None):
            return

        self._begin_prepared_model_overview_render(
            token=token,
            model_name=self._pending_overview_model_name,
            attributes=self._pending_overview_attributes,
            prepared_rows=self._pending_overview_rows,
        )

    def _begin_prepared_model_overview_render(
            self,
            token: int,
            model_name: str,
            attributes: List[BaseMlmAttribute],
            prepared_rows: list,
            column_widths: Optional[list[int]] = None,
    ):
        if token != getattr(self, "_detail_load_token", None):
            return

        if not hasattr(self, "_table_column_widths"):
            self._table_column_widths = {}
        width_key = ("overview",)
        default = [220] + [180] * len(attributes)
        previous = column_widths if column_widths is not None else self._table_column_widths.get(width_key, default)
        previous = [previous[index] if index < len(previous) else default[index]
                    for index in range(len(default))]
        viewport = self.detail_canvas.winfo_width()
        widths = self._fit_column_widths(previous, viewport if viewport > 1 else sum(previous))
        self._table_column_widths[width_key] = list(widths)
        self._overview_resize_context = (token, model_name, attributes, prepared_rows, list(widths))
        name_width = widths[0]
        attribute_width = max(widths[1:], default=180)
        header_height = 42
        row_height = 46
        total_width = sum(widths)
        total_cells = (len(prepared_rows) + 1) * (len(attributes) + 1)
        total_work = max(1, total_cells)

        try:
            self.detail_table.destroy()
        except tk.TclError:
            pass
        self.detail_canvas.delete("all")
        self.detail_canvas.configure(scrollregion=(0, 0, 0, 0))
        self.detail_table = tk.Frame(
            self.detail_canvas,
            background="#FFFFFF",
            bd=0,
            highlightthickness=0,
        )
        self.detail_canvas_window = None
        self._detail_staging_table = None
        self._detail_staging_window = None
        self._detail_canvas_overview_loading = True
        panel = getattr(self, "_detail_loading_panel", None)
        if panel is not None and panel.winfo_exists():
            panel.lift()

        headers = [model_name] + [attr.name for attr in attributes]
        x = 0
        for column, text in enumerate(headers):
            column_width = widths[column]
            self._draw_model_overview_cell(
                x=x,
                y=0,
                width=column_width,
                height=header_height,
                text=text,
                background="#DFE9FD",
                foreground="#04173D",
                font=("Segoe UI", 12, "bold"),
                tags=("overview_corner",) if column == 0 else ("overview_header",),
            )
            if column + 1 < len(headers):
                drag_tag = f"overview_resize_{column}"
                handle = self.detail_canvas.create_rectangle(
                    x + column_width - 5, 0, x + column_width, header_height,
                    fill="#DFE9FD", outline="", tags=(drag_tag, "overview_corner" if column == 0 else "overview_header"))
                self.detail_canvas.tag_bind(handle, "<Enter>", lambda _event: self.detail_canvas.configure(cursor="sb_h_double_arrow"))
                self.detail_canvas.tag_bind(handle, "<Leave>", lambda _event: self.detail_canvas.configure(cursor=""))
                self.detail_canvas.tag_bind(handle, "<ButtonPress-1>",
                    lambda event, index=column: setattr(self, "_overview_drag", (index, event.x_root, list(widths))))
                def finish_resize(event):
                    index, origin, original = self._overview_drag
                    adjusted = self._move_column_boundary(original, index, event.x_root - origin)
                    self._table_column_widths[width_key] = list(adjusted)
                    self._begin_prepared_model_overview_render(token, model_name, attributes, prepared_rows, adjusted)
                self.detail_canvas.tag_bind(handle, "<ButtonRelease-1>", finish_resize)
            x += column_width

        state = {
            "name_width": name_width,
            "attribute_width": attribute_width,
            "column_widths": widths,
            "header_height": header_height,
            "row_height": row_height,
            "total_width": total_width,
            "column_count": len(attributes) + 1,
            "total_cells": total_cells,
            "total_work": total_work,
        }

        row_heights = []
        row_offsets = []
        current_y = header_height
        for name, row_values in prepared_rows:
            row_offsets.append(current_y)
            dynamic_height = self._model_overview_row_height(
                name=name,
                row_values=row_values,
                state=state,
            )
            row_heights.append(dynamic_height)
            current_y += dynamic_height
        state["row_heights"] = row_heights
        state["row_offsets"] = row_offsets
        state["total_height"] = current_y

        self._detail_progress_loaded = 0
        self._detail_progress_total = len(prepared_rows)
        self._detail_progress_work_loaded = len(headers)
        self._detail_progress_work_total = total_work
        self._overview_sticky_x = 0
        self._overview_sticky_y = 0
        self._refresh_determinate_progress_display(token)

        self._schedule_detail_batch(
            token,
            1,
            lambda: self._render_prepared_overview_batch(
                token=token,
                prepared_rows=prepared_rows,
                state=state,
                start_index=0,
            ),
        )

    def _wrapped_line_count(self, text: Any, width: int, font) -> int:
        # Estimate how many text lines are needed before drawing a row.
        # This helps the table make rows taller when text would otherwise be cut off.
        value = "" if text is None else str(text)
        if not value:
            return 1

        measure_font = tk_font.Font(self.detail_canvas, font=font)
        available_width = max(20, width - 18)
        lines = 0

        for paragraph in value.splitlines() or [""]:
            words = paragraph.split()
            if not words:
                lines += 1
                continue

            current = ""
            for word in words:
                candidate = word if not current else f"{current} {word}"
                if measure_font.measure(candidate) <= available_width:
                    current = candidate
                    continue

                if current:
                    lines += 1
                    current = word
                while measure_font.measure(current) > available_width and len(current) > 1:
                    split_at = max(1, len(current) - 1)
                    while (
                            split_at > 1
                            and measure_font.measure(current[:split_at]) > available_width
                    ):
                        split_at -= 1
                    lines += 1
                    current = current[split_at:]

            if current:
                lines += 1

        return max(1, lines)

    def _model_overview_row_height(
            self,
            name: str,
            row_values: List[Any],
            state: dict,
    ) -> int:
        # Pick a row height that can hold the object name and all shown values.
        line_counts = [
            self._wrapped_line_count(
                name,
                state["name_width"],
                ("Segoe UI", 12, "bold"),
            )
        ]
        for column, value in enumerate(row_values, start=1):
            line_counts.append(
                self._wrapped_line_count(
                    value,
                    state["column_widths"][column],
                    ("Segoe UI", 12),
                )
            )
        return max(state["row_height"], (max(line_counts) * 18) + 18)

    def _render_prepared_overview_batch(
            self,
            token: int,
            prepared_rows: list,
            state: dict,
            start_index: int,
    ):
        self._detail_batch_after_id = None
        if token != getattr(self, "_detail_load_token", None):
            return

        # Canvas items are much lighter than per-cell Tk widgets, so larger
        # batches remain responsive and avoid widget resource exhaustion.
        batch_size = 40
        end_index = min(start_index + batch_size, len(prepared_rows))

        for object_index in range(start_index, end_index):
            name, row_values = prepared_rows[object_index]
            row_index = object_index + 1
            row_bg = "#FFFFFF" if row_index % 2 else "#F3F7FD"
            y = state["row_offsets"][object_index]
            row_height = state["row_heights"][object_index]

            self._draw_model_overview_cell(
                x=0,
                y=y,
                width=state["name_width"],
                height=row_height,
                text=name,
                background=row_bg,
                foreground="#16A34A",
                font=("Segoe UI", 12, "bold"),
                tags=("overview_column",),
            )

            x = state["name_width"]
            for column, value in enumerate(row_values, start=1):
                self._draw_model_overview_cell(
                    x=x,
                    y=y,
                    width=state["column_widths"][column],
                    height=row_height,
                    text=value,
                    background=row_bg,
                    foreground=self.colors["text"],
                    font=("Segoe UI", 12),
                )
                x += state["column_widths"][column]

        loaded = end_index
        rendered_cells = state["column_count"] + (loaded * state["column_count"])
        work_loaded = rendered_cells
        self._update_model_loading_progress(
            token=token,
            loaded=loaded,
            total=len(prepared_rows),
            phase="loading",
            work_loaded=work_loaded,
            work_total=state["total_work"],
        )

        if end_index < len(prepared_rows):
            self._schedule_detail_batch(
                token,
                1,
                lambda: self._render_prepared_overview_batch(
                    token=token,
                    prepared_rows=prepared_rows,
                    state=state,
                    start_index=end_index,
                ),
            )
        else:
            self._finish_model_overview_render(
                token=token,
                state=state,
            )

    def _finish_model_overview_render(
            self,
            token: int,
            state: dict,
    ):
        if token != getattr(self, "_detail_load_token", None):
            return

        progress_id = getattr(self, "_detail_progress_after_id", None)
        if progress_id is not None:
            try:
                self.after_cancel(progress_id)
            except tk.TclError:
                pass
            self._detail_progress_after_id = None

        self.detail_canvas.configure(
            scrollregion=(
                0,
                0,
                state["total_width"],
                max(state["total_height"], 122),
            )
        )
        self._update_detail_x_scrollbar_visibility()
        self.detail_canvas.xview_moveto(0)
        self.detail_canvas.yview_moveto(0)
        self._overview_sticky_x = 0
        self._overview_sticky_y = 0
        self._sync_model_overview_sticky_items()

        panel = getattr(self, "_detail_loading_panel", None)
        if panel is not None and panel.winfo_exists():
            panel.destroy()
        self._detail_loading_panel = None
        self._detail_canvas_overview_loading = False
        self.detail_subtitle.configure(
            text="Complete model overview loaded."
        )
        self._show_model_overview_loaded_toolbar()

    def _sync_model_overview_sticky_items(self):
        if not getattr(self, "_detail_canvas_overview_loading", False) and getattr(self, "_detail_overview_toolbar", None) is None:
            return
        if not hasattr(self, "detail_canvas"):
            return
        current_x = self.detail_canvas.canvasx(0)
        current_y = self.detail_canvas.canvasy(0)
        previous_x = getattr(self, "_overview_sticky_x", 0)
        previous_y = getattr(self, "_overview_sticky_y", 0)
        dx = current_x - previous_x
        dy = current_y - previous_y
        if dx:
            self.detail_canvas.move("overview_column", dx, 0)
            self.detail_canvas.move("overview_corner", dx, 0)
        if dy:
            self.detail_canvas.move("overview_header", 0, dy)
            self.detail_canvas.move("overview_corner", 0, dy)
        self._overview_sticky_x = current_x
        self._overview_sticky_y = current_y
        self.detail_canvas.tag_raise("overview_header")
        self.detail_canvas.tag_raise("overview_column")
        self.detail_canvas.tag_raise("overview_corner")

    def _show_model_overview_loaded_toolbar(self):
        existing = getattr(self, "_detail_overview_toolbar", None)
        if existing is not None and existing.winfo_exists():
            existing.destroy()

        toolbar = ctk.CTkFrame(
            self.detail_card,
            fg_color="#FFFFFF",
            corner_radius=8,
            border_width=1,
            border_color="#D8E3F5",
        )
        toolbar.place(relx=1.0, y=12, anchor="ne", x=-16)

        ctk.CTkButton(
            toolbar,
            text="Change selection",
            width=142,
            height=32,
            corner_radius=7,
            fg_color="#FFFFFF",
            hover_color=self.colors["primary_soft"],
            border_width=1,
            border_color="#BBD0F4",
            text_color=self.colors["primary"],
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            command=self._return_to_model_overview_options,
        ).grid(row=0, column=0, padx=8, pady=8)

        self._detail_overview_toolbar = toolbar
        toolbar.lift()

    def _return_to_model_overview_options(self):
        model = getattr(self, "_current_overview_model", None)
        if model is None:
            return
        toolbar = getattr(self, "_detail_overview_toolbar", None)
        if toolbar is not None and toolbar.winfo_exists():
            toolbar.destroy()
        self._detail_overview_toolbar = None
        self._show_model_overview_load_options(model)

    def _render_empty_detail_state(self):
        """
        Shows the default Details state in Inspect Model.

        The methods in this block render the Details area for classes, objects,
        enums, attributes, values, associations, links, operations, and generalizations.
        """
        self._clear_detail_option_bar()
        self.detail_title.configure(
            text="Details",
            text_color=self.colors["text"],
        )
        self.detail_subtitle.configure(
            text="Select the model, a class, or an object to load its details."
        )
        self._render_detail_rows([])

    def _render_class_details(self, obj: BaseMlmObject) -> None:
        """Show the available attribute, relationship, operation and inheritance views of a class."""
        self.detail_title.configure(
            text=f"Class: {obj.name}",
            text_color="#2563EB",
        )
        self.detail_subtitle.configure(
            text="Select which class details should be shown."
        )
        options = [
            ("Attributes", self._has_attribute_rows(obj), partial(self._render_class_attribute_table, obj)),
            ("Associations", self._has_association_rows(obj), partial(self._render_class_association_table, obj)),
            ("Generalization", bool(self._generalization_rows(obj)), partial(self._render_class_generalization_table, obj)),
        ]
        self._render_detail_option_buttons(options)
        for _label, enabled, callback in options:
            if enabled:
                callback()
                return
        self._render_detail_table(("Name", "Type", "Slot"), [])

    def _render_object_details(self, obj: BaseMlmObject) -> None:
        """Show the slot and link views available for one instance."""
        self.detail_title.configure(
            text=f"Object: {obj.name}",
            text_color="#16A34A",
        )
        self.detail_subtitle.configure(
            text="Select whether slots or links should be shown."
        )
        options = [
            ("Slots", bool(obj.get_regular_slots()), partial(self._render_object_value_table, obj)),
            ("Links", bool(self._links_for_object(self.current_model, obj)), partial(self._render_object_link_table, obj)),
        ]
        self._render_detail_option_buttons(options)
        for _label, enabled, callback in options:
            if enabled:
                callback()
                return
        self._render_detail_table(("Name", "Type", "Slot"), [])

    def _render_enum_details(self, enum: BaseMlmEnumType):
        self._clear_detail_option_bar()
        self.detail_title.configure(
            text=f"Enumeration Type: {enum.name}",
            text_color="#F59E0B",
        )
        self.detail_subtitle.configure(
            text="Slots defined for the selected enumeration type."
        )
        self._render_detail_table(
            ("Enumeration Type", "Slot", "Index"),
            [
                (enum.name, value, index)
                for index, value in enumerate(enum.enum_values, start=1)
            ],
            cell_elements=[[(enum, "name"), (enum, f"value:{value}"), None]
                           for value in enum.enum_values],
        )

    def _render_detail_option_buttons(self, options):
        self._clear_detail_option_bar()

        bar = ctk.CTkFrame(self.detail_card, fg_color="transparent")
        bar.grid(row=1, column=0, sticky="e", padx=16, pady=(0, 8))
        buttons = []
        def activate(selected, callback):
            for button in buttons:
                active = button is selected
                enabled = button.cget("state") == "normal"
                button.configure(fg_color=self.colors["primary"] if active else "#FFFFFF" if enabled else self.colors["disabled_bg"],
                                 text_color="#FFFFFF" if active else self.colors["primary"] if enabled else "#94A3B8")
            callback()
        for index, (label, enabled, callback) in enumerate(options):
            button = ctk.CTkButton(
                bar, text=label, width=118 if label == "Generalization" else 102,
                height=30, corner_radius=7, border_width=1,
                fg_color="#FFFFFF" if enabled else self.colors["disabled_bg"],
                hover_color=self.colors["primary_soft"] if enabled else self.colors["disabled_bg"],
                border_color="#BBD0F4" if enabled else self.colors["border"],
                text_color=self.colors["primary"] if enabled else "#94A3B8",
                font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
                state="normal" if enabled else "disabled",
            )
            button.configure(command=lambda target=button, action=callback: activate(target, action))
            button.grid(row=0, column=index, padx=(0 if index == 0 else 8, 0))
            buttons.append(button)
        first = next((button for button in buttons if button.cget("state") == "normal"), None)
        if first is not None:
            first.configure(fg_color=self.colors["primary"], text_color="#FFFFFF")
        self._detail_option_bar = bar

    def _clear_detail_option_bar(self):
        existing = getattr(self, "_detail_option_bar", None)
        if existing is not None and existing.winfo_exists():
            existing.destroy()
        self._detail_option_bar = None

    @staticmethod
    def _name(obj) -> str:
        return obj.name if obj is not None else "-"

    @staticmethod
    def _associations_for_class(model: Optional[BaseMlmModel], obj: BaseMlmObject):
        if model is None:
            return []
        return [
            association
            for association in model.associations
            if association.source_object is obj or association.target_object is obj
        ]

    @staticmethod
    def _links_for_object(model: Optional[BaseMlmModel], obj: BaseMlmObject):
        if model is None:
            return []
        return [
            link
            for link in model.links
            if link.source_object is obj or link.target_object is obj
        ]

    def _association_table_row(self, association: BaseMlmAssociation,
                               inherited_from: Optional[BaseMlmObject] = None) -> tuple:
        """Returns one row of the association table, with the name of the parent for an inherited association.

        The name that leads to the target is stored as the source access name, and the other way round.
        """
        name = association.name
        if inherited_from is not None:
            name = f"{name} (inherited from {inherited_from.name})"
        return (
            name,
            self._class_with_access_name(association.source_object, association.get_target_access_name(),
                                         (self._has_duplicate_association_end(association.target_object, association.source_object)
                                          or bool(association.get_target_association_end().get_import_notes()))),
            self._class_with_access_name(association.target_object, association.get_source_access_name(),
                                         (self._has_duplicate_association_end(association.source_object, association.target_object)
                                          or bool(association.get_source_association_end().get_import_notes()))),
            self._association_multiplicity_text(association),
        )

    def _has_duplicate_association_end(self, owner: BaseMlmObject, reached: BaseMlmObject) -> bool:
        """Return whether an owner has several association ends reaching the same class."""
        if self.current_model is None:
            return False
        count = 0
        for association in self.current_model.associations:
            if association.source_object is owner and association.target_object is reached:
                count += 1
            if association.target_object is owner and association.source_object is reached:
                count += 1
        return count > 1

    def _class_with_access_name(self, class_object: BaseMlmObject, access_name: str, duplicate: bool) -> str:
        """Return the class name and, for duplicate ends, its access name."""
        class_name = self._name(class_object)
        if not duplicate:
            return class_name
        return f"{class_name} ({access_name})"

    def _inherited_associations(self, obj: BaseMlmObject) -> list:
        """Returns (parent, association) for every association of the parents that obj does not have itself."""
        known_associations = list(self._associations_for_class(self.current_model, obj))
        inherited = []
        for parent in self._all_parent_classes(obj):
            for association in self._associations_for_class(self.current_model, parent):
                if association not in known_associations:
                    known_associations.append(association)
                    inherited.append((parent, association))
        return inherited

    @staticmethod
    def _link_access_names(link: BaseMlmLink) -> list:
        """Returns the names of the association ends of a link, which are the names of its slot links."""
        association = link.get_association()
        if association is None:
            return []
        return [association.get_source_access_name(), association.get_target_access_name()]

    @staticmethod
    def _association_multiplicity_text(association) -> str:
        source = association.source_multiplicity or "-"
        target = association.target_multiplicity or "-"
        return f"{source} → {target}"

    @staticmethod
    def _short_type_name(type_name: str) -> str:
        if not type_name:
            return "-"
        return ModelDeepenerApp._clean_display_value(type_name)

    @staticmethod
    def _operations_for_object(obj: BaseMlmObject):
        operations = list(obj.operations_list)
        if obj.class_of_object is not None:
            operations.extend(
                operation
                for operation in obj.class_of_object.operations_list
                if operation not in operations
            )
        return operations

    def _generalization_rows(self, obj: BaseMlmObject):
        rows = [
            (parent.name, obj.name)
            for parent in obj.parent_classes
        ]
        if self.current_model is not None:
            rows.extend(
                (obj.name, candidate.name)
                for candidate in self.current_model.mlm_objects
                if obj in candidate.parent_classes
            )
        return rows

    def _all_parent_classes(self, obj: BaseMlmObject):
        parents = []
        pending = list(obj.parent_classes)
        while pending:
            parent = pending.pop(0)
            if parent in parents:
                continue
            parents.append(parent)
            pending.extend(parent.parent_classes)
        return parents

    def _has_attribute_rows(self, obj: BaseMlmObject) -> bool:
        """Returns whether the class has attributes of its own or inherits attributes from a parent."""
        for class_object in [obj] + self._all_parent_classes(obj):
            if class_object.get_regular_attributes():
                return True
        return False

    def _has_association_rows(self, obj: BaseMlmObject) -> bool:
        """Returns whether the class has associations of its own or inherits associations from a parent."""
        if self._associations_for_class(self.current_model, obj):
            return True
        return bool(self._inherited_associations(obj))

    def _render_class_attribute_table(self, obj: BaseMlmObject) -> None:
        """Show declared and inherited attributes with field-specific import notes."""
        attributes = list(obj.get_regular_attributes())
        inherited = [(parent, attr) for parent in self._all_parent_classes(obj)
                     for attr in parent.get_regular_attributes()]
        rows = [(attr.name, attr.attr_type_str_short, str(attr.multiplicity or "-"), attr.inst_level)
                for attr in attributes]
        rows.extend((attr.name, attr.attr_type_str_short, str(attr.multiplicity or "-"),
                     f"Level {attr.inst_level}, inherited from {parent.name}")
                    for parent, attr in inherited)
        cells = [[(attr, "name"), (attr, "type"), (attr, "multiplicity"), None] for attr in attributes]
        cells.extend([[None, None, None, None] for _parent, _attr in inherited])
        self._render_detail_table(("Attribute", "Type", "Multiplicity", "Level"), rows,
                                  cell_elements=cells, highlight_column=1)

    def _render_class_association_table(self, obj: BaseMlmObject) -> None:
        """Show declared and inherited associations with field-specific import notes."""
        associations = self._associations_for_class(self.current_model, obj)
        inherited = self._inherited_associations(obj)
        rows = [self._association_table_row(association) for association in associations]
        rows.extend(self._association_table_row(association, inherited_from=parent)
                    for parent, association in inherited)
        cells = [[(association, "name"), (association.get_target_association_end(), "name"),
                  (association.get_source_association_end(), "name"), (association, "multiplicity")]
                 for association in associations]
        cells.extend([[None, None, None, None] for _parent, _association in inherited])
        self._render_detail_table(self.ASSOCIATION_TABLE_HEADERS, rows,
                                  highlight_column=self.ASSOCIATION_TABLE_HEADERS.index("Multiplicity"),
                                  cell_elements=cells)

    def _render_class_operation_table(self, obj: BaseMlmObject):
        self._render_detail_table(
            ("Operation", "Type", "Slot"),
            [
                (operation.operation_name, self._short_type_name(operation.return_type), "-")
                for operation in obj.operations_list
            ],
        )

    def _render_class_generalization_table(self, obj: BaseMlmObject):
        self._render_detail_table(
            ("Superclass", "Subclass"),
            self._generalization_rows(obj),
        )

    def _render_object_value_table(self, obj: BaseMlmObject) -> None:
        """Display regular slot values together with their resolved types."""
        self._render_detail_table(
            ("Attribute", "Type", "Slot"),
            [
                (slot.name, self._slot_type(slot), slot.get_value_as_text())
                for slot in obj.get_regular_slots()
            ],
        )

    def _render_object_link_table(self, obj: BaseMlmObject):
        self._render_detail_table(
            ("Linkname", "Source", "Target", "Multiplicity"),
            [
                (
                    link.name,
                    self._name(link.source_object),
                    self._name(link.target_object),
                    "-",
                )
                for link in self._links_for_object(self.current_model, obj)
            ],
            highlight_column=3,
        )

    def _render_object_operation_table(self, obj: BaseMlmObject) -> None:
        """Display operations available to the instance through its class."""
        slot_by_name = {
            slot.name: slot.get_value_as_text()
            for slot in obj.get_regular_slots()
        }
        self._render_detail_table(
            ("Operation", "Type", "Slot"),
            [
                (
                    operation.operation_name,
                    self._short_type_name(operation.return_type),
                    slot_by_name.get(operation.operation_name, "-"),
                )
                for operation in self._operations_for_object(obj)
            ],
        )

    def _render_detail_rows(self, rows):
        self._render_detail_table(("Attribute", "Type", "Slot"), rows)

    @staticmethod
    def _standard_detail_column_widths(count: int, column_minsizes=None) -> list[int]:
        """Return the default detail table widths, including explicit per-table widths."""
        return [column_minsizes[column] if column_minsizes and column < len(column_minsizes)
                else (220 if column == 0 else 170) for column in range(count)]

    @staticmethod
    def _fit_column_widths(widths: list[int], total: int, minimum: int = 60) -> list[int]:
        """Fit column widths to the available space without going below the minimum."""
        if not widths:
            return []
        total = max(total, minimum * len(widths))
        extra = total - minimum * len(widths)
        shares = [max(0, width - minimum) for width in widths]
        if not sum(shares):
            shares = [1] * len(widths)
        result = [minimum + extra * share // sum(shares) for share in shares]
        for index in range(total - sum(result)):
            result[index % len(result)] += 1
        return result

    @staticmethod
    def _move_column_boundary(widths: list[int], column: int, delta: int, minimum: int = 60) -> list[int]:
        """Move one boundary while preserving the width of the two columns."""
        result = list(widths)
        if column < 0 or column + 1 >= len(result):
            return result
        delta = max(minimum - result[column], min(delta, result[column + 1] - minimum))
        result[column] += delta
        result[column + 1] -= delta
        return result

    def _start_detail_column_resize(self, event, column: int) -> None:
        """Remember the position and widths at the start of a column drag."""
        self._detail_resize_start = (column, event.x_root, list(self._detail_column_widths))

    def _resize_detail_column(self, event) -> None:
        """Move a boundary between two neighboring detail columns."""
        column, start_x, original = self._detail_resize_start
        widths = self._move_column_boundary(original, column, event.x_root - start_x)
        self._detail_column_widths = widths
        for index in (column, column + 1):
            self.detail_table.grid_columnconfigure(index, minsize=widths[index])
        self.detail_table.update_idletasks()
        self.detail_canvas.configure(scrollregion=self.detail_canvas.bbox("all"))
        self._update_detail_x_scrollbar_visibility()
        ModelDeepenerApp._refresh_detail_sticky_header(self)

    def _finish_detail_column_resize(self, _event=None) -> None:
        """Keep the selected widths for subsequent tables of the same kind."""
        self._table_column_widths[self._detail_width_key] = list(self._detail_column_widths)

    @staticmethod
    def _refresh_detail_sticky_header(owner):
        header = getattr(owner, "_detail_sticky_header", None)
        if header is None or not header.winfo_exists():
            return
        header.delete("all")
        x = 0
        widths = owner._detail_column_widths
        for index, (text, width) in enumerate(zip(owner._detail_sticky_labels, widths)):
            header.create_rectangle(x, 0, x + width, 42, fill="#DFE9FD", outline="#AFC1D9")
            header.create_text(x + width / 2, 21, text=text, fill="#04173D", font=("Segoe UI", 12, "bold"))
            if index + 1 < len(widths):
                handle = header.create_rectangle(x + width - 5, 0, x + width, 42, fill="#DFE9FD", outline="")
                header.tag_bind(handle, "<ButtonPress-1>", lambda event, col=index: owner._start_detail_column_resize(event, col))
                header.tag_bind(handle, "<B1-Motion>", owner._resize_detail_column)
                header.tag_bind(handle, "<ButtonRelease-1>", owner._finish_detail_column_resize)
            x += width
        header.configure(scrollregion=(0, 0, max(1, x), 42))
        header.xview_moveto(owner.detail_canvas.xview()[0])

    def _render_detail_table(
            self,
            headers,
            rows,
            highlight_column: int = 1,
            muted_row_indexes=None,
            column_weights=None,
            column_minsizes=None,
            cell_elements=None,
    ):
        self._reset_detail_canvas_table()
        for child in self.detail_table.winfo_children():
            child.destroy()
        muted_row_indexes = muted_row_indexes or set()

        if not hasattr(self, "_table_column_widths"):
            self._table_column_widths = {}
        self._detail_width_key = ("detail", tuple(headers))
        default = self._standard_detail_column_widths(len(headers), column_minsizes)
        saved = self._table_column_widths.get(self._detail_width_key, default)
        viewport = self.detail_canvas.winfo_width()
        self._detail_column_widths = self._fit_column_widths(saved, viewport if viewport > 1 else sum(saved))
        for column, width in enumerate(self._detail_column_widths):
            self.detail_table.grid_columnconfigure(column, weight=0, minsize=width)

        header_bg = "#DFE9FD"

        for column, text in enumerate(headers):
            cell = tk.Frame(
                self.detail_table,
                height=42,
                background=header_bg,
                bd=0,
                highlightthickness=1,
                highlightbackground="#AFC1D9",
                highlightcolor="#AFC1D9",
            )
            cell.grid(
                row=0,
                column=column,
                sticky="nsew",
            )
            cell.grid_propagate(False)

            if column > 0:
                tk.Frame(
                    cell,
                    width=1,
                    background="#AFC1D9",
                    bd=0,
                    highlightthickness=0,
                ).place(x=0, y=0, width=1, height=42)

            ctk.CTkLabel(
                cell,
                text=text,
                anchor="center",
                justify="center",
                text_color="#04173D",
                font=ctk.CTkFont(
                    family="Segoe UI",
                    size=12,
                    weight="bold",
                ),
            ).place(relx=0.5, rely=0.5, anchor="center")
            if column + 1 < len(headers):
                handle = tk.Frame(cell, width=8, background=header_bg, cursor="sb_h_double_arrow")
                handle.place(relx=1, y=0, anchor="ne", relheight=1)
                handle.bind("<ButtonPress-1>", lambda event, index=column: self._start_detail_column_resize(event, index))
                handle.bind("<B1-Motion>", self._resize_detail_column)
                handle.bind("<ButtonRelease-1>", self._finish_detail_column_resize)

        if not rows:
            empty = tk.Frame(
                self.detail_table,
                height=80,
                background="#FFFFFF",
                bd=0,
                highlightthickness=1,
                highlightbackground="#AFC1D9",
                highlightcolor="#AFC1D9",
            )
            empty.grid(
                row=1,
                column=0,
                columnspan=len(headers),
                sticky="nsew",
            )
            empty.grid_propagate(False)

            ctk.CTkLabel(
                empty,
                text="Nothing selected.",
                text_color=self.colors["muted"],
                font=ctk.CTkFont(family="Segoe UI", size=12),
            ).place(relx=0.5, rely=0.5, anchor="center")
        else:
            for row_index, row_values in enumerate(rows, start=1):
                row_bg = "#FFFFFF" if row_index % 2 else "#F3F7FD"
                is_muted_row = (row_index - 1) in muted_row_indexes
                normalized_values = list(row_values)[:len(headers)]
                if len(normalized_values) < len(headers):
                    normalized_values.extend([""] * (len(headers) - len(normalized_values)))

                for column, cell_value in enumerate(normalized_values):
                    cell = tk.Frame(
                        self.detail_table,
                        height=46,
                        background=row_bg,
                        bd=0,
                        highlightthickness=1,
                        highlightbackground="#AFC1D9",
                        highlightcolor="#AFC1D9",
                    )
                    cell.grid(
                        row=row_index,
                        column=column,
                        sticky="nsew",
                    )
                    cell.grid_propagate(False)

                    if column > 0:
                        tk.Frame(
                            cell,
                            width=1,
                            background="#AFC1D9",
                            bd=0,
                            highlightthickness=0,
                        ).place(
                            x=0,
                            y=0,
                            width=1,
                            height=46,
                        )

                    element = None
                    if cell_elements and row_index - 1 < len(cell_elements) and column < len(cell_elements[row_index - 1]):
                        element = cell_elements[row_index - 1][column]
                    if isinstance(element, tuple):
                        target, field = element
                        notes = getattr(target, "get_import_notes_for", lambda _field: [])(field)
                    else:
                        notes = getattr(element, "get_import_notes", lambda: [])()
                    notes = visible_import_notes(notes)
                    marked = bool(notes)
                    highlight = column == highlight_column and bool(cell_value) and not marked
                    color = ("#B45309" if any(serious for _text, serious in notes) else "#647A94") if marked else (
                        "#64748B" if is_muted_row else "#013897") if highlight else (
                        self.colors["muted"] if is_muted_row else self.colors["text"])
                    label = ctk.CTkLabel(
                        cell, text=self._display_table_value(cell_value), anchor="center", justify="center",
                        text_color=color,
                        fg_color=("#E2E8F0" if is_muted_row else self.colors["primary_soft"]) if highlight else "transparent",
                        corner_radius=12 if highlight else 0,
                        font=ctk.CTkFont(family="Segoe UI", size=11 if highlight else 12,
                                         weight="bold" if highlight else "normal"))
                    label.place(relx=0.5, rely=0.5, anchor="center", relwidth=0.92)
                    full_text = str(cell_value) if cell_value is not None else ""
                    tooltip_notes = list(notes)
                    if full_text:
                        tooltip_notes.append((full_text, False))
                    if tooltip_notes:
                        label.bind("<Enter>", lambda event, texts=tooltip_notes: self._show_import_note_tooltip(event, texts))
                        label.bind("<Leave>", self._hide_adapted_tooltip)

        self.detail_table.update_idletasks()
        self.detail_canvas.itemconfigure(
            self.detail_canvas_window,
            width=sum(self._detail_column_widths),
        )
        self.detail_canvas.configure(
            scrollregion=self.detail_canvas.bbox("all")
        )
        self._update_detail_x_scrollbar_visibility()
        self.detail_canvas.xview_moveto(0)
        self.detail_canvas.yview_moveto(0)
        sticky = tk.Canvas(self.detail_table_wrapper, background="#DFE9FD", highlightthickness=0, height=42)
        sticky.place(in_=self.detail_canvas, x=0, y=0, relwidth=1, height=42)
        self._detail_sticky_header = sticky
        self._detail_sticky_labels = tuple(headers)
        ModelDeepenerApp._refresh_detail_sticky_header(self)
        ModelDeepenerApp._bind_table_wheel(sticky, self.detail_canvas)
        ModelDeepenerApp._bind_table_wheel(self.detail_table, self.detail_canvas)
        def sync_x(first, last):
            scrollbar = getattr(self, "detail_x_scrollbar", None)
            if scrollbar is not None:
                scrollbar.set(first, last)
            if sticky.winfo_exists():
                sticky.xview_moveto(float(first))
        self.detail_canvas.configure(xscrollcommand=sync_x)

    def _overview_counts_for(self, loaded: LoadedModel) -> tuple[int, int, int, int]:
        """Return the prepared counts for an overview row."""
        cached = getattr(self, "_overview_model_counts", {}).get(id(loaded))
        if cached is not None:
            return cached
        model = loaded.model
        return (self._count_higher_level_classes(model), len(model.get_all_flat_classes()),
                self._count_attributes(model), len(model.get_all_pure_objects()))

    def _populate_models_table(self):
        """Apply filters and draw the currently visible overview rows."""
        if not hasattr(self, "models_canvas") or not self.models_canvas.winfo_exists():
            return
        filtered = [(index, loaded) for index, loaded in enumerate(self.loaded_models)
                    if self._model_matches_overview_filters(loaded)]
        ordered = models_newest_first([loaded for _, loaded in filtered])
        indices = {id(loaded): index for index, loaded in filtered}
        self._models_filtered = [(indices[id(loaded)], loaded) for loaded in ordered]
        self.models_canvas.yview_moveto(0)
        self.models_canvas.xview_moveto(0)
        self._draw_visible_models_rows()

    def _on_models_canvas_scroll(self, first: str, last: str) -> None:
        """Update the scrollbar and schedule a redraw after vertical scrolling."""
        ModelDeepenerApp._autohide_scroll(self.models_scrollbar)(first, last)
        position = (first, last)
        if position == getattr(self, "_models_last_scroll_position", None):
            return
        self._models_last_scroll_position = position
        if getattr(self, "_models_redraw_after", None) is None:
            self._models_redraw_after = self.models_canvas.after_idle(self._draw_visible_models_rows)

    def _cancel_models_canvas_redraw(self, event) -> None:
        """Cancel the pending row redraw when its canvas is destroyed."""
        if event.widget is self.models_canvas:
            after_id = getattr(self, "_models_redraw_after", None)
            if after_id is not None:
                self.models_canvas.after_cancel(after_id)
                self._models_redraw_after = None

    def _draw_visible_models_rows(self) -> None:
        """Draw the overview header and rows intersecting the canvas viewport."""
        self._models_redraw_after = None
        canvas = self.models_canvas
        if not canvas.winfo_exists():
            return
        canvas.delete("all")
        self._models_canvas_rows = {}
        canvas_width = max(canvas.winfo_width(), 900)
        column_specs = [
            ("delete", " ", 0.06), ("name", "Model Name", 0.13), ("source", "Source File", 0.16),
            ("type", "Type", 0.06), ("level_classes", "Higher Level Classes", 0.09),
            ("classes", "Classes", 0.07), ("attributes", "Attributes", 0.09),
            ("objects", "Objects", 0.08), ("status", "Last Action", 0.09),
            ("worked", "Last worked on", 0.09), ("open", "Open Model", 0.08),
        ]
        columns = [(key, label, max(78, int(canvas_width * fraction))) for key, label, fraction in column_specs]
        row_height, header_height = 64, 58
        table_width = max(sum(width for _key, _label, width in columns), canvas_width)
        filtered = getattr(self, "_models_filtered", [])
        total_height = header_height + max(1, len(filtered)) * row_height
        region = (0, 0, table_width, total_height)
        if getattr(canvas, "_models_scrollregion", None) != region:
            canvas._models_scrollregion = region
            canvas.configure(scrollregion=region)
        x = 0
        header_items = []
        for _key, label, width in columns:
            header_items.extend(self._draw_models_table_cell(x=x, y=canvas.canvasy(0), width=width, height=header_height, text=label,
                                         background="#DFE9FD", foreground="#04173D", font=("Segoe UI", 12, "bold")))
            x += width
        first = max(0, int((canvas.canvasy(0) - header_height) // row_height) - 1)
        last = min(len(filtered), int((canvas.canvasy(canvas.winfo_height()) - header_height) // row_height) + 2)
        for position in range(first, last):
            model_index, loaded = filtered[position]
            row_index = position + 1
            model = loaded.model
            y = header_height + ((row_index - 1) * row_height)
            row_bg = "#FFFFFF" if row_index % 2 else "#F3F7FD"
            counts = self._overview_counts_for(loaded)
            values = [
                "Delete",
                loaded.name,
                loaded.source_file,
                ModelDeepenerApp._display_file_type(loaded.file_type),
                *counts,
                self._model_last_action_label(loaded),
                loaded.last_worked_on or loaded.uploaded or "Unknown",
                "Open Model",
            ]
            x = 0
            row_items = []
            delete_items = []
            badge = None
            badges = []
            for _column_index, ((key, _label, width), value) in enumerate(zip(columns, values)):
                if key == "delete":
                    foreground = self.colors["danger"]
                    font = ("Segoe UI", 12, "bold underline")
                elif key == "status":
                    foreground = self.colors["danger"] if "fail" in str(value).lower() else self.colors["success"]
                    font = ("Segoe UI", 12, "bold")
                elif key == "open":
                    foreground = self.colors["primary"]
                    font = ("Segoe UI", 12, "bold underline")
                else:
                    foreground = self.colors["text"]
                    font = ("Segoe UI", 12)
                items = self._draw_models_table_cell(
                    x=x,
                    y=y,
                    width=width,
                    height=row_height,
                    text=value,
                    background=row_bg,
                    foreground=foreground,
                    font=font,
                )
                if key == "name" and (model.get_is_adapted() or getattr(model, "get_is_deepened", lambda: False)()):
                    self.models_canvas.move(items[1], 0, -10)
                    both = model.get_is_adapted() and getattr(model, "get_is_deepened", lambda: False)()
                    for text, present, color, tooltip, offset in (
                            ("adapted", model.get_is_adapted(), "#A34D00", self._show_adapted_tooltip, -31 if both else 0),
                            ("deepened", getattr(model, "get_is_deepened", lambda: False)(), "#08765E", getattr(self, "_show_deepened_tooltip", lambda _event: None), 31 if both else 0)):
                        if not present:
                            continue
                        badge = self.models_canvas.create_text(
                            x + width / 2 + offset, y + row_height / 2 + 13, text=text,
                            fill=color, font=("Segoe UI", 9, "bold"))
                        self.models_canvas.tag_bind(badge, "<Button-1>",
                            lambda _event, target=loaded: self._open_loaded_model(target))
                        self.models_canvas.tag_bind(badge, "<Enter>", tooltip)
                        self.models_canvas.tag_bind(badge, "<Leave>", self._hide_adapted_tooltip)
                        row_items.append(badge)
                        badges.append(badge)
                if key == "delete":
                    delete_items.extend(items)
                row_items.extend(items)
                x += width
            for item in row_items:
                if item in badges:
                    continue
                if item in delete_items:
                    command = lambda _event, target=loaded: self._delete_loaded_model(target)
                else:
                    command = lambda _event, target=loaded: self._open_loaded_model(target)
                self.models_canvas.tag_bind(item, "<Button-1>", command)
                self.models_canvas.tag_bind(item, "<Enter>", lambda _event: self.models_canvas.configure(cursor="hand2"))
                self.models_canvas.tag_bind(item, "<Leave>", lambda _event: self.models_canvas.configure(cursor=""))
            self._models_canvas_rows[model_index] = row_items
        canvas.create_rectangle(0, 0, max(1, table_width - 1), max(1, total_height - 1), outline="#AFC1D9", width=1)
        for item in header_items:
            canvas.addtag_withtag("sticky_header", item)
        canvas.tag_raise("sticky_header")


    def _model_matches_overview_filters(self, loaded: LoadedModel) -> bool:
        query_var = getattr(self, "models_search_var", None)
        query = query_var.get().strip().lower() if query_var is not None else ""
        if query and query not in loaded.name.lower() and query not in loaded.source_file.lower():
            return False

        type_var = getattr(self, "models_type_filter_var", None)
        type_filter = type_var.get() if type_var is not None else "All"
        if type_filter != "All" and ModelDeepenerApp._display_file_type(loaded.file_type).casefold() != ModelDeepenerApp._display_file_type(type_filter).casefold():
            return False

        counts = self._overview_counts_for(loaded)
        min_objects_var = getattr(self, "models_min_objects_var", None)
        min_objects = self._optional_int_filter(
            min_objects_var.get() if min_objects_var is not None else ""
        )
        if min_objects is not None and counts[3] < min_objects:
            return False

        min_attributes_var = getattr(self, "models_min_attributes_var", None)
        min_attributes = self._optional_int_filter(
            min_attributes_var.get() if min_attributes_var is not None else ""
        )
        if min_attributes is not None and counts[2] < min_attributes:
            return False

        return True

    @staticmethod
    def _optional_int_filter(value: str) -> Optional[int]:
        value = value.strip()
        if not value:
            return None
        try:
            return int(value)
        except ValueError:
            return None

    @staticmethod
    def _model_last_action_label(loaded: LoadedModel) -> str:
        return loaded.last_action or "Imported"

    def _bind_models_scroll_events(self, _event=None):
        self.bind_all("<MouseWheel>", self._on_models_mousewheel)

    def _unbind_models_scroll_events(self, _event=None):
        self.unbind_all("<MouseWheel>")

    def _on_models_mousewheel(self, event):
        delta = int(-1 * (event.delta / 120)) if event.delta else 0
        if delta:
            self.models_canvas.yview_scroll(delta, "units")

    def _open_loaded_model(self, loaded: LoadedModel):
        self.current_model = loaded.model
        self.current_file_path = loaded.source_path
        self.current_file_type = loaded.file_type
        self.current_selected_columns = list(loaded.selected_columns)
        self._show_model_page()

    def _ask_delete_confirmation(self, model_name: str) -> bool:
        """Ask in a modal dialog whether the model should really be deleted.

        The dialog has the same look as the Select Example dialog and is centered on the main
        window. Enter, Escape and closing the window mean "No". Returns True only if the user
        clicks "Yes".
        """
        answer = {"delete": False}
        dialog = ctk.CTkToplevel(self)
        dialog.title("Delete model")
        dialog.resizable(False, False)
        dialog.transient(self)
        dialog.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            dialog,
            text="Delete this model?",
            anchor="w",
            text_color=self.colors["text"],
            font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"),
        ).grid(row=0, column=0, sticky="ew", padx=18, pady=(18, 6))
        ctk.CTkLabel(
            dialog,
            text=f"Do you really want to delete '{model_name}'?\nThis cannot be undone.",
            anchor="w",
            justify="left",
            text_color=self.colors["text"],
            font=ctk.CTkFont(family="Segoe UI", size=13),
        ).grid(row=1, column=0, sticky="ew", padx=18, pady=(0, 18))

        def close(delete: bool):
            answer["delete"] = delete
            dialog.grab_release()
            dialog.destroy()

        actions = ctk.CTkFrame(dialog, fg_color="transparent")
        actions.grid(row=2, column=0, sticky="ew", padx=18, pady=(0, 18))
        actions.grid_columnconfigure(0, weight=1)
        ctk.CTkButton(
            actions,
            text="No",
            width=100,
            height=36,
            fg_color="#FFFFFF",
            hover_color="#EEF2F7",
            border_width=1,
            border_color=self.colors["border"],
            text_color=self.colors["text"],
            command=lambda: close(False),
        ).grid(row=0, column=1, padx=(0, 8))
        ctk.CTkButton(
            actions,
            text="Yes",
            width=100,
            height=36,
            fg_color=self.colors["danger"],
            hover_color="#b91c1c",
            text_color="#FFFFFF",
            command=lambda: close(True),
        ).grid(row=0, column=2)

        self._overlay.cover(dialog)
        dialog.protocol("WM_DELETE_WINDOW", lambda: close(False))
        dialog.bind("<Escape>", lambda _event: close(False))
        dialog.bind("<Return>", lambda _event: close(False))
        dialog.grab_set()
        dialog.wait_window()
        return answer["delete"]

    def _delete_loaded_model(self, loaded: LoadedModel) -> None:
        """Confirm deletion and save it without blocking the interface."""
        if not self._ask_delete_confirmation(loaded.name) or loaded not in self.loaded_models:
            return
        database = self._database
        def delete(_progress):
            database.delete(loaded.get_oid())
            try:
                database.commit()
            except Exception:
                database.store(loaded)
                raise
        def done(_result):
            self.loaded_models.remove(loaded)
            if self.current_model is loaded.model:
                self.current_model = self.loaded_models[-1].model if self.loaded_models else None
            self._populate_models_table()
        self._run_model_task(1, "Deleting model...", delete, done,
                             lambda error: self._show_error("Delete Model", save_error_message(error)))

    def _model_metrics(self, model: BaseMlmModel):
        return [
            ("Higher Level Classes", self._count_higher_level_classes(model)),
            ("Classes", len(model.get_all_flat_classes())),
            ("Attributes", self._count_attributes(model)),
            ("Enumeration Types", len(model.enums)),
            ("Generalizations", self._count_generalizations(model)),
            ("Associations", len(model.associations)),
            ("Objects", len(model.get_all_pure_objects())),
            ("Slots", self._count_slots(model)),
            ("Links", len(model.links)),
        ]

    @staticmethod
    def _count_attributes(model: BaseMlmModel) -> int:
        """Counts the attributes of all objects, without the ends of associations."""
        count = 0
        for obj in model.mlm_objects:
            count += len(obj.get_regular_attributes())
        return count

    @staticmethod
    def _count_higher_level_classes(model: BaseMlmModel) -> int:
        """
        Counts classes above level 1 for the separate higher-level metric card.
        """
        count = 0
        for obj in model.mlm_objects:
            if obj.level > 1:
                count += 1
        return count

    @staticmethod
    def _count_slots(model: BaseMlmModel) -> int:
        """Counts the slots of all objects, without the ones that stand for links."""
        count = 0
        for obj in model.mlm_objects:
            count += len(obj.get_regular_slots())
        return count

    @staticmethod
    def _count_operations(model: BaseMlmModel) -> int:
        return sum(len(obj.operations_list) for obj in model.mlm_objects)

    @staticmethod
    def _count_generalizations(model: BaseMlmModel) -> int:
        return sum(len(obj.parent_classes) for obj in model.mlm_objects)

    @staticmethod
    def _slot_type(slot: BaseMlmSlot) -> str:
        """Resolve the display type from the slot attribute or available model metadata."""
        if slot.attribute is not None:
            return ModelDeepenerApp._clean_display_value(slot.attribute.attr_type_str_short)
        owner = getattr(slot, "owner", None)
        model = getattr(owner, "_active_model", None)
        if model is not None:
            matches = []
            for obj in model.mlm_objects:
                for attr in obj.get_regular_attributes():
                    if attr.name == slot.name:
                        matches.append(attr)
            enum_matches = []
            for attr in matches:
                type_name = ModelDeepenerApp._clean_display_value(attr.attr_type_str_short)
                for enum in model.enums:
                    if enum.name == type_name:
                        enum_matches.append(attr)
                        break
            if enum_matches:
                return ModelDeepenerApp._clean_display_value(enum_matches[0].attr_type_str_short)
            if matches:
                return ModelDeepenerApp._clean_display_value(matches[0].attr_type_str_short)
        return ModelDeepenerApp._clean_display_value(type(slot.value).__name__)

    @staticmethod
    def _set_windows_app_id():
        """
        Gives Windows a stable app id for the taskbar icon.

        Without this, Windows can show the Python icon for Tk apps.
        """
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("ModelDeepener.App")
        except (AttributeError, OSError):
            pass

    def _metric_card_no_icon(
            self,
            parent,
            label: str,
            value: int,
            value_color: str,
            average: bool = False,
    ) -> ctk.CTkFrame:
        """
        Creates one metric card used in the app.

        This starts the shared UI helper block. The methods below create
        repeated visual elements such as cards, page headers, tree widgets,
        canvas table cells, and table clearing.
        """
        card = self._card(parent)
        card.configure(height=104)
        card.grid_propagate(False)

        is_zero = value == 0
        muted_color = "#A8B2C1"
        label_color = muted_color if is_zero else self.colors["text"]
        number_color = muted_color if is_zero else value_color

        value_text = f"{value:.1f}" if average else str(value)
        if len(value_text) >= 7:
            value_size = 17
        elif len(value_text) >= 6:
            value_size = 18
        elif len(value_text) >= 5:
            value_size = 20
        else:
            value_size = 22
        label_size = 10 if len(label) > 16 else 11 if len(label) > 13 else 13

        ctk.CTkLabel(
            card,
            text=label,
            text_color=label_color,
            wraplength=112,
            justify="center",
            font=ctk.CTkFont(
                family="Segoe UI",
                size=label_size,
                weight="bold",
            ),
        ).place(
            relx=0.5,
            y=28,
            anchor="center",
        )

        ctk.CTkLabel(
            card,
            text=value_text,
            text_color=number_color,
            font=ctk.CTkFont(
                family="Segoe UI",
                size=value_size,
                weight="bold",
            ),
        ).place(
            relx=0.5,
            y=69,
            anchor="center",
        )

        return card

    def _page_header(self, title: str, subtitle: str):
        header = ctk.CTkFrame(self.content, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 18))
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header,
            text=title,
            anchor="w",
            text_color=self.colors["text"],
            font=ctk.CTkFont(size=24, weight="bold"),
        ).grid(row=0, column=0, sticky="w")

        ctk.CTkLabel(
            header,
            text=subtitle,
            anchor="w",
            text_color=self.colors["muted"],
            font=ctk.CTkFont(size=12),
        ).grid(row=1, column=0, sticky="w", pady=(3, 0))
        return header

    @staticmethod
    def _import_note_tag(element) -> str:
        """Return the display tag for an element's import notes."""
        notes = visible_import_notes(getattr(element, "get_import_notes", lambda: [])())
        if not notes:
            return ""
        return "serious_adaptation" if any(serious for _text, serious in notes) else "automatic_adaptation"

    def _show_import_note_tooltip(self, event, notes: list[tuple[str, bool]]) -> None:
        """Show the supplied import notes next to a marked element."""
        self._hide_adapted_tooltip()
        window = tk.Toplevel(self)
        window.overrideredirect(True)
        window.geometry(f"+{event.x_root + 12}+{event.y_root + 18}")
        tk.Label(window, text="\n".join(text for text, _serious in notes), justify="left", wraplength=700,
                 background="#FFF8EC", foreground="#29384D", relief="solid",
                 borderwidth=1, padx=6, pady=4).pack()
        self._adapted_tooltip = window

    ADAPTATION_LEGEND = (
        ("#B45309", "Orange", "Changed during import in a way that may affect the meaning "
                              "(e.g. unknown type replaced by String)."),
        ("#647A94", "Grey-blue", "Adjusted automatically (e.g. renamed elements, generated role names)."),
    )

    def _show_adaptation_legend(self, event) -> None:
        """Show a small card that explains the colors of marked elements."""
        self._hide_adapted_tooltip()
        window = tk.Toplevel(self)
        window.overrideredirect(True)
        window.configure(background=self.colors["border"])
        card = tk.Frame(window, background=WHITE, padx=14, pady=12)
        card.pack(padx=1, pady=1)
        tk.Label(card, text="Import Markers", background=WHITE, foreground=self.colors["text"],
                 font=(FONT_FAMILY, 11, "bold"), anchor="w").grid(row=0, column=0, columnspan=2, sticky="w",
                                                                   pady=(0, 8))
        for row, (color, name, text) in enumerate(self.ADAPTATION_LEGEND, 1):
            tk.Frame(card, background=color, width=14, height=14).grid(row=row, column=0, sticky="nw",
                                                                         padx=(0, 10), pady=(3, 6))
            tk.Label(card, text=f"{name}: {text}", background=WHITE, foreground=self.colors["text"],
                     font=(FONT_FAMILY, 10), justify="left", anchor="w", wraplength=340).grid(
                         row=row, column=1, sticky="w", pady=(0, 6))
        tk.Label(card, text="Hover over a marked cell for details.", background=WHITE,
                 foreground=self.colors["muted"], font=(FONT_FAMILY, 10, "italic"), anchor="w").grid(
                     row=len(self.ADAPTATION_LEGEND) + 1, column=0, columnspan=2, sticky="w", pady=(4, 0))
        window.geometry(f"+{event.x_root + 12}+{event.y_root + 18}")
        self._adapted_tooltip = window

    def _show_tree_import_notes(self, event) -> None:
        """Show the import notes of the tree element under the pointer."""
        item = self.model_tree.identify_row(event.y)
        if item == getattr(self, "_import_note_hover_item", None):
            return
        self._hide_adapted_tooltip()
        self._import_note_hover_item = item
        element = self.tree_item_payload.get(item)
        if isinstance(element, tuple) and len(element) == 3 and element[0] == "enum_value":
            notes = element[1].get_import_notes_for(f"value:{element[2]}")
        else:
            if isinstance(element, tuple) and len(element) == 3:
                element = element[2]
            notes = getattr(element, "get_import_notes", lambda: [])()
        notes = visible_import_notes(notes)
        if not notes:
            return
        window = tk.Toplevel(self)
        window.overrideredirect(True)
        window.geometry(f"+{event.x_root + 12}+{event.y_root + 18}")
        tk.Label(window, text="\n".join(text for text, _serious in notes),
                 justify="left", background="#FFF8EC", foreground="#29384D", relief="solid",
                 borderwidth=1, padx=6, pady=4).pack()
        self._adapted_tooltip = window

    def _show_adapted_tooltip(self, event) -> None:
        """Show the explanation of the import adaptation badge."""
        self._hide_adapted_tooltip()
        window = tk.Toplevel(self)
        window.overrideredirect(True)
        window.geometry(f"+{event.x_root + 12}+{event.y_root + 18}")
        tk.Label(window, text="Adapted during import. Orange cells show what was changed \u2013 hover over them for details.",
                 background="#FFF0DF", foreground="#7A3F00", relief="solid",
                 borderwidth=1, padx=6, pady=4).pack()
        self._adapted_tooltip = window

    def _show_deepened_tooltip(self, event) -> None:
        self._hide_adapted_tooltip()
        window = tk.Toplevel(self)
        window.overrideredirect(True)
        window.geometry(f"+{event.x_root + 12}+{event.y_root + 18}")
        tk.Label(window, text="Created by a deepening transformation.",
                 background="#DDF3EE", foreground="#08765E", relief="solid",
                 borderwidth=1, padx=6, pady=4).pack()
        self._adapted_tooltip = window

    def _hide_adapted_tooltip(self, _event=None) -> None:
        """Hide the import adaptation tooltip."""
        self._import_note_hover_item = None
        window = getattr(self, "_adapted_tooltip", None)
        if window is not None:
            window.destroy()
            self._adapted_tooltip = None

    def _card(self, parent) -> ctk.CTkFrame:
        return ctk.CTkFrame(
            parent,
            fg_color=self.colors["surface"],
            corner_radius=12,
            border_width=1,
            border_color=self.colors["border"],
        )

    def _card_title(self, parent, text: str) -> ctk.CTkLabel:
        return ctk.CTkLabel(
            parent,
            text=text,
            anchor="w",
            text_color=self.colors["text"],
            font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"),
        )

    @staticmethod

    def _tree(parent, **kwargs) -> ttk.Treeview:
        tree = ttk.Treeview(parent, **kwargs)
        tree.tag_configure("even", background="#ffffff")
        tree.tag_configure("odd", background="#f8fafc")
        return tree

    def _draw_model_overview_cell(
            self,
            x: int,
            y: int,
            width: int,
            height: int,
            text: Any,
            background: str,
            foreground: str,
            font,
            tags=(),
    ):
        # Draw one cell in the large model overview table.
        # "Any" is used because a cell may contain text, numbers, or empty values.
        self.detail_canvas.create_rectangle(
            x,
            y,
            x + width,
            y + height,
            fill=background,
            outline="#E4EBF4",
            width=1,
            tags=tags,
        )
        text_item = self.detail_canvas.create_text(
            x + (width / 2),
            y + (height / 2),
            text=self._display_table_value(text),
            fill=foreground,
            font=font,
            anchor="center",
            justify="center",
            width=max(20, width - 18),
            tags=tags,
        )
        if text is not None and str(text):
            self.detail_canvas.tag_bind(text_item, "<Enter>",
                lambda event, value=str(text): self._show_import_note_tooltip(event, [(value, False)]))
            self.detail_canvas.tag_bind(text_item, "<Leave>", self._hide_adapted_tooltip)

    def _draw_models_table_cell(
            self,
            x: int,
            y: int,
            width: int,
            height: int,
            text: Any,
            background: str,
            foreground: str,
            font,
    ) -> List[int]:
        # Draw one cell in the models overview list and return its canvas pieces.
        rect = self.models_canvas.create_rectangle(
            x,
            y,
            x + width,
            y + height,
            fill=background,
            outline="#AFC1D9",
            width=1,
        )
        label = self.models_canvas.create_text(
            x + (width / 2),
            y + (height / 2),
            text=self._display_table_value(text),
            fill=foreground,
            font=font,
            anchor="center",
            justify="center",
            width=max(20, width - 18),
        )
        return [rect, label]

    def _clear_tree(self, tree: ttk.Treeview):
        for item in tree.get_children():
            tree.delete(item)


class Overlay:
    """A dark, half transparent window that lies over the main window while a pop-up is open.

    Under Windows the overlay belongs to the main window, so Windows keeps it directly above the
    main window and below the pop-ups of the tool. It is disabled, so a click on it does nothing.
    A counter keeps the overlay visible until the last open pop-up is closed. On other systems
    show() and hide() do nothing, and cover() only centers the dialog.
    """

    def __init__(self, master: ModelDeepenerApp) -> None:
        """Create the hidden overlay for the given main window."""
        self._master = master
        self._open_count = 0
        self._hide_after_id = None
        self._window = tk.Toplevel(master)
        self._window.withdraw()
        self._window.overrideredirect(True)
        self._window.configure(background=master.colors["text"])
        self._window.attributes("-alpha", 0.35)

    def show(self) -> None:
        """Lay the overlay over the main window. Only under Windows."""
        if sys.platform != "win32":
            return
        if self._hide_after_id is not None:
            self._master.after_cancel(self._hide_after_id)
            self._hide_after_id = None
        self._open_count = self._open_count + 1
        if self._open_count > 1:
            return
        self._master.update_idletasks()
        x = self._master.winfo_rootx()
        y = self._master.winfo_rooty()
        width = self._master.winfo_width()
        height = self._master.winfo_height()
        self._window.geometry(f"{width}x{height}+{x}+{y}")
        self._window.deiconify()
        self._window.update_idletasks()
        # The main window becomes the owner, which keeps the overlay above the main window.
        overlay_handle = ctypes.windll.user32.GetParent(self._window.winfo_id())
        master_handle = ctypes.windll.user32.GetParent(self._master.winfo_id())
        ctypes.windll.user32.SetWindowLongPtrW(overlay_handle, OWNER_WINDOW_INDEX, master_handle)
        ctypes.windll.user32.EnableWindow(overlay_handle, False)
        self._window.lift(self._master)

    def hide(self) -> None:
        """Remove the overlay when no pop-up is open any more. Only under Windows."""
        if sys.platform != "win32" or self._open_count == 0:
            return
        self._open_count = self._open_count - 1
        if self._open_count == 0:
            def withdraw():
                self._hide_after_id = None
                if self._open_count == 0:
                    self._window.withdraw()
            self._hide_after_id = self._master.after(80, withdraw)

    def cover(self, dialog: ctk.CTkToplevel) -> None:
        """Center the dialog over the main window and show the overlay while it is open.

        The overlay is hidden when the dialog is destroyed, no matter how it is closed.
        """
        self.show()
        center_popup(dialog, self._master)
        recenter = dialog.after(RECENTER_DELAY_MILLISECONDS, center_popup, dialog, self._master)
        dialog.lift()

        def hide_after_close(event: tk.Event) -> None:
            """Hand the event of a closed window to the overlay, together with the dialog it covers."""
            if event.widget is dialog:
                try:
                    dialog.after_cancel(recenter)
                except tk.TclError:
                    pass
            self._hide_after_close(event, dialog)

        dialog.bind("<Destroy>", hide_after_close, add="+")

    def _hide_after_close(self, event: tk.Event, dialog: ctk.CTkToplevel) -> None:
        """Hide the overlay when the dialog itself is destroyed, not one of its widgets."""
        if event.widget is dialog:
            self.hide()


class DatabaseDialog(ctk.CTkToplevel):
    """Shows the list of databases with "Open" and a name field with "Create".

    The dialog only uses the public methods of DatabaseFolder. Checking a name is the job of
    DatabaseFolder, the dialog only shows its error messages. The colors come from the colors of
    the main window.

    The dialog is not transient, because the main window is still hidden at startup and a
    transient dialog would be hidden with it. Under Windows it is a tool window, so Windows shows
    no minimize button. It stays on top, because a tool window has no taskbar entry and would
    otherwise be lost behind other windows while the main window is hidden.
    """

    def __init__(self, master: ModelDeepenerApp, folder: DatabaseFolder) -> None:
        """Build the dialog for the databases in the given folder."""
        super().__init__(master)
        self._folder = folder
        self._colors = master.colors
        self._result: tuple[Database, str] | None = None
        self._loading = False
        # These widgets are created in _build_layout().
        self._name_list: tk.Listbox
        self._empty_hint: ctk.CTkLabel
        self._open_button: ctk.CTkButton
        self._name_entry: ctk.CTkEntry
        self._error_label: ctk.CTkLabel
        self.title("Choose database")
        self.resizable(False, False)
        if sys.platform == "win32":
            self.attributes("-toolwindow", True)
        self.attributes("-topmost", True)
        self.grid_columnconfigure(0, weight=1)
        self._build_layout()
        self._scale_database_font()
        self._fill_list()
        self._center()
        self.after(200, self._center)
        self.bind("<Escape>", lambda _event: self._cancel())
        self.protocol("WM_DELETE_WINDOW", self._cancel)
        # The main window is hidden at startup, so the dialog takes the keyboard focus by hand.
        self.after(150, self._take_focus)

    def _scale_database_font(self) -> None:
        """Match database names to the name entry, without changing headings.

        CTk uses logical pixels; Tk's listbox needs a negative, scaled pixel
        size to display the same font at the same size.
        """
        scaling = ctk.ScalingTracker.get_widget_scaling(self)
        entry_font = self._name_entry.cget("font")
        self._name_list.configure(font=(
            entry_font.cget("family"),
            -max(1, round(abs(entry_font.cget("size")) * scaling)),
        ))

    def _set_scaling(self, new_widget_scaling: float, new_window_scaling: float) -> None:
        """Adjust the font of the database list when CustomTkinter changes the scaling of the window."""
        super()._set_scaling(new_widget_scaling, new_window_scaling)
        if hasattr(self, "_name_list"):
            self._scale_database_font()

    @property
    def colors(self) -> Dict[str, str]:
        """Return the colors of the application, which popups over this dialog use too."""
        return self._colors

    def get_result(self) -> tuple[Database, str] | None:
        """Return the opened database and its name, or None if the user cancelled."""
        return self._result

    def _build_layout(self) -> None:
        """Create the widgets of the dialog.

        These are the list with "Open", the name field with "Create", the error label and "Cancel".
        """
        self._make_heading("Open a database", 0)

        self._name_list = tk.Listbox(
            self,
            height=8,
            activestyle="none",
            exportselection=False,
            font=("Segoe UI", 11),
            fg=self._colors["text"],
            selectbackground=self._colors["primary_soft"],
            selectforeground=self._colors["text"],
            highlightthickness=1,
            highlightbackground=self._colors["border"],
            highlightcolor=self._colors["border"],
            borderwidth=0,
        )
        self._name_list.grid(row=1, column=0, sticky="ew", padx=18)
        self._name_list.bind("<Double-Button-1>", lambda _event: self._open_selected())
        self._name_list.bind("<Return>", lambda _event: self._open_selected())

        # The hint uses the same row as the list. _fill_list() shows one of the two.
        self._empty_hint = ctk.CTkLabel(
            self,
            text="No database yet. Create your first database.",
            anchor="w",
            text_color=self._colors["muted"],
            font=ctk.CTkFont(family="Segoe UI", size=13),
        )
        self._empty_hint.grid(row=1, column=0, sticky="ew", padx=18)

        self._open_button = ctk.CTkButton(
            self,
            text="Open",
            width=100,
            height=36,
            fg_color=self._colors["primary"],
            hover_color=self._colors["primary_hover"],
            text_color="#FFFFFF",
            text_color_disabled="#FFFFFF",
            command=self._open_selected,
        )
        self._open_button.grid(row=2, column=0, sticky="e", padx=18, pady=(8, 0))
        self._delete_button = ctk.CTkButton(
            self, text="Delete", width=100, height=36,
            fg_color=self._colors["danger"], command=self._delete_selected,
        )
        self._delete_button.grid(row=2, column=0, sticky="w", padx=18, pady=(8, 0))

        self._make_heading("Create a new database", 3)

        create_row = ctk.CTkFrame(self, fg_color="transparent")
        create_row.grid(row=4, column=0, sticky="ew", padx=18)
        create_row.grid_columnconfigure(0, weight=1)
        self._name_entry = ctk.CTkEntry(
            create_row,
            height=36,
            width=260,
            placeholder_text="Name of the new database",
            border_color=self._colors["border"],
            text_color=self._colors["text"],
        )
        self._name_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self._name_entry.bind("<Return>", lambda _event: self._create_new())
        self._create_button = ctk.CTkButton(
            create_row,
            text="Create",
            width=100,
            height=36,
            fg_color=self._colors["primary"],
            hover_color=self._colors["primary_hover"],
            text_color="#FFFFFF",
            command=self._create_new,
        )
        self._create_button.grid(row=0, column=1)

        self._error_label = ctk.CTkLabel(
            self,
            text="",
            anchor="w",
            justify="left",
            wraplength=360,
            text_color=self._colors["danger"],
            font=ctk.CTkFont(family="Segoe UI", size=12),
        )
        self._error_label.grid(row=5, column=0, sticky="ew", padx=18, pady=(8, 0))

        ctk.CTkButton(
            self,
            text="Cancel",
            width=100,
            height=36,
            fg_color="#FFFFFF",
            hover_color="#EEF2F7",
            border_width=1,
            border_color=self._colors["border"],
            text_color=self._colors["text"],
            command=self._cancel,
        ).grid(row=6, column=0, sticky="e", padx=18, pady=(8, 18))

    def _make_heading(self, text: str, row: int) -> None:
        """Create a bold heading in the given row."""
        ctk.CTkLabel(
            self,
            text=text,
            anchor="w",
            text_color=self._colors["text"],
            font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"),
        ).grid(row=row, column=0, sticky="ew", padx=18, pady=(18, 6))

    def _fill_list(self) -> None:
        """Show the names of all databases in the list and select the first one.

        If there is no database yet, the list is hidden, the hint is shown and "Open" cannot be
        clicked.
        """
        self._name_list.delete(0, tk.END)
        for name in self._folder.get_names():
            self._name_list.insert(tk.END, name)
        self._delete_button.configure(state="disabled" if self._is_empty() else "normal")
        if self._is_empty():
            self._name_list.grid_remove()
            self._empty_hint.grid()
            self._open_button.configure(state="disabled", fg_color=self._colors["disabled"])
        else:
            self._empty_hint.grid_remove()
            self._name_list.grid()
            self._name_list.selection_set(0)
            self._open_button.configure(state="normal", fg_color=self._colors["primary"])

    def _is_empty(self) -> bool:
        """Return True if the list contains no database."""
        return self._name_list.size() == 0

    def _open_selected(self) -> None:
        """Open the selected database and close the dialog, or show why it cannot be opened.

        The message "Please select a database first." is only a safeguard: "Open" cannot be
        clicked when the list is empty, and otherwise one entry is always selected.
        """
        if self._loading:
            return
        selection = self._name_list.curselection()
        if len(selection) == 0:
            self._show_dialog_error("Please select a database first.")
            return
        name = self._name_list.get(selection[0])
        self._loading = True
        self._open_button.configure(state="disabled")
        self._delete_button.configure(state="disabled")
        self._create_button.configure(state="disabled")
        self._name_entry.configure(state="disabled")
        self._name_list.configure(state="disabled")
        results = queue.Queue()
        def load():
            try:
                results.put((self._folder.open_database(name), None))
            except Exception as error:
                results.put((None, error))
        def show_loading():
            if self._loading:
                self._error_label.configure(text="Loading database...")
        def finish():
            try:
                database, error = results.get_nowait()
            except queue.Empty:
                self.after(30, finish)
                return
            self.after_cancel(timer)
            self._loading = False
            self._name_entry.configure(state="normal")
            self._name_list.configure(state="normal")
            self._create_button.configure(state="normal")
            self._error_label.configure(text="")
            if isinstance(error, IncompatibleDatabaseError):
                self._fill_list()
                self._handle_incompatible_database(name)
            elif error is not None:
                self._show_dialog_error(str(error))
                self._fill_list()
            else:
                self._close_with(database, name)
        timer = self.after(500, show_loading)
        threading.Thread(target=load, daemon=True).start()
        self.after(30, finish)

    def _handle_incompatible_database(self, name: str) -> None:
        """Update only after the user chooses conversion; keep a recovery backup."""
        choice = ask_database_conversion(self, name)
        if choice == "delete":
            self._delete_selected()
        elif choice == "convert":
            try:
                database, converted_name, report = self._folder.convert_database(name)
            except Exception as error:
                self._show_dialog_error(f"Conversion failed. The original database is unchanged. {error}")
                return
            popup_message(self, "Database converted", f"Updated '{converted_name}'.\n\n{report}")
            self._close_with(database, converted_name)

    def _delete_selected(self) -> None:
        """Confirm deletion. Deleting the active database forces a new selection.

        Cancel and X close this dialog. The caller then offers a new selection
        or application shutdown while keeping the main window inaccessible.
        """
        selection = self._name_list.curselection()
        if not selection:
            return
        name = self._name_list.get(selection[0])
        if not popup_message(self, "Delete database",
                f"Do you really want to delete database '{name}' and all models it contains?\n"
                "This cannot be undone.", confirm=True):
            return
        try:
            self._folder.delete_database(name)
        except (OSError, KeyError) as error:
            self._show_dialog_error(str(error))
            return
        if self.master.forget_deleted_database(name):
            self._show_dialog_error("The active database was deleted. Open or create a database to continue.")
        self._fill_list()

    def _create_new(self) -> None:
        """Create a database with the entered name and close the dialog, or show the error."""
        if self._loading:
            return
        name = self._name_entry.get().strip()
        try:
            database = self._folder.create_database(name)
        except ValueError as error:
            self._show_dialog_error(error.args[0])
            return
        self._close_with(database, name)

    def _show_dialog_error(self, message: str) -> None:
        """Show an error message in the dialog. The dialog stays open."""
        self._error_label.configure(text=message)

    def _cancel(self) -> None:
        """Close the dialog without a database."""
        if not self._loading:
            self._close()

    def _close_with(self, database: Database, name: str) -> None:
        """Remember the database and its name as result and close the dialog."""
        self._result = (database, name)
        self._close()

    def _close(self) -> None:
        """Release the input grab and close the dialog."""
        self.grab_release()
        self.destroy()

    def _center(self) -> None:
        """Center on the screen at startup, otherwise on the visible main window.

        The delayed pass uses the same owner, so it cannot move a switching
        dialog away from the main window after the overlay has positioned it.
        """
        center_popup(self, self.master)

    def _take_focus(self) -> None:
        """Give the keyboard focus to the dialog and to the list.

        If there is no database yet, the name field gets the focus. focus_force() is used, because
        Windows does not always give a new window the focus, for example when the user clicks
        into another window at startup.
        """
        if not self.winfo_exists():
            return
        self.focus_force()
        if self._is_empty():
            self._name_entry.focus_set()
        else:
            self._name_list.focus_set()


def _cancel_widget_timers(widget: tk.Misc) -> None:
    """Cancel callbacks registered by a widget and its children before destroying them."""
    commands = set()
    def collect(item):
        commands.update(getattr(item, "_tclCommands", None) or ())
        for child in item.winfo_children():
            collect(child)
    collect(widget)
    for after_id in widget.tk.call("after", "info"):
        script = widget.tk.call("after", "info", after_id)[0]
        if str(script).split(" ", 1)[0] in commands:
            widget.tk.call("after", "cancel", after_id)


def _styled_dialog(master, title, resizable=False):
    """Create a dialog with the same base styling as the import problem dialog."""
    dialog = ctk.CTkToplevel(master)
    dialog.title(title)
    dialog.transient(master)
    if not resizable:
        dialog.resizable(False, False)
    dialog.configure(fg_color=master.colors["app_bg"])
    return dialog


def _dialog_heading(parent, text, colors):
    ctk.CTkLabel(parent, text=text, anchor="w", text_color=colors["text"],
                 font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold")).pack(
                     fill="x", padx=18, pady=(18, 4))


def _dialog_primary_button(parent, text, command, colors):
    return ctk.CTkButton(parent, text=text, height=36, fg_color=colors["primary"],
                         hover_color=colors["primary_hover"], text_color="#FFFFFF", command=command)


def _dialog_plain_button(parent, text, command, colors):
    return ctk.CTkButton(parent, text=text, height=36, fg_color="#FFFFFF", hover_color="#EEF2F7",
                         border_width=1, border_color=colors["border"], text_color=colors["text"], command=command)


def _dialog_checkbox(parent, text, variable, colors):
    return ctk.CTkCheckBox(parent, text=text, variable=variable, text_color=colors["text"],
                           fg_color=colors["primary"], hover_color=colors["primary_hover"],
                           border_color=colors["border"], font=ctk.CTkFont(family="Segoe UI", size=13))


class BatchProblemDetails(ctk.CTkFrame):
    """Display only the visible rows of expandable batch import reports."""
    ROW_HEIGHT = 28

    def __init__(self, master, reports, colors, prepared=False, initial_rows=None):
        super().__init__(master, fg_color=colors["surface"])
        self.reports = list(reports) if prepared else [(name, visible_import_report(report)) for name, report in reports]
        self.expanded = set()
        self.rows = []
        self.configure(height=self.ROW_HEIGHT * 5)
        self.pack_propagate(False)
        self.canvas = tk.Canvas(self, bg="#FFFFFF", highlightthickness=0, bd=0)
        self.scrollbar = ctk.CTkScrollbar(self, orientation="vertical", command=self.canvas.yview)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")
        self.canvas.configure(yscrollcommand=self._on_scroll)
        self.canvas.bind("<Configure>", self._draw_rows)
        self.canvas.bind("<MouseWheel>", self._wheel)
        self.canvas.bind("<Button-1>", self._click)
        self.headers = list(initial_rows) if initial_rows is not None else batch_report_rows(self.reports)
        self.rows = list(self.headers)
        self._update_scrollregion()

    def _rebuild(self):
        self.rows = []
        for index, (_name, report) in enumerate(self.reports):
            self.rows.append(self.headers[index])
            if index in self.expanded:
                lines = (report.get_conversion_summary_lines() + report.get_structure_summary_lines()
                         + report.get_adaptation_summary_lines())
                for line in lines:
                    for part in textwrap.wrap("- " + line, width=92, subsequent_indent="  ") or [""]:
                        self.rows.append((index, False, part))
        self._update_scrollregion()

    def _update_scrollregion(self):
        self.canvas.configure(scrollregion=(0, 0, 1, max(1, len(self.rows)) * self.ROW_HEIGHT))
        self._draw_rows()

    def _on_scroll(self, first, last):
        self.scrollbar.set(first, last)
        self._draw_rows()

    def _wheel(self, event):
        self.canvas.yview_scroll(int(-event.delta / 120), "units")
        return "break"

    def _click(self, event):
        index = int(self.canvas.canvasy(event.y) // self.ROW_HEIGHT)
        if 0 <= index < len(self.rows):
            model_index, header, _text = self.rows[index]
            if header:
                if model_index in self.expanded:
                    self.expanded.remove(model_index)
                else:
                    self.expanded.add(model_index)
                self._rebuild()

    def _draw_rows(self, _event=None):
        self.canvas.delete("all")
        top = max(0, int(self.canvas.canvasy(0) // self.ROW_HEIGHT))
        bottom = min(len(self.rows), int(self.canvas.canvasy(self.canvas.winfo_height()) // self.ROW_HEIGHT) + 2)
        width = self.canvas.winfo_width()
        for row in range(top, bottom):
            index, header, text = self.rows[row]
            y = row * self.ROW_HEIGHT
            if header:
                self.canvas.create_rectangle(0, y, width, y + self.ROW_HEIGHT,
                                             fill="#F3F7FD" if row % 2 else "#FFFFFF", outline="")
                text = ("\u2212  " if index in self.expanded else "+  ") + text
            self.canvas.create_text(10 if header else 30, y + self.ROW_HEIGHT // 2, text=text,
                                    anchor="w", fill="#0F172A", font=("Segoe UI", 11, "bold") if header else ("Segoe UI", 11))


class VirtualModelSelector(ctk.CTkFrame):
    """Display and select models while drawing only rows in the viewport."""
    ROW_HEIGHT = 34
    BOX_SIZE = 22

    def __init__(self, master, models, colors):
        super().__init__(master, fg_color=colors["surface"], corner_radius=6, width=680, height=260)
        self.models = list(models)
        self.selected = [True] * len(self.models)
        self.colors = colors
        self._focus_index = 0
        self.canvas = tk.Canvas(self, width=660, height=260, background=colors["surface"],
                                highlightthickness=0, takefocus=True)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar = ctk.CTkScrollbar(self, orientation="vertical", command=self.canvas.yview)
        self.scrollbar.pack(side="right", fill="y")
        self.canvas.configure(scrollregion=(0, 0, 1, max(1, len(self.models)) * self.ROW_HEIGHT),
                              yscrollcommand=self._scroll)
        self.canvas.bind("<Configure>", self._draw_rows)
        self.canvas.bind("<Button-1>", self._click)
        self.canvas.bind("<MouseWheel>", self._wheel)
        self.canvas.bind("<space>", self._toggle_focused)
        self.canvas.bind("<Up>", lambda _event: self._move_focus(-1))
        self.canvas.bind("<Down>", lambda _event: self._move_focus(1))
        self._draw_rows()

    def selected_models(self):
        """Return the checked models in their original order."""
        return [model for model, checked in zip(self.models, self.selected) if checked]

    def _scroll(self, first, last):
        self.scrollbar.set(first, last)
        self._draw_rows()

    def _draw_rows(self, _event=None):
        self.canvas.delete("all")
        top = max(0, int(self.canvas.canvasy(0) // self.ROW_HEIGHT))
        bottom = min(len(self.models), int(self.canvas.canvasy(self.canvas.winfo_height()) // self.ROW_HEIGHT) + 2)
        for index in range(top, bottom):
            y = index * self.ROW_HEIGHT
            self._draw_checkbox(12, y + 6, self.selected[index])
            self.canvas.create_text(43, y + 17, text=self.models[index].name, anchor="w",
                                    fill=self.colors["text"], font=("Segoe UI", 12))

    def _draw_checkbox(self, x, y, checked):
        """Draw a box like a CTkCheckBox: blue with a white check mark when checked, otherwise empty."""
        size, radius = self.BOX_SIZE, 6
        right, bottom = x + size, y + size
        points = [x + radius, y, right - radius, y, right, y, right, y + radius, right, bottom - radius,
                  right, bottom, right - radius, bottom, x + radius, bottom, x, bottom, x, bottom - radius,
                  x, y + radius, x, y]
        fill = self.colors["primary"] if checked else self.colors["surface"]
        outline = self.colors["primary"] if checked else self.colors["border"]
        self.canvas.create_polygon(points, smooth=True, fill=fill, outline=outline, width=1 if checked else 3,
                                   tags=("checkbox",))
        if checked:
            self.canvas.create_line(x + size * 0.25, y + size * 0.52, x + size * 0.43, y + size * 0.7,
                                    x + size * 0.76, y + size * 0.32, fill="#FFFFFF", width=2.5,
                                    capstyle="round", joinstyle="round", tags=("checkmark",))

    def _click(self, event):
        index = int(self.canvas.canvasy(event.y) // self.ROW_HEIGHT)
        if 0 <= index < len(self.models):
            self._focus_index = index
            self.canvas.focus_set()
            self.selected[index] = not self.selected[index]
            self._draw_rows()

    def _wheel(self, event):
        self.canvas.yview_scroll(int(-event.delta / 120), "units")
        return "break"

    def _toggle_focused(self, _event):
        if self.models:
            self.selected[self._focus_index] = not self.selected[self._focus_index]
            self._draw_rows()
        return "break"

    def _move_focus(self, delta):
        if self.models:
            self._focus_index = max(0, min(len(self.models) - 1, self._focus_index + delta))
            self.canvas.yview_moveto(self._focus_index / len(self.models))
        return "break"


class InlineModelProgress(ctk.CTkFrame):
    """Show model progress within an existing dialog."""
    def __init__(self, master: ctk.CTkToplevel, total: int, message: str, colors: dict[str, str]) -> None:
        super().__init__(master, fg_color="transparent")
        anchor = getattr(master, "_progress_anchor", None)
        self.pack(fill="x", padx=18, pady=(4, 12), **({"before": anchor} if anchor else {}))
        self.label = ctk.CTkLabel(self, text=message, text_color=colors["muted"])
        self.label.pack(anchor="w")
        self._indeterminate = total <= 1
        self.bar = ctk.CTkProgressBar(self, progress_color=colors["primary"],
                                      mode="indeterminate" if self._indeterminate else "determinate")
        self.bar.pack(fill="x", pady=4)
        self.count = ctk.CTkLabel(self, text=f"0 / {total} models", text_color=colors["muted"])
        if not self._indeterminate:
            self.count.pack(anchor="e")
        self.bar.set(0)
        if self._indeterminate:
            self.bar.start()
        master.update_idletasks()
        scale = ctk.ScalingTracker.get_window_scaling(master)
        width = round(master.winfo_width() / scale)
        height = round(master.winfo_height() / scale)
        requested = round(master.winfo_reqheight() / scale)
        max_height = max(1, int((master.winfo_screenheight() - 80) / scale))
        master.geometry(f"{width}x{min(max_height, max(height, requested))}")
        master.update_idletasks()
        center_popup(master, master.master)

    def set_message(self, message: str) -> None:
        """Update the displayed progress message."""
        self.label.configure(text=message)
        if message == "Writing database..." and not self._indeterminate:
            self._indeterminate = True
            self.count.pack_forget()
            self.bar.configure(mode="indeterminate")
            self.bar.start()

    def update_progress(self, count: int, total: int, fraction: float | None = None) -> None:
        """Update the bar and model count for determinate progress."""
        if not self._indeterminate:
            self.bar.set(fraction if fraction is not None else count / total if total else 0)
            self.count.configure(text=f"{count} / {total} models")


class ModelProgressDialog(ctk.CTkToplevel):
    """Reusable centered modal window for model progress."""
    def __init__(self, master: ModelDeepenerApp, total: int, message: str) -> None:
        super().__init__(master)
        self.withdraw()
        self.title("Loading Data...")
        self.transient(master)
        self.resizable(False, False)
        self.protocol("WM_DELETE_WINDOW", lambda: None)
        self.configure(fg_color="#FFFFFF")
        colors = master.colors
        panel = ctk.CTkFrame(self, fg_color="#FFFFFF", corner_radius=12,
                             border_width=1, border_color=colors["border"], width=500)
        panel.pack(fill="both", expand=True, padx=8, pady=8)
        panel.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(panel, text="Loading Data...", text_color=colors["text"],
                     font=ctk.CTkFont(family="Segoe UI", size=17, weight="bold")).grid(row=0, column=0, pady=(26, 6))
        self.message = ctk.CTkLabel(panel, text=message, text_color=colors["muted"],
                                    font=ctk.CTkFont(family="Segoe UI", size=12))
        self.message.grid(row=1, column=0, pady=(0, 18))
        self.bar = ctk.CTkProgressBar(panel, width=420, height=13, corner_radius=7, progress_color=colors["primary"])
        self.bar.grid(row=2, column=0, sticky="ew", padx=34)
        self.count = ctk.CTkLabel(panel, text="", text_color=colors["muted"],
                                  font=ctk.CTkFont(family="Segoe UI", size=12))
        self._show_after = None
        self.prepare(total, message)

    def prepare(self, total: int, message: str) -> None:
        """Reset the message and bar for a new operation."""
        self.bar.stop()
        self.message.configure(text=message)
        self._indeterminate = total <= 1 and message != "Preparing analysis..."
        self.bar.configure(mode="indeterminate" if self._indeterminate else "determinate")
        self.bar.set(0)
        self.count.configure(text=f"0 / {total} models")
        if self._indeterminate:
            self.count.grid_remove()
        else:
            self.count.grid(row=3, column=0, pady=(12, 26))

    def show(self) -> None:
        """Display the progress window and keep it modal until hidden."""
        self.update_idletasks()
        self.deiconify()
        self.update_idletasks()
        center_popup(self, self.master)
        self.lift()
        self.grab_set()
        if self._indeterminate:
            self.bar.start()
        self._show_after = self.after(50, self._ensure_visible)

    def _ensure_visible(self) -> None:
        self._show_after = None
        self.deiconify()
        self.lift()

    def hide(self) -> None:
        """Hide the window until the next operation."""
        if self._show_after is not None:
            self.after_cancel(self._show_after)
            self._show_after = None
        self.bar.stop()
        self.grab_release()
        self.withdraw()

    def set_message(self, message: str) -> None:
        """Update the displayed progress message."""
        self.message.configure(text=message)
        if message == "Writing database..." and not self._indeterminate:
            self._indeterminate = True
            self.count.grid_remove()
            self.bar.configure(mode="indeterminate")
            self.bar.start()

    def update_progress(self, count: int, total: int, fraction: float | None = None) -> None:
        """Update the bar and model count for determinate progress."""
        if not getattr(self, "_indeterminate", False):
            self.bar.set(fraction if fraction is not None else count / total if total else 0)
            self.count.configure(text=f"{count} / {total} models")
        self.update_idletasks()


class ImportProblemDialog(ctk.CTkToplevel):
    """Shows the problems of an import in one section per kind and lets the user continue or cancel the import.

    The height of a list follows its content up to a maximum, then the list scrolls.
    "Continue Import" is the default button. Closing the window cancels the import. The dialog
    only shows the texts of the ImportReport and uses Tk widgets, so it works on every system.
    """

    DATA_TYPE_TITLE = "Some values do not match their data type"
    STRUCTURE_TITLE = "The file contains elements that could not be resolved"
    STRUCTURE_EXPLANATION = "These problems already exist in the file and were not caused by the import."
    ADAPTED_TITLE = "Some elements were adapted during the import"
    ADAPTED_EXPLANATION = "These elements have no direct counterpart in the model, so they were changed or left out."
    SEVERAL_TITLE = "Import Problems"
    LIST_WIDTH = 680
    LIST_TEXT_WIDTH = 640
    LIST_PADDING = 20
    MAX_LIST_HEIGHT = 220

    def __init__(self, master: ModelDeepenerApp, report: ImportReport) -> None:
        """Build the dialog for the given report."""
        super().__init__(master)
        self._report = visible_import_report(report)
        self._colors = master.colors
        self._continue_import = False
        self.title(self._window_title())
        self.resizable(False, False)
        self.transient(master)
        self.configure(fg_color=self._colors["app_bg"])
        self._status_label = self._build_layout()
        self.bind("<Return>", self._continue_with_key)
        self.bind("<Escape>", self._cancel_with_key)
        self.protocol("WM_DELETE_WINDOW", self._cancel)

    def should_continue(self) -> bool:
        """Return True if the user continued the import."""
        return self._continue_import

    def _build_layout(self) -> ctk.CTkLabel:
        """Create the widgets and return the label that reports on the saved list."""
        if self._report.has_conversion_failures():
            self._add_section(self.DATA_TYPE_TITLE, self._data_type_explanation(),
                              self._report.get_conversion_summary_lines())
        if self._report.has_structure_problems():
            self._add_section(self.STRUCTURE_TITLE, self.STRUCTURE_EXPLANATION,
                              self._report.get_structure_summary_lines())
        if self._report.has_adaptations():
            self._add_section(self.ADAPTED_TITLE, self.ADAPTED_EXPLANATION,
                              self._report.get_adaptation_summary_lines())
        status_label = ctk.CTkLabel(self, text="", anchor="w", wraplength=self.LIST_WIDTH, justify="left",
                                    text_color=self._colors["muted"],
                                    font=ctk.CTkFont(family="Segoe UI", size=12))
        status_label.pack(fill="x", padx=18, pady=(6, 0))

        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=18, pady=(8, 18))
        continue_button = ctk.CTkButton(row, text="Continue Import", height=36, fg_color=self._colors["primary"],
                                        hover_color=self._colors["primary_hover"], text_color="#FFFFFF",
                                        command=self._continue)
        continue_button.pack(side="right")
        self._make_plain_button(row, "Cancel Import", self._cancel).pack(side="right", padx=(0, 8))
        self._make_plain_button(row, "Export Problem List (CSV)", self._save_list).pack(side="left")
        continue_button.focus_set()
        return status_label

    def _add_section(self, title: str, explanation: str, lines: list[str]) -> None:
        """Add a heading, a sentence and a list that fits its content."""
        ctk.CTkLabel(self, text=title, anchor="w", text_color=self._colors["text"],
                     font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold")).pack(
                         fill="x", padx=18, pady=(18, 4))
        ctk.CTkLabel(self, text=explanation, anchor="w", wraplength=self.LIST_WIDTH, justify="left",
                     text_color=self._colors["muted"], font=ctk.CTkFont(family="Segoe UI", size=13)).pack(
                         fill="x", padx=18, pady=(0, 10))
        list_font = ctk.CTkFont(family="Segoe UI", size=13)
        list_text = "\n".join(lines)
        text_box = ctk.CTkTextbox(self, width=self.LIST_WIDTH, height=self._list_height(list_text, list_font),
                                  wrap="word", text_color=self._colors["text"], font=list_font)
        text_box.pack(fill="both", padx=18)
        text_box.insert("1.0", list_text)
        text_box.configure(state="disabled")

    def _window_title(self) -> str:
        """Return the title that fits the kinds of problems in the report."""
        titles = []
        if self._report.has_conversion_failures():
            titles.append(self.DATA_TYPE_TITLE)
        if self._report.has_structure_problems():
            titles.append(self.STRUCTURE_TITLE)
        if self._report.has_adaptations():
            titles.append(self.ADAPTED_TITLE)
        return titles[0] if len(titles) == 1 else self.SEVERAL_TITLE

    def _make_plain_button(self, parent: ctk.CTkFrame, text: str, command: Callable[[], None]) -> ctk.CTkButton:
        """Create a white button in the style of the other dialogs."""
        return ctk.CTkButton(parent, text=text, height=36, fg_color="#FFFFFF", hover_color="#EEF2F7",
                             border_width=1, border_color=self._colors["border"],
                             text_color=self._colors["text"], command=command)

    def _data_type_explanation(self) -> str:
        """Return the sentence that says what happened to the listed values."""
        count = len(self._report.get_conversion_failures())
        if count == 1:
            return "1 value was kept as text because it does not fit the data type of its attribute."
        return f"{count} values were kept as text because they do not fit the data types of their attributes."

    def _list_height(self, text: str, font: ctk.CTkFont) -> int:
        """Return the height that shows the text with its wrapped lines, up to the maximum height."""
        line_count = 0
        for line in text.split("\n"):
            line_count += max(1, math.ceil(font.measure(line) / self.LIST_TEXT_WIDTH))
        return min(self.MAX_LIST_HEIGHT, line_count * font.metrics("linespace") + self.LIST_PADDING)

    def _save_list(self) -> None:
        """Ask for a file and write all problems to it. The dialog stays open."""
        file_path = filedialog.asksaveasfilename(
            parent=self.master, title="Export Problem List (CSV)", initialfile="import_problems.csv",
            defaultextension=".csv", filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        )
        if not file_path:
            return
        try:
            self._report.write_problem_list(file_path)
        except OSError as error:
            self._status_label.configure(text=f"The list could not be saved: {error.strerror}")
            return
        self._status_label.configure(text=f"List saved: {file_path}")

    def _continue(self) -> None:
        """Close the dialog and continue the import."""
        self._continue_import = True
        self.destroy()

    def _cancel(self) -> None:
        """Close the dialog and cancel the import."""
        self._continue_import = False
        self.destroy()

    def _continue_with_key(self, _event: tk.Event) -> None:
        """Continue the import with the Return key."""
        self._continue()

    def _cancel_with_key(self, _event: tk.Event) -> None:
        """Cancel the import with the Escape key."""
        self._cancel()


def ask_import_problems(master: ModelDeepenerApp, report: ImportReport, overlay: Overlay) -> bool:
    """Show the problems of an import and return True if the user continues the import."""
    report = visible_import_report(report)
    if not report.has_problems():
        return True
    dialog = ImportProblemDialog(master, report)
    overlay.cover(dialog)
    dialog.grab_set()
    master.wait_window(dialog)
    return dialog.should_continue()


def ask_for_database(
        master: ModelDeepenerApp,
        folder: DatabaseFolder,
        overlay: Overlay | None,
) -> tuple[Database, str] | None:
    """Show the dialog and wait until it is closed.

    Without an overlay the dialog is centered on the screen. With an overlay it is centered over
    the darkened main window. Returns the opened database and its name, or None if the user
    cancelled or closed the dialog.
    """
    dialog = DatabaseDialog(master, folder)
    if overlay is not None:
        overlay.cover(dialog)
    dialog.grab_set()
    master.wait_window(dialog)
    return dialog.get_result()


def run() -> None:
    """Starts Model Deepener and keeps its interface active until it is closed.

    If the database dialog is cancelled at startup, the tool is already closed and destroyed.
    mainloop() is not started then, because CTk.mainloop() fails on a destroyed window.
    """
    ModelDeepenerApp._set_windows_app_id()
    app = ModelDeepenerApp()
    if app.is_running():
        app.mainloop()

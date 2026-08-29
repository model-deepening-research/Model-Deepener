# External packages for this project belong to the Python 3.12 environment in .venv312.
# Keeping one shared environment makes the GUI use the same library versions on every start.
# noinspection PyPackageRequirements
import csv
import json
import os
import random
import re
import shutil
import tkinter as tk
import customtkinter as ctk
from dataclasses import dataclass, field
from datetime import datetime
from PIL import Image
from tkinter import filedialog, messagebox, ttk
from tkinter import font as tk_font
from typing import Any, Dict, List, Optional

from src.fmmlx_mlm_structure.fm_attr import FmmlxAttribute
from src.fmmlx_mlm_structure.fm_enum_type import FmmlxEnumType
from src.fmmlx_mlm_structure.fm_multi_level_model import FmmlxModel
from src.fmmlx_mlm_structure.fm_object import FmmlxObject
from src.fmmlx_mlm_structure.fm_slot import FmmlxSlot


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
    model: Optional[FmmlxModel] = None


@dataclass
class LoadedModel:
    name: str
    source_file: str
    file_type: str
    model: FmmlxModel
    source_path: str = ""
    selected_columns: List[str] = field(default_factory=list)
    uploaded: str = ""
    last_worked_on: str = ""
    last_action: str = "Imported"


# noinspection PyAttributeOutsideInit,PyUnresolvedReferences,PyTypeChecker,SpellCheckingInspection
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
        1: "Upload File or Select Example",
        2: "Inspect Model",
        3: "Conduct Model Deepening Analysis",
    }

    def __init__(self):
        """
        Prepares the main window and all data needed by the interface.

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
        self.minsize(1220, 760)
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

        self.current_model: Optional[FmmlxModel] = None
        self.current_file_path: Optional[str] = None
        self.current_file_type: str = ""
        self.current_selected_columns: List[str] = []
        self.csv_preview: Optional[CsvImportPreview] = None
        self.xml_preview: Optional[XmlImportPreview] = None
        self.selected_csv_columns: Dict[str, tk.BooleanVar] = {}
        self.tree_item_payload: Dict[str, object] = {}
        self.tree_item_view: Dict[str, str] = {}
        self.loaded_models: List[LoadedModel] = []
        self.loaded_models_store_path = os.path.join(os.getcwd(), "example_models", "loaded_models.json")
        self.action_unlocked = {1: True, 2: False, 3: False}
        self.action_completed = {1: False, 2: False, 3: False}
        self.current_action = 1
        self.active_top_tab = "new"
        self.model_tab = None
        self.logo_image = None
        self.titlebar_logo_image = None
        # These values remember how the user moves and resizes the window.
        self._window_drag_offset = (0, 0)
        self._window_restore_geometry = None
        self._window_maximized = False
        self._window_restore_binding_id = None
        # This flag prevents the close procedure from running twice.
        self._is_closing = False
        self._detail_load_token = 0
        self._detail_batch_after_id = None
        self._detail_loading_overlay = None
        self.column_selection_expanded = False
        self.all_columns_selected_var = tk.BooleanVar(value=True)

        self._load_saved_models()
        self._configure_ttk_style()
        self._build_layout()
        self._show_import_page()
        self.after_idle(self._show_configured_window)

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

    def _toggle_maximize_window(self):
        """
        Switches between the maximized and normal window sizes.

        The maximized size uses the available area of the current monitor, so
        the window fits different screens and leaves the Windows taskbar free.
        """
        if self._window_maximized:
            if self._window_restore_geometry:
                tk.Tk.geometry(self, self._window_restore_geometry)
            self._window_maximized = False
            return

        self._window_restore_geometry = tk.Tk.geometry(self)
        try:
            import ctypes
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

            # The work area is the part of the monitor not occupied by the
            # taskbar. The window fills exactly this area.
            work_area = monitor_info.rcWork
            width = work_area.right - work_area.left
            height = work_area.bottom - work_area.top
            swp_no_zorder = 0x0004
            swp_show_window = 0x0040
            ctypes.windll.user32.SetWindowPos(
                hwnd,
                None,
                work_area.left,
                work_area.top,
                width,
                height,
                swp_no_zorder | swp_show_window,
            )
            self._window_maximized = True
        except (AttributeError, OSError):
            # Tk's normal maximize mode is used if Windows cannot provide the
            # monitor information.
            self.state("zoomed")

    def _minimize_window(self):
        """Minimizes the application and keeps it available in the taskbar."""
        self.overrideredirect(False)
        self.iconify()
        # The Map event occurs when the minimized window becomes visible again.
        if self._window_restore_binding_id is None:
            self._window_restore_binding_id = self.bind(
                "<Map>",
                self._restore_custom_window,
                add="+",
            )

    def _close_application(self):
        """
        Closes the complete application when the user selects the X button.

        Scheduled interface tasks are cancelled before the window and its
        event loop are stopped, so the application does not remain active in
        the background.
        """
        if self._is_closing:
            return
        self._is_closing = True
        try:
            for after_id in self.tk.call("after", "info"):
                try:
                    self.after_cancel(after_id)
                except tk.TclError:
                    pass
        except tk.TclError:
            pass
        self.quit()
        self.destroy()

    def _restore_custom_window(self, _event=None):
        """Restores the tool's own top row after the window was minimized."""
        if self._window_restore_binding_id is not None:
            self.unbind("<Map>", self._window_restore_binding_id)
            self._window_restore_binding_id = None

        def restore():
            """Shows the tool's own top row when the window becomes visible again."""
            self.overrideredirect(True)
            self._configure_custom_window()

        self.after_idle(restore)

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
            import ctypes
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
        self.header.grid_columnconfigure(3, weight=1)

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
        self.new_model_tab.grid(row=0, column=0, padx=(24, 8), pady=12)

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
        self.models_tab.grid(row=0, column=1, padx=(0, 8), pady=12)

        self.model_tab = ctk.CTkButton(
            self.header,
            text="",
            width=160,
            height=42,
            corner_radius=8,
            fg_color="transparent",
            hover_color=self.colors["surface_alt"],
            text_color=self.colors["text"],
            font=ctk.CTkFont(size=14),
            command=self._show_model_page,
        )
        self.model_tab.grid(row=0, column=2, padx=(0, 8), pady=12)
        self.model_tab.grid_remove()

        self.logo_label = ctk.CTkLabel(self.header, text="", width=1)
        self.logo_label.grid(row=0, column=4, sticky="e", padx=(8, 24), pady=8)
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

        sidebar_note = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        sidebar_note.pack(fill="x", side="bottom", padx=20, pady=24)

        ctk.CTkLabel(
            sidebar_note,
            text="i",
            text_color=self.colors["muted"],
            font=ctk.CTkFont(size=15),
        ).grid(row=0, column=0, sticky="nw", padx=(0, 8))

        ctk.CTkLabel(
            sidebar_note,
            text=(
                "Upload a file first.\n"
                "Then switch between the available\n"
                "model actions whenever needed."
            ),
            justify="left",
            anchor="w",
            text_color=self.colors["muted"],
            font=ctk.CTkFont(size=11),
        ).grid(row=0, column=1, sticky="w")

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
            import ctypes
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

    def _clear_content(self):
        for child in self.content.winfo_children():
            child.destroy()

    def _show_workflow_sidebar(self):
        self.sidebar.grid(row=0, column=0, sticky="nsw")
        self.content.grid_configure(row=0, column=1, columnspan=1, sticky="nsew", padx=18, pady=18)

    def _hide_workflow_sidebar(self):
        self.sidebar.grid_remove()
        self.content.grid_configure(row=0, column=0, columnspan=2, sticky="nsew", padx=18, pady=18)

    def _set_top_tab(self, active: str):
        self.active_top_tab = active
        for button, is_active in (
                (self.new_model_tab, active == "new"),
                (self.models_tab, active == "models"),
                (self.model_tab, active == "model"),
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
        if not self._is_navigation_item_available(action):
            return
        if action == 1:
            self._show_import_page()
        elif action == 2:
            self._show_model_page()
        else:
            self._open_placeholder_action(action)

    def _is_navigation_item_available(self, action: int) -> bool:
        if action == 1:
            return self.current_model is None
        if action != 1:
            return self.current_model is not None
        return True

    def _update_model_tab(self):
        """
        Shows or hides the top tab for the open model.

        The New Model tab starts a new import. The model tab returns to the
        currently opened model.
        """
        if self.model_tab is None:
            return
        if self.current_model is None:
            self.model_tab.grid_remove()
            return
        self.model_tab.configure(text=self._short_tab_text(self._current_model_display_name()))
        self.model_tab.grid()

    def _current_model_display_name(self) -> str:
        """
        Returns the model name shown in the top tab.

        If the model has no path name, the file name is used instead.
        """
        if self.current_model is None:
            return "Model"
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

    def _show_import_page(self):
        """
        Shows the New Model page.

        This page contains Upload File, Select Example, Validation Results,
        Column Selection, and the Create Model and Continue button.
        """
        self._reset_current_import_state()
        self._update_model_tab()
        self.current_action = 1
        self._set_last_action(1)
        self._show_workflow_sidebar()
        self._set_top_tab("new")
        self._refresh_actions()
        self._clear_content()

        self._page_header(
            "Upload File or Select Example",
            "Import a CSV or FMMLx/XML file. Validation starts automatically after a file is selected.",
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
        tab_row.grid_columnconfigure((0, 1), weight=1)

        ctk.CTkButton(
            tab_row,
            text="Upload File",
            height=38,
            corner_radius=7,
            fg_color=self.colors["primary"],
            hover_color=self.colors["primary_hover"],
            text_color="#ffffff",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            command=self._browse_file,
        ).grid(row=0, column=0, sticky="ew", padx=(0, 5))

        ctk.CTkButton(
            tab_row,
            text="Select Example",
            height=38,
            corner_radius=7,
            fg_color=self.colors["surface_alt"],
            hover_color="#EEF2F7",
            text_color=self.colors["text"],
            border_width=1,
            border_color=self.colors["border"],
            font=ctk.CTkFont(family="Segoe UI", size=12),
            command=self._select_example_file,
        ).grid(row=0, column=1, sticky="ew", padx=(5, 0))

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

        ctk.CTkButton(
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
        ).grid(row=0, column=1)

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
        selection_card.grid_rowconfigure(3, weight=1)

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

        ctk.CTkLabel(
            selection_card,
            text="Selected columns become attributes of the generated class.",
            anchor="w",
            text_color=self.colors["muted"],
            font=ctk.CTkFont(family="Segoe UI", size=13),
        ).grid(row=1, column=0, sticky="w", padx=16, pady=(0, 10))

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
        self.column_canvas.configure(yscrollcommand=self.column_scrollbar.set)

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
            self._render_empty_preview("Select a CSV or XML file to start.")

    def _reset_current_import_state(self):
        self.current_model = None
        self.current_file_path = None
        self.current_file_type = ""
        self.current_selected_columns = []
        self.csv_preview = None
        self.xml_preview = None
        self.selected_csv_columns.clear()
        self.action_completed = {1: False, 2: False, 3: False}

    def _show_model_page(self):
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
        self._show_workflow_sidebar()
        self._update_model_tab()
        self._set_top_tab("model")
        self._refresh_actions()
        self._clear_content()

        self._page_header(
            "Inspect Model",
            "Review the imported or generated model structure and content.",
        )

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

        summary_items = [
            ("Higher Level Classes", self._count_higher_level_classes(model), "#315D9B"),
            ("Classes", len(model.get_all_flat_classes()), "#2563EB"),
            ("Attributes", self._count_attributes(model), "#7C3AED"),
            ("Enumeration Types", len(model.enums), "#F59E0B"),
            ("Operations", self._count_operations(model), "#0D9488"),
            ("Generalizations", self._count_generalizations(model), "#E11D48"),
            ("Associations", len(model.associations), "#64748B"),
            ("Objects", len(model.get_all_pure_objects()), "#16A34A"),
            ("Slots", self._count_slots(model), "#EA580C"),
            ("Links", len(model.links), "#0891B2"),
        ]

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

        self.model_search_var = tk.StringVar()
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
        self.model_tree.grid(
            row=0,
            column=0,
            sticky="nsew",
        )
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
            yscrollcommand=self.model_tree_scrollbar.set,
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
            yscrollcommand=self.detail_scrollbar.set,
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
            column=2,
            sticky="e",
        )

        self._populate_model_tree(model)
        self._render_model_structure_overview(model)

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
            return
        try:
            self.detail_canvas.itemconfigure(window_id, width=event.width)
            self._update_detail_x_scrollbar_visibility()
        except tk.TclError:
            pass

    def _reset_detail_canvas_table(self):
        self.detail_canvas.delete("all")
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
    def _model_overview_display_name(model: FmmlxModel) -> str:
        class_objects = [
            obj
            for obj in model.mlm_objects
            if obj.level > 0 and obj.attr_list
        ]
        if class_objects:
            return class_objects[0].name
        if model.path_name:
            return model.path_name.split("::")[-1]
        return "Model"


    def _open_placeholder_action(self, action: int):
        """
        Shows workflow steps that are not implemented yet.

        This block also contains the export logic, so the current model can be
        written back as CSV or XML from the workflow.
        """
        self.current_action = action
        self._set_last_action(action)
        self._update_model_tab()
        self._set_top_tab("model")
        self._refresh_actions()
        self._clear_content()
        self._page_header(
            self.ACTION_TITLES[action],
            "This action will be implemented next.",
        )
        body = ctk.CTkFrame(self.content, fg_color="transparent")
        body.grid(row=1, column=0, sticky="nsew")
        body.grid_columnconfigure(0, weight=1)
        body.grid_rowconfigure(0, weight=1)

        panel = self._card(body)
        panel.grid(row=0, column=0, sticky="nsew")
        panel.grid_columnconfigure(0, weight=1)
        panel.grid_rowconfigure(0, weight=1)
        ctk.CTkLabel(
            panel,
            text="Action area not implemented yet.",
            text_color=self.colors["muted"],
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
        ).grid(row=0, column=0, sticky="nsew", padx=24, pady=24)

        actions = ctk.CTkFrame(self.content, fg_color="transparent")
        actions.grid(row=2, column=0, sticky="ew", pady=(14, 0))
        actions.grid_columnconfigure(0, weight=1)
        if action == 3 and self.current_model is not None:
            ctk.CTkButton(
                actions,
                text="Inspect Model",
                width=150,
                height=42,
                corner_radius=8,
                fg_color="#FFFFFF",
                hover_color=self.colors["primary_soft"],
                border_width=1,
                border_color="#C7D2E3",
                text_color=self.colors["text"],
                font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
                command=self._show_model_page,
            ).grid(row=0, column=1, sticky="e", padx=(0, 10))
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
        ).grid(row=0, column=2, sticky="e")

    def _export_current_model_placeholder(self):
        if self.current_model is None:
            messagebox.showinfo("Export Model", "Create or open a model before exporting.")
            return
        file_type = (self.current_file_type or os.path.splitext(self.current_file_path or "")[1].lstrip(".")).upper()
        if file_type == "XML":
            self._export_current_xml_model()
        elif file_type == "CSV":
            self._export_current_csv_model()
        else:
            messagebox.showerror("Export Model", "Only CSV and XML models can be exported.")

    def _export_current_xml_model(self):
        if not self.current_file_path or not os.path.exists(self.current_file_path):
            messagebox.showerror("Export Model", "The source XML file is missing.")
            return
        source_name = os.path.basename(self.current_file_path)
        target_path = filedialog.asksaveasfilename(
            title="Export Model",
            initialfile=source_name,
            defaultextension=".xml",
            filetypes=[("XML files", "*.xml"), ("All files", "*.*")],
        )
        if not target_path:
            return
        try:
            shutil.copyfile(self.current_file_path, target_path)
            os.utime(target_path, None)
        except OSError as exc:
            messagebox.showerror("Export Model", f"Could not export XML: {exc}")
            return
        messagebox.showinfo("Export Model", f"Model exported to:\n{target_path}")

    def _export_current_csv_model(self):
        if not self.current_file_path or not os.path.exists(self.current_file_path):
            messagebox.showerror("Export Model", "The source CSV file is missing.")
            return
        selected_columns = self.current_selected_columns or [
            column
            for column, selected in self.selected_csv_columns.items()
            if selected.get()
        ]
        if not selected_columns:
            messagebox.showerror("Export Model", "No CSV columns were selected.")
            return
        source_name = os.path.basename(self.current_file_path)
        target_path = filedialog.asksaveasfilename(
            title="Export Model",
            initialfile=source_name,
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        )
        if not target_path:
            return
        try:
            self._write_selected_csv_columns(self.current_file_path, target_path, selected_columns)
        except (OSError, csv.Error, ValueError) as exc:
            messagebox.showerror("Export Model", f"Could not export CSV: {exc}")
            return
        messagebox.showinfo("Export Model", f"Model exported to:\n{target_path}")

    def _write_selected_csv_columns(self, source_path: str, target_path: str, selected_columns: List[str]):
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
            for row in rows:
                writer.writerow([
                    row[index] if index < len(row) else ""
                    for index in selected_indexes
                ])
        os.utime(target_path, None)

    def _show_models_overview_page(self):
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
        header.grid_columnconfigure(0, weight=1)
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
        total_card = ctk.CTkFrame(
            header,
            width=214,
            height=82,
            fg_color=self.colors["primary"],
            corner_radius=8,
        )
        total_card.grid(row=0, column=1, rowspan=2, sticky="e")
        total_card.grid_propagate(False)
        total_card.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            total_card,
            text="Total Models",
            text_color="#FFFFFF",
            anchor="w",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
        ).grid(row=0, column=0, sticky="sw", padx=24, pady=(14, 0))
        self.total_models_label = ctk.CTkLabel(
            total_card,
            text=str(len(self.loaded_models)),
            text_color="#FFFFFF",
            anchor="w",
            font=ctk.CTkFont(family="Segoe UI", size=24, weight="bold"),
        )
        self.total_models_label.grid(row=1, column=0, sticky="nw", padx=24, pady=(0, 14))

        body = ctk.CTkFrame(self.content, fg_color="transparent")
        body.grid(row=1, column=0, sticky="nsew")
        body.grid_columnconfigure(0, weight=1)
        body.grid_rowconfigure(0, weight=3)
        body.grid_rowconfigure(1, weight=2)

        list_card = self._card(body)
        list_card.grid(row=0, column=0, sticky="nsew", pady=(0, 14))
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
            values=["All", "CSV", "XML"],
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
            yscrollcommand=self.models_scrollbar.set,
        )
        self.models_canvas.bind("<Enter>", self._bind_models_scroll_events)
        self.models_canvas.bind("<Leave>", self._unbind_models_scroll_events)
        self.models_canvas.bind("<Configure>", lambda _event: self._populate_models_table())

        details_card = self._card(body)
        details_card.grid(row=1, column=0, sticky="nsew")
        details_card.grid_columnconfigure(0, weight=1)
        self._card_title(details_card, "Selected Model").grid(row=0, column=0, sticky="w", padx=16, pady=(14, 8))
        self.overview_details = ctk.CTkFrame(details_card, fg_color="#ffffff")
        self.overview_details.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 16))
        self.overview_details.grid_columnconfigure(0, weight=0, minsize=380)
        self.overview_details.grid_columnconfigure(1, weight=1)

        self._populate_models_table()
        self._render_overview_details(None)

    def _select_example_file(self):
        """
        Opens the Select Example dialog.

        The methods in this block handle both ways to choose input: selecting
        an example from example_models or browsing for a CSV/XML file manually.
        """
        examples_root = os.path.join(os.getcwd(), "example_models")
        if not os.path.isdir(examples_root):
            messagebox.showinfo(
                "No examples found",
                "Place XML files in example_models.",
            )
            return

        example_files = self._collect_example_files(examples_root)
        if not example_files:
            messagebox.showinfo(
                "No examples found",
                "No XML files were found in example_models.",
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
            text="Select an example from example_models",
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
        root_id = tree.insert("", "end", text="example_models", open=True)
        folder_ids = {examples_root: root_id}
        for folder_path, file_names in example_files:
            parent_path = os.path.dirname(folder_path)
            if folder_path == examples_root:
                folder_id = root_id
            else:
                parent_id = folder_ids.get(parent_path, root_id)
                folder_id = tree.insert(parent_id, "end", text=os.path.basename(folder_path), open=False)
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
            dialog.destroy()
            self._validate_current_file()

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

    @staticmethod
    def _collect_example_files(examples_root: str):
        rows = []
        for folder_path, subfolders, file_names in os.walk(examples_root):
            subfolders[:] = sorted(
                folder
                for folder in subfolders
                if folder not in {"__pycache__"}
            )
            supported_files = sorted(
                file_name
                for file_name in file_names
                if file_name.lower().endswith((".xml", ".csv"))
            )
            if supported_files or folder_path == examples_root:
                rows.append((folder_path, supported_files))
        return rows

    def _browse_file(self):
        file_path = filedialog.askopenfilename(
            filetypes=[
                ("Supported files", "*.csv *.xml"),
                ("CSV files", "*.csv"),
                ("XML files", "*.xml"),
                ("All files", "*.*"),
            ]
        )
        if file_path:
            self.file_path_var.set(file_path)
            self.current_file_path = file_path
            self._validate_current_file()

    def _validate_current_file(self):
        file_path = self.file_path_var.get().strip()
        self.current_file_path = file_path or None
        self.csv_preview = None
        self.xml_preview = None
        self.selected_csv_columns.clear()

        if not file_path:
            self._set_validation_badge_visible(True)
            self.validation_status_badge.configure(
                text="Not validated",
                fg_color=self.colors["disabled_bg"],
                text_color=self.colors["muted"],
            )
            self._set_validation_rows([("File", "No file selected")])
            self._render_empty_preview("Select a CSV or XML file to start.")
            self._set_create_button_enabled(False)
            return

        self._set_validation_badge_visible(False)
        extension = os.path.splitext(file_path)[1].lower()
        if extension == ".csv":
            csv_preview = self._build_csv_preview(file_path)
            self.csv_preview = csv_preview
            self._render_csv_validation(csv_preview)
            self._render_csv_mapping(csv_preview)
            can_create = not csv_preview.errors and csv_preview.header_detected
        elif extension == ".xml":
            xml_preview = self._build_xml_preview(file_path)
            self.xml_preview = xml_preview
            self._render_xml_validation(xml_preview)
            self._render_xml_preview(xml_preview)
            can_create = not xml_preview.errors
        else:
            self._set_validation_rows([
                ("File type", extension or "unknown"),
                ("Errors", "Unsupported file type"),
            ])
            self._render_empty_preview("Only CSV and XML files are supported.")
            can_create = False

        self._set_create_button_enabled(can_create and self._can_create_current_file())

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

    @staticmethod
    def _simple_csv_value_type(value: str) -> str:
        # Give one cell a simple everyday label, so header cells can be compared with data cells.
        value = value.strip()
        if value == "":
            return "empty"
        try:
            int(value)
            return "int"
        except ValueError:
            pass
        try:
            float(value)
            return "float"
        except ValueError:
            return "text"

    @staticmethod
    def _csv_attribute_type(values: List[str]) -> str:
        # Decide what kind of values a CSV column mostly contains.
        # Empty cells are ignored because they should not change the column type.
        populated_values = [
            value.strip()
            for value in values
            if value.strip()
        ]
        if populated_values:
            try:
                for value in populated_values:
                    int(value)
                return "Integer"
            except ValueError:
                pass
            try:
                for value in populated_values:
                    float(value)
                return "Float"
            except ValueError:
                pass
        return "String"

    @staticmethod
    def _is_simple_header_name(value: str) -> bool:
        # A plain word like "name" or "age_2" is a good sign that the first row is a header.
        return re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value) is not None

    @classmethod
    def _first_row_looks_like_header(
            cls,
            header_row: List[str],
            data_rows: List[List[str]],
    ) -> bool:
        # Check whether the first CSV row looks like column names or like normal data.
        # This keeps accidental data rows from becoming model attribute names.
        if not data_rows:
            return True

        if all(cls._is_simple_header_name(header_value) for header_value in header_row):
            return True

        for column_index, header_value in enumerate(header_row):
            column_values = [
                row[column_index]
                for row in data_rows
                if column_index < len(row)
            ]
            column_types = {
                cls._simple_csv_value_type(value)
                for value in column_values
            }
            if cls._simple_csv_value_type(header_value) not in column_types:
                return True
        return False

    @classmethod
    def _build_csv_preview(cls, file_path: str) -> CsvImportPreview:
        # Build a small summary before importing the CSV for real.
        # The GUI uses this summary to explain what the selected file contains.
        warnings: List[str] = []
        errors: List[str] = []

        try:
            with open(file_path, "r", newline="", encoding="utf-8-sig") as csv_file:
                dialect = cls._detect_csv_dialect(csv_file)
                reader = csv.reader(csv_file, dialect, skipinitialspace=True)
                rows = [[value.strip().strip('"') for value in row] for row in reader if row]
                delimiter = dialect.delimiter
        except FileNotFoundError:
            return CsvImportPreview(file_path, "", [], [], 0, 0, False, warnings, [f"File not found: {file_path}"])
        except (OSError, UnicodeError, csv.Error) as exc:
            # File and CSV reading problems become readable messages in the GUI.
            return CsvImportPreview(file_path, "", [], [], 0, 0, False, warnings, [f"Could not read CSV: {exc}"])

        if not rows:
            return CsvImportPreview(file_path, delimiter, [], [], 0, 0, False, warnings, ["CSV file is empty."])

        header = rows[0]
        data_rows = rows[1:]
        column_count = len(header)
        header_detected = cls._first_row_looks_like_header(header, data_rows)

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
        # Try to open the XML model once so the GUI can report problems before the real import.
        try:
            model = FmmlxModel(file_path=file_path)
            warnings = []
            if ModelDeepenerApp._count_attributes(model) == 0:
                warnings.append(
                    "No attributes were attached to model classes. The XML may not contain addAttribute entries, "
                    "or its attribute class names may not match the class names in the model."
                )
            return XmlImportPreview(file_path=file_path, errors=[], warnings=warnings, model=model)
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
            ("File type", "XML"),
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
            highlightthickness=0,
            bd=0,
        )
        cell.grid(row=row, column=column, sticky="nsew")
        cell.grid_propagate(False)

        if border_left:
            separator = tk.Frame(
                cell,
                width=1,
                background="#DCE6F2",
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

    def _render_csv_mapping(self, preview: CsvImportPreview):
        self.selected_csv_columns.clear()
        self.all_columns_selected_var.set(True)

        row_count = len(preview.header)
        total_height = (
                self.TABLE_HEADER_HEIGHT
                + row_count * self.TABLE_ROW_HEIGHT
        )

        self._reset_column_table(total_height)
        self._build_column_table_header()

        for column_index, column_name in enumerate(preview.header):
            values = [
                row[column_index]
                for row in preview.data_rows
                if column_index < len(row)
            ]
            data_type = self._csv_attribute_type(values)
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
        extension = os.path.splitext(self.current_file_path or "")[1].lower()
        if extension == ".csv":
            return self._has_selected_columns()
        if extension == ".xml":
            return self.xml_preview is not None and not self.xml_preview.errors
        return False

    def _has_selected_columns(self) -> bool:
        if self.csv_preview is None or self.csv_preview.errors or not self.csv_preview.header_detected:
            return False
        return any(var.get() for var in self.selected_csv_columns.values())

    def _render_xml_preview(self, preview: XmlImportPreview):
        """
        Shows the XML state in the Column Selection area.

        XML files do not use CSV Column Selection, so this block shows the
        message for XML files and the empty state before a file is selected.
        """
        total_height = 118
        self._reset_column_table(total_height)

        for child in self.column_table.winfo_children():
            child.destroy()

        self.column_table.grid_columnconfigure(0, weight=1)
        self.column_table.grid_rowconfigure(0, weight=1, minsize=118)
        ctk.CTkLabel(
            self.column_table,
            text="Columns cannot be selected for XML files.",
            anchor="w",
            justify="left",
            text_color=self.colors["muted"],
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
        ).grid(row=0, column=0, sticky="new", padx=0, pady=18)

    def _render_empty_preview(self, text: str):
        if not hasattr(self, "column_canvas"):
            return

        total_height = self.TABLE_HEADER_HEIGHT + 76
        self._reset_column_table(total_height)
        self._build_column_table_header()

        self.column_table.grid_rowconfigure(
            1,
            weight=0,
            minsize=76,
        )

        empty_cell = tk.Frame(
            self.column_table,
            height=76,
            background="#FFFFFF",
            bd=0,
            highlightthickness=0,
        )
        empty_cell.grid(
            row=1,
            column=0,
            columnspan=4,
            sticky="nsew",
        )
        empty_cell.grid_propagate(False)

        ctk.CTkLabel(
            empty_cell,
            text=text,
            anchor="center",
            justify="center",
            text_color=self.colors["muted"],
            font=ctk.CTkFont(
                family="Segoe UI",
                size=12,
            ),
        ).place(relx=0.5, rely=0.5, anchor="center")

    def _create_model(self):
        """
        Creates the model after validation succeeds.

        This block turns the selected CSV/XML file into the current model,
        stores the imported source file, updates Models Overview, and reloads
        saved models from loaded_models.json.
        """
        if not self.current_file_path:
            messagebox.showerror("Import blocked", "Select a file first.")
            return

        try:
            extension = os.path.splitext(self.current_file_path)[1].lower()
            if extension == ".csv":
                selected_columns = [
                    column
                    for column, selected in self.selected_csv_columns.items()
                    if selected.get()
                ]

                if not selected_columns:
                    messagebox.showerror(
                        "Import blocked",
                        "Select at least one CSV column.",
                    )
                    return

                self.current_model = FmmlxModel(
                    file_path=self.current_file_path,
                    selected_csv_columns=selected_columns,
                )
                self.current_selected_columns = selected_columns
            elif extension == ".xml":
                self.current_model = self.xml_preview.model if self.xml_preview and self.xml_preview.model else FmmlxModel(
                    file_path=self.current_file_path
                )
                self.current_selected_columns = []
            else:
                raise ValueError("Only CSV and XML files are supported.")
        except Exception as exc:
            messagebox.showerror("Import failed", str(exc))
            self.action_unlocked[2] = False
            self._refresh_actions()
            return

        self.action_completed[1] = True
        self.action_unlocked[2] = True
        self.current_file_path = self._persist_imported_source_file(
            self.current_file_path,
            extension,
        )
        self.current_file_type = extension.lstrip(".").upper()
        self._store_loaded_model(extension)
        self._show_model_page()

    def _persist_imported_source_file(
            self,
            source_path: Optional[str],
            extension: str,
    ) -> Optional[str]:
        if not source_path:
            return source_path
        target_dir = "csv_files" if extension == ".csv" else "example_models"
        os.makedirs(target_dir, exist_ok=True)

        source_abs = os.path.abspath(source_path)
        target_abs_dir = os.path.abspath(target_dir)
        if os.path.dirname(source_abs).lower() == target_abs_dir.lower():
            return source_path

        base_name = os.path.basename(source_path)
        name, suffix = os.path.splitext(base_name)
        target_path = os.path.join(target_dir, base_name)
        counter = 1
        while os.path.exists(target_path):
            try:
                if os.path.samefile(source_path, target_path):
                    return target_path
            except OSError:
                pass
            target_path = os.path.join(target_dir, f"{name}_{counter}{suffix}")
            counter += 1

        shutil.copy2(source_path, target_path)
        if hasattr(self, "file_path_var"):
            self.file_path_var.set(target_path)
        return target_path

    def _store_loaded_model(self, extension: str):
        if self.current_model is None or self.current_file_path is None:
            return
        source_file = os.path.basename(self.current_file_path)
        name = self.current_model.path_name.split("::")[-1] if self.current_model.path_name else os.path.splitext(source_file)[0]
        uploaded = datetime.now().strftime("%Y-%m-%d %H:%M")
        now_text = self._current_timestamp_text()
        selected_columns = [
            column
            for column, selected in self.selected_csv_columns.items()
            if selected.get()
        ] if extension == ".csv" else []
        self.loaded_models.append(
            LoadedModel(
                name=name,
                source_file=source_file,
                file_type=extension.lstrip(".").upper(),
                model=self.current_model,
                source_path=self.current_file_path,
                selected_columns=selected_columns,
                uploaded=uploaded,
                last_worked_on=now_text,
                last_action=self.ACTION_TITLES[2],
            )
        )
        self._save_loaded_models()

    def _save_loaded_models(self):
        # The overview needs a small address book of imported files.
        # The real model data stays in the copied CSV or XML files.
        os.makedirs(os.path.dirname(self.loaded_models_store_path), exist_ok=True)
        records = []
        for loaded in self.loaded_models:
            records.append(
                {
                    "name": loaded.name,
                    "source_file": loaded.source_file,
                    "source_path": loaded.source_path,
                    "file_type": loaded.file_type,
                    "selected_columns": loaded.selected_columns,
                    "uploaded": loaded.uploaded,
                    "last_worked_on": loaded.last_worked_on,
                    "last_action": loaded.last_action,
                }
            )
        with open(self.loaded_models_store_path, "w", encoding="utf-8") as file:
            json.dump(records, file, indent=2)

    def _load_saved_models(self):
        # On startup, rebuild the overview from files that were imported earlier.
        if not os.path.exists(self.loaded_models_store_path):
            return
        try:
            with open(self.loaded_models_store_path, "r", encoding="utf-8") as file:
                records = json.load(file)
        except (OSError, json.JSONDecodeError):
            return

        for record in records:
            source_path = record.get("source_path") or record.get("source_file", "")
            if source_path and not os.path.isabs(source_path):
                source_path = os.path.join(os.getcwd(), source_path)
            if not source_path or not os.path.exists(source_path):
                continue
            file_type = record.get("file_type", "").upper()
            selected_columns = record.get("selected_columns") or []
            try:
                if file_type == "CSV":
                    model = FmmlxModel(
                        file_path=source_path,
                        selected_csv_columns=selected_columns or None,
                    )
                elif file_type == "XML":
                    model = FmmlxModel(file_path=source_path)
                else:
                    continue
            except Exception:
                continue
            self.loaded_models.append(
                LoadedModel(
                    name=record.get("name") or self._model_overview_display_name(model),
                    source_file=record.get("source_file") or os.path.basename(source_path),
                    file_type=file_type,
                    model=model,
                    source_path=source_path,
                    selected_columns=selected_columns,
                    uploaded=record.get("uploaded", ""),
                    last_worked_on=record.get("last_worked_on", ""),
                    last_action=record.get("last_action", "Imported"),
                )
            )

    @staticmethod
    def _current_timestamp_text() -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M")

    def _touch_loaded_model(self, model: Optional[FmmlxModel]):
        if model is None:
            return
        for loaded in self.loaded_models:
            if loaded.model is model:
                loaded.last_worked_on = self._current_timestamp_text()
                self._save_loaded_models()
                break

    def _set_last_action(self, action: int):
        self.last_action_label = self.ACTION_TITLES.get(action, "Imported")
        if self.current_model is None:
            return
        for loaded in self.loaded_models:
            if loaded.model is self.current_model:
                loaded.last_action = self.last_action_label
                self._save_loaded_models()
                break

    def _populate_model_tree(
            self,
            model: FmmlxModel,
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
            open=True,
            tags=("enum_group",),
        )
        self.tree_item_payload[enum_id] = None
        self.tree_item_view[enum_id] = "group"

        for enum in sorted(enumerations, key=lambda item: self._natural_sort_key(item.name)):
            item_id = self.model_tree.insert(
                enum_id,
                "end",
                text=enum.name,
                open=False,
                tags=("enum_item",),
            )
            self.tree_item_payload[item_id] = enum
            self.tree_item_view[item_id] = "enumeration"
            self._insert_enum_search_hits(item_id, enum, normalized_query)

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
                open=True,
                tags=("level_object" if level == 0 else "level_class",),
            )
            self.tree_item_payload[level_id] = None
            self.tree_item_view[level_id] = "group"

            for obj in sorted(
                    level_objects,
                    key=lambda item: self._natural_sort_key(item.name),
            ):
                obj_id = self.model_tree.insert(
                    level_id,
                    "end",
                    text=obj.name,
                    open=bool(normalized_query),
                    tags=("object_item" if level == 0 else "class_item",),
                )
                self.tree_item_payload[obj_id] = obj
                self.tree_item_view[obj_id] = "object" if level == 0 else "class"
                self._insert_object_search_hits(obj_id, model, obj, normalized_query)

        self.model_tree.selection_remove(
            self.model_tree.selection()
        )
        self.model_tree.yview_moveto(0)

    def _object_matches_search(self, model: FmmlxModel, obj: FmmlxObject, query: str) -> bool:
        if not query:
            return True
        values = [obj.name, obj.full_name]
        values.extend(attr.name for attr in obj.attr_list)
        values.extend(attr.attr_type_short for attr in obj.attr_list)
        object_operations = self._operations_for_object(obj)
        values.extend(operation.operation_name for operation in object_operations)
        values.extend(operation.return_type for operation in object_operations)
        values.extend(slot.name for slot in obj.slot_list)
        values.extend(str(slot.value) for slot in obj.slot_list)
        values.extend(parent.name for parent in obj.parent_classes)
        values.extend(
            candidate.name
            for candidate in model.mlm_objects
            if obj in candidate.parent_classes
        )
        for association in self._associations_for_class(model, obj):
            values.append("association")
            values.extend(
                [
                    association.name,
                    self._name(association.source_object),
                    self._name(association.target_object),
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
                ]
            )
        if object_operations:
            values.append("operation")
        if self._generalization_rows(obj):
            values.extend(["generalization", "superclass", "subclass"])
        return any(query in str(value).lower() for value in values if value is not None)

    def _insert_object_search_hits(self, parent_id: str, model: FmmlxModel, obj: FmmlxObject, query: str):
        if not query:
            return
        hit_groups = [
            ("Attributes", "attribute", [
                attr for attr in obj.attr_list
                if self._query_matches_values(query, attr.name, attr.attr_type_short, attr.inst_level)
            ]),
            ("Slots", "slot", [
                slot for slot in obj.slot_list
                if self._query_matches_values(query, slot.name, slot.value, self._slot_type(slot))
            ]),
            ("Associations", "association", [
                association for association in self._associations_for_class(model, obj)
                if query == "association" or self._query_matches_values(
                    query,
                    association.name,
                    self._name(association.source_object),
                    self._name(association.target_object),
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
            if not hits:
                continue
            group_id = self.model_tree.insert(parent_id, "end", text=f"{group_label} ({len(hits)})", open=True)
            self.tree_item_payload[group_id] = None
            self.tree_item_view[group_id] = "group"
            for hit in hits:
                text = self._search_hit_text(view_name, hit)
                item_id = self.model_tree.insert(group_id, "end", text=text, open=False)
                self.tree_item_payload[item_id] = (view_name, obj, hit)
                self.tree_item_view[item_id] = view_name

    def _insert_enum_search_hits(self, parent_id: str, enum: FmmlxEnumType, query: str):
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
            item_id = self.model_tree.insert(group_id, "end", text=str(value), open=False)
            self.tree_item_payload[item_id] = ("enum_value", enum, value)
            self.tree_item_view[item_id] = "enum_value"

    @staticmethod
    def _query_matches_values(query: str, *values) -> bool:
        return any(query in str(value).lower() for value in values if value is not None)

    def _search_hit_text(self, view_name: str, hit) -> str:
        if view_name == "attribute":
            return f"{hit.name}: {hit.attr_type_short}"
        if view_name == "slot":
            return f"{hit.name}: {self._display_table_value(hit.value)}"
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
    def _enum_matches_search(enum: FmmlxEnumType, query: str) -> bool:
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

        if isinstance(payload, FmmlxModel):
            self._start_model_overview_loading(payload)
        elif isinstance(payload, FmmlxObject):
            if selected_view == "class":
                self._render_class_details(payload)
            elif selected_view == "object":
                self._render_object_details(payload)
            else:
                self._render_empty_detail_state()
        elif isinstance(payload, FmmlxEnumType):
            self._render_enum_details(payload)
        elif isinstance(payload, tuple):
            self._render_search_hit_details(payload)
        else:
            self._render_empty_detail_state()

    def _render_search_hit_details(self, payload: tuple):
        view_name = payload[0] if payload else ""
        if view_name == "attribute":
            _view, obj, attr = payload
            self.detail_title.configure(text=f"Attribute: {attr.name}", text_color="#7C3AED")
            self.detail_subtitle.configure(text=f"Defined on {obj.name}.")
            self._render_detail_table(
                ("Attribute", "Type", "Slot"),
                [(attr.name, attr.attr_type_short, "-")],
            )
        elif view_name == "slot":
            _view, obj, slot = payload
            self.detail_title.configure(text=f"Slot: {slot.name}", text_color="#16A34A")
            self.detail_subtitle.configure(text=f"Defined on {obj.name}.")
            self._render_detail_table(
                ("Attribute", "Type", "Slot"),
                [(slot.name, self._slot_type(slot), slot.value)],
            )
        elif view_name == "association":
            _view, _obj, association = payload
            self.detail_title.configure(text=f"Association: {association.name}", text_color="#64748B")
            self.detail_subtitle.configure(text="Matching association.")
            self._render_detail_table(
                ("Associationname", "Source", "Target", "Multiplicity"),
                [(
                    association.name,
                    self._name(association.source_object),
                    self._name(association.target_object),
                    self._association_multiplicity_text(association),
                )],
                highlight_column=3,
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
            slot_by_name = {slot.name: slot.value for slot in obj.slot_list}
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
            self._render_detail_table(("Enumeration Type", "Slot", "Index"), [(enum.name, value, enum.enum_values.index(value) + 1)])
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

        overlay = getattr(self, "_detail_loading_overlay", None)
        if overlay is not None and overlay.winfo_exists():
            try:
                if hasattr(self, "detail_loading_bar"):
                    self.detail_loading_bar.stop()
            except tk.TclError:
                # The progress bar may already have been destroyed while the screen was changing.
                pass
            overlay.destroy()
        self._detail_loading_overlay = None
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

    def _start_model_overview_loading(self, model: FmmlxModel):
        """
        Starts loading the large Model Overview table in Inspect Model.

        This block asks how many objects should be shown, prepares the values,
        shows progress, and draws the large object/value table in batches.
        """
        self._render_model_structure_overview(model)

    @staticmethod
    def _attach_active_model_reference(model: FmmlxModel):
        for obj in model.mlm_objects:
            obj._active_model = model

    def _show_model_overview_load_options(self, model: FmmlxModel):
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
            if obj.level > 0 and obj.attr_list
        ]
        attributes = class_objects[0].attr_list if class_objects else []
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
        default_count = next((count for count in object_count_options if total_objects >= count), None)
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

    def _render_model_structure_overview(self, model: FmmlxModel):
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

    def _model_structure_content_text(self, model: FmmlxModel, obj: FmmlxObject) -> str:
        operation_count = len(self._operations_for_object(obj)) if obj.level == 0 else len(obj.operations_list)
        parts = [
            f"{len(obj.attr_list)} attributes",
            f"{operation_count} operations",
        ]
        associations = self._associations_for_class(model, obj)
        if associations:
            parts.append(f"{len(associations)} associations")
        links = self._links_for_object(model, obj)
        if links:
            parts.append(f"{len(links)} links")
        if obj.slot_list:
            parts.append(f"{len(obj.slot_list)} slots")
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
            model: FmmlxModel,
            attributes: List[FmmlxAttribute],
            objects: List[FmmlxObject],
    ):
        try:
            requested_count = int(self.model_overview_count_var.get().strip())
        except ValueError:
            messagebox.showerror(
                "Invalid object count",
                "Enter a whole number of objects to load.",
            )
            return

        if requested_count <= 0:
            messagebox.showerror(
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
            1000,
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
            objects: List[FmmlxObject],
            count: int,
            mode: str,
    ) -> List[FmmlxObject]:
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

        existing = getattr(self, "_detail_loading_overlay", None)
        if existing is not None and existing.winfo_exists():
            existing.destroy()

        overlay = ctk.CTkFrame(
            self.detail_table_wrapper,
            fg_color="#FFFFFF",
            corner_radius=0,
            border_width=0,
        )
        overlay.place(x=0, y=0, relwidth=1, relheight=1)
        overlay.grid_columnconfigure(0, weight=1)
        overlay.grid_rowconfigure(0, weight=1)

        loading_panel = ctk.CTkFrame(
            overlay,
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
            text="Loading data...",
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

        self._detail_loading_overlay = overlay
        overlay.lift()
        self._refresh_determinate_progress_display(token)

        # Force Tk to paint the loading layer before the first data batch starts.
        self.update_idletasks()

    def _refresh_determinate_progress_display(self, token: int):
        if token != getattr(self, "_detail_load_token", None):
            return
        if not getattr(self, "_detail_progress_determinate", False):
            return

        overlay = getattr(self, "_detail_loading_overlay", None)
        if overlay is None or not overlay.winfo_exists():
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
            attributes: List[FmmlxAttribute],
            objects: List[FmmlxObject],
            start_index: int,
    ):
        self._detail_batch_after_id = None
        if token != getattr(self, "_detail_load_token", None):
            return

        batch_size = 40
        end_index = min(start_index + batch_size, len(objects))

        for object_index in range(start_index, end_index):
            obj = objects[object_index]
            slot_by_name = {
                slot.name: slot.value
                for slot in obj.slot_list
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
                lambda: self._prepare_model_overview_batch(
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
            attributes: List[FmmlxAttribute],
            prepared_rows: list,
    ):
        if token != getattr(self, "_detail_load_token", None):
            return

        name_width = 220
        attribute_width = 180
        header_height = 42
        row_height = 46
        total_width = max(
            name_width + len(attributes) * attribute_width,
            self.detail_canvas.winfo_width(),
            )
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
        overlay = getattr(self, "_detail_loading_overlay", None)
        if overlay is not None and overlay.winfo_exists():
            overlay.lift()

        headers = [model_name] + [attr.name for attr in attributes]
        x = 0
        for column, text in enumerate(headers):
            column_width = name_width if column == 0 else attribute_width
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
            x += column_width

        state = {
            "name_width": name_width,
            "attribute_width": attribute_width,
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
        for value in row_values:
            line_counts.append(
                self._wrapped_line_count(
                    value,
                    state["attribute_width"],
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
                    width=state["attribute_width"],
                    height=row_height,
                    text=self._display_table_value(value),
                    background=row_bg,
                    foreground=self.colors["text"],
                    font=("Segoe UI", 12),
                )
                x += state["attribute_width"]

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

        overlay = getattr(self, "_detail_loading_overlay", None)
        if overlay is not None and overlay.winfo_exists():
            overlay.destroy()
        self._detail_loading_overlay = None
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

    def _render_class_details(self, obj: FmmlxObject):
        self.detail_title.configure(
            text=f"Class: {obj.name}",
            text_color="#2563EB",
        )
        self.detail_subtitle.configure(
            text="Select which class details should be shown."
        )
        options = [
            ("Attributes", bool(obj.attr_list), lambda: self._render_class_attribute_table(obj)),
            ("Associations", bool(self._associations_for_class(self.current_model, obj)), lambda: self._render_class_association_table(obj)),
            ("Operations", bool(obj.operations_list), lambda: self._render_class_operation_table(obj)),
            ("Generalization", bool(self._generalization_rows(obj)), lambda: self._render_class_generalization_table(obj)),
        ]
        self._render_detail_option_buttons(options)
        for _label, enabled, callback in options:
            if enabled:
                callback()
                return
        self._render_detail_table(("Name", "Type", "Slot"), [])

    def _render_object_details(self, obj: FmmlxObject):
        self.detail_title.configure(
            text=f"Object: {obj.name}",
            text_color="#16A34A",
        )
        self.detail_subtitle.configure(
            text="Select whether slots or links should be shown."
        )
        options = [
            ("Slots", bool(obj.slot_list), lambda: self._render_object_value_table(obj)),
            ("Operations", bool(self._operations_for_object(obj)), lambda: self._render_object_operation_table(obj)),
            ("Links", bool(self._links_for_object(self.current_model, obj)), lambda: self._render_object_link_table(obj)),
        ]
        self._render_detail_option_buttons(options)
        for _label, enabled, callback in options:
            if enabled:
                callback()
                return
        self._render_detail_table(("Name", "Type", "Slot"), [])

    def _render_enum_details(self, enum: FmmlxEnumType):
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
        )

    def _render_detail_option_buttons(self, options):
        self._clear_detail_option_bar()

        bar = ctk.CTkFrame(self.detail_card, fg_color="transparent")
        bar.grid(row=1, column=0, sticky="e", padx=16, pady=(0, 8))
        for index, (label, enabled, callback) in enumerate(options):
            ctk.CTkButton(
                bar,
                text=label,
                width=118 if label == "Generalization" else 102,
                height=30,
                corner_radius=7,
                border_width=1,
                fg_color="#FFFFFF" if enabled else self.colors["disabled_bg"],
                hover_color=self.colors["primary_soft"] if enabled else self.colors["disabled_bg"],
                border_color="#BBD0F4" if enabled else self.colors["border"],
                text_color=self.colors["primary"] if enabled else "#94A3B8",
                font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
                state="normal" if enabled else "disabled",
                command=callback,
            ).grid(row=0, column=index, padx=(0 if index == 0 else 8, 0))
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
    def _associations_for_class(model: Optional[FmmlxModel], obj: FmmlxObject):
        if model is None:
            return []
        return [
            association
            for association in model.associations
            if association.source_object is obj or association.target_object is obj
        ]

    @staticmethod
    def _links_for_object(model: Optional[FmmlxModel], obj: FmmlxObject):
        if model is None:
            return []
        return [
            link
            for link in model.links
            if link.source_object is obj or link.target_object is obj
        ]

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
    def _operations_for_object(obj: FmmlxObject):
        operations = list(obj.operations_list)
        if obj.class_of_object is not None:
            operations.extend(
                operation
                for operation in obj.class_of_object.operations_list
                if operation not in operations
            )
        return operations

    def _generalization_rows(self, obj: FmmlxObject):
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

    def _all_parent_classes(self, obj: FmmlxObject):
        parents = []
        pending = list(obj.parent_classes)
        while pending:
            parent = pending.pop(0)
            if parent in parents:
                continue
            parents.append(parent)
            pending.extend(parent.parent_classes)
        return parents

    def _render_class_attribute_table(self, obj: FmmlxObject):
        rows = [
            (attr.name, attr.attr_type_short, attr.inst_level)
            for attr in obj.attr_list
        ]
        inherited_rows = [
            (attr.name, attr.attr_type_short, f"Level {attr.inst_level}, inherited from {parent.name}")
            for parent in self._all_parent_classes(obj)
            for attr in parent.attr_list
        ]
        self._render_detail_table(
            ("Attribute", "Type", "Level"),
            rows + inherited_rows,
            muted_row_indexes=set(range(len(rows), len(rows) + len(inherited_rows))),
        )

    def _render_class_association_table(self, obj: FmmlxObject):
        self._render_detail_table(
            ("Associationname", "Source", "Target", "Multiplicity"),
            [
                (
                    association.name,
                    self._name(association.source_object),
                    self._name(association.target_object),
                    self._association_multiplicity_text(association),
                )
                for association in self._associations_for_class(self.current_model, obj)
            ],
            highlight_column=3,
        )

    def _render_class_operation_table(self, obj: FmmlxObject):
        self._render_detail_table(
            ("Operation", "Type", "Slot"),
            [
                (operation.operation_name, self._short_type_name(operation.return_type), "-")
                for operation in obj.operations_list
            ],
        )

    def _render_class_generalization_table(self, obj: FmmlxObject):
        self._render_detail_table(
            ("Superclass", "Subclass"),
            self._generalization_rows(obj),
        )

    def _render_object_value_table(self, obj: FmmlxObject):
        self._render_detail_table(
            ("Attribute", "Type", "Slot"),
            [
                (slot.name, self._slot_type(slot), slot.value)
                for slot in obj.slot_list
            ],
        )

    def _render_object_link_table(self, obj: FmmlxObject):
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

    def _render_object_operation_table(self, obj: FmmlxObject):
        slot_by_name = {
            slot.name: slot.value
            for slot in obj.slot_list
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

    def _render_detail_table(
            self,
            headers,
            rows,
            highlight_column: int = 1,
            muted_row_indexes=None,
            column_weights=None,
            column_minsizes=None,
    ):
        self._reset_detail_canvas_table()
        for child in self.detail_table.winfo_children():
            child.destroy()
        muted_row_indexes = muted_row_indexes or set()

        for column in range(len(headers)):
            self.detail_table.grid_columnconfigure(
                column,
                weight=(column_weights[column] if column_weights and column < len(column_weights) else (2 if column == 0 else 1)),
                minsize=(column_minsizes[column] if column_minsizes and column < len(column_minsizes) else (220 if column == 0 else 170)),
            )

        header_bg = "#DFE9FD"

        for column, text in enumerate(headers):
            cell = tk.Frame(
                self.detail_table,
                height=42,
                background=header_bg,
                bd=0,
                highlightthickness=0,
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
                    background="#DCE6F2",
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

        if not rows:
            empty = tk.Frame(
                self.detail_table,
                height=80,
                background="#FFFFFF",
                bd=0,
                highlightthickness=0,
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
                        highlightthickness=0,
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
                            background="#E4EBF4",
                            bd=0,
                            highlightthickness=0,
                        ).place(
                            x=0,
                            y=0,
                            width=1,
                            height=46,
                        )

                    if column == highlight_column and cell_value:
                        ctk.CTkLabel(
                            cell,
                            text=self._display_table_value(cell_value),
                            height=24,
                            corner_radius=12,
                            fg_color="#E2E8F0" if is_muted_row else self.colors["primary_soft"],
                            text_color="#64748B" if is_muted_row else "#013897",
                            font=ctk.CTkFont(
                                family="Segoe UI",
                                size=11,
                                weight="bold",
                            ),
                        ).place(
                            relx=0.5,
                            rely=0.5,
                            anchor="center",
                        )
                    else:
                        ctk.CTkLabel(
                            cell,
                            text=self._display_table_value(cell_value),
                            anchor="center",
                            justify="center",
                            text_color=self.colors["muted"] if is_muted_row else self.colors["text"],
                            font=ctk.CTkFont(
                                family="Segoe UI",
                                size=12,
                            ),
                        ).place(
                            relx=0.5,
                            rely=0.5,
                            anchor="center",
                            relwidth=0.92,
                        )

        self.detail_table.update_idletasks()
        self.detail_canvas.itemconfigure(
            self.detail_canvas_window,
            width=max(self.detail_canvas.winfo_width(), 700),
        )
        self.detail_canvas.configure(
            scrollregion=self.detail_canvas.bbox("all")
        )
        self._update_detail_x_scrollbar_visibility()
        self.detail_canvas.xview_moveto(0)
        self.detail_canvas.yview_moveto(0)

    def _populate_models_table(self):
        """
        Draws the table on the Models Overview page.

        This block applies the filters, draws one row per stored model, handles
        row selection, and updates the detail panel with Open Model and Delete Model.
        """
        if not hasattr(self, "models_canvas"):
            return
        self.models_canvas.delete("all")
        self._models_canvas_rows = {}

        canvas_width = max(self.models_canvas.winfo_width(), 900)
        column_specs = [
            ("name", "Model Name", 0.13),
            ("source", "Source File", 0.16),
            ("type", "Type", 0.06),
            ("level_classes", "Higher Level Classes", 0.09),
            ("classes", "Classes", 0.07),
            ("attributes", "Attributes", 0.09),
            ("objects", "Objects", 0.08),
            ("status", "Last Action", 0.12),
            ("worked", "Last worked on", 0.12),
            ("open", "Open Model", 0.08),
        ]
        columns = [
            (key, label, max(78, int(canvas_width * fraction)))
            for key, label, fraction in column_specs
        ]
        row_height = 64
        header_height = 58
        table_width = max(sum(width for _key, _label, width in columns), canvas_width)
        x = 0
        for _key, label, width in columns:
            self._draw_models_table_cell(
                x=x,
                y=0,
                width=width,
                height=header_height,
                text=label,
                background="#DFE9FD",
                foreground="#04173D",
                font=("Segoe UI", 12, "bold"),
            )
            x += width

        filtered = []
        for index, loaded in enumerate(self.loaded_models):
            if not self._model_matches_overview_filters(loaded):
                continue
            filtered.append((index, loaded))

        for row_index, (model_index, loaded) in enumerate(filtered, start=1):
            model = loaded.model
            y = header_height + ((row_index - 1) * row_height)
            row_bg = "#FFFFFF" if row_index % 2 else "#F3F7FD"
            values = [
                loaded.name,
                loaded.source_file,
                loaded.file_type,
                self._count_higher_level_classes(model),
                len(model.get_all_flat_classes()),
                self._count_attributes(model),
                len(model.get_all_pure_objects()),
                self._model_last_action_label(loaded),
                loaded.last_worked_on or loaded.uploaded or "Unknown",
                "Open Model",
            ]
            x = 0
            row_items = []
            for _column_index, ((key, _label, width), value) in enumerate(zip(columns, values)):
                if key == "status":
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
                row_items.extend(items)
                x += width
            for item in row_items:
                self.models_canvas.tag_bind(
                    item,
                    "<Button-1>",
                    lambda _event, target=loaded: self._open_loaded_model(target),
                )
                self.models_canvas.tag_bind(item, "<Enter>", lambda _event: self.models_canvas.configure(cursor="hand2"))
                self.models_canvas.tag_bind(item, "<Leave>", lambda _event: self.models_canvas.configure(cursor=""))
            self._models_canvas_rows[model_index] = row_items

        total_height = header_height + max(1, len(filtered)) * row_height
        self.models_canvas.configure(scrollregion=(0, 0, table_width, total_height))
        self.models_canvas.xview_moveto(0)
        self.models_canvas.yview_moveto(0)

    def _model_matches_overview_filters(self, loaded: LoadedModel) -> bool:
        query_var = getattr(self, "models_search_var", None)
        query = query_var.get().strip().lower() if query_var is not None else ""
        if query and query not in loaded.name.lower() and query not in loaded.source_file.lower():
            return False

        type_var = getattr(self, "models_type_filter_var", None)
        type_filter = type_var.get() if type_var is not None else "All"
        if type_filter != "All" and loaded.file_type != type_filter:
            return False

        model = loaded.model
        min_objects_var = getattr(self, "models_min_objects_var", None)
        min_objects = self._optional_int_filter(
            min_objects_var.get() if min_objects_var is not None else ""
        )
        if min_objects is not None and len(model.get_all_pure_objects()) < min_objects:
            return False

        min_attributes_var = getattr(self, "models_min_attributes_var", None)
        min_attributes = self._optional_int_filter(
            min_attributes_var.get() if min_attributes_var is not None else ""
        )
        if min_attributes is not None and self._count_attributes(model) < min_attributes:
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

    def _select_model_from_overview_index(self, index: int):
        self._highlight_models_canvas_row(index)
        loaded = self.loaded_models[index]
        self.current_model = loaded.model
        self.current_file_path = loaded.source_path
        self.current_file_type = loaded.file_type
        self.current_selected_columns = list(loaded.selected_columns)
        self.last_action_label = loaded.last_action or "Imported"
        self._touch_loaded_model(loaded.model)
        self._populate_models_table()
        self._highlight_models_canvas_row(index)
        self._render_overview_details(loaded)

    def _highlight_models_canvas_row(self, index: int):
        for row_items in getattr(self, "_models_canvas_rows", {}).values():
            for item in row_items:
                try:
                    self.models_canvas.itemconfigure(item, width=1)
                except tk.TclError:
                    pass
        for item in getattr(self, "_models_canvas_rows", {}).get(index, []):
            try:
                if self.models_canvas.type(item) == "rectangle":
                    self.models_canvas.itemconfigure(item, outline="#AFCBFF", width=2)
            except tk.TclError:
                pass

    def _bind_models_scroll_events(self, _event=None):
        self.bind_all("<MouseWheel>", self._on_models_mousewheel)

    def _unbind_models_scroll_events(self, _event=None):
        self.unbind_all("<MouseWheel>")

    def _on_models_mousewheel(self, event):
        delta = int(-1 * (event.delta / 120)) if event.delta else 0
        if delta:
            self.models_canvas.yview_scroll(delta, "units")

    def _render_overview_details(self, loaded: Optional[LoadedModel] = None):
        for child in self.overview_details.winfo_children():
            child.destroy()
        self.overview_details.grid_columnconfigure(0, weight=0, minsize=430)
        self.overview_details.grid_columnconfigure(1, weight=1)
        if loaded is None:
            message = "No model selected." if self.loaded_models else "No models created yet."
            ctk.CTkLabel(
                self.overview_details,
                text=message,
                text_color=self.colors["muted"],
                anchor="center",
                font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            ).grid(row=0, column=0, sticky="nsew", padx=18, pady=32)
            return
        self.current_model = loaded.model
        model = loaded.model

        meta = ctk.CTkFrame(self.overview_details, fg_color="#F8FAFC", corner_radius=7, border_width=1, border_color=self.colors["border"])
        meta.grid(row=0, column=0, rowspan=2, sticky="nsew", padx=(0, 14), pady=(0, 12))
        meta.grid_columnconfigure(1, weight=1)
        rows = [
            ("Model Name", loaded.name),
            ("Source File", loaded.source_file),
            ("Type", loaded.file_type),
            ("Imported", loaded.uploaded or "Unknown"),
            ("Last worked on", loaded.last_worked_on or loaded.uploaded or "Unknown"),
        ]
        for row, (label, value) in enumerate(rows):
            ctk.CTkLabel(meta, text=label, text_color=self.colors["muted"], anchor="w", font=ctk.CTkFont(size=12, weight="bold")).grid(
                row=row, column=0, sticky="w", padx=(14, 18), pady=(12 if row == 0 else 6, 12 if row == len(rows) - 1 else 6)
            )
            ctk.CTkLabel(meta, text=str(value), anchor="w", text_color=self.colors["text"], font=ctk.CTkFont(size=12, weight="bold")).grid(
                row=row, column=1, sticky="ew", padx=(0, 14), pady=(12 if row == 0 else 6, 12 if row == len(rows) - 1 else 6)
            )

        actions = ctk.CTkFrame(self.overview_details, fg_color="transparent")
        actions.grid(row=0, column=1, sticky="ew", pady=(0, 12))
        actions.grid_columnconfigure(0, weight=1)
        actions.grid_columnconfigure(3, weight=1)
        ctk.CTkButton(
            actions,
            text="Open Model",
            width=150,
            height=40,
            corner_radius=7,
            fg_color=self.colors["primary"],
            hover_color=self.colors["primary_hover"],
            text_color="#FFFFFF",
            font=ctk.CTkFont(family="Segoe UI", size=15, weight="bold"),
            command=lambda target=loaded: self._open_loaded_model(target),
        ).grid(row=0, column=1, padx=(0, 10))
        ctk.CTkButton(
            actions,
            text="Delete Model",
            width=150,
            height=40,
            corner_radius=7,
            fg_color=self.colors["danger"],
            hover_color="#b91c1c",
            text_color="#FFFFFF",
            font=ctk.CTkFont(family="Segoe UI", size=15, weight="bold"),
            command=lambda target=loaded: self._delete_loaded_model(target),
        ).grid(row=0, column=2, padx=(10, 0))

        metrics = ctk.CTkFrame(self.overview_details, fg_color="transparent")
        metrics.grid(row=1, column=1, sticky="nsew", pady=(0, 12))
        metric_colors = {
            "Higher Level Classes": "#315D9B",
            "Classes": "#2563EB",
            "Attributes": "#7C3AED",
            "Enumeration Types": "#F59E0B",
            "Associations": "#64748B",
            "Objects": "#16A34A",
            "Slots": "#EA580C",
            "Links": "#0891B2",
            "Operations": "#0D9488",
            "Generalizations": "#E11D48",
        }
        for index, (label, value) in enumerate(self._model_metrics(model)):
            metrics.grid_columnconfigure(index, weight=1)
            self._metric_card_no_icon(
                metrics,
                label,
                value,
                metric_colors.get(label, self.colors["primary"]),
            ).grid(row=0, column=index, sticky="ew", padx=4)

    def _open_loaded_model(self, loaded: LoadedModel):
        self.current_model = loaded.model
        self.current_file_path = loaded.source_path
        self.current_file_type = loaded.file_type
        self.current_selected_columns = list(loaded.selected_columns)
        self._touch_loaded_model(loaded.model)
        self._show_model_page()

    def _delete_loaded_model(self, loaded: LoadedModel):
        if not messagebox.askyesno(
                "Delete model",
                f"Remove '{loaded.name}' from the models overview?",
        ):
            return
        if loaded in self.loaded_models:
            self.loaded_models.remove(loaded)
            self._save_loaded_models()
        if self.current_model is loaded.model:
            self.current_model = self.loaded_models[-1].model if self.loaded_models else None
        self._populate_models_table()
        self._render_overview_details(None)

    def _model_metrics(self, model: FmmlxModel):
        return [
            ("Higher Level Classes", self._count_higher_level_classes(model)),
            ("Classes", len(model.get_all_flat_classes())),
            ("Attributes", self._count_attributes(model)),
            ("Enumeration Types", len(model.enums)),
            ("Operations", self._count_operations(model)),
            ("Generalizations", self._count_generalizations(model)),
            ("Associations", len(model.associations)),
            ("Objects", len(model.get_all_pure_objects())),
            ("Slots", self._count_slots(model)),
            ("Links", len(model.links)),
        ]

    @staticmethod
    def _count_attributes(model: FmmlxModel) -> int:
        return sum(len(obj.attr_list) for obj in model.mlm_objects)

    @staticmethod
    def _count_higher_level_classes(model: FmmlxModel) -> int:
        """
        Counts classes above level 1 for the separate higher-level metric card.
        """
        return sum(1 for obj in model.mlm_objects if obj.level > 1)

    @staticmethod
    def _count_slots(model: FmmlxModel) -> int:
        return sum(len(obj.slot_list) for obj in model.mlm_objects)

    @staticmethod
    def _count_operations(model: FmmlxModel) -> int:
        return sum(len(obj.operations_list) for obj in model.mlm_objects)

    @staticmethod
    def _count_generalizations(model: FmmlxModel) -> int:
        return sum(len(obj.parent_classes) for obj in model.mlm_objects)

    @staticmethod
    def _slot_type(slot: FmmlxSlot) -> str:
        if slot.attribute is not None:
            return ModelDeepenerApp._clean_display_value(slot.attribute.attr_type_short)
        owner = getattr(slot, "owner", None)
        model = getattr(owner, "_active_model", None)
        if model is not None:
            matches = [
                attr
                for obj in model.mlm_objects
                for attr in obj.attr_list
                if attr.name == slot.name
            ]
            enum_matches = [
                attr
                for attr in matches
                if any(enum.name == ModelDeepenerApp._clean_display_value(attr.attr_type_short) for enum in model.enums)
            ]
            if enum_matches:
                return ModelDeepenerApp._clean_display_value(enum_matches[0].attr_type_short)
            if matches:
                return ModelDeepenerApp._clean_display_value(matches[0].attr_type_short)
        return ModelDeepenerApp._clean_display_value(type(slot.value).__name__)

    @staticmethod
    def _set_windows_app_id():
        """
        Gives Windows a stable app id for the taskbar icon.

        Without this, Windows can show the Python icon for Tk apps.
        """
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("ModelDeepener.App")
        except (AttributeError, OSError):
            pass

    def _metric_card_no_icon(
            self,
            parent,
            label: str,
            value: int,
            value_color: str,
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

        value_text = str(value)
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
        self.detail_canvas.create_text(
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
            outline="#E4EBF4",
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


def run():
    """Starts Model Deepener and keeps its interface active until it is closed."""
    ModelDeepenerApp._set_windows_app_id()
    app = ModelDeepenerApp()
    app.mainloop()

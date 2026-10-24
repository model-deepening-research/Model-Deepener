"""Dialog that lets the user open an existing database or create a new one.

The dialog only uses the public methods of DatabaseFolder. Checking a name is the job of
DatabaseFolder, the dialog only shows its error messages. The color constants below use the
same values as ModelDeepenerApp.colors in app.py.
"""
import tkinter as tk

import customtkinter as ctk

from src.object_database.database import Database
from src.object_database.database_folder import DatabaseFolder

TEXT_COLOR = "#0f172a"
MUTED_COLOR = "#64748b"
BORDER_COLOR = "#e2e8f0"
DISABLED_COLOR = "#cbd5e1"
PRIMARY_COLOR = "#04173D"
PRIMARY_HOVER_COLOR = "#013897"
PRIMARY_SOFT_COLOR = "#DFE9FD"
DANGER_COLOR = "#dc2626"


class DatabaseDialog(ctk.CTkToplevel):
    """Shows the list of databases with "Open" and a name field with "Create".

    The dialog is not transient, because the main window is still hidden at startup and a
    transient dialog would be hidden with it. It is a tool window, so Windows shows no minimize
    button, and it stays on top, because a tool window has no taskbar entry and would otherwise
    be lost behind other windows while the main window is hidden.
    """

    def __init__(self, master: ctk.CTk, folder: DatabaseFolder) -> None:
        """Build the dialog for the databases in the given folder."""
        super().__init__(master)
        self._folder = folder
        self._result: tuple[Database, str] | None = None
        # These widgets are created in _build_layout().
        self._name_list: tk.Listbox
        self._empty_hint: ctk.CTkLabel
        self._open_button: ctk.CTkButton
        self._name_entry: ctk.CTkEntry
        self._error_label: ctk.CTkLabel
        self.title("Choose database")
        self.resizable(False, False)
        self.attributes("-toolwindow", True)
        self.attributes("-topmost", True)
        self.grid_columnconfigure(0, weight=1)
        self._build_layout()
        self._fill_list()
        self._center()
        self.bind("<Escape>", lambda _event: self._cancel())
        self.protocol("WM_DELETE_WINDOW", self._cancel)
        # The main window is hidden at startup, so the dialog takes the keyboard focus by hand.
        self.after(150, self._take_focus)

    def get_result(self) -> tuple[Database, str] | None:
        """Return the opened database and its name, or None if the user cancelled."""
        return self._result

    def _build_layout(self) -> None:
        """Create the list with "Open", the name field with "Create", the error label and "Cancel"."""
        self._make_heading("Open a database", 0)

        self._name_list = tk.Listbox(
            self,
            height=8,
            activestyle="none",
            exportselection=False,
            font=("Segoe UI", 11),
            fg=TEXT_COLOR,
            selectbackground=PRIMARY_SOFT_COLOR,
            selectforeground=TEXT_COLOR,
            highlightthickness=1,
            highlightbackground=BORDER_COLOR,
            highlightcolor=BORDER_COLOR,
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
            text_color=MUTED_COLOR,
            font=ctk.CTkFont(family="Segoe UI", size=13),
        )
        self._empty_hint.grid(row=1, column=0, sticky="ew", padx=18)

        self._open_button = ctk.CTkButton(
            self,
            text="Open",
            width=100,
            height=36,
            fg_color=PRIMARY_COLOR,
            hover_color=PRIMARY_HOVER_COLOR,
            text_color="#FFFFFF",
            text_color_disabled="#FFFFFF",
            command=self._open_selected,
        )
        self._open_button.grid(row=2, column=0, sticky="e", padx=18, pady=(8, 0))

        self._make_heading("Create a new database", 3)

        create_row = ctk.CTkFrame(self, fg_color="transparent")
        create_row.grid(row=4, column=0, sticky="ew", padx=18)
        create_row.grid_columnconfigure(0, weight=1)
        self._name_entry = ctk.CTkEntry(
            create_row,
            height=36,
            width=260,
            placeholder_text="Name of the new database",
            border_color=BORDER_COLOR,
            text_color=TEXT_COLOR,
        )
        self._name_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self._name_entry.bind("<Return>", lambda _event: self._create_new())
        ctk.CTkButton(
            create_row,
            text="Create",
            width=100,
            height=36,
            fg_color=PRIMARY_COLOR,
            hover_color=PRIMARY_HOVER_COLOR,
            text_color="#FFFFFF",
            command=self._create_new,
        ).grid(row=0, column=1)

        self._error_label = ctk.CTkLabel(
            self,
            text="",
            anchor="w",
            justify="left",
            wraplength=360,
            text_color=DANGER_COLOR,
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
            border_color=BORDER_COLOR,
            text_color=TEXT_COLOR,
            command=self._cancel,
        ).grid(row=6, column=0, sticky="e", padx=18, pady=(8, 18))

    def _make_heading(self, text: str, row: int) -> None:
        """Create a bold heading in the given row."""
        ctk.CTkLabel(
            self,
            text=text,
            anchor="w",
            text_color=TEXT_COLOR,
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
        if self._is_empty():
            self._name_list.grid_remove()
            self._empty_hint.grid()
            self._open_button.configure(state="disabled", fg_color=DISABLED_COLOR)
        else:
            self._empty_hint.grid_remove()
            self._name_list.grid()
            self._name_list.selection_set(0)
            self._open_button.configure(state="normal", fg_color=PRIMARY_COLOR)

    def _is_empty(self) -> bool:
        """Return True if the list contains no database."""
        return self._name_list.size() == 0

    def _open_selected(self) -> None:
        """Open the selected database and close the dialog, or show why it cannot be opened.

        The message "Please select a database first." is only a safeguard: "Open" cannot be
        clicked when the list is empty, and otherwise one entry is always selected.
        """
        selection = self._name_list.curselection()
        if len(selection) == 0:
            self._show_error("Please select a database first.")
            return
        name = self._name_list.get(selection[0])
        try:
            database = self._folder.open_database(name)
        except (KeyError, ValueError) as error:
            self._show_error(error.args[0])
            self._fill_list()
            return
        self._close_with(database, name)

    def _create_new(self) -> None:
        """Create a database with the entered name and close the dialog, or show the error."""
        name = self._name_entry.get().strip()
        try:
            database = self._folder.create_database(name)
        except ValueError as error:
            self._show_error(str(error))
            return
        self._close_with(database, name)

    def _show_error(self, message: str) -> None:
        """Show an error message in the dialog. The dialog stays open."""
        self._error_label.configure(text=message)

    def _cancel(self) -> None:
        """Close the dialog without a database."""
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
        """Center the dialog on the screen.

        The screen is used, because the main window is hidden at startup. The position is
        computed from the size of the dialog content, so the frame and the title bar move the
        dialog a few pixels away from the exact center.
        """
        self.update_idletasks()
        x = (self.winfo_screenwidth() - self.winfo_reqwidth()) // 2
        y = (self.winfo_screenheight() - self.winfo_reqheight()) // 2
        self.geometry(f"+{x}+{y}")

    def _take_focus(self) -> None:
        """Give the keyboard focus to the dialog and to the list.

        If there is no database yet, the name field gets the focus. focus_force() is used, because
        Windows does not always give a new window the focus, e.g. when the user clicks into
        another window at startup.
        """
        if not self.winfo_exists():
            return
        self.focus_force()
        if self._is_empty():
            self._name_entry.focus_set()
        else:
            self._name_list.focus_set()


def ask_for_database(master: ctk.CTk, folder: DatabaseFolder) -> tuple[Database, str] | None:
    """Show the dialog and wait until it is closed.

    Returns the opened database and its name, or None if the user cancelled or closed the dialog.
    """
    dialog = DatabaseDialog(master, folder)
    dialog.grab_set()
    master.wait_window(dialog)
    return dialog.get_result()

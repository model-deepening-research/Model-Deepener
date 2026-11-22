"""Run the real application and exercise the 864-file batch warning dialog."""
import ctypes
import json
import os
import runpy
import tempfile
import time
from pathlib import Path

import customtkinter as ctk

from src.gui.app import ModelDeepenerApp, ModelProgressDialog
from src.object_database.database import Database
from src.object_database.folder import DatabaseFolder
from src.object_database.storage import FileStorage

# Reading all files takes at least this long, well above the 0.5 s after which the loading window appears.
MINIMUM_READ_SECONDS = 1.2


def run_smoke() -> dict:
    """Open an isolated application and click through the batch warning."""
    started = time.monotonic()
    result = {"callback_errors": []}
    original_page = ModelDeepenerApp._show_import_page
    original_ask = ModelDeepenerApp._ask_batch_problems
    original_choose = ModelDeepenerApp._choose_database
    original_source = ModelDeepenerApp._ask_batch_source
    original_folders = ModelDeepenerApp._choose_batch_folders
    original_grab = ctk.CTkToplevel.grab_set
    original_progress_show = ModelProgressDialog.show
    original_importer = ModelDeepenerApp.__dict__["_importer_for_file"]
    plantuml = os.environ.get("BATCH_SMOKE_PLANTUML") == "1"
    expected = 60 if plantuml else 864
    user = ctypes.windll.user32

    class Point(ctypes.Structure):
        _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

    user.WindowFromPoint.argtypes = [Point]
    user.WindowFromPoint.restype = ctypes.c_void_p
    user.GetAncestor.argtypes = [ctypes.c_void_p, ctypes.c_uint]
    user.GetAncestor.restype = ctypes.c_void_p
    user.GetParent.argtypes = [ctypes.c_void_p]
    user.GetParent.restype = ctypes.c_void_p

    def children(widget):
        for child in widget.winfo_children():
            yield child
            yield from children(child)

    def click(button):
        button._on_enter()
        button._canvas.event_generate("<Button-1>", x=10, y=10)
        button._canvas.event_generate("<ButtonRelease-1>", x=10, y=10)

    with tempfile.TemporaryDirectory(prefix="automlm_gui_batch_test_") as directory:
        def choose_database(self, is_startup=True):
            self._database_folder = DatabaseFolder(directory)
            self._open_database(Database(FileStorage(str(Path(directory) / "temporary.pkl"))), "Test")
            return True

        def ask(self, *args, **kwargs):
            result["ask_started"] = True
            return original_ask(self, *args, **kwargs)

        def finish(self):
            result["final_grab"] = str(self.grab_current())
            result["overlay_count"] = self._overlay._open_count
            self._close_application()

        def poll_selection(self):
            if len(self.current_batch_paths) == expected and not self._model_task_active:
                result["selected"] = len(self.current_batch_paths)
                self.create_button.invoke()
            elif time.monotonic() - started < 18:
                self.after(50, lambda: poll_selection(self))
            else:
                result["selection_timeout"] = True
                self._close_application()

        def poll_dialog(self):
            dialogs = [w for w in self.winfo_children() if isinstance(w, ctk.CTkToplevel)
                       and not isinstance(w, ModelProgressDialog) and w.title() == "Import Problems"]
            if dialogs:
                dialog = dialogs[0]
                if dialog.winfo_ismapped():
                    show = next((w for w in children(dialog) if isinstance(w, ctk.CTkButton)
                                 and w.cget("text") == "Show Details"), None)
                    if show and show.winfo_ismapped():
                        progress = getattr(self, "_model_progress_dialog", None)
                        result["progress_exists"] = progress is not None
                        result["progress_mapped"] = bool(progress and progress.winfo_ismapped())
                        result["progress_grab"] = bool(progress and self.grab_current() is progress)
                        result["mapped"] = True
                        result["grab_is_dialog"] = self.grab_current() is dialog
                        focus = self.focus_get()
                        result["focus_is_dialog"] = focus is not None and focus.winfo_toplevel() is dialog
                        result["geometry"] = [dialog.winfo_rootx(), dialog.winfo_rooty(),
                                              dialog.winfo_width(), dialog.winfo_height()]
                        result["root_geometry"] = [self.winfo_rootx(), self.winfo_rooty(),
                                                   self.winfo_width(), self.winfo_height()]
                        point = Point(show.winfo_rootx() + show.winfo_width() // 2,
                                      show.winfo_rooty() + show.winfo_height() // 2)
                        native_at_button = user.GetAncestor(user.WindowFromPoint(point), 2)
                        result["dialog_above_overlay"] = native_at_button == user.GetParent(dialog.winfo_id())
                        click(show)
                        def cancel():
                            result["show_result"] = show.cget("text")
                            button = next(w for w in children(dialog) if isinstance(w, ctk.CTkButton)
                                          and w.cget("text") == "Cancel Import")
                            click(button)
                            result["closed"] = not bool(dialog.winfo_exists())
                            self.after(200, lambda: finish(self))
                        self.after(200, cancel)
                        return
            if time.monotonic() - started < 18:
                self.after(50, lambda: poll_dialog(self))
            else:
                result["dialog_timeout"] = True
                if dialogs:
                    dialogs[0].destroy()
                self.after(100, lambda: finish(self))

        def show_page(self):
            value = original_page(self)
            if not getattr(self, "_batch_smoke_scheduled", False):
                self._batch_smoke_scheduled = True
                self.report_callback_exception = lambda typ, error, _trace: result["callback_errors"].append(
                    f"{typ.__name__}: {error}")
                self.after(400, lambda: self._file_input_buttons["batch"].invoke())
                self.after(500, lambda: poll_selection(self))
                self.after(1000, lambda: poll_dialog(self))
            return value

        class SlowImporter:
            """Read like the real importer, but slowly enough that the loading window always appears.

            The tool shows its loading window only after 0.5 s, so on a fast computer the real
            reading could finish before it.
            """
            def __init__(self, importer):
                self._importer = importer

            def import_file(self, path):
                time.sleep(MINIMUM_READ_SECONDS / expected)
                return self._importer.import_file(path)

            def __getattr__(self, name):
                return getattr(self._importer, name)

        def slow_importer(path):
            importer = original_importer.__func__(path)
            return None if importer is None else SlowImporter(importer)

        def progress_show(window):
            result["progress_was_shown"] = True
            return original_progress_show(window)

        def grab(window):
            if window.title() == "Import Problems":
                progress = getattr(window.master, "_model_progress_dialog", None)
                result["handoff_progress_mapped"] = bool(progress and progress.winfo_ismapped())
                result["handoff_progress_grab"] = bool(progress and window.grab_current() is progress)
            return original_grab(window)

        ctk.CTkToplevel.grab_set = grab
        ModelProgressDialog.show = progress_show
        ModelDeepenerApp._choose_database = choose_database
        ModelDeepenerApp._ask_batch_source = lambda _self: "folder"
        ModelDeepenerApp._choose_batch_folders = lambda _self, _title: [
            str(Path("models/plantuml" if plantuml else "models/ecore").resolve()), str(Path("models/csv").resolve())]
        ModelDeepenerApp._show_import_page = show_page
        ModelDeepenerApp._ask_batch_problems = ask
        ModelDeepenerApp._importer_for_file = staticmethod(slow_importer)
        try:
            runpy.run_path("src/__main__.py", run_name="__main__")
        finally:
            ctk.CTkToplevel.grab_set = original_grab
            ModelProgressDialog.show = original_progress_show
            ModelDeepenerApp._choose_database = original_choose
            ModelDeepenerApp._ask_batch_source = original_source
            ModelDeepenerApp._choose_batch_folders = original_folders
            ModelDeepenerApp._show_import_page = original_page
            ModelDeepenerApp._ask_batch_problems = original_ask
            ModelDeepenerApp._importer_for_file = original_importer
    return result


if __name__ == "__main__":
    print("BATCH_SMOKE " + json.dumps(run_smoke()), flush=True)

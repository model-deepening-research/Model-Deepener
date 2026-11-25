"""Loading indicator that keeps moving while the application builds a view.

Building a view blocks the Tk thread of the application, so no window of the application could
move a bar meanwhile. The indicator therefore runs as a small separate process with its own Tk.
This file is also the program of that process and uses only the standard library.
"""
import ctypes
import json
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import ttk

SHOW_DELAY_MILLISECONDS = 500
POLL_MILLISECONDS = 15
# WM_SETREDRAW and the RedrawWindow flags of the Windows application programming interface (API).
WM_SETREDRAW = 0x000B
RDW_INVALIDATE = 0x0001
RDW_ERASE = 0x0004
RDW_ALLCHILDREN = 0x0080
RDW_FRAME = 0x0400
# Extended window styles that keep the indicator from taking the focus of the application.
GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000


class ViewLoadingIndicator:
    """A large loading window with a running bar and no percentage.

    start() asks the indicator process to show the window after the delay; stop() hides it or
    cancels it when it is not visible yet. Without a working process both calls do nothing.
    """

    def __init__(self, colors: dict) -> None:
        self._colors = {name: colors[name] for name in ("text", "muted", "border", "primary")}
        self._process = None
        self.shown = threading.Event()

    def prepare(self) -> None:
        """Start the indicator process early, so the first build does not wait for it."""
        if self._process is not None and self._process.poll() is None:
            return
        flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        try:
            self._process = subprocess.Popen(
                [sys.executable, "-I", os.path.abspath(__file__), json.dumps(self._colors)],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                text=True, encoding="utf-8", bufsize=1, creationflags=flags)
        except OSError:
            self._process = None
            return
        threading.Thread(target=self._read_reports, args=(self._process,), daemon=True).start()

    def start(self, geometry: tuple, message: str, scaling: float = 1.0,
              delay_ms: int = SHOW_DELAY_MILLISECONDS) -> None:
        """Show the window centered in geometry (x, y, width, height) unless stop() follows in time."""
        self.prepare()
        self.shown.clear()
        x, y, width, height = (int(value) for value in geometry)
        self._send({"command": "start", "geometry": [x, y, width, height], "message": message,
                    "scaling": float(scaling), "delay": int(delay_ms)})

    def stop(self) -> None:
        """Hide the window, or cancel it when it is not visible yet."""
        self._send({"command": "stop"})

    def close(self) -> None:
        """End the indicator process."""
        process, self._process = self._process, None
        if process is None:
            return
        try:
            process.stdin.close()
            process.wait(2)
        except (OSError, subprocess.TimeoutExpired):
            process.kill()
            process.wait()
        process.stdout.close()

    def _send(self, command: dict) -> None:
        if self._process is None:
            return
        try:
            self._process.stdin.write(json.dumps(command) + "\n")
            self._process.stdin.flush()
        except (OSError, ValueError):
            self._process = None

    def _read_reports(self, process) -> None:
        """Note when the process has shown the window."""
        try:
            for line in process.stdout:
                if line.strip() == "shown":
                    self.shown.set()
        except (OSError, ValueError):
            # close() has closed the output of the ended process.
            pass


def set_window_redraw(window: tk.Misc, enabled: bool) -> bool:
    """Stop or resume painting of the application window under Windows.

    While painting is stopped the screen keeps the previous view, so a view can be built without
    showing half finished widgets. Returns False when the window system does not support it.
    """
    if sys.platform != "win32":
        return False
    try:
        user32 = ctypes.windll.user32
        user32.GetParent.argtypes = [ctypes.c_void_p]
        user32.GetParent.restype = ctypes.c_void_p
        user32.SendMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p]
        user32.RedrawWindow.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint]
        handle = user32.GetParent(window.winfo_id()) or window.winfo_id()
        user32.SendMessageW(handle, WM_SETREDRAW, 1 if enabled else 0, 0)
        if enabled:
            user32.RedrawWindow(handle, None, None, RDW_ERASE | RDW_FRAME | RDW_INVALIDATE | RDW_ALLCHILDREN)
        return True
    except (AttributeError, OSError, tk.TclError):
        return False


def _run_indicator(colors: dict) -> None:
    """Show the loading window of the indicator process until its input ends."""
    if sys.platform == "win32":
        try:
            # The same pixel coordinates as the application, which is aware of the monitor scaling.
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except (AttributeError, OSError):
            pass
    commands = queue.Queue()

    def read_commands():
        for line in sys.stdin:
            commands.put(json.loads(line))
        commands.put({"command": "quit"})

    threading.Thread(target=read_commands, daemon=True).start()
    root = tk.Tk()
    root.withdraw()
    root.overrideredirect(True)
    root.attributes("-topmost", True)
    root.configure(background=colors["border"])
    if sys.platform == "win32":
        root.update_idletasks()
        user32 = ctypes.windll.user32
        user32.GetParent.argtypes = [ctypes.c_void_p]
        user32.GetParent.restype = ctypes.c_void_p
        user32.GetWindowLongW.argtypes = [ctypes.c_void_p, ctypes.c_int]
        user32.SetWindowLongW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_long]
        handle = user32.GetParent(root.winfo_id()) or root.winfo_id()
        style = user32.GetWindowLongW(handle, GWL_EXSTYLE)
        user32.SetWindowLongW(handle, GWL_EXSTYLE, style | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE)
    panel = tk.Frame(root, background="#FFFFFF")
    panel.pack(fill="both", expand=True, padx=1, pady=1)
    title = tk.Label(panel, text="Loading View...", background="#FFFFFF", foreground=colors["text"])
    title.pack(pady=(26, 6))
    message = tk.Label(panel, background="#FFFFFF", foreground=colors["muted"])
    message.pack(pady=(0, 18))
    style = ttk.Style(root)
    style.theme_use("clam")
    bar = ttk.Progressbar(panel, mode="indeterminate", style="ViewLoading.Horizontal.TProgressbar")
    bar.pack(fill="x", padx=34, pady=(0, 30))
    pending = [None]

    def reveal(geometry, scaling):
        # A stop already in the input queue must be handled before showing.
        if not commands.empty():
            pending[0] = root.after(1, reveal, geometry, scaling)
            return
        pending[0] = None
        x, y, width, height = geometry
        size = (round(500 * scaling), round(150 * scaling))
        root.geometry(f"{size[0]}x{size[1]}+{x + (width - size[0]) // 2}+{y + (height - size[1]) // 2}")
        root.deiconify()
        root.lift()
        bar.start(POLL_MILLISECONDS)
        print("shown", flush=True)

    def hide():
        if pending[0] is not None:
            root.after_cancel(pending[0])
            pending[0] = None
        bar.stop()
        root.withdraw()

    def poll():
        while True:
            try:
                command = commands.get_nowait()
            except queue.Empty:
                break
            if command["command"] == "start":
                hide()
                scaling = command["scaling"]
                title.configure(font=("Segoe UI", -round(17 * scaling), "bold"))
                message.configure(text=command["message"], font=("Segoe UI", -round(12 * scaling)))
                style.configure("ViewLoading.Horizontal.TProgressbar", thickness=round(13 * scaling),
                                troughcolor=colors["border"], background=colors["primary"],
                                bordercolor=colors["border"], lightcolor=colors["primary"],
                                darkcolor=colors["primary"])
                pending[0] = root.after(command["delay"], reveal, command["geometry"], scaling)
            elif command["command"] == "stop":
                hide()
            else:
                root.destroy()
                return
        root.after(POLL_MILLISECONDS, poll)

    poll()
    root.mainloop()


if __name__ == "__main__":
    _run_indicator(json.loads(sys.argv[1]))

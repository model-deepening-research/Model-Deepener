"""Start the real application and check that the header and its buttons are visible."""
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from src.gui.app import ModelDeepenerApp
from src.object_database.database import Database
from src.object_database.folder import DatabaseFolder
from src.object_database.storage import FileStorage


class HeaderStartupTests(unittest.TestCase):
    """Test header startup."""
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        directory = self.directory.name

        def choose_database(app, is_startup=True):
            app._database_folder = DatabaseFolder(directory)
            app._open_database(Database(FileStorage(str(Path(directory) / "test.pkl"))), "Test")
            return True
        with patch.object(ModelDeepenerApp, "_choose_database", choose_database):
            self.app = ModelDeepenerApp()
        self._pump(1.0)

    def tearDown(self):
        self.app._finish_close()
        self.directory.cleanup()

    def _pump(self, seconds):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            self.app.update()

    def _assert_header_visible(self):
        app = self.app
        header = app.header
        self.assertTrue(header.winfo_ismapped())
        buttons = [app.new_model_tab, app.models_tab, app._database_name_label, app.logo_label]
        buttons += [state["button"] for state in app._model_tabs.values() if state["button"].winfo_manager()]
        for widget in buttons:
            with self.subTest(widget=str(widget)):
                self.assertTrue(widget.winfo_ismapped())
                self.assertGreater(widget.winfo_height(), 20)
                top = widget.winfo_rooty() - header.winfo_rooty()
                self.assertGreaterEqual(top, 0)
                self.assertLessEqual(top + widget.winfo_height(), header.winfo_height())
        # No header widget may make the header row taller than the header itself.
        self.assertLessEqual(max(child.winfo_reqheight() for child in header.grid_slaves()), header.winfo_height())

    def test_header_is_visible_after_start(self):
        """Check header is visible after start."""
        self._assert_header_visible()
        self.assertFalse(self.app.model_tabs_container.winfo_ismapped())

    def test_header_stays_visible_with_and_without_model_tabs(self):
        """Check header stays visible with and without model tabs."""
        app = self.app
        app._show_model_page = lambda: None
        models = [SimpleNamespace(name=f"Model {index}", path_name="") for index in range(8)]
        for model in models:
            app.current_model = model
            app.current_file_path = model.name + ".xmi"
            app._update_model_tab()
            self._pump(0.05)
        self._pump(0.3)
        self._assert_header_visible()
        self.assertTrue(app.model_tabs_container.winfo_ismapped())
        for key in list(app._model_tabs):
            app._close_model_tab(key)
        self._pump(0.3)
        self._assert_header_visible()
        self.assertFalse(app.model_tabs_container.winfo_ismapped())


if __name__ == "__main__":
    unittest.main()

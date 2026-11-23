import ctypes
import sys
import unittest
from unittest.mock import Mock, patch
from ctypes import wintypes

from src.gui import folder_dialog


@unittest.skipUnless(sys.platform == "win32", "Windows COM folder dialog")
class NativeFolderDialogTests(unittest.TestCase):
    """Test native folder dialog."""
    def test_selects_multiple_paths_and_releases_com_resources(self):
        """Check selects multiple paths and releases com resources."""
        ole = Mock()
        ole.CoInitializeEx.return_value = 0
        def create(_clsid, _outer, _context, _iid, output):
            ctypes.cast(output, ctypes.POINTER(ctypes.c_void_p))[0] = 101
            return 0
        ole.CoCreateInstance.side_effect = create
        paths = [ctypes.create_unicode_buffer("C:\\First"), ctypes.create_unicode_buffer("C:\\Second")]
        flags = []
        released = []
        def bind(interface, index, _result_type, *_types):
            def call(_interface, *args):
                if index == 2:
                    released.append(interface.value)
                elif index == 10:
                    ctypes.cast(args[0], ctypes.POINTER(wintypes.DWORD))[0] = 0x4000
                elif index == 9:
                    flags.append(args[0])
                elif index == 27:
                    ctypes.cast(args[0], ctypes.POINTER(ctypes.c_void_p))[0] = 202
                elif index == 7:
                    ctypes.cast(args[0], ctypes.POINTER(wintypes.DWORD))[0] = 2
                elif index == 8:
                    ctypes.cast(args[1], ctypes.POINTER(ctypes.c_void_p))[0] = 301 + args[0]
                elif index == 5:
                    ctypes.cast(args[1], ctypes.POINTER(ctypes.c_void_p))[0] = ctypes.addressof(paths[interface.value - 301])
                return 0
            return call
        with patch.object(folder_dialog.ctypes, "WinDLL", return_value=ole), patch.object(folder_dialog, "_method", side_effect=bind):
            selected = folder_dialog.choose_windows_folders(123)
        self.assertEqual(selected, ["C:\\First", "C:\\Second"])
        required = folder_dialog.FOS_PICKFOLDERS | folder_dialog.FOS_ALLOWMULTISELECT | folder_dialog.FOS_FORCEFILESYSTEM
        self.assertEqual(flags[0] & required, required)
        self.assertEqual(released, [301, 302, 202, 101])
        self.assertEqual(ole.CoTaskMemFree.call_count, 2)
        ole.CoUninitialize.assert_called_once()

    def test_cancel_returns_empty_without_requesting_results(self):
        """Check cancel returns empty without requesting results."""
        ole = Mock()
        ole.CoInitializeEx.return_value = 0
        ole.CoCreateInstance.side_effect = lambda _a, _b, _c, _d, out: (ctypes.cast(out, ctypes.POINTER(ctypes.c_void_p)).__setitem__(0, 101) or 0)
        calls = []
        def bind(_interface, index, _return_type, *_types):
            def call(_self, *args):
                calls.append(index)
                if index == 3:
                    return ctypes.c_long(folder_dialog.ERROR_CANCELLED).value
                return 0
            return call
        with patch.object(folder_dialog.ctypes, "WinDLL", return_value=ole), patch.object(folder_dialog, "_method", side_effect=bind):
            self.assertEqual(folder_dialog.choose_windows_folders(), [])
        self.assertNotIn(27, calls)
        ole.CoUninitialize.assert_called_once()


if __name__ == "__main__":
    unittest.main()

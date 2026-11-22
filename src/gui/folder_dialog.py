"""Native Windows folder selection using the system file dialog."""
import ctypes
import sys
import uuid
from ctypes import wintypes
from typing import Any

FOS_PICKFOLDERS = 0x00000020
FOS_FORCEFILESYSTEM = 0x00000040
FOS_ALLOWMULTISELECT = 0x00000200
FOS_PATHMUSTEXIST = 0x00000800
SIGDN_FILESYSPATH = 0x80058000
ERROR_CANCELLED = 0x800704C7
RPC_E_CHANGED_MODE = 0x80010106

VTABLE_RELEASE = 2
VTABLE_DIALOG_SHOW = 3
VTABLE_DIALOG_SET_OPTIONS = 9
VTABLE_DIALOG_GET_OPTIONS = 10
VTABLE_DIALOG_GET_RESULTS = 27
VTABLE_ARRAY_GET_COUNT = 7
VTABLE_ARRAY_GET_ITEM_AT = 8
VTABLE_ITEM_GET_DISPLAY_NAME = 5


class _Guid(ctypes.Structure):
    _fields_ = [("data1", ctypes.c_uint32), ("data2", ctypes.c_uint16),
                ("data3", ctypes.c_uint16), ("data4", ctypes.c_ubyte * 8)]

    @classmethod
    def parse(cls, value: str) -> "_Guid":
        return cls.from_buffer_copy(uuid.UUID(value).bytes_le)


def _check(result: int) -> None:
    if result < 0:
        raise OSError(result, "Windows folder dialog failed")


def _method(interface: ctypes.c_void_p, index: int, result_type: Any, *argument_types: Any) -> Any:
    """Bind a COM vtable method to its interface pointer."""
    table = ctypes.cast(interface, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    prototype = ctypes.WINFUNCTYPE(result_type, ctypes.c_void_p, *argument_types)
    return prototype(table[index])


def _release(interface) -> None:
    if interface:
        _method(interface, VTABLE_RELEASE, ctypes.c_ulong)(interface)


def choose_windows_folders(owner: int = 0) -> list[str]:
    """Return filesystem folders selected in the Windows multi-select dialog."""
    if sys.platform != "win32":
        raise OSError("The native folder dialog is available only on Windows.")
    ole = ctypes.WinDLL("ole32")
    ole.CoInitializeEx.argtypes = [ctypes.c_void_p, wintypes.DWORD]
    ole.CoInitializeEx.restype = ctypes.c_long
    ole.CoCreateInstance.argtypes = [ctypes.POINTER(_Guid), ctypes.c_void_p, wintypes.DWORD,
                                     ctypes.POINTER(_Guid), ctypes.POINTER(ctypes.c_void_p)]
    ole.CoCreateInstance.restype = ctypes.c_long
    ole.CoTaskMemFree.argtypes = [ctypes.c_void_p]
    ole.CoTaskMemFree.restype = None
    result = ole.CoInitializeEx(None, 2)
    initialized = result >= 0
    if not initialized and result & 0xFFFFFFFF != RPC_E_CHANGED_MODE:
        _check(result)
    dialog = ctypes.c_void_p()
    items = ctypes.c_void_p()
    try:
        clsid = _Guid.parse("dc1c5a9c-e88a-4dde-a5a1-60f82a20aef7")
        iid = _Guid.parse("d57c7288-d4ad-4768-be02-9d969532d960")
        _check(ole.CoCreateInstance(ctypes.byref(clsid), None, 1, ctypes.byref(iid), ctypes.byref(dialog)))
        options = wintypes.DWORD()
        _check(_method(dialog, VTABLE_DIALOG_GET_OPTIONS, ctypes.c_long, ctypes.POINTER(wintypes.DWORD))(dialog, ctypes.byref(options)))
        flags = FOS_PICKFOLDERS | FOS_ALLOWMULTISELECT | FOS_FORCEFILESYSTEM | FOS_PATHMUSTEXIST
        _check(_method(dialog, VTABLE_DIALOG_SET_OPTIONS, ctypes.c_long, wintypes.DWORD)(dialog, options.value | flags))
        result = _method(dialog, VTABLE_DIALOG_SHOW, ctypes.c_long, wintypes.HWND)(dialog, owner)
        if result & 0xFFFFFFFF == ERROR_CANCELLED:
            return []
        _check(result)
        _check(_method(dialog, VTABLE_DIALOG_GET_RESULTS, ctypes.c_long, ctypes.POINTER(ctypes.c_void_p))(dialog, ctypes.byref(items)))
        count = wintypes.DWORD()
        _check(_method(items, VTABLE_ARRAY_GET_COUNT, ctypes.c_long, ctypes.POINTER(wintypes.DWORD))(items, ctypes.byref(count)))
        paths = []
        for index in range(count.value):
            item = ctypes.c_void_p()
            path_pointer = ctypes.c_void_p()
            try:
                _check(_method(items, VTABLE_ARRAY_GET_ITEM_AT, ctypes.c_long, wintypes.DWORD, ctypes.POINTER(ctypes.c_void_p))(
                    items, index, ctypes.byref(item)))
                _check(_method(item, VTABLE_ITEM_GET_DISPLAY_NAME, ctypes.c_long, ctypes.c_uint32, ctypes.POINTER(ctypes.c_void_p))(
                    item, SIGDN_FILESYSPATH, ctypes.byref(path_pointer)))
                paths.append(ctypes.wstring_at(path_pointer.value))
            finally:
                if path_pointer:
                    ole.CoTaskMemFree(path_pointer)
                _release(item)
        return paths
    finally:
        _release(items)
        _release(dialog)
        if initialized:
            ole.CoUninitialize()

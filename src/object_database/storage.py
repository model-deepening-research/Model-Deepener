"""Save the data of a Database in one file with pickle and load it again.

The file also stores a format version, so a file in an unknown format is not loaded by mistake.
"""
import os
import io
import hashlib
import pickle
import time
from typing import Any

FORMAT_VERSION = 2


class _CooperativeBuffer(io.BytesIO):
    """Yield between pickle frames so other threads can process interface events."""
    def read(self, size: int = -1) -> bytes:
        value = super().read(size)
        time.sleep(0)
        return value

    def readline(self, size: int = -1) -> bytes:
        value = super().readline(size)
        time.sleep(0)
        return value

    def write(self, value: bytes) -> int:
        count = super().write(value)
        time.sleep(0)
        return count


class _CooperativePickler(pickle.Pickler):
    """Yield periodically while serializing custom model objects."""
    def __init__(self, output: io.BytesIO) -> None:
        super().__init__(output, protocol=pickle.DEFAULT_PROTOCOL)
        self._objects_seen = 0

    def reducer_override(self, obj: Any) -> Any:
        self._objects_seen += 1
        if self._objects_seen % 256 == 0:
            time.sleep(0)
        return NotImplemented


class _StoredModelUnpickler(pickle.Unpickler):
    """Reads stored objects whose classes are in another module than when they were stored."""

    MOVED_MODULES = {"src.basemlm.import_report": "src.importers.import_report"}

    def find_class(self, module: str, name: str) -> Any:
        """Return the stored class, and look in its new module if the module has moved."""
        return super().find_class(self.MOVED_MODULES.get(module, module), name)


class FileStorage:
    """Reads and writes the data of a Database in one file."""

    def __init__(self, file_name: str) -> None:
        """Create a storage for the given file. The file does not need to exist yet."""
        self._file_name = file_name
        self._saved_digest: bytes | None = None

    def exists(self) -> bool:
        """Return True if the data file exists."""
        return os.path.exists(self._file_name)

    def load(self) -> dict[str, Any]:
        """Read the data file and return the stored data.

        The file contains a dict with the format version and the data. Raises a ValueError if the
        file has a different or missing format version.
        """
        with open(self._file_name, "rb") as file:
            encoded = file.read()
        content = _StoredModelUnpickler(_CooperativeBuffer(encoded)).load()
        version = None
        if isinstance(content, dict):
            version = content.get("format_version")
        if version != FORMAT_VERSION:
            raise ValueError(
                f"The file has format version {version}, "
                f"but this program can only read format version {FORMAT_VERSION}."
            )
        self._saved_digest = hashlib.sha256(encoded).digest()
        return content["data"]

    @staticmethod
    def serialize(data: dict[str, Any]) -> bytes:
        """Serialize a database in the current storage format."""
        buffer = _CooperativeBuffer()
        _CooperativePickler(buffer).dump({"format_version": FORMAT_VERSION, "data": data})
        return buffer.getvalue()

    @property
    def saved_digest(self) -> bytes | None:
        """Return the digest of the last successfully read or written file."""
        return self._saved_digest

    def save(self, data: dict[str, Any]) -> None:
        """Write the data safely: first into a temporary file, then swap it in.

        os.replace() swaps the two files in one single step. So if the program crashes while
        writing, only the temporary file is broken, and the real file still holds the last
        committed state. A temporary file left by a failed save is removed again.
        """
        self.save_serialized(self.serialize(data))

    def save_serialized(self, encoded: bytes, digest: bytes | None = None) -> None:
        """Atomically write a previously serialized database."""
        temporary_name = f"{self._file_name}.tmp"
        try:
            with open(temporary_name, "wb") as file:
                file.write(encoded)
            os.replace(temporary_name, self._file_name)
            self._saved_digest = digest if digest is not None else hashlib.sha256(encoded).digest()
        finally:
            if os.path.exists(temporary_name):
                os.remove(temporary_name)

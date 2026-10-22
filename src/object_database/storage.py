"""Save the data of a Database in one file with pickle and load it again.

The file also stores a format version, so a file in an unknown format is not loaded by mistake.
"""
import os
import pickle
from datetime import datetime

FORMAT_VERSION = 1


class FileStorage:
    """Reads and writes the data of a Database in one file."""

    def __init__(self, file_name):
        """Create a storage for the given file. The file does not need to exist yet."""
        self._file_name = file_name

    def exists(self):
        """Return True if the data file exists."""
        return os.path.exists(self._file_name)

    def load(self):
        """Read the data file and return the stored data.

        The file contains a dict with the format version and the data. Raises a ValueError if the file has a different or missing format version.
        """
        with open(self._file_name, "rb") as file:
            content = pickle.load(file)
        version = None
        if isinstance(content, dict):
            version = content.get("format_version")
        if version != FORMAT_VERSION:
            raise ValueError(
                f"The file {self._file_name} has format version {version}, "
                f"but this program can only read format version {FORMAT_VERSION}."
            )
        return content["data"]

    def save(self, data):
        """Write the data safely: first into a temporary file, then swap it in.

        os.replace() swaps the two files in one single step. So if the program crashes while writing, only the temporary file is broken, and the real file still holds the last committed state.
        """
        content = {"format_version": FORMAT_VERSION, "data": data}
        temporary_name = f"{self._file_name}.tmp"
        with open(temporary_name, "wb") as file:
            pickle.dump(content, file)
        os.replace(temporary_name, self._file_name)

    def move_to_backup(self):
        """Rename the data file to <name>_unreadable_<date-time> and return the new file name.

        The backup stays in the same folder. This is meant for a data file that cannot be loaded.
        The old data is kept, and a new Database starts empty because the data file no longer
        exists. The date and time contain no colons, because Windows does not allow them in file
        names. Raises an OSError if renaming fails, so the data file is never lost.
        """
        name, extension = os.path.splitext(self._file_name)
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        backup_name = f"{name}_unreadable_{timestamp}{extension}"
        os.rename(self._file_name, backup_name)
        return backup_name

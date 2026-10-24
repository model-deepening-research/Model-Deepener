"""A folder that holds several databases, one .pkl file for each database.

The name of a database is the file name without the ending .pkl.
"""
import os

from src.object_database.database import Database
from src.object_database.storage import FileStorage

FILE_ENDING = ".pkl"
ALLOWED_SPECIAL_CHARACTERS = " -_"
WINDOWS_RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
    "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9",
}


class DatabaseFolder:
    """Finds, opens and creates the databases in one folder.

    Names are cleaned with strip() first, so "Default " and "Default" are the same name.
    """

    def __init__(self, folder_path: str) -> None:
        """Create a DatabaseFolder for the given folder. The folder does not need to exist yet."""
        self._folder_path = folder_path

    def get_names(self) -> list[str]:
        """Return the names of all databases in the folder, sorted and without the ending .pkl."""
        if not os.path.isdir(self._folder_path):
            return []
        names = []
        for file_name in os.listdir(self._folder_path):
            if file_name.endswith(FILE_ENDING):
                names.append(os.path.splitext(file_name)[0])
        names.sort(key=str.lower)
        return names

    def open_database(self, name: str) -> Database:
        """Open the database with the given name.

        Raises a KeyError if there is no database with this name. Raises a ValueError if the file
        cannot be read. The file is not changed in that case, because a file with a newer format
        version is not broken. Any error while loading is turned into a ValueError, so the caller
        only has to handle one error type.
        """
        name = name.strip()
        if name not in self.get_names():
            raise KeyError(f"There is no database with the name: {name}")
        try:
            return Database(FileStorage(self._get_path(name)))
        except Exception as error:
            raise ValueError(f"Database {name} cannot be read: {error}") from error

    def create_database(self, name: str) -> Database:
        """Create a new, empty database with the given name and save it at once.

        commit() is called right away, so the file exists and the new database shows up in
        get_names(). Raises a ValueError if the name is not allowed or already used.
        """
        name = name.strip()
        self._check_name(name)
        os.makedirs(self._folder_path, exist_ok=True)
        database = Database(FileStorage(self._get_path(name)))
        database.commit()
        return database

    def _check_name(self, name: str) -> None:
        """Check that a cleaned name can be used for a new database.

        The name must not be empty, may only contain letters, digits, spaces, - and _, must not
        be a reserved Windows name, and must not be used yet. Upper and lower case are not told
        apart, because Windows treats Default.pkl and default.pkl as the same file. Raises a
        ValueError if one of these rules is broken.
        """
        if name == "":
            raise ValueError("The name of the database must not be empty.")
        for character in name:
            if not character.isalnum() and character not in ALLOWED_SPECIAL_CHARACTERS:
                raise ValueError(f"The name {name} contains the character '{character}'. "
                                 f"Only letters, digits, spaces, - and _ are allowed.")
        if name.upper() in WINDOWS_RESERVED_NAMES:
            raise ValueError(f"The name {name} is reserved by Windows and cannot be used.")
        for existing_name in self.get_names():
            if existing_name.lower() == name.lower():
                raise ValueError(f"A database with the name {existing_name} already exists.")

    def _get_path(self, name: str) -> str:
        """Return the path of the file that belongs to the given name."""
        return os.path.join(self._folder_path, name + FILE_ENDING)

"""Tests for DatabaseFolder: create, list and open several databases in one folder.

Run from the project folder with: python -m src.object_database.test_database_folder
The test folder is created in the folder you run from and deleted at the end.
"""
import os
import shutil

from src.object_database.database_folder import DatabaseFolder
from src.object_database.persistent import Persistent

FOLDER_NAME = "test_databases"


class Note(Persistent):
    """A small object that can be stored, so the tests can check what a database contains."""

    def __init__(self, text: str) -> None:
        """Create a note with the given text."""
        super().__init__()
        self._text = text

    def get_text(self) -> str:
        """Return the text of the note."""
        return self._text


def remove_test_folder() -> None:
    """Delete the test folder, so every test starts from an empty folder."""
    if os.path.exists(FOLDER_NAME):
        shutil.rmtree(FOLDER_NAME)


def test_create() -> None:
    """Test that create_database() creates the folder and the file at once."""
    print("--- (a) Create a new database ---")
    remove_test_folder()
    folder = DatabaseFolder(FOLDER_NAME)
    database = folder.create_database("Default")
    print("Does the file exist?", os.path.exists(os.path.join(FOLDER_NAME, "Default.pkl")),
          "(expected: True)")
    print("Number of objects in the new database:", len(database.get_root()), "(expected: 0)")


def test_get_names() -> None:
    """Test that get_names() returns all names, sorted and without the ending .pkl."""
    print("--- (b) List the databases ---")
    remove_test_folder()
    folder = DatabaseFolder(FOLDER_NAME)
    print("Names of a folder that does not exist yet:", folder.get_names(), "(expected: [])")
    folder.create_database("Zoo")
    folder.create_database("cars")
    folder.create_database(" Flights ")
    print("Names:", folder.get_names(), "(expected: ['cars', 'Flights', 'Zoo'])")


def test_open() -> None:
    """Test that open_database() returns the stored objects again after a restart."""
    print("--- (c) Open a database ---")
    remove_test_folder()
    folder = DatabaseFolder(FOLDER_NAME)
    database = folder.create_database("Default")
    database.store("first", Note("hello"))
    database.commit()
    folder.create_database("Other")

    folder = DatabaseFolder(FOLDER_NAME)
    database = folder.open_database("Default")
    print("Text of the note:", database.get("first").get_text(), "(expected: hello)")
    other = folder.open_database("Other ")
    print("Number of objects in Other:", len(other.get_root()), "(expected: 0)")


def test_invalid_names() -> None:
    """Test that names that are empty, have wrong characters or are reserved raise a ValueError."""
    print("--- (d) Invalid names ---")
    remove_test_folder()
    folder = DatabaseFolder(FOLDER_NAME)
    for name in ["", "   ", "a/b", "x.y", "con", "LPT1"]:
        try:
            folder.create_database(name)
            print(f"'{name}' was accepted (expected: ValueError)")
        except ValueError as error:
            print(f"'{name}' raised ValueError:", error)
    print("Names after the invalid names:", folder.get_names(), "(expected: [])")


def test_duplicate_name() -> None:
    """Test that a name that differs only in upper and lower case raises a ValueError."""
    print("--- (e) Duplicate name in a different case ---")
    remove_test_folder()
    folder = DatabaseFolder(FOLDER_NAME)
    folder.create_database("Default")
    for name in ["default", "DEFAULT ", "Default"]:
        try:
            folder.create_database(name)
            print(f"'{name}' was accepted (expected: ValueError)")
        except ValueError as error:
            print(f"'{name}' raised ValueError:", error)
    print("Names:", folder.get_names(), "(expected: ['Default'])")


def test_open_missing() -> None:
    """Test that opening a database that does not exist raises a KeyError."""
    print("--- (f) Open a database that does not exist ---")
    remove_test_folder()
    folder = DatabaseFolder(FOLDER_NAME)
    try:
        folder.open_database("Missing")
        print("Missing was opened (expected: KeyError)")
    except KeyError as error:
        print("open_database() raised KeyError:", error)


def test_open_unreadable() -> None:
    """Test that an unreadable file raises a ValueError and is left unchanged.

    The file is filled by hand with bytes that are no pickle data, as a broken file would be.
    """
    print("--- (g) Open an unreadable database ---")
    remove_test_folder()
    folder = DatabaseFolder(FOLDER_NAME)
    folder.create_database("Broken")
    path = os.path.join(FOLDER_NAME, "Broken.pkl")
    with open(path, "wb") as file:
        file.write(b"this is no pickle data")
    try:
        folder.open_database("Broken")
        print("Broken was opened (expected: ValueError)")
    except ValueError as error:
        print("open_database() raised ValueError:", error)
    print("Does the file still exist?", os.path.exists(path), "(expected: True)")
    print("Names:", folder.get_names(), "(expected: ['Broken'])")


if __name__ == "__main__":
    test_create()
    test_get_names()
    test_open()
    test_invalid_names()
    test_duplicate_name()
    test_open_missing()
    test_open_unreadable()
    remove_test_folder()

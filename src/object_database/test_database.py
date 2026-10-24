"""Tests for Database: store, find, delete, commit and abort objects.

Run from the project folder with: python -m src.object_database.test_database
The test data file is created in the folder you run from and deleted at the end.
"""
import os
import pickle

from src.object_database.database import Database
from src.object_database.persistent import Persistent
from src.object_database.storage import FileStorage

FILE_NAME = "test_data.pkl"


def remove_data_file() -> None:
    """Delete the data file, so every test starts from an empty file."""
    if os.path.exists(FILE_NAME):
        os.remove(FILE_NAME)


def open_database() -> Database:
    """Open the database. Opening it again simulates a program restart."""
    return Database(FileStorage(FILE_NAME))


def test_store_and_find() -> None:
    """Test that name and OID lead to the same object after a restart."""
    print("--- (1) Store two objects and find them after a restart ---")
    remove_data_file()
    database = open_database()
    database.store("first", Persistent())
    database.store("second", Persistent())
    database.commit()

    database = open_database()
    first = database.get("first")
    second = database.get("second")
    print("OIDs:", first.get_oid(), second.get_oid(), "(expected: 1 2)")
    print("Same object via name and OID?",
          first is database.get_by_oid(first.get_oid()), "(expected: True)")
    print("Two different objects?", first is not second, "(expected: True)")


def test_delete() -> None:
    """Test that delete() removes the object from the root and the OID table."""
    print("--- (2) delete() an object ---")
    remove_data_file()
    database = open_database()
    database.store("first", Persistent())
    database.commit()
    oid = database.get("first").get_oid()
    database.delete("first")
    database.commit()

    database = open_database()
    print("Is 'first' still in the root?", "first" in database.get_root(), "(expected: False)")
    try:
        database.get_by_oid(oid)
        print("get_by_oid() still found the object (expected: KeyError)")
    except KeyError as error:
        print("get_by_oid() raised KeyError:", error)


def test_commit_and_abort() -> None:
    """Test that abort() throws away the changes after an error, but keeps committed ones."""
    print("--- (3) commit() and abort() ---")
    remove_data_file()
    database = open_database()
    database.store("a", Persistent())
    database.commit()
    try:
        database.store("b", Persistent())
        raise ValueError("Simulated error")
    except ValueError as error:
        print("Error:", error)
        database.abort()
    print("Is 'b' in the root?", "b" in database.get_root(), "(expected: False)")
    print("Is 'a' in the root?", "a" in database.get_root(), "(expected: True)")


def test_format_version() -> None:
    """Test that a file with a different format version raises a ValueError.

    The file is written by hand, as a future program version with format 2 would do.
    """
    print("--- (4) Wrong format version ---")
    remove_data_file()
    with open(FILE_NAME, "wb") as file:
        pickle.dump({"format_version": 2, "data": {}}, file)
    try:
        open_database()
        print("The file was loaded (expected: ValueError)")
    except ValueError as error:
        print("ValueError:", error)


if __name__ == "__main__":
    test_store_and_find()
    test_delete()
    test_commit_and_abort()
    test_format_version()
    remove_data_file()

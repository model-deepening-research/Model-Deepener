"""Database that keeps Persistent objects in memory and finds them by their OID.

Changes are saved with commit() or thrown away with abort().
"""
from src.object_database.persistent import Persistent
from src.object_database.storage import FileStorage


class Database:
    """Keeps Persistent objects in memory and saves them with a FileStorage.

    Every stored object gets an OID, by which it can be found again. All changes stay in memory
    until commit() is called; abort() throws them away again.
    """

    def __init__(self, storage: FileStorage) -> None:
        """Create a database and load the last committed state from the storage.

        Raises a ValueError if the data file has a different format version
        (see FileStorage.load()).
        """
        self._storage = storage
        # These attributes are set in _start_empty() and _load().
        self._objects: dict[int, Persistent]
        self._next_oid: int
        self._start_empty()
        if storage.exists():
            self._load()

    def store(self, stored_object: Persistent) -> int:
        """Store an object and return its OID.

        An object without an OID gets the next free OID. An object that already has an OID keeps
        it. Raises a TypeError if the object is not a Persistent object.
        """
        if not isinstance(stored_object, Persistent):
            raise TypeError("Only Persistent objects can be stored.")
        if stored_object.get_oid() is None:
            stored_object.assign_oid(self._next_oid)
            self._next_oid = self._next_oid + 1
        self._objects[stored_object.get_oid()] = stored_object
        return stored_object.get_oid()

    def get(self, oid: int) -> Persistent:
        """Return the object with the given OID.

        Raises a KeyError if no object has this OID.
        """
        if oid not in self._objects:
            raise KeyError(f"No object with the OID: {oid}")
        return self._objects[oid]

    def delete(self, oid: int) -> None:
        """Delete the object with the given OID.

        Like every change, the deletion is only saved by commit(). Raises a KeyError if no object
        has this OID.
        """
        if oid not in self._objects:
            raise KeyError(f"No object with the OID: {oid}")
        del self._objects[oid]

    def get_all(self) -> list[Persistent]:
        """Return all stored objects, ordered by their OID, which is the order of storing."""
        objects = []
        for oid in sorted(self._objects):
            objects.append(self._objects[oid])
        return objects

    def commit(self) -> None:
        """Make all changes since the last commit permanent by writing them to the file."""
        data = {"objects": self._objects, "next_oid": self._next_oid}
        self._storage.save(data)

    def abort(self) -> None:
        """Throw away all changes since the last commit.

        The last committed state is loaded from the file again. Variables that still point to old
        objects are not updated, so fetch objects again via get() or get_all() after an abort.
        Raises a ValueError if the data file has a different format version.
        """
        if self._storage.exists():
            self._load()
        else:
            self._start_empty()

    def _start_empty(self) -> None:
        """Reset the database to the empty state."""
        self._objects = {}
        self._next_oid = 1

    def _load(self) -> None:
        """Replace everything in memory with the data from the file.

        Raises a ValueError if the data file has a different format version.
        """
        data = self._storage.load()
        self._objects = data["objects"]
        self._next_oid = data["next_oid"]

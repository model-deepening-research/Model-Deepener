"""Database that keeps Persistent objects in memory and finds them by name or OID.

Changes are saved with commit() or thrown away with abort().
"""
from src.object_database.persistent import Persistent
from src.object_database.storage import FileStorage


class Database:
    """Keeps Persistent objects in memory and saves them with a FileStorage.

    Objects are stored under a name in the root and can also be found by their OID. All changes
    stay in memory until commit() is called; abort() throws them away again.
    """

    def __init__(self, storage: FileStorage) -> None:
        """Create a database and load the last committed state from the storage.

        Raises a ValueError if the data file has a different format version
        (see FileStorage.load()).
        """
        self._storage = storage
        self._start_empty()
        if storage.exists():
            self._load()

    def get_root(self) -> dict[str, Persistent]:
        """Return a copy of the root, a dictionary from names to objects."""
        return self._root.copy()

    def store(self, name: str, obj: Persistent) -> None:
        """Store an object under a name. It gets an OID if it has none yet.

        Raises a TypeError if the object is not a Persistent object.
        """
        if not isinstance(obj, Persistent):
            raise TypeError("Only Persistent objects can be stored.")
        self._register(obj)
        self._root[name] = obj

    def get(self, name: str) -> Persistent:
        """Return the object stored under a name.

        Raises a KeyError if no object is stored under this name.
        """
        if name not in self._root:
            raise KeyError(f"No object stored under the name: {name}")
        return self._root[name]

    def get_by_oid(self, oid: int) -> Persistent:
        """Return the object with the given OID.

        Raises a KeyError if no object has this OID.
        """
        if oid not in self._objects:
            raise KeyError(f"No object with the OID: {oid}")
        return self._objects[oid]

    def delete(self, name: str) -> None:
        """Delete the object stored under a name from the root and from the OID table.

        Like every change, the deletion is only saved by commit(). Raises a KeyError if no object
        is stored under this name.

        Known limit: if the same object is stored under two names, it can still be reached under
        the second name after delete(), but its OID is not in the OID table.
        """
        obj = self.get(name)
        del self._root[name]
        del self._objects[obj.get_oid()]

    def commit(self) -> None:
        """Make all changes since the last commit permanent by writing them to the file."""
        data = {"root": self._root, "objects": self._objects, "next_oid": self._next_oid}
        self._storage.save(data)

    def abort(self) -> None:
        """Throw away all changes since the last commit.

        The last committed state is loaded from the file again. Variables that still point to old
        objects are not updated, so fetch objects again via get() or get_by_oid() after an abort.
        Raises a ValueError if the data file has a different format version.
        """
        if self._storage.exists():
            self._load()
        else:
            self._start_empty()

    def _start_empty(self) -> None:
        """Reset the database to the empty state."""
        self._root = {}
        self._objects = {}
        self._next_oid = 1

    def _register(self, obj: Persistent) -> None:
        """Give the object an OID if needed and add it to the OID table."""
        if obj.get_oid() is None:
            obj.assign_oid(self._next_oid)
            self._next_oid = self._next_oid + 1
        self._objects[obj.get_oid()] = obj

    def _load(self) -> None:
        """Replace everything in memory with the data from the file.

        Raises a ValueError if the data file has a different format version.
        """
        data = self._storage.load()
        self._root = data["root"]
        self._objects = data["objects"]
        self._next_oid = data["next_oid"]

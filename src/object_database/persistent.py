"""Base class for objects that can be stored in a Database."""


class Persistent:
    """Base class for every object that is stored in a Database.

    Each object knows its own object ID (OID). The Database gives it the OID when the object is
    stored for the first time; after that it never changes.
    """

    def __init__(self) -> None:
        """Create an object that has no OID yet."""
        self._oid = None

    def get_oid(self) -> int | None:
        """Return the OID, or None if the object was never stored."""
        return self._oid

    def assign_oid(self, oid: int) -> None:
        """Set the OID once. Only the Database should call this method.

        Raises a ValueError if the object already has an OID.
        """
        if self._oid is not None:
            raise ValueError(f"The object already has the OID {self._oid}.")
        self._oid = oid

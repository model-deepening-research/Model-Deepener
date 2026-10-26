"""A small object database modeled on the building blocks of ZODB.

- persistent.py: Persistent, the base class for every object that can be stored.
- storage.py: FileStorage, which reads and writes the data file.
- database.py: Database, which finds objects by their OID, with commit() and abort().
- folder.py: DatabaseFolder, which lists, opens and creates the databases in one folder.
"""

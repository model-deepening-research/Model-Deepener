"""A small object database modeled on the building blocks of ZODB.

- persistent.py: Persistent, the base class for every object that can be stored.
- storage.py: FileStorage, which reads and writes the data file.
- database.py: Database, with root, OIDs, commit() and abort().
- database_folder.py: DatabaseFolder, which lists, opens and creates the databases in one folder.
- test_database.py and test_database_folder.py: the tests, started with python -m.
"""

"""A small object database modeled on the building blocks of ZODB.

- persistent.py: Persistent, the base class for every object that can be stored.
- storage.py: FileStorage, which reads and writes the data file.
- database.py: Database, with root, OIDs, commit() and abort().
- example_fmmlx.py: an FMMLx-like example class and the tests.
"""

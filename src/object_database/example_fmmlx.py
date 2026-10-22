"""Example and tests: FMMLx-like objects stored in the object database.

Run from the project folder with: python -m src.object_database.example_fmmlx
The test data file is created in the folder you run from and deleted at the end.
"""
import os
import pickle

from src.object_database.database import Database
from src.object_database.persistent import Persistent
from src.object_database.storage import FileStorage

FILE_NAME = "example_data.pkl"


class MLMObject(Persistent):
    """An FMMLx-like object: a class (level 1 or higher) or an instance (level 0).

    One class is enough for both, because in FMMLx a class is also just an object on a higher level. A class keeps a list of its instances, and each instance points back to its class.
    """

    def __init__(self, name, level, class_of_object=None):
        """Create an object. If a class is given, the object is added to its instances.

        Both directions of the link (instance -> class and class -> instance) are set here, in one single place, so they always fit together. Raises a ValueError if level is lower than 0, and any error that add_instance() raises.
        """
        if level < 0:
            raise ValueError(f"{name} has level {level}, but the level must be 0 or higher.")
        super().__init__()
        self._name = name
        self._level = level
        self._class_of_object = class_of_object
        self._attributes = []
        self._slots = {}
        self._instances = []
        if class_of_object is not None:
            class_of_object.add_instance(self)

    def get_name(self):
        """Return the name of the object."""
        return self._name

    def get_level(self):
        """Return the level of the object."""
        return self._level

    def get_class_of_object(self):
        """Return the class this object is an instance of, or None."""
        return self._class_of_object

    def get_attributes(self):
        """Return a copy of the attribute names this class defines for its instances."""
        return self._attributes.copy()

    def get_slots(self):
        """Return a copy of the attribute values this instance has."""
        return self._slots.copy()

    def get_instances(self):
        """Return a copy of the list of instances of this class."""
        return self._instances.copy()

    def add_attribute(self, attribute_name):
        """Define a new attribute for the instances of this class.

        Raises a ValueError if the class already has this attribute.
        """
        if attribute_name in self._attributes:
            raise ValueError(f"{self._name} already has the attribute {attribute_name}.")
        self._attributes.append(attribute_name)

    def set_slot(self, attribute_name, value):
        """Set the value of an attribute that the class of this object defines.

        Raises a ValueError if the class of this object does not define this attribute.
        """
        attributes = []
        if self._class_of_object is not None:
            attributes = self._class_of_object.get_attributes()
        if attribute_name not in attributes:
            raise ValueError(f"{self._name} has no attribute {attribute_name}.")
        self._slots[attribute_name] = value

    def add_instance(self, instance):
        """Add an instance to the list of instances of this class.

        This only works if the instance points to this class, has a level exactly one below the level of this class, and is not in the list yet. Otherwise it raises a ValueError.
        """
        if instance.get_class_of_object() is not self:
            raise ValueError(f"{instance.get_name()} is not an instance of {self._name}.")
        if instance.get_level() != self._level - 1:
            raise ValueError(f"{instance.get_name()} has level {instance.get_level()}, "
                             f"but instances of {self._name} must have level {self._level - 1}.")
        if instance in self._instances:
            raise ValueError(f"{instance.get_name()} is already an instance of {self._name}.")
        self._instances.append(instance)

    def remove_instance(self, instance):
        """Remove an instance from the list of instances of this class.

        Raises a ValueError if the instance is not in the list.
        """
        if instance not in self._instances:
            raise ValueError(f"{instance.get_name()} is not an instance of {self._name}.")
        self._instances.remove(instance)

    def before_delete(self):
        """Keep the model consistent when this object is deleted.

        A class that still has instances cannot be deleted. An instance removes itself from the instance list of its class. Raises a ValueError if this object is a class that still has instances.
        """
        if len(self._instances) > 0:
            names = []
            for instance in self._instances:
                names.append(instance.get_name())
            names_text = ", ".join(names)
            raise ValueError(f"Cannot delete {self._name}, "
                             f"it still has instances: {names_text}")
        if self._class_of_object is not None:
            self._class_of_object.remove_instance(self)


def remove_data_file():
    """Delete the data file, so every test starts from an empty file."""
    if os.path.exists(FILE_NAME):
        os.remove(FILE_NAME)


def open_database():
    """Open the database. Opening it again simulates a program restart."""
    return Database(FileStorage(FILE_NAME))


def create_car_model():
    """Create an empty database with the class Car and its instance myCar, and commit it."""
    remove_data_file()
    db = open_database()
    car_class = MLMObject("Car", 1)
    car_class.add_attribute("color")
    my_car = MLMObject("myCar", 0, car_class)
    my_car.set_slot("color", "blue")
    db.store("Car", car_class)
    db.store("myCar", my_car)
    db.commit()
    return db


def test_circular_reference():
    """Test that the circle Car <-> myCar is still intact after a restart."""
    print("--- (1) Circular reference after restart ---")
    create_car_model()
    db = open_database()
    loaded_class = db.get("Car")
    loaded_car = db.get("myCar")
    print(f"Loaded: {loaded_class.get_name()} (level {loaded_class.get_level()}) "
          f"and {loaded_car.get_name()} (level {loaded_car.get_level()})")
    print("myCar.class_of_object is Car?",
          loaded_car.get_class_of_object() is loaded_class, "(expected: True)")
    print("Car.instances[0] is myCar?",
          loaded_class.get_instances()[0] is loaded_car, "(expected: True)")
    print("Number of entries in Car.instances:", len(loaded_class.get_instances()), "(expected: 1)")
    print("myCar color:", loaded_car.get_slots()["color"], "(expected: blue)")
    print("Same object via name and OID?",
          loaded_car is db.get_by_oid(loaded_car.get_oid()), "(expected: True)")


def test_delete():
    """Test that delete() removes an instance and also removes it from its class."""
    print("--- (2) delete() an instance ---")
    db = create_car_model()
    car_oid = db.get("myCar").get_oid()
    db.delete("myCar")
    print("Car.instances right after delete:", len(db.get("Car").get_instances()), "(expected: 0)")
    db.commit()

    db = open_database()
    print("Car.instances after restart:", len(db.get("Car").get_instances()), "(expected: 0)")
    print("Is 'myCar' still in the root?", "myCar" in db.get_root(), "(expected: False)")
    try:
        db.get_by_oid(car_oid)
        print("get_by_oid() still found myCar (expected: KeyError)")
    except KeyError as error:
        print("get_by_oid() raised KeyError:", error)


def test_delete_class_with_instances():
    """Test that a class that still has instances cannot be deleted."""
    print("--- (3) delete() a class that still has instances ---")
    db = create_car_model()
    try:
        db.delete("Car")
        print("Car was deleted (expected: ValueError)")
    except ValueError as error:
        print("delete() raised ValueError:", error)
    print("Is 'Car' still in the root?", "Car" in db.get_root(), "(expected: True)")
    print("Car.instances:", len(db.get("Car").get_instances()), "(expected: 1)")


def test_commit_and_abort():
    """Test that commit() saves changes and abort() throws them away after an error.

    The second change fails on purpose: Car has no attribute "speed", so set_slot() raises a ValueError, commit() is never reached, and the except block calls abort().
    """
    print("--- (4) commit() and abort() ---")
    db = create_car_model()
    db.get("myCar").set_slot("color", "black")
    db.commit()
    db = open_database()
    print("Color after commit and restart:",
          db.get("myCar").get_slots()["color"], "(expected: black)")

    try:
        db.get("myCar").set_slot("color", "pink")
        db.store("Bike", MLMObject("Bike", 1))
        db.get("myCar").set_slot("speed", 200)
        db.commit()
    except ValueError as error:
        print("Error:", error)
        db.abort()
    print("Color after abort:", db.get("myCar").get_slots()["color"], "(expected: black)")
    print("Is 'Bike' in the root?", "Bike" in db.get_root(), "(expected: False)")
    db = open_database()
    print("Color after restart:", db.get("myCar").get_slots()["color"], "(expected: black)")


def test_format_version():
    """Test that a file with a different format version raises a ValueError.

    The file is written by hand, as a future program version with format 2 would do.
    """
    print("--- (5) Wrong format version ---")
    remove_data_file()
    with open(FILE_NAME, "wb") as file:
        pickle.dump({"format_version": 2, "data": {}}, file)
    try:
        open_database()
        print("The file was loaded (expected: ValueError)")
    except ValueError as error:
        print("ValueError:", error)


def test_wrong_instance_level():
    """Test that an instance whose level is not one below its class raises a ValueError."""
    print("--- (6) Instance with the wrong level ---")
    car_class = MLMObject("Car", 1)
    try:
        MLMObject("badCar", 1, car_class)
        print("badCar was created (expected: ValueError)")
    except ValueError as error:
        print("ValueError:", error)
    print("Car.instances:", len(car_class.get_instances()), "(expected: 0)")


def test_level_check_on_any_level():
    """Test that the level check works on any level, and that a level below 0 is not allowed."""
    print("--- (7) Level check on any level ---")
    vehicle_class = MLMObject("Vehicle", 2)
    car_class = MLMObject("Car", 1, vehicle_class)
    print("Vehicle.instances:", len(vehicle_class.get_instances()), "(expected: 1)")
    print("Car.class_of_object is Vehicle?",
          car_class.get_class_of_object() is vehicle_class, "(expected: True)")

    my_car = MLMObject("myCar", 0, car_class)
    try:
        MLMObject("tinyCar", -1, my_car)
        print("tinyCar was created (expected: ValueError)")
    except ValueError as error:
        print("ValueError:", error)
    print("myCar.instances:", len(my_car.get_instances()), "(expected: 0)")


if __name__ == "__main__":
    test_circular_reference()
    test_delete()
    test_delete_class_with_instances()
    test_commit_and_abort()
    test_format_version()
    test_wrong_instance_level()
    test_level_check_on_any_level()
    remove_data_file()
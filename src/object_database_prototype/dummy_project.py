"""Dummy project for the object-database prototype.

Run with: ``python -m src.object_database_prototype.dummy_project``
"""

from pathlib import Path
from tempfile import TemporaryDirectory

from src.fmmlx_mlm_structure.fm_multi_level_model import FmmlxModel, metaClass
from src.fmmlx_mlm_structure.fm_object import FmmlxObject
from src.object_database_prototype.repository import PrototypeObjectDatabase


def build_dummy_model() -> FmmlxModel:
    model = FmmlxModel()
    model.model_name = "DummyProject"
    model.path_name = "Root::DummyProject"
    car_class = FmmlxObject(
        "Root::DummyProject::Car", "Car", "1", metaClass, "false", model
    )
    car = FmmlxObject(
        "Root::DummyProject::myCar", "myCar", "0", car_class, "false", model
    )
    car_class.add_instance(car)
    model.add_mlm_object(car_class)
    model.add_mlm_object(car)
    model.set_instances_of_mlm_objects()
    return model


def run_prototype() -> None:
    with TemporaryDirectory(prefix="automlm-object-database-") as directory:
        database = PrototypeObjectDatabase(Path(directory))
        database.save("dummy-project", build_dummy_model())
        loaded = database.load("dummy-project")
        assert loaded.model_name == "DummyProject"
        assert [obj.name for obj in loaded.mlm_objects] == ["Car", "myCar"]
        assert loaded.mlm_objects[1].class_of_object is loaded.mlm_objects[0]
        assert loaded.mlm_objects[0].instances[0] is loaded.mlm_objects[1]
        assert database.delete("dummy-project")
        assert list(database.list_ids()) == []
        print("Object-database prototype save/load/delete succeeded")


if __name__ == "__main__":
    run_prototype()

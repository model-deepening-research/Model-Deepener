"""Conversion preserves the source, identities, metadata and invalid model states."""
import pickle
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from src.basemlm.basemlm_model import BaseMlmModel
from src.basemlm.basemlm_object import BaseMlmObject
from src.gui.app import DatabaseDialog, ModelDeepenerApp
from src.object_database.folder import DatabaseFolder
from src.object_database.persistent import Persistent
from src.object_database.storage import FORMAT_VERSION


def legacy_fixture() -> bytes:
    """Build the content of a stored database in the former format."""
    modules = {}
    classes = []
    for module_name, class_name in (
        ("fm_multi_level_model", "FmmlxModel"),
        ("fm_object", "FmmlxObject"),
        ("fm_attr", "FmmlxAttribute"),
    ):
        full_name = "src.fmmlx_mlm_structure." + module_name
        module = types.ModuleType(full_name)
        cls = type(class_name, (), {"__module__": full_name})
        setattr(module, class_name, cls)
        modules[full_name] = module
        classes.append(cls)
    model, obj, attr = [cls() for cls in classes]
    model.__dict__.update(vars(BaseMlmModel()))
    obj.__dict__.update(vars(BaseMlmObject("Root::Test::Item", "Item", "1", None, "false")))
    obj.is_abstract = obj.__dict__.pop("abstract")
    obj.model = model
    obj.level = "1"
    attr.__dict__.update(name="unfinished", print_name="unfinished", owner=obj,
                         attr_type="Root::XCore::String", attr_type_short="String",
                         inst_level="99", attr_category="ATTR", multiplicity=None)
    obj.attr_list = [attr]
    model.path_name = "Root::Test"
    model.mlm_objects = [obj]
    stored = Persistent()
    stored.assign_oid(1)
    stored.model = model
    stored.name = "Keep this name"
    with patch.dict(sys.modules, modules):
        return pickle.dumps({"format_version": FORMAT_VERSION,
                             "data": {"objects": {1: stored}, "next_oid": 2}})


class MigrationTests(unittest.TestCase):
    """Checks the conversion of a database in the former format."""

    def test_convert_overwrites_database_and_preserves_backup_and_references(self) -> None:
        """Convert legacy objects while preserving backup bytes, identities, metadata and later saving."""
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "Old.pkl"
            original = legacy_fixture()
            source.write_bytes(original)
            folder = DatabaseFolder(directory)
            database, name, report = folder.convert_database("Old")
            self.assertNotEqual(source.read_bytes(), original)
            self.assertEqual((Path(directory) / "Old.pkl.bak").read_bytes(), original)
            self.assertEqual(name, "Old")
            self.assertEqual(folder.get_names(), ["Old"])
            restored = folder.open_database(name).get(1)
            self.assertEqual(restored.name, "Keep this name")
            model = restored.model
            self.assertIsInstance(model, BaseMlmModel)
            obj = model.mlm_objects[0]
            attr = obj.attr_list[0]
            self.assertIs(obj.model, model)
            self.assertIs(attr.owner, obj)
            self.assertEqual(attr.inst_level, 99)  # Preserve the invalid intermediate state.
            self.assertEqual(attr.attr_type_spec.get_type_name(), "String")
            self.assertFalse(obj.abstract)
            self.assertIn("Backup: Old.pkl.bak", report)
            _, second_name, _ = folder.convert_database("Old")
            self.assertEqual(second_name, "Old")
            self.assertEqual((Path(directory) / "Old.pkl.bak").read_bytes(), original)
            self.assertTrue((Path(directory) / "Old.pkl.bak.2").exists())
            database.get(1).name = "Saved after conversion"
            database.commit()
            self.assertEqual(folder.open_database("Old").get(1).name, "Saved after conversion")

    def test_failed_write_removes_new_file_and_preserves_original(self) -> None:
        """Keep the original legacy bytes and database listing when the staged save runs out of space."""
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "Old.pkl"
            original = legacy_fixture()
            source.write_bytes(original)
            folder = DatabaseFolder(directory)
            with patch("src.object_database.folder.FileStorage.save", side_effect=OSError("Disk full")):
                with self.assertRaises(OSError):
                    folder.convert_database("Old")
            self.assertEqual(source.read_bytes(), original)
            self.assertEqual(folder.get_names(), ["Old"])

    def test_failed_final_replacement_preserves_original_and_cleans_staging(self) -> None:
        """Keep the original and its backup while removing staged files after a final replacement error."""
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "Old.pkl"
            original = legacy_fixture()
            source.write_bytes(original)
            replace = os.replace

            def fail_final_replacement(staged: str, target: str) -> None:
                """Stand in for os.replace and fail when the database itself would be replaced."""
                if str(staged).endswith(".migration"):
                    raise OSError("Replacement failed")
                return replace(staged, target)

            with patch("src.object_database.folder.os.replace", side_effect=fail_final_replacement):
                with self.assertRaises(OSError):
                    DatabaseFolder(directory).convert_database("Old")
            self.assertEqual(source.read_bytes(), original)
            self.assertEqual((Path(directory) / "Old.pkl.bak").read_bytes(), original)
            self.assertEqual(sorted(item.name for item in Path(directory).iterdir()),
                             ["Old.pkl", "Old.pkl.bak"])

    def test_unsupported_legacy_class_does_not_create_a_partial_database(self) -> None:
        """Reject an unknown legacy type before replacing or adding any database."""
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "Old.pkl"
            original = legacy_fixture().replace(b"FmmlxModel", b"OtherModel")
            source.write_bytes(original)
            folder = DatabaseFolder(directory)
            with self.assertRaisesRegex(ValueError, "does not support legacy type"):
                folder.convert_database("Old")
            self.assertEqual(source.read_bytes(), original)
            self.assertEqual(folder.get_names(), ["Old"])

    def test_failed_constraint_check_blocks_export_without_discarding_model(self) -> None:
        """Warn instead of exporting when validation raises, retaining the active model."""
        model = Mock()
        model.validate_basemlm_integrity.side_effect = AttributeError("Incomplete type")
        ui = types.SimpleNamespace(current_model=model, _show_warning=Mock(),
                                   _export_current_xml_model=Mock())
        ModelDeepenerApp._export_current_model_placeholder(ui)
        ui._show_warning.assert_called_once()
        ui._export_current_xml_model.assert_not_called()
        self.assertIs(ui.current_model, model)

    def test_conversion_is_only_started_after_explicit_choice(self) -> None:
        """Start migration only for Convert, route Delete separately and ignore the other choice."""
        for choice in ("other", "delete", "convert"):
            with self.subTest(choice=choice):
                folder = Mock()
                folder.convert_database.return_value = (Mock(), "New", "Report")
                ui = types.SimpleNamespace(_folder=folder, _delete_selected=Mock(),
                                           _close_with=Mock(), _show_dialog_error=Mock())
                with patch("src.gui.app.ask_database_conversion", return_value=choice), patch(
                        "src.gui.app.popup_message"):
                    DatabaseDialog._handle_incompatible_database(ui, "Old")
                self.assertEqual(folder.convert_database.call_count, int(choice == "convert"))
                self.assertEqual(ui._delete_selected.call_count, int(choice == "delete"))


if __name__ == "__main__":
    unittest.main()

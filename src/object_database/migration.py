"""Explicit migration of the former FMMLx object schema to BaseMLM.

Only known class renames are supported. Unpickling retains object identity and
cycles; normalization adds the new type specifications without reimporting source
files or discarding edited model state. The caller verifies and atomically replaces the database after making a backup.
"""
import importlib
import pickle
from typing import Any, Dict, List, Tuple

from src.basemlm.basemlm_attribute import BaseMlmAttribute
from src.basemlm.basemlm_model import BaseMlmModel
from src.basemlm.basemlm_object import BaseMlmObject
from src.basemlm.multiplicity import Multiplicity
from src.object_database.persistent import Persistent
from src.object_database.storage import FORMAT_VERSION


LEGACY_CLASSES = {
    ("fm_multi_level_model", "FmmlxModel"): ("basemlm_model", "BaseMlmModel"),
    ("fm_object", "FmmlxObject"): ("basemlm_object", "BaseMlmObject"),
    ("fm_attr", "FmmlxAttribute"): ("basemlm_attribute", "BaseMlmAttribute"),
    ("fm_association_end", "FmmlxAssociationEnd"): ("basemlm_assoc_end", "BaseMlmAssocEnd"),
    ("fm_association", "FmmlxAssociation"): ("basemlm_association", "BaseMlmAssociation"),
    ("fm_link", "FmmlxLink"): ("basemlm_link", "BaseMlmLink"),
    ("fm_slot", "FmmlxSlot"): ("basemlm_slot", "BaseMlmSlot"),
    ("slot_link", "FmmlxSlotLink"): ("basemlm_slot_link", "BaseMlmSlotLink"),
    ("fm_constraint", "FmmlxConstraint"): ("basemlm_constraint", "BaseMlmConstraint"),
    ("fm_operation", "FmmlxOperation"): ("basemlm_operation", "BaseMlmOperation"),
    ("fm_enum_type", "FmmlxEnumType"): ("basemlm_enum_type", "BaseMlmEnumType"),
    ("multiplicity", "Multiplicity"): ("multiplicity", "Multiplicity"),
    ("model_property_enum", "ModelPropertyEnum"): ("model_property_enum", "ModelPropertyEnum"),
}
LEGACY_MODULE_PREFIXES = ("src.fmmlx_mlm_structure.", "fmmlx_mlm_structure.")
MODEL_MODULE_PREFIXES = ("src.", "basemlm.")
CURRENT_MODEL_PACKAGE = "src.basemlm."
LEGACY_NUMERIC_FIELDS = ("level", "inst_level", "source_inst_level", "target_inst_level",
                         "proposed_inst_level", "min_multiplicity", "max_multiplicity")


class LegacyUnpickler(pickle.Unpickler):
    """Reads a stored database and replaces the former FMMLx classes by the current BaseMLM classes."""

    def find_class(self, module: str, name: str) -> Any:
        """Return the current class of a stored class. A former class that is not known stops the conversion."""
        for prefix in LEGACY_MODULE_PREFIXES:
            if module.startswith(prefix):
                key = (module[len(prefix):], name)
                if key not in LEGACY_CLASSES:
                    raise ValueError(f"Conversion does not support legacy type {module}.{name}.")
                target_module, target_name = LEGACY_CLASSES[key]
                return getattr(importlib.import_module(CURRENT_MODEL_PACKAGE + target_module), target_name)
        return super().find_class(module, name)


def model_elements(root: Any) -> List[Any]:
    """Return every model object reachable from the root once, including shared elements and cyclic references."""
    elements = []
    seen = set()
    pending = [root]
    while pending:
        value = pending.pop()
        if id(value) in seen:
            continue
        seen.add(id(value))
        if isinstance(value, dict):
            pending.extend(value.values())
        elif isinstance(value, (list, tuple, set)):
            pending.extend(value)
        elif hasattr(value, "__dict__") and type(value).__module__.startswith(MODEL_MODULE_PREFIXES):
            elements.append(value)
            pending.extend(vars(value).values())
    return elements


def convert_legacy_data(path: str) -> Tuple[Dict[str, Any], str]:
    """Read and normalize a supported file in memory, preserving invalid model states.

    Return the converted data and a text for the user.
    """
    data = _load_legacy_data(path)
    elements = model_elements(data["objects"])
    models = _find_models(elements)
    owners = _find_owner_models(models)
    _set_missing_owners(elements)
    converted_attributes = 0
    for element in elements:
        _convert_numeric_fields(element)
        _rename_fields(element)
        if _convert_attribute_type(element, owners):
            converted_attributes += 1
    # Verify that the result can be serialized before any destination file is created.
    pickle.dumps(data)
    return data, (
        f"Converted {len(models)} model(s) and {converted_attributes} attribute(s). "
        "Model contents and references were retained; "
        "constraint validity is checked separately before export."
    )


def _load_legacy_data(path: str) -> Dict[str, Any]:
    """Read the stored data. A ValueError means that the file is not a database that can be converted."""
    with open(path, "rb") as source:
        content = LegacyUnpickler(source).load()
    if not isinstance(content, dict) or content.get("format_version") != FORMAT_VERSION:
        raise ValueError("Conversion does not support this database format version.")
    data = content["data"]
    stored = data["objects"]
    if not isinstance(stored, dict):
        raise ValueError("The database does not contain supported stored models.")
    for item in stored.values():
        if not isinstance(item, Persistent):
            raise ValueError("The database does not contain supported stored models.")
    return data


def _find_models(elements: List[Any]) -> List[BaseMlmModel]:
    """Return the models among the elements. A database without a model cannot be converted."""
    models = []
    for element in elements:
        if isinstance(element, BaseMlmModel):
            models.append(element)
    if not models:
        raise ValueError("No supported models were found for conversion.")
    return models


def _find_owner_models(models: List[BaseMlmModel]) -> Dict[int, BaseMlmModel]:
    """Return the model of each object, by the id of the object.

    Precedence analyses may retain copies of properties and their owners. Those are looked up too,
    keeping the original references and analysis state.
    """
    owners = {}
    for model in models:
        for mlm_object in model.mlm_objects:
            owners[id(mlm_object)] = model
    for model in models:
        for element in model_elements(model):
            if isinstance(element, BaseMlmObject):
                owners.setdefault(id(element), model)
    return owners


def _set_missing_owners(elements: List[Any]) -> None:
    """Set the object as the owner of its attributes and slots, if a stored one has none."""
    for element in elements:
        if isinstance(element, BaseMlmObject):
            for stored_property in element.attr_list + element.slot_list:
                if getattr(stored_property, "owner", None) is None:
                    stored_property.owner = element


def _convert_numeric_fields(element: Any) -> None:
    """Turn levels and multiplicities that were stored as text into numbers."""
    state = vars(element)
    for field in LEGACY_NUMERIC_FIELDS:
        if field in state and isinstance(state[field], str):
            try:
                state[field] = int(state[field])
            except ValueError as error:
                raise ValueError(f"Cannot convert non-numeric legacy field '{field}'.") from error


def _rename_fields(element: Any) -> None:
    """Move the values of renamed fields to their current names."""
    state = vars(element)
    if isinstance(element, BaseMlmObject) and "is_abstract" in state:
        element.abstract = state.pop("is_abstract")
    if isinstance(element, Multiplicity) and "is_unbounded" in state:
        element.unbound = state.pop("is_unbounded")


def _convert_attribute_type(element: Any, owners: Dict[int, BaseMlmModel]) -> bool:
    """Give an attribute stored in the former form its type specification. Return True if it was converted."""
    if not isinstance(element, BaseMlmAttribute) or "attr_type" not in vars(element):
        return False
    element.attr_type_str = element.attr_type
    element.attr_type_str_short = element.attr_type_short
    model = owners.get(id(element.owner))
    if model is None and hasattr(element, "association"):
        model = owners.get(id(element.association.source_object))
    if model is None:
        raise ValueError(f"Cannot resolve the model for attribute '{element.name}'.")
    try:
        element.attr_type_spec = model.parse_attribute_type(element.attr_type_str)
    except (IndexError, KeyError, AttributeError, StopIteration) as error:
        raise ValueError(f"Cannot resolve the type of attribute '{element.name}'.") from error
    if element.attr_type_spec is None:
        raise ValueError(f"Cannot resolve the type of attribute '{element.name}'.")
    return True

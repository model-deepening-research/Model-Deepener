"""Prepare model names for XML serialization."""
from __future__ import annotations

from typing import TYPE_CHECKING

from src.importers.model_names import normalized_name, unique_name, make_inherited_names_unique

if TYPE_CHECKING:
    from src.basemlm.basemlm_model import BaseMlmModel


def normalize_export_names(model: BaseMlmModel) -> None:
    """Normalize names and object references in a model prepared for export."""
    used: set[str] = set()
    for obj in model.get_objects():
        name = unique_name(normalized_name(obj.get_name()), used)
        obj.set_name(name)
        obj.full_name = obj.full_name.rsplit('::', 1)[0] + '::' + name
    enum_values: dict[int, dict[str, str]] = {}
    for enum in model.get_enum_types():
        enum.set_name(unique_name(normalized_name(enum.get_name()), used))
        literals: set[str] = set()
        replacements: dict[str, str] = {}
        values: list[str] = []
        for old in enum.enum_values:
            value = unique_name(normalized_name(old), literals)
            replacements.setdefault(old, value)
            values.append(value)
        enum.enum_values = values
        enum_values[id(enum)] = replacements

    for obj in model.get_objects():
        names: set[str] = set()
        for attr in obj.get_regular_attributes():
            attr.set_name(unique_name(normalized_name(attr.get_name(), attribute=True), names))
            spec = attr.get_type_spec()
            if spec in model.get_objects() or spec in model.get_enum_types():
                attr.attr_type_str = attr.attr_type_str.rsplit('::', 1)[0] + '::' + spec.get_name()
                attr.attr_type_str_short = spec.get_name()

    used_roles = {id(obj): {attr.get_name() for attr in obj.get_regular_attributes()}
                  for obj in model.get_objects()}
    for association in model.get_associations():
        association.set_name(normalized_name(association.get_name(), association=True))
        source = association.get_source_object()
        target = association.get_target_object()
        association.source_access_name = unique_name(normalized_name(association.source_access_name), used_roles[id(source)])
        association.target_access_name = unique_name(normalized_name(association.target_access_name), used_roles[id(target)])
        if association.get_source_association_end() is not None:
            association.get_source_association_end().set_name(association.source_access_name)
        if association.get_target_association_end() is not None:
            association.get_target_association_end().set_name(association.target_access_name)

    make_inherited_names_unique(model.get_objects())

    for obj in model.get_objects():
        for slot in obj.get_regular_slots():
            attr = slot.get_attribute()
            if attr is None:
                slot.set_name(normalized_name(slot.get_name(), attribute=True))
                continue
            slot.set_name(attr.get_name())
            replacements = enum_values.get(id(attr.get_type_spec()))
            if replacements and isinstance(slot.value, str):
                slot.value = '///'.join(replacements.get(value, value) for value in slot.value.split('///'))
                slot.xml_value = None
    for link in model.get_links():
        if link.get_association() is not None:
            link.set_name(link.get_association().get_name())

from xml.dom.minidom import parse
import copy
import xml.etree.ElementTree as ElementTree
from src.fmmlx_mlm_structure import xml_export as export_xml

from typing import List, Optional
import csv
import keyword  # für reservierten Wert
import os  # für Dateinamen aus Dateiendung
import re  # für Prüfung von Zeichen
import unicodedata
import math
import networkx as nx

from src.fmmlx_mlm_structure.fm_association import FmmlxAssociation
from src.fmmlx_mlm_structure.fm_association_end import FmmlxAssociationEnd
from src.fmmlx_mlm_structure.fm_attr import FmmlxAttribute
from src.fmmlx_mlm_structure.fm_constraint import FmmlxConstraint
from src.fmmlx_mlm_structure.fm_enum_type import FmmlxEnumType
from src.fmmlx_mlm_structure.fm_link import FmmlxLink
from src.fmmlx_mlm_structure.fm_object import FmmlxObject
from src.fmmlx_mlm_structure.fm_operation import FmmlxOperation
from src.fmmlx_mlm_structure.fm_slot import FmmlxSlot
from src.fmmlx_mlm_structure.multiplicity import Multiplicity
from src.fmmlx_mlm_structure.slot_link import FmmlxSlotLink

metaClass = FmmlxObject("MetaClass",
                        "MetaClass", "99",
                        None, "false",
                        None)


class FmmlxModel:
    """
    This class serves to represent complete MultiLevelModels. It offers functions for importing standard FMMLx XML files
    into a Python representation and exporting them again to XML documents once processed as intended.
    All elements within a multi-level model are themselves instances of
    Python classes specified in mlm_helper_classes.py
    """

    def __init__(self, file_path: str = "", print_progress: bool = False,
                 selected_csv_columns: Optional[List[str]] = None):
        """
        Creates an empty model and optionally imports a CSV or XML document.

        XModeler version details, imported type references, and diagram data
        are retained so a later export can reproduce the source information.
        """
        self.path_name = ""
        self.mlm_objects: List[FmmlxObject] = []
        self.enums: List[FmmlxEnumType] = []
        self.associations: List[FmmlxAssociation] = []
        self.links: List[FmmlxLink] = []
        self.parsed_xml = None
        self.diagram_xml = None
        self.imports_xml = None
        self.xml_root_attributes = {}
        self.model_name: str = ""
        self.print_progress = print_progress
        if file_path != "":
            # Der Parameter heisst noch xml_file_path, weil er frueher nur fuer XML gedacht war.
            # Inzwischen darf hier aber auch ein CSV-Pfad stehen.
            # Die Dateiendung entscheidet, wie die Datei gelesen wird.
            file_extension = os.path.splitext(file_path)[1].lower() #[1] für Dateiende
            if file_extension == ".csv":
                self._import_csv(file_path, selected_csv_columns)
            elif file_extension == ".xml":
                self._parse_xml(file_path)
            else:
                raise ValueError(f"File '{file_path}' must be a CSV or XML file.")

    def get_model_name(self):
        return self.model_name

    def validate_basemlm_integrity(self):
        """Return all implemented BaseMLM integrity violations for this model."""
        from src.fmmlx_mlm_structure.integrity import BaseMLMValidator

        return BaseMLMValidator(self).validate()

    def _import_csv(self, csv_file_path: str, selected_csv_columns: Optional[List[str]] = None):
        """
        Imports a CSV file as one class with one instance per data row.

        Every heading becomes a unique XModeler-compatible attribute name.
        Empty cells do not create slots because they contain no exportable
        value. CSV input contains no relationships, so none are invented.
        """
        all_mlm_objects: List[FmmlxObject] = []
        # CSV files can contain special characters such as umlauts or non-English names.
        # On Windows, open() may otherwise use the local default encoding and fail while reading.
        # utf-8-sig reads normal UTF-8 files and also ignores a possible BOM marker from Excel.
        with open(csv_file_path, "r", newline="", encoding="utf-8-sig") as csv_file: #r = read
            # Das Trennzeichen wird erkannt, damit auch Dateien mit ; oder Tab funktionieren.
            self.model_name = os.path.basename(csv_file_path)
            csv_reader = csv.reader(csv_file, self._get_csv_dialect(csv_file), skipinitialspace=True)
            #mit strip vorne und hinten Leerzeichen und Anführungszeichen entfernen
            rows = [[value.strip().strip("\"") for value in row] for row in csv_reader if row]

        # prüft, dass Datei nicht leer ist
        assert len(rows) > 0, "CSV file must contain at least one row."

        # Die erste Zeile beschreibt die Spalten. Die restlichen Zeilen sind die Daten.
        header_row = rows[0]
        data_rows = rows[1:]
        number_of_columns = len(header_row)
        # prüft, dass erste Zele mindestens eine Spalte hat
        assert number_of_columns > 0, "CSV header must contain at least one column."
        # prüft, ob erste Zeile wirklich Schema-Infos enthält
        assert self._first_row_looks_like_header(header_row, data_rows), (
            "CSV header does not look valid. The first row seems to contain data instead of attribute names."
        )

        # Jede Datenzeile muss genauso viele Werte haben wie die erste Zeile (daher start bei 2)
        for row_number, row in enumerate(data_rows, start=2):
            assert len(row) == number_of_columns, (
                f"CSV row {row_number} has {len(row)} values, but the header has {number_of_columns} values."
            )

        if selected_csv_columns is not None:
            # The user can list the columns that should become attributes in the model.
            header_row, data_rows = self._select_csv_columns(header_row, data_rows, selected_csv_columns)
            number_of_columns = len(header_row)

        # Der Klassenname kommt aus dem Dateinamen.
        class_name = self._make_csv_class_name(csv_file_path)
        project_name = f"Root::{class_name}"
        self.path_name = project_name

        # Hier wird die eine Klasse gebaut, zu der alle CSV-Zeilen später gehören.
        # Beispiel: Aus der Datei news_decline.csv wird die Klasse NewsDecline.
        mlm_class: FmmlxObject = FmmlxObject(
            f"{project_name}::{class_name}", class_name, "1", FmmlxObject.meta_class(),
            "false", self)
        all_mlm_objects.append(mlm_class) #speichert Klasse im Modell

        all_csv_attr = []
        used_attribute_names = []
        for col_counter, raw_attribute_name in enumerate(header_row):
            attribute_name = self._make_csv_attribute_name(raw_attribute_name)
            attribute_name = self._make_unique_csv_attribute_name(attribute_name, used_attribute_names)
            column_values = [row[col_counter] for row in data_rows] #holt alle Werte dieser Spalte
            attribute_type = self._get_csv_attribute_type(column_values) #String, Integer oder Float
            new_attr: FmmlxAttribute = FmmlxAttribute(attribute_name, attribute_type, 0)
            new_attr.set_owner(mlm_class)
            all_csv_attr.append(new_attr) #attribut in Liste
            mlm_class.add_attr(new_attr) #fügt zur Klasse hinzu

        for row_counter, row in enumerate(data_rows, start=1):
            # Aus jeder Datenzeile wird eine Instanz mit eindeutigem Namen.
            instance_name = f"{class_name.lower()}{row_counter}"
            mlm_instance: FmmlxObject = FmmlxObject(
                f"{project_name}::{instance_name}", instance_name, "0",
                mlm_class, "false", self)
            mlm_class.add_instance(mlm_instance)
            all_mlm_objects.append(mlm_instance)

            #Slots einfügen
            for col_counter, value in enumerate(row):
                if value == "":
                    continue
                attribute = all_csv_attr[col_counter]
                new_slot: FmmlxSlot = FmmlxSlot(attribute.name, self._convert_csv_value(value, attribute.attr_type))
                new_slot.set_owner_object(mlm_instance)
                # Der Slot bekommt direkt das Attribut aus seiner Spalte.
                new_slot.set_attribute(attribute)
                mlm_instance.add_slot(new_slot)

        self._set_mlm_objects(all_mlm_objects)

    # Ab hier kommen kleine Hilfsfunktionen, um den Import oben kuerzer zu halten.
    def _get_csv_dialect(self, csv_file):
        # Es wird nur ein kleiner Anfang der Datei angeschaut, per Default ",".
        sample = csv_file.read(2048)
        csv_file.seek(0)
        try:
            return csv.Sniffer().sniff(sample, delimiters=",;\t|")
        except csv.Error:
            # csv.Sniffer can fail when the first rows contain many empty cells or irregular values.
            # Returning csv.excel directly would use "," as delimiter, which breaks semicolon CSV files.
            # Therefore, we count the allowed delimiters in the sample and use the one that appears most often.
            dialect = csv.excel
            delimiter_counts = {delimiter: sample.count(delimiter) for delimiter in [",", ";", "\t", "|"]}
            dialect.delimiter = max(delimiter_counts, key=delimiter_counts.get)
            return dialect

    def _select_csv_columns(self, header_row: List[str], data_rows: List[List[str]],
                            selected_csv_columns: List[str]):
        # Without at least one selected column, the CSV class would not have any attributes.
        assert len(selected_csv_columns) > 0, "At least one CSV column must be selected."

        selected_column_numbers = []
        missing_column_names = []
        for selected_column in selected_csv_columns:
            # For every selected column name, we search the matching position in the CSV header.
            matching_column_number = self._get_csv_column_number(header_row, selected_column)
            if matching_column_number is None:
                # Missing names are collected first, so the error can show all wrong column names at once.
                missing_column_names.append(selected_column)
            else:
                # We store the column number because the data rows are selected by position later.
                selected_column_numbers.append(matching_column_number)

        assert not missing_column_names, f"Selected CSV columns were not found: {missing_column_names}"

        # The header is reduced to the selected columns, so only these columns become attributes.
        selected_header_row = [header_row[col_number] for col_number in selected_column_numbers]
        # Every data row is reduced in the same order, so the slots still match the selected attributes.
        selected_data_rows = [
            [row[col_number] for col_number in selected_column_numbers]
            for row in data_rows
        ]
        return selected_header_row, selected_data_rows

    def _get_csv_column_number(self, header_row: List[str], selected_column: str):
        for col_counter, raw_header_name in enumerate(header_row):
            # The user may enter the original CSV name or the safe attribute name used in the model.
            safe_header_name = self._make_csv_attribute_name(raw_header_name)
            if selected_column == raw_header_name or selected_column == safe_header_name:
                return col_counter
        # None means that this selected column does not exist in the CSV header.
        return None

    #Wenn es keine Daten gibt, kann man nicht vergleichen. Dann wird die Kopfzeile akzeptiert.
    def _first_row_looks_like_header(self, header_row: List[str], data_rows: List[List[str]]) -> bool:
        if len(data_rows) == 0:
            return True

        # Namen wie "name" oder "city" sind als erste Zeile in Ordnung.
        if all(self._is_simple_header_name(header_value) for header_value in header_row):
            return True

        # Wenn die erste Zeile wie normale Daten aussieht, ist sie wahrscheinlich keine Kopfzeile.
        for col_counter, header_value in enumerate(header_row):
            column_values = [row[col_counter] for row in data_rows]
            if self._get_simple_csv_value_type(header_value) not in self._get_simple_csv_column_types(column_values):
                # also wenn erste Zeile anders aussieht als die Daten darunter, ist es wahrscheinlich ein Header
                return True
        return False

    def _is_simple_header_name(self, value: str) -> bool:
        return re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value) is not None

    def _get_simple_csv_column_types(self, values: List[str]) -> List[str]:
        column_types = []
        for value in values:
            value_type = self._get_simple_csv_value_type(value)
            if value_type not in column_types:
                column_types.append(value_type)
        return column_types

    def _get_simple_csv_value_type(self, value: str) -> str:
        if value == "":
            return "empty"
        if self._is_integer(value):
            return "integer"
        if self._is_float(value):
            return "float"
        return "string"

    def _make_csv_class_name(self, csv_file_path: str) -> str:
        # Aus "news_decline.csv" wird zum Beispiel "NewsDecline".
        file_name = os.path.splitext(os.path.basename(csv_file_path))[0]
        safe_name = self._make_safe_name(file_name, "CsvClass")
        return "".join(name_part.capitalize() for name_part in safe_name.split("_"))

    def _make_csv_attribute_name(self, raw_name: str) -> str:
        """Converts every CSV heading to an XModeler-friendly lowerCamelCase name."""
        ascii_name = unicodedata.normalize("NFKD", raw_name.strip()).encode("ascii", "ignore").decode("ascii")
        separated_words = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", ascii_name)
        words = re.findall(r"[A-Za-z0-9]+", separated_words)
        if not words:
            return "attribute"

        first_word = words[0].lower()
        remaining_words = "".join(word.lower().capitalize() for word in words[1:])
        attribute_name = first_word + remaining_words
        if attribute_name[0].isdigit():
            attribute_name = "attribute" + attribute_name[0].upper() + attribute_name[1:]

        reserved_names = {"self", "super", "null", "true", "false"}
        if keyword.iskeyword(attribute_name) or attribute_name in reserved_names:
            attribute_name += "Attribute"
        return attribute_name

    @staticmethod
    def _make_unique_csv_attribute_name(name: str, already_used_names: List[str]) -> str:
        """Adds a number when different CSV headings result in the same attribute name."""
        used_lowercase_names = {used_name.lower() for used_name in already_used_names}
        unique_name = name
        number = 2
        while unique_name.lower() in used_lowercase_names:
            unique_name = f"{name}{number}"
            number += 1
        already_used_names.append(unique_name)
        return unique_name

    def _make_safe_name(self, name: str, fallback_name: str, allow_first_char_digit: bool = False) -> str:
        # Zeichen, die in Namen stören können, werden durch _ ersetzt.
        # name attribute is occupied
        # attribute names must be String
        safe_name = re.sub(r"\W", "_", name.strip())
        safe_name = re.sub(r"_+", "_", safe_name).strip("_")
        if safe_name == "":
            safe_name = fallback_name
        if safe_name[0].isdigit() and not allow_first_char_digit:
            safe_name = f"{fallback_name}_{safe_name}"
        if keyword.iskeyword(safe_name):
            safe_name = f"{safe_name}_{fallback_name}"
        return safe_name

    def _get_csv_attribute_type(self, values: List[str]) -> str:
        # Wenn alle Werte Zahlen sind, wird auch das Attribut als Zahl gespeichert.
        values_without_empty_strings = [value for value in values if value != ""]
        if values_without_empty_strings and all(self._is_integer(value) for value in values_without_empty_strings):
            return "Root::XCore::Integer"
        if values_without_empty_strings and all(self._is_float(value) for value in values_without_empty_strings):
            return "Root::XCore::Float"
        return "Root::XCore::String"

    def _convert_csv_value(self, value: str, attribute_type: str):
        # Der Wert wird passend zum erkannten Attribut gespeichert.
        if value == "":
            return value
        if attribute_type == "Root::XCore::Integer":
            return int(value)
        if attribute_type == "Root::XCore::Float":
            return float(value)
        return value

    def _is_integer(self, value: str) -> bool:
        try:
            int(value)
            return True
        except ValueError:
            return False

    def _is_float(self, value: str) -> bool:
        try:
            float(value)
            return True
        except ValueError:
            return False

    # Ab hier gehen die normalen Funktionen weiter.
    def _set_mlm_objects(self, mlm_objects: List[FmmlxObject]):
        self.mlm_objects = mlm_objects

    def add_mlm_object(self, mlm_object: FmmlxObject):
        self.mlm_objects.append(mlm_object)

    def set_instances_of_mlm_objects(self):
        mlm_classes: List[FmmlxObject] = []
        for mlm_object in self.mlm_objects:
            if mlm_object.level > 0:
                mlm_classes.append(mlm_object)
        for mlm_class in mlm_classes:
            objects_beneath: List[FmmlxObject] = self.get_all_objects_at_level_x(mlm_class.level-1)
            for object_beneath in objects_beneath:
                if object_beneath.class_of_object == mlm_class:
                    mlm_class.add_instance(object_beneath)

    def get_all_objects_at_level_x(self, level: int) -> List[FmmlxObject]:
        objects_at_level_x: List[FmmlxObject] = []
        for obj in self.mlm_objects:
            if obj.level == level:
                objects_at_level_x.append(obj)
        return objects_at_level_x

    def get_all_flat_classes(self) -> List[FmmlxObject]:
        return self.get_all_objects_at_level_x(1)

    def get_all_pure_objects(self) -> List[FmmlxObject]:
        return self.get_all_objects_at_level_x(0)

    def export_xml(self, filepath: str = 'export_test.xml', project_name='Root::Export',
                   max_instances_per_class: Optional[int] = None,
                   diagram_mode: str = "both"):
        """
        Writes the model and its imported diagram information to an XML file.

        Level 0 instances can be limited per class. Diagrams keep their views
        and settings while their elements are arranged from high to low level.
        """
        if max_instances_per_class is not None and max_instances_per_class < 0:
            raise ValueError("The number of instances per class cannot be negative.")
        if diagram_mode not in {"fmmlx", "uml", "both"}:
            raise ValueError("The diagram mode must be fmmlx, uml, or both.")

        exported_objects = self._objects_for_export(max_instances_per_class)
        # create the root
        root = export_xml.preamble(project_name)
        self._restore_imported_xml_metadata(root, project_name)
        # export all objects
        for mlm_object in exported_objects:
            mlm_object.export(root)

        for enum in self.enums:
           enum.export(root)
        
        for assoc in self.associations:
           if assoc.source_object in exported_objects and assoc.target_object in exported_objects:
               assoc.export(root)

        for link in self.links:
           if link.source_object in exported_objects and link.target_object in exported_objects:
               link.export(root)

        self._order_model_commands_for_xmodeler(root)
        self._prepare_export_diagrams(root, project_name, exported_objects, diagram_mode)

        # xml is written and saved
        root = export_xml.writeXML(root, filepath)
        print('New XML created at ' + filepath)

        # root is returned in case it is needed ?!
        return root

    @staticmethod
    def _order_model_commands_for_xmodeler(root):
        """
        Orders model commands so every referenced type already exists.

        XModeler executes the XML from top to bottom. All classes and enums are
        therefore created before instances, inheritance, attributes, slots,
        associations, and links use them. Higher-level instances are created
        before the lower-level objects that instantiate them.
        """
        model = root.find("Model")
        commands = list(model)

        def command_order(command):
            """Returns the execution phase and level for one XModeler command."""
            phases = {
                "addMetaClass": 0,
                "addEnumeration": 1,
                "addEnumerationValue": 1,
                "addInstance": 2,
                "changeParent": 3,
                "addAttribute": 4,
                "addOperation": 5,
                "addConstraint": 5,
                "changeSlotValue": 6,
                "addAssociation": 7,
                "addLink": 8,
            }
            phase = phases.get(command.tag, 9)
            level_order = -int(command.get("level", "0")) if command.tag == "addInstance" else 0
            return phase, level_order

        model[:] = sorted(commands, key=command_order)

    def _restore_imported_xml_metadata(self, root, project_name: str):
        """
        Restores XModeler version details and imports from the source document.

        XModeler can require these values to understand external types and the
        exact file format. The selected export project remains authoritative.
        """
        root.attrib.update(self.xml_root_attributes)
        root.set("path", project_name)
        if self.imports_xml is None:
            return

        imported_section = copy.deepcopy(self.imports_xml)
        current_section = root.find("Imports")
        insertion_index = list(root).index(current_section)
        root.remove(current_section)
        root.insert(insertion_index, imported_section)

    def _objects_for_export(self, max_instances_per_class: Optional[int]) -> List[FmmlxObject]:
        """
        Selects all MLM classes and at most the requested Level 0 instances.

        The limit is applied separately to each direct class. Keeping every
        object above Level 0 preserves the complete multilevel class structure.
        """
        if max_instances_per_class is None:
            return list(self.mlm_objects)

        selected_objects = [mlm_object for mlm_object in self.mlm_objects if mlm_object.level > 0]
        instance_counts = {}
        for mlm_object in self.mlm_objects:
            if mlm_object.level != 0:
                continue
            class_key = mlm_object.class_of_object
            current_count = instance_counts.get(class_key, 0)
            if current_count < max_instances_per_class:
                selected_objects.append(mlm_object)
                instance_counts[class_key] = current_count + 1
        return selected_objects

    def _prepare_export_diagrams(self, root, project_name: str,
                                 exported_objects: List[FmmlxObject], diagram_mode: str):
        """
        Prepares the diagrams for the selected objects and their model levels.

        Existing diagram settings, labels, and edges are retained. Elements
        excluded by the instance limit are removed. Remaining model objects are
        placed ten per row, starting with the highest model level.
        """
        diagrams = root.find("Diagrams")
        if self.diagram_xml is not None:
            diagrams = copy.deepcopy(self.diagram_xml)
            current_diagrams = root.find("Diagrams")
            insertion_index = list(root).index(current_diagrams)
            root.remove(current_diagrams)
            root.insert(insertion_index, diagrams)

        old_project_name = self.path_name
        if old_project_name and old_project_name != project_name:
            for element in diagrams.iter():
                for attribute_name, attribute_value in element.attrib.items():
                    if old_project_name in attribute_value:
                        element.set(attribute_name, attribute_value.replace(old_project_name, project_name))

        exported_paths = {
            project_name + "::" + mlm_object.name: mlm_object
            for mlm_object in exported_objects
        }
        excluded_paths = {
            project_name + "::" + mlm_object.name
            for mlm_object in self.mlm_objects
            if mlm_object not in exported_objects
        }
        self._remove_excluded_diagram_elements(diagrams, excluded_paths)
        self._add_missing_diagram_objects(diagrams, exported_paths)
        self._apply_export_diagram_mode(diagrams, diagram_mode)
        self._normalize_export_diagram_names(diagrams)
        positions, dimensions = self._diagram_layout_by_level(exported_objects, project_name)

        for element in diagrams.iter():
            model_path = element.get("path") or element.get("ref")
            if model_path not in exported_paths:
                continue
            x_coordinate, y_coordinate = positions[model_path]
            if "xCoordinate" in element.attrib:
                element.set("xCoordinate", str(x_coordinate))
                element.set("yCoordinate", str(y_coordinate))
            elif "x" in element.attrib:
                element.set("x", str(x_coordinate))
                element.set("y", str(y_coordinate))
        self._route_diagram_edges(diagrams, positions, dimensions, project_name)

    @staticmethod
    def _apply_export_diagram_mode(diagrams, diagram_mode: str):
        """Keeps FMMLx, UML++, or one copy of each diagram as selected for export."""
        original_diagrams = list(diagrams.findall("Diagram"))
        if not original_diagrams:
            return
        if diagram_mode == "both":
            diagrams[:] = []
            for original_diagram in original_diagrams:
                fmmlx_diagram = copy.deepcopy(original_diagram)
                fmmlx_diagram.set("umlMode", "false")
                diagrams.append(fmmlx_diagram)
                uml_diagram = copy.deepcopy(original_diagram)
                uml_diagram.set("umlMode", "true")
                diagrams.append(uml_diagram)
            return
        selected_uml_mode = "true" if diagram_mode == "uml" else "false"
        for diagram in original_diagrams:
            diagram.set("umlMode", selected_uml_mode)

    @staticmethod
    def _normalize_export_diagram_names(diagrams):
        """Names every diagram according to the diagram mode understood by XModeler."""
        diagram_numbers = {"FmmlxDiagram": 0, "UMLppDiagram": 0}
        for diagram in diagrams.findall("Diagram"):
            diagram_prefix = "UMLppDiagram" if diagram.get("umlMode", "false").lower() == "true" else "FmmlxDiagram"
            diagram_numbers[diagram_prefix] += 1
            diagram.set("name", f"{diagram_prefix}_{diagram_numbers[diagram_prefix]}")

    @staticmethod
    def _remove_excluded_diagram_elements(diagrams, excluded_paths):
        """Removes diagram nodes and edges that refer to skipped instances."""
        for parent in diagrams.iter():
            for child in list(parent):
                values = child.attrib.values()
                if any(excluded_path in value for excluded_path in excluded_paths for value in values):
                    parent.remove(child)

    @staticmethod
    def _add_missing_diagram_objects(diagrams, exported_paths):
        """Adds newly created model objects to the first available diagram."""
        displayed_paths = {
            element.get("path") or element.get("ref")
            for element in diagrams.iter()
            if element.tag in {"Instance", "Object"}
        }
        missing_paths = sorted(set(exported_paths) - displayed_paths)
        if not missing_paths:
            return

        diagram = diagrams.find("Diagram")
        if diagram is None:
            diagram = ElementTree.SubElement(
                diagrams, "Diagram", name="FmmlxDiagram_1", umlMode="false"
            )
        container = diagram.find("Instances")
        if container is None:
            container = ElementTree.SubElement(diagram, "Instances")
        for model_path in missing_paths:
            ElementTree.SubElement(
                container,
                "Instance",
                hidden="false",
                path=model_path,
                xCoordinate="0",
                yCoordinate="0",
            )

    def _diagram_layout_by_level(self, exported_objects: List[FmmlxObject], project_name: str):
        """
        Calculates non-overlapping boxes from highest to lowest model level.

        Width and height are estimated from the visible class content. A
        connection-aware graph layout places related classes near each other.
        The square-root column count keeps the complete diagram approximately
        square. Different model levels remain on separate, centered rows.
        Each block retains its content-based size. Only visible relationships
        reserve routing space. Large levels continue on additional rows, short
        rows are centered, and vertical gaps grow with crossing connections.
        """
        positions = {}
        dimensions = {
            mlm_object: self._estimate_diagram_box_size(mlm_object)
            for mlm_object in exported_objects
        }
        graph_positions = self._connection_aware_positions(exported_objects)
        connection_pairs = self._diagram_connection_pairs(exported_objects)
        diagram_rows = []
        column_count = max(1, math.ceil(math.sqrt(len(exported_objects))))
        higher_level_objects = set()
        levels = sorted({mlm_object.level for mlm_object in exported_objects}, reverse=True)
        for level in levels:
            level_objects = sorted(
                (mlm_object for mlm_object in exported_objects if mlm_object.level == level),
                key=lambda mlm_object: (
                    round(graph_positions[mlm_object][0], 2),
                    round(graph_positions[mlm_object][1], 2),
                    mlm_object.name.lower(),
                ),
            )
            level_objects = self._order_level_for_higher_connections(
                level_objects, higher_level_objects, connection_pairs
            )
            diagram_rows.extend(
                level_objects[row_start:row_start + column_count]
                for row_start in range(0, len(level_objects), column_count)
            )
            higher_level_objects.update(level_objects)

        row_widths = [
            self._diagram_row_width(row_objects, dimensions, connection_pairs)
            for row_objects in diagram_rows
        ]
        diagram_width = max(row_widths, default=0)
        current_y = 100
        placed_objects = set()
        for row_objects, row_width in zip(diagram_rows, row_widths):
            current_x = 100 + (diagram_width - row_width) / 2
            row_height = max(dimensions[mlm_object][1] for mlm_object in row_objects)
            for column, mlm_object in enumerate(row_objects):
                positions[project_name + "::" + mlm_object.name] = (round(current_x), current_y)
                current_x += dimensions[mlm_object][0]
                if column + 1 < len(row_objects):
                    current_x += self._diagram_horizontal_gap(
                        row_objects, column, connection_pairs
                    )
            placed_objects.update(row_objects)
            remaining_objects = set(exported_objects) - placed_objects
            crossing_connections = sum(
                1
                for source, target in connection_pairs
                if (source in placed_objects and target in remaining_objects)
                or (target in placed_objects and source in remaining_objects)
            )
            vertical_gap = 80 + min(380, crossing_connections * 18)
            current_y += row_height + vertical_gap
        path_dimensions = {
            project_name + "::" + mlm_object.name: dimensions[mlm_object]
            for mlm_object in exported_objects
        }
        return positions, path_dimensions

    @classmethod
    def _order_level_for_higher_connections(cls, level_objects, higher_level_objects,
                                            connection_pairs):
        """
        Places classes linked to a higher level in their level's first row.

        The connection count measures each class's visible links to previously
        placed higher levels. Connected classes precede unrelated classes, and
        several higher-level links give a class the earliest available place.
        """
        connection_strength = {mlm_object: 0 for mlm_object in level_objects}
        for source, target in connection_pairs:
            if source in connection_strength and target in higher_level_objects:
                connection_strength[source] += 1
            elif target in connection_strength and source in higher_level_objects:
                connection_strength[target] += 1

        connected_to_higher = [
            mlm_object for mlm_object in level_objects
            if connection_strength[mlm_object] > 0
        ]
        not_connected_to_higher = [
            mlm_object for mlm_object in level_objects
            if connection_strength[mlm_object] == 0
        ]
        connected_order = []
        for strength in sorted(
                {connection_strength[mlm_object] for mlm_object in connected_to_higher},
                reverse=True):
            same_strength = [
                mlm_object for mlm_object in connected_to_higher
                if connection_strength[mlm_object] == strength
            ]
            connected_order.extend(
                cls._connection_aware_level_order(same_strength, connection_pairs)
            )
        not_connected_to_higher = cls._connection_aware_level_order(
            not_connected_to_higher, connection_pairs
        )
        return connected_order + not_connected_to_higher

    @staticmethod
    def _connection_aware_level_order(level_objects, connection_pairs):
        """
        Moves directly connected classes closer without mixing model levels.

        Adjacent swaps are retained only when they shorten the combined grid
        distance of the visible connections within this level.
        """
        if len(level_objects) < 3:
            return level_objects
        level_set = set(level_objects)
        connection_weights = {}
        for source, target in connection_pairs:
            if source not in level_set or target not in level_set:
                continue
            pair = frozenset((source, target))
            connection_weights[pair] = connection_weights.get(pair, 0) + 1

        def total_distance(order):
            """Measures how many grid positions separate connected classes."""
            indexes = {mlm_object: index for index, mlm_object in enumerate(order)}
            return sum(
                weight * abs(indexes[source] - indexes[target])
                for pair, weight in connection_weights.items()
                for source, target in [tuple(pair)]
            )

        if not connection_weights:
            return level_objects
        optimized_order = list(level_objects)
        current_distance = total_distance(optimized_order)
        improvement_found = True
        while improvement_found:
            improvement_found = False
            for left_index in range(len(optimized_order) - 1):
                candidate_order = list(optimized_order)
                candidate_order[left_index], candidate_order[left_index + 1] = (
                    candidate_order[left_index + 1], candidate_order[left_index]
                )
                candidate_distance = total_distance(candidate_order)
                if candidate_distance < current_distance:
                    optimized_order = candidate_order
                    current_distance = candidate_distance
                    improvement_found = True
        return optimized_order

    @staticmethod
    def _diagram_horizontal_gap(row_objects, column, connection_pairs):
        """Makes one horizontal corridor wider when more lines cross through it."""
        left_objects = set(row_objects[:column + 1])
        right_objects = set(row_objects[column + 1:])
        crossing_connections = sum(
            1
            for source, target in connection_pairs
            if (source in left_objects and target in right_objects)
            or (target in left_objects and source in right_objects)
        )
        return 70 + min(280, crossing_connections * 24)

    @classmethod
    def _diagram_row_width(cls, row_objects, dimensions, connection_pairs):
        """Adds the real block widths and flexible gaps of one diagram row."""
        block_width = sum(dimensions[mlm_object][0] for mlm_object in row_objects)
        gap_width = sum(
            cls._diagram_horizontal_gap(row_objects, column, connection_pairs)
            for column in range(len(row_objects) - 1)
        )
        return block_width + gap_width

    @staticmethod
    def _estimate_diagram_box_size(mlm_object: FmmlxObject):
        """
        Estimates the visible width and height of one XModeler class block.

        Long names and type labels increase the width. Every visible attribute,
        slot, operation, and constraint adds one line to the estimated height.
        Generous minimum values leave room for XModeler's headers and borders.
        Applicable class attributes are counted even without slot values because
        XModeler still displays those empty rows on an instance.
        """
        direct_attributes = [
            attribute for attribute in mlm_object.attr_list
            if attribute.attr_category != "ASSOC-END"
        ]
        visible_lines = [mlm_object.name]
        visible_lines.extend(
            f"{attribute.name}: {attribute.attr_type_short} [{attribute.inst_level}]"
            for attribute in direct_attributes
        )
        inherited_attributes, inherited_operations = FmmlxModel._inherited_diagram_members(mlm_object)
        visible_lines.extend(
            f"{attribute.name}: {attribute.attr_type_short} [{attribute.inst_level}] (from {owner_name})"
            for attribute, owner_name in inherited_attributes
        )
        slot_values = {
            slot.name: slot.value
            for slot in mlm_object.slot_list
            if slot.slot_category != "SLOT-LINK"
        }
        classification_attributes, classification_operations = (
            FmmlxModel._classification_diagram_members(mlm_object)
        )
        visible_classification_names = set()
        for attribute in classification_attributes:
            if attribute.name in visible_classification_names:
                continue
            visible_classification_names.add(attribute.name)
            visible_lines.append(
                f"{attribute.name} = {slot_values.get(attribute.name, '')}"
            )
        visible_lines.extend(
            f"{slot_name} = {slot_value}"
            for slot_name, slot_value in slot_values.items()
            if slot_name not in visible_classification_names
        )
        visible_lines.extend(FmmlxModel._operation_diagram_text(operation) for operation in mlm_object.operations_list)
        visible_lines.extend(
            f"{FmmlxModel._operation_diagram_text(operation)} (from {owner_name})"
            for operation, owner_name in inherited_operations
        )
        visible_lines.extend(
            FmmlxModel._operation_diagram_text(operation)
            for operation in classification_operations
        )
        visible_lines.extend(constraint.constraint_name for constraint in mlm_object.constraints_list)
        longest_line = max(len(str(line)) for line in visible_lines)
        width = max(280, min(1000, round(120 + longest_line * 10)))
        content_rows = max(1, len(visible_lines) - 1)
        section_count = 1
        if mlm_object.slot_list:
            section_count += 1
        if mlm_object.operations_list or inherited_operations:
            section_count += 1
        height = 100 + content_rows * 28 + section_count * 12
        return width, height

    @staticmethod
    def _classification_diagram_members(mlm_object: FmmlxObject):
        """Collects members that XModeler displays on an instance of its class."""
        attributes = []
        operations = []
        visited_classes = set()

        def collect(class_object):
            """Reads the direct class and its parents once without following cycles."""
            if class_object is None or class_object in visited_classes:
                return
            visited_classes.add(class_object)
            attributes.extend(
                attribute
                for attribute in class_object.attr_list
                if attribute.attr_category != "ASSOC-END"
                and int(attribute.inst_level) == int(mlm_object.level)
            )
            operations.extend(
                operation
                for operation in class_object.operations_list
                if int(operation.inst_level) == int(mlm_object.level)
            )
            for parent_class in class_object.parent_classes:
                collect(parent_class)

        collect(mlm_object.class_of_object)
        return attributes, operations

    @staticmethod
    def _inherited_diagram_members(mlm_object: FmmlxObject):
        """Collects inherited attributes and operations displayed by XModeler."""
        attributes = []
        operations = []
        visited_classes = set()

        def collect(parent):
            """Walks each parent once and remembers where a member originates."""
            if parent in visited_classes:
                return
            visited_classes.add(parent)
            attributes.extend(
                (attribute, parent.name)
                for attribute in parent.attr_list
                if attribute.attr_category != "ASSOC-END"
            )
            operations.extend((operation, parent.name) for operation in parent.operations_list)
            for next_parent in parent.parent_classes:
                collect(next_parent)

        for parent_class in mlm_object.parent_classes:
            collect(parent_class)
        return attributes, operations

    @staticmethod
    def _operation_diagram_text(operation):
        """Builds the complete visible operation signature used for width estimation."""
        xml_attributes = operation.xml_attributes or {}
        parameter_names = xml_attributes.get("paramNames", "")
        parameter_types = xml_attributes.get("paramTypes", "")
        parameters = parameter_names
        if parameter_types:
            parameters = f"{parameter_names}: {parameter_types}" if parameter_names else parameter_types
        return_type = operation.return_type.split("::")[-1]
        return f"{operation.operation_name}({parameters}): {return_type} [{operation.inst_level}]"

    def _diagram_connection_pairs(self, exported_objects: List[FmmlxObject]):
        """
        Lists visible relationships that require room between diagram blocks.

        Classification is not included because XModeler does not draw it as a
        separate edge. This keeps ordinary CSV instances close together.
        """
        exported_set = set(exported_objects)
        connection_pairs = []

        def add_connection(source, target):
            """Keeps a visible connection only when both ends are exported."""
            if source in exported_set and target in exported_set and source is not target:
                connection_pairs.append((source, target))

        for association in self.associations:
            add_connection(association.source_object, association.target_object)
        for link in self.links:
            add_connection(link.source_object, link.target_object)
        for mlm_object in exported_objects:
            for parent in mlm_object.parent_classes:
                add_connection(mlm_object, parent)
        return connection_pairs

    def _connection_aware_positions(self, exported_objects: List[FmmlxObject]):
        """
        Produces stable guide positions that keep connected classes together.

        Associations have the strongest weight, followed by inheritance and
        classification. The guide positions determine ordering only; the final
        coordinates are still assigned to non-overlapping level rows.
        """
        graph = nx.Graph()
        graph.add_nodes_from(exported_objects)

        def add_weighted_edge(source, target, weight):
            """Adds connection weight only when both objects are exported."""
            if source not in graph or target not in graph or source is target:
                return
            existing_weight = graph.get_edge_data(source, target, {}).get("weight", 0)
            graph.add_edge(source, target, weight=existing_weight + weight)

        for association in self.associations:
            add_weighted_edge(association.source_object, association.target_object, 5)
        for link in self.links:
            add_weighted_edge(link.source_object, link.target_object, 5)
        for mlm_object in exported_objects:
            add_weighted_edge(mlm_object, mlm_object.class_of_object, 4)
            for parent in mlm_object.parent_classes:
                add_weighted_edge(mlm_object, parent, 3)

        if graph.number_of_edges() == 0:
            return {
                mlm_object: (index, 0)
                for index, mlm_object in enumerate(sorted(exported_objects, key=lambda item: item.name.lower()))
            }
        return nx.spring_layout(graph, seed=42, weight="weight", iterations=150)

    def _route_diagram_edges(self, diagrams, positions, dimensions, project_name: str):
        """
        Routes each edge through free horizontal and vertical corridors.

        Direct paths are preferred when they do not touch another class block.
        Blocked connections receive bend points outside the occupied blocks.
        Inheritance paths contain child and parent directly. Imported
        associations may store their visible end name on either side, so both
        valid directions are considered when their endpoints are resolved.
        """
        edge_endpoints = {}
        for association in self.associations:
            source_path = project_name + "::" + association.source_object.name
            target_path = project_name + "::" + association.target_object.name
            edge_endpoints[f"AssociationMapping: {source_path}::{association.source_access_name}"] = (
                source_path,
                target_path,
            )
        for mlm_object in self.mlm_objects:
            child_path = project_name + "::" + mlm_object.name
            for parent in mlm_object.parent_classes:
                parent_path = project_name + "::" + parent.name
                edge_endpoints[f"InheritanceMapping: {child_path}/{parent_path}"] = (
                    child_path,
                    parent_path,
                )

        for edge_number, edge in enumerate(diagrams.iter("Edge")):
            edge_path = edge.get("path") or edge.get("ref") or ""
            intermediate_points = edge.find("IntermediatePoints")
            if intermediate_points is not None:
                intermediate_points.clear()
            labels = edge.find("Labels")
            if labels is not None:
                for label in labels:
                    if "xCoordinate" in label.attrib:
                        label.set("xCoordinate", "0")
                        label.set("yCoordinate", "0")
            endpoints = edge_endpoints.get(edge_path)
            if endpoints is None and edge_path.startswith("InheritanceMapping: "):
                inheritance_paths = edge_path.removeprefix("InheritanceMapping: ").split("/", 1)
                if len(inheritance_paths) == 2:
                    endpoints = inheritance_paths[0], inheritance_paths[1]
            if endpoints is None and edge_path.startswith("AssociationMapping: "):
                mapping_path = edge_path.removeprefix("AssociationMapping: ")
                for association in self.associations:
                    source_path = project_name + "::" + association.source_object.name
                    target_path = project_name + "::" + association.target_object.name
                    possible_mappings = {
                        f"{source_path}::{association.source_access_name}": (source_path, target_path),
                        f"{source_path}::{association.target_access_name}": (source_path, target_path),
                        f"{target_path}::{association.source_access_name}": (target_path, source_path),
                        f"{target_path}::{association.target_access_name}": (target_path, source_path),
                    }
                    if mapping_path in possible_mappings:
                        endpoints = possible_mappings[mapping_path]
                        break
            if endpoints is None and edge_path.startswith("AssociationLinkMapping: "):
                link_parts = edge_path.removeprefix("AssociationLinkMapping: ").split("/")
                if len(link_parts) >= 2:
                    endpoints = link_parts[0], link_parts[1]
            if endpoints is None:
                continue
            source_path, target_path = endpoints
            if source_path not in positions or target_path not in positions:
                continue
            source_port, target_port, route_points = self._route_between_boxes(
                source_path, target_path, positions, dimensions, edge_number,
            )
            source_attribute = "sourcePort" if "sourcePort" in edge.attrib else "source_port"
            target_attribute = "targetPort" if "targetPort" in edge.attrib else "target_port"
            edge.set(source_attribute, source_port)
            edge.set(target_attribute, target_port)
            if intermediate_points is None:
                intermediate_points = ElementTree.Element("IntermediatePoints")
                edge.insert(0, intermediate_points)
            for point_x, point_y in route_points:
                ElementTree.SubElement(
                    intermediate_points,
                    "IntermediatePoint",
                    xCoordinate=str(round(point_x, 2)),
                    yCoordinate=str(round(point_y, 2)),
                )

    @classmethod
    def _route_between_boxes(cls, source_path, target_path, positions, dimensions, edge_number):
        """
        Chooses the shortest orthogonal route that does not cross another box.

        An outer detour remains available when every shorter candidate is
        blocked by an unusually crowded set of diagram rows.
        """
        source_position, target_position = positions[source_path], positions[target_path]
        source_size, target_size = dimensions[source_path], dimensions[target_path]
        source_center = cls._box_center(source_position, source_size)
        target_center = cls._box_center(target_position, target_size)
        all_boxes = [
            (path, position[0], position[1], dimensions[path][0], dimensions[path][1])
            for path, position in positions.items()
        ]
        lane_offset = 70 + (edge_number % 12) * 14
        minimum_x = min(box[1] for box in all_boxes) - lane_offset
        maximum_x = max(box[1] + box[3] for box in all_boxes) + lane_offset
        minimum_y = min(box[2] for box in all_boxes) - lane_offset
        maximum_y = max(box[2] + box[4] for box in all_boxes) + lane_offset

        candidates = []

        def add_candidate(source_port, target_port, bend_points):
            """Keeps a candidate when none of its segments enters another class block."""
            start = cls._box_port_point(source_position, source_size, source_port)
            end = cls._box_port_point(target_position, target_size, target_port)
            complete_route = [start, *bend_points, end]
            if cls._route_crosses_box(complete_route, all_boxes, {source_path, target_path}):
                return
            length = sum(
                abs(second[0] - first[0]) + abs(second[1] - first[1])
                for first, second in zip(complete_route, complete_route[1:])
            )
            candidates.append((length + len(bend_points) * 30, source_port, target_port, bend_points))

        middle_x = (source_center[0] + target_center[0]) / 2
        middle_y = (source_center[1] + target_center[1]) / 2
        horizontal_ports = ("EAST", "WEST") if target_center[0] >= source_center[0] else ("WEST", "EAST")
        vertical_ports = ("SOUTH", "NORTH") if target_center[1] >= source_center[1] else ("NORTH", "SOUTH")
        add_candidate(*horizontal_ports, [(middle_x, source_center[1]), (middle_x, target_center[1])])
        add_candidate(*vertical_ports, [(source_center[0], middle_y), (target_center[0], middle_y)])
        add_candidate("WEST", "WEST", [(minimum_x, source_center[1]), (minimum_x, target_center[1])])
        add_candidate("EAST", "EAST", [(maximum_x, source_center[1]), (maximum_x, target_center[1])])
        add_candidate("NORTH", "NORTH", [(source_center[0], minimum_y), (target_center[0], minimum_y)])
        add_candidate("SOUTH", "SOUTH", [(source_center[0], maximum_y), (target_center[0], maximum_y)])
        local_clearance = 35 + (edge_number % 8) * 8
        source_top_lane = source_position[1] - local_clearance
        target_top_lane = target_position[1] - local_clearance
        add_candidate(
            "NORTH",
            "NORTH",
            [
                (source_center[0], source_top_lane),
                (minimum_x, source_top_lane),
                (minimum_x, target_top_lane),
                (target_center[0], target_top_lane),
            ],
        )
        source_bottom_lane = source_position[1] + source_size[1] + local_clearance
        target_bottom_lane = target_position[1] + target_size[1] + local_clearance
        add_candidate(
            "SOUTH",
            "SOUTH",
            [
                (source_center[0], source_bottom_lane),
                (maximum_x, source_bottom_lane),
                (maximum_x, target_bottom_lane),
                (target_center[0], target_bottom_lane),
            ],
        )

        if candidates:
            _, source_port, target_port, points = min(candidates, key=lambda candidate: candidate[0])
            return source_port, target_port, cls._remove_redundant_route_points(points)
        fallback_points = [
            (source_center[0], source_top_lane),
            (minimum_x, source_top_lane),
            (minimum_x, target_top_lane),
            (target_center[0], target_top_lane),
        ]
        return "NORTH", "NORTH", cls._remove_redundant_route_points(fallback_points)

    @staticmethod
    def _box_center(position, size):
        """Returns the center coordinate of one positioned class block."""
        return position[0] + size[0] / 2, position[1] + size[1] / 2

    @staticmethod
    def _box_port_point(position, size, port):
        """Returns the coordinate where a connection leaves a class block."""
        center_x, center_y = FmmlxModel._box_center(position, size)
        return {
            "NORTH": (center_x, position[1]),
            "SOUTH": (center_x, position[1] + size[1]),
            "WEST": (position[0], center_y),
            "EAST": (position[0] + size[0], center_y),
        }[port]

    @staticmethod
    def _route_crosses_box(route, boxes, endpoint_paths):
        """Reports whether an orthogonal route enters a class other than its endpoints."""
        clearance = 20
        for first, second in zip(route, route[1:]):
            for path, box_x, box_y, box_width, box_height in boxes:
                if path in endpoint_paths:
                    continue
                left, right = box_x - clearance, box_x + box_width + clearance
                top, bottom = box_y - clearance, box_y + box_height + clearance
                if first[0] == second[0]:
                    low_y, high_y = sorted((first[1], second[1]))
                    if left <= first[0] <= right and low_y <= bottom and high_y >= top:
                        return True
                elif first[1] == second[1]:
                    low_x, high_x = sorted((first[0], second[0]))
                    if top <= first[1] <= bottom and low_x <= right and high_x >= left:
                        return True
        return False

    @staticmethod
    def _remove_redundant_route_points(points):
        """Removes repeated bend points so XModeler receives a compact route."""
        compact_points = []
        for point in points:
            if not compact_points or point != compact_points[-1]:
                compact_points.append(point)
        return compact_points

    def _parse_xml(self, doc_file_path: str):
        document = None
        try:
            document = parse(doc_file_path)
        except FileNotFoundError:
            raise FileNotFoundError(f"File '{doc_file_path}' was not found!")
        except:
            raise Exception(f"File '{doc_file_path}' could not be parsed!")

        self.parsed_xml = document
        self.extract_mlm_from_xml()

    @classmethod
    def input_xml_path(cls):
        print("BEGIN MLM EXTRACTION\nEnter the MLM Source Location:")
        loc = input()
        return cls(file_path=loc)

    def import_xml(self, xml_file_path: str):
        """Loads XML into an empty model and reports completion when requested."""
        assert self.parsed_xml is None, ("Multi-level model is already imported! "
                                         "Overriding of existing model is forbidden.")
        self._parse_xml(xml_file_path)
        if self.print_progress:
            print("Extraction completed successfully!")

    def extract_mlm_from_xml(self):
        """Reads the semantic model and keeps its complete diagram section."""
        self.xml_root_attributes = {
            attribute_name: self.parsed_xml.documentElement.getAttribute(attribute_name)
            for attribute_name in self.parsed_xml.documentElement.attributes.keys()
        }
        import_nodes = self.parsed_xml.getElementsByTagName("Imports")
        if import_nodes:
            self.imports_xml = ElementTree.fromstring(import_nodes[0].toxml())
        self.path_name = self.retrieve_path_name()
        self.model_name = self.path_name.split("::")[-1]
        if self.print_progress:
            print("BEGIN MLM EXTRACTION")
        self.mlm_objects = self.retrieve_all_mlm_objects()
        self.set_instances_of_mlm_objects()
        if self.print_progress:
            print("ALL OBJECTS RETRIEVED")
        self._set_generalizations()
        if self.print_progress:
            print("ALL GENERALIZATIONS RETRIEVED")
        self.enums = self.retrieve_all_enums()
        if self.print_progress:
            print("ALL ENUMS RETRIEVED")
        self.retrieve_all_attributes()
        if self.print_progress:
            print("ALL ATTRIBUTES RETRIEVED")
        self.retrieve_all_slots()
        if self.print_progress:
            print("ALL SLOTS RETRIEVED")
        self.retrieve_all_operations()
        self.retrieve_all_constraints()
        self.retrieve_all_associations()
        self.retrieve_all_links()
        self.add_association_ends()
        self.add_slot_links()

        diagram_nodes = self.parsed_xml.getElementsByTagName("Diagrams")
        if diagram_nodes:
            self.diagram_xml = ElementTree.fromstring(diagram_nodes[0].toxml())

    def add_association_ends(self):
        """For every association, this operation adds the respective association ends. It must be executed after
        the associations and links have been retrieved"""
        if len(self.associations) > 0:
            for assoc in self.associations:
                src_assoc_end: FmmlxAssociationEnd = FmmlxAssociationEnd(assoc.get_source_access_name(),
                                                                         assoc.get_target_object().full_name,
                                                                         assoc.get_source_inst_level(),
                                                                         assoc, True)
                tgt_assoc_end: FmmlxAssociationEnd = FmmlxAssociationEnd(assoc.get_target_access_name(),
                                                                         assoc.get_source_object().full_name,
                                                                         assoc.get_target_inst_level(),
                                                                         assoc, False)
                assoc.get_source_object().add_attr(src_assoc_end)
                assoc.set_source_association_end(src_assoc_end)
                assoc.get_target_object().add_attr(tgt_assoc_end)
                assoc.set_target_association_end(tgt_assoc_end)

    def add_slot_links(self):
        """This operation adds slots for each link the attribute of each is an association end"""
        for link in self.links:
            src_slot_link: FmmlxSlotLink = FmmlxSlotLink(link.get_association().get_source_access_name(),
                                                         link.get_target_object().full_name, link, True)
            tgt_slot_link: FmmlxSlotLink = FmmlxSlotLink(link.get_association().get_target_access_name(),
                                                         link.get_source_object().full_name, link, False)
            link.get_source_object().add_slot(src_slot_link)
            link.get_target_object().add_slot(tgt_slot_link)

    def retrieve_path_name(self) -> str:
        """
        Returns the model path from current and older XModeler XML files.

        Version 4 stores the path on the root element. Version 3 stores it as
        the name of the first Project element, so both locations are checked.
        """
        root_path = self.parsed_xml.documentElement.getAttribute("path")
        if root_path:
            return root_path

        project_nodes = self.parsed_xml.getElementsByTagName("Project")
        if project_nodes and project_nodes[0].getAttribute("name"):
            return project_nodes[0].getAttribute("name")
        raise ValueError("The XML file does not contain an XModeler project path.")

    def retrieve_all_mlm_objects(self) -> List[FmmlxObject]:
        """
        This operation retrieves all MLM objects/classes. First all highest-level classes are retrieved via the
        function `_retrieve_all_mlm_metaclass_objects.` This is important since they have a separate XML tag.
        Afterward, the remaining MLM objects are retrieved.
        """
        mlm_objects = self._retrieve_metaclass_objects()
        for instance_object in self._retrieve_instance_objects():
            declared_level = instance_object.level
            instance_object.set_class_of_object(self._get_class_of_mlm_object(instance_object.class_of_object.full_name,
                                                                              mlm_objects))
            instance_object.level = declared_level
            if self.print_progress:
                print(f"Object {instance_object.name} extracted.")
            mlm_objects.append(instance_object)
        return mlm_objects

    def _retrieve_metaclass_objects(self) -> List[FmmlxObject]:
        mlm_objects = []
        for object_element in self.parsed_xml.getElementsByTagName("addMetaClass"):
            mlm_object_long = object_element.getAttribute("package") + "::" + object_element.getAttribute("name")
            mlm_object = FmmlxObject(mlm_object_long, object_element.getAttribute("name"),
                                     object_element.getAttribute("level"), metaClass,
                                     object_element.getAttribute("abstract"), self)
            mlm_objects.append(mlm_object)

        return mlm_objects

    def _retrieve_instance_objects(self) -> List[FmmlxObject]:
        mlm_objects = []
        for object_element in self.parsed_xml.getElementsByTagName("addInstance"):
            mlm_object_long = object_element.getAttribute("package") + "::" + object_element.getAttribute("name")
            declared_level = object_element.getAttribute("level") or "99"
            mlm_object = FmmlxObject(mlm_object_long, object_element.getAttribute("name"), declared_level,
                                     FmmlxObject(object_element.getAttribute("of"),
                                             "", "99", None, "false", self),
                                     object_element.getAttribute("abstract"), self)
            mlm_objects.append(mlm_object)

        return mlm_objects

    def _get_class_of_mlm_object(self, full_object_name: str, mlm_instance_objects: List[FmmlxObject]) -> FmmlxObject:
        for object_elem in mlm_instance_objects:
            if object_elem.full_name == full_object_name:
                return object_elem

    def _set_generalizations(self):
        for parent_element in self.parsed_xml.getElementsByTagName("changeParent"):
            child_class: FmmlxObject = self.get_mlm_object_by_fullname(parent_element.getAttribute("class"))
            for parent_class_name in parent_element.getAttribute("new").split(","):
                child_class.add_parent_class(self.get_mlm_object_by_fullname(parent_class_name))

    def retrieve_all_enums(self):
        enums_tmp: List[FmmlxEnumType] = []
        for enum_element in self.parsed_xml.getElementsByTagName("addEnumeration"):
            enums_tmp.append(FmmlxEnumType(enum_element.getAttribute("name")))
        for enum_value_element in self.parsed_xml.getElementsByTagName("addEnumerationValue"):
            for enum_tmp in enums_tmp:
                if enum_value_element.getAttribute("enum_name") == enum_tmp.name:
                    enum_tmp.add_enum_value(enum_value_element.getAttribute("enum_value_name"))
        return enums_tmp

    def retrieve_all_attributes(self):
        for attribute_element in self.parsed_xml.getElementsByTagName("addAttribute"):
            new_attr = FmmlxAttribute(attribute_element.getAttribute("name"), attribute_element.getAttribute("type"),
                                      attribute_element.getAttribute("level"),
                                      multiplicity=self._parse_attribute_multiplicity(
                                          attribute_element.getAttribute("multiplicity")))
            # need to look for custom attr data types: enums or custom class types
            if new_attr.attr_type.split("::")[1] != "XCore" and new_attr.attr_type.split("::")[1] != "Auxiliary":
                if not self._is_custom_attribute_type_an_enum(new_attr):
                    print("TO-DO: Custom Data Type " + new_attr.attr_type_short + " Detected") #TODO CUSTOM CLASS AS OBJECT
            owner_object = self._find_object_named_in_xml(attribute_element.getAttribute("class"))
            if owner_object is not None:
                owner_object.add_attr(new_attr)
                new_attr.set_owner(owner_object)

    @staticmethod
    def _parse_attribute_multiplicity(multiplicity_value: str):
        """Read an XModeler ``Seq`` multiplicity used by an attribute."""
        if not multiplicity_value:
            return None
        match = re.search(r"Seq\{\s*(-?\d+)\s*,\s*(-?\d+)\s*,\s*(true|false)",
                          multiplicity_value, re.IGNORECASE)
        if match is None:
            return None
        lower_bound = int(match.group(1))
        upper_bound = int(match.group(2))
        is_unbounded = match.group(3).lower() == "true"
        return Multiplicity(lower_bound, upper_bound, is_unbounded=is_unbounded)

    def _find_object_named_in_xml(self, xml_object_name: str):
        # XML files sometimes use the full model path and sometimes only the final class name.
        # This finds the same class in both cases.
        for mlm_object in self.mlm_objects:
            if xml_object_name == mlm_object.full_name:
                return mlm_object
        short_name = xml_object_name.split("::")[-1]
        matching_objects = [
            mlm_object
            for mlm_object in self.mlm_objects
            if short_name == mlm_object.name
        ]
        if len(matching_objects) == 1:
            return matching_objects[0]
        return None

    def _is_custom_attribute_type_an_enum(self, mlm_attr: FmmlxAttribute) -> bool:
        # check 1: look if in list of enums
        for enum in self.enums:
            if enum.name == mlm_attr.attr_type_short:
                mlm_attr.set_enum_type(enum)
                return True
        return False

    def retrieve_all_slots(self):
        """Reads slot values while retaining their original XML expressions."""
        for slot_element in self.parsed_xml.getElementsByTagName("changeSlotValue"):
            xml_value = slot_element.getAttribute("valueToBeParsed")
            new_slot = FmmlxSlot(slot_element.getAttribute("slotName"),
                                 self._parse_slot_value(xml_value), xml_value=xml_value)
            owner_object = self._find_object_named_in_xml(slot_element.getAttribute("class"))
            if owner_object is not None:
                owner_object.add_slot(new_slot)
                new_slot.set_owner_object(owner_object)
                new_slot.set_attribute()

    def _parse_slot_value(self, slot_value: str):
        if slot_value.endswith("asString()"):
            sign_list = slot_value[1:].split("]")[0].split(",")
            slot_value = ""
            if sign_list[0] != "":
                for sign_code in sign_list:
                    slot_value += chr(int(sign_code))
        return slot_value

    def retrieve_all_operations(self):
        for operations_element in self.parsed_xml.getElementsByTagName("addOperation"):
            new_operation = FmmlxOperation(operations_element.getAttribute("name"),
                                           operations_element.getAttribute("level"),
                                           operations_element.getAttribute("type"))
            new_operation.xml_attributes = {
                attribute_name: operations_element.getAttribute(attribute_name)
                for attribute_name in operations_element.attributes.keys()
            }

            for mlm_object in self.mlm_objects:
                if operations_element.getAttribute("class") == mlm_object.full_name:
                    mlm_object.add_operation(new_operation)

    def retrieve_all_constraints(self):
        for constraint_element in self.parsed_xml.getElementsByTagName("addConstraint"):
            new_constraint = FmmlxConstraint(constraint_element.getAttribute("constName"),
                                             constraint_element.getAttribute("instLevel"))
            new_constraint.xml_attributes = {
                attribute_name: constraint_element.getAttribute(attribute_name)
                for attribute_name in constraint_element.attributes.keys()
            }
            for mlm_object in self.mlm_objects:
                if constraint_element.getAttribute("class") == mlm_object.full_name:
                    mlm_object.add_constraint(new_constraint)

    def retrieve_all_associations(self):
        for association_element in self.parsed_xml.getElementsByTagName("addAssociation"):
            new_association = FmmlxAssociation(association_element.getAttribute("fwName"),
                                               association_element.getAttribute("instLevelSource"),
                                               association_element.getAttribute("instLevelTarget"),
                                               association_element.getAttribute("accessTargetFromSourceName"),
                                               association_element.getAttribute("accessSourceFromTargetName"))
            new_association.xml_attributes = {
                attribute_name: association_element.getAttribute(attribute_name)
                for attribute_name in association_element.attributes.keys()
            }
            tgt_mult = association_element.getAttribute("multSourceToTarget")[4:-1].split(",")
            src_mult = association_element.getAttribute("multTargetToSource")[4:-1].split(",")
            new_association.set_source_multiplicity(int(src_mult[0]), int(src_mult[1]))
            new_association.set_target_multiplicity(int(tgt_mult[0]), int(tgt_mult[1]))
            for mlm_object in self.mlm_objects:
                if association_element.getAttribute("classSource") == mlm_object.full_name:
                    new_association.set_source_object(mlm_object)
                if association_element.getAttribute("classTarget") == mlm_object.full_name:
                    new_association.set_target_object(mlm_object)
            self.associations.append(new_association)

    def retrieve_all_links(self):
        """
        Reads links and connects each one to the association named in the XML.

        Some older files use the association's forward name while other files
        use an access name. The forward name is preferred because it is the
        direct and unambiguous reference used by the example models.
        """
        for link_element in self.parsed_xml.getElementsByTagName("addLink"):
            new_link: FmmlxLink = FmmlxLink(link_element.getAttribute("name"))
            for mlm_object in self.mlm_objects:
                if link_element.getAttribute("classSource") == mlm_object.full_name:
                    new_link.set_source_object(mlm_object)
                if link_element.getAttribute("classTarget") == mlm_object.full_name:
                    new_link.set_target_object(mlm_object)
            matching_associations = [
                association for association in self.associations
                if association.name == link_element.getAttribute("name")
            ]
            if len(matching_associations) != 1:
                matching_associations = [
                    association for association in self.associations
                    if association.get_source_access_name() == link_element.getAttribute("name")
                ]
            if len(matching_associations) == 1:
                new_link.set_association(matching_associations[0])
            self.links.append(new_link)

    def get_mlm_object_by_fullname(self, full_name: str) -> FmmlxObject:
        for mlm_object in self.mlm_objects:
            if mlm_object.full_name == full_name:
                return mlm_object
        raise Exception(f"No matching MLM object ({full_name}) found!")

    def get_mlm_object_by_shortname(self, short_name: str) -> FmmlxObject:
        full_name = f"{self.path_name}::{short_name}"
        for mlm_object in self.mlm_objects:
            if mlm_object.full_name == full_name:
                return mlm_object
        raise Exception(f"No matching MLM object ({full_name}) found!")

    def get_all_objects_for_class(self, search_class: FmmlxObject) -> List[FmmlxObject]:
        instances_for_class:List[FmmlxObject] = []
        for mlm_object in self.mlm_objects:
            if mlm_object.class_of_object == search_class:
                instances_for_class.append(mlm_object)
        return instances_for_class

    def perform_change_operations_for_precedence_analysis(self, fm_object: FmmlxObject):
        assert fm_object.level == 1, "Change operations performed on L1 classes only"
        assert fm_object.attribute_precedence_graph is not None, ("Precedence graph not detected, "
                                                                  "precedence analysis must be performed first")
        flat_class: FmmlxObject = self.get_mlm_object_by_fullname(fm_object.full_name)
        max_inst_level: int = flat_class.get_attribute_precedence_graph().get_max_level()
        flat_class.promote_to_level_x(max_inst_level + 1)
        flat_class.promote_attributes()
        while max_inst_level > 0:
            attrs_at_inst_level: [FmmlxAttribute] = flat_class.get_attributes_at_inst_level_x(max_inst_level)
            print(attrs_at_inst_level[0].get_slots_for_unique_values())
            for unique_value_slot in attrs_at_inst_level[0].get_slots_for_unique_values():
                new_instance: FmmlxObject = FmmlxObject(flat_class.full_name, unique_value_slot.get_value().upper(),
                                                        str(max_inst_level),flat_class, "false", self)
                self.mlm_objects.append(new_instance)
            print(max_inst_level)
            max_inst_level -= max_inst_level

    def get_assoc_classification_indicators(self) -> List[FmmlxAssociation]:
        indicating_associations: List[FmmlxAssociation] = []
        for mlm_assoc in self.associations:
            if mlm_assoc.is_classification_indicator():
                indicating_associations.append(mlm_assoc)
        return indicating_associations

    def __repr__(self):
        print(f"Multilevel Model <{self.model_name}>")
        print(*self.enums, sep="Syntax Error at line: 38")#lmao opfer
        print("\n--------------------------------------------------------------\n")
        print(*self.mlm_objects, sep="----------------------------------------------\n")
        print("\n--------------------------------------------------------------\n")
        print(*self.associations, sep="\n---\n")
        print("\n--------------------------------------------------------------\n")
        print(*self.links, sep="\n---\n")
        return ""

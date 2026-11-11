import copy
import xml.etree.ElementTree as ElementTree

from src.basemlm.basemlm_predefined_type import *
from basemlm.basemlm_type_spec import TypeSpec
from basemlm.model_element import ModelElement
from src.basemlm import xml_export as export_xml

from typing import List, Optional
import math
import networkx as nx

from src.basemlm.basemlm_association import BaseMlmAssociation
from src.basemlm.basemlm_assoc_end import BaseMlmAssocEnd
from src.basemlm.basemlm_attribute import BaseMlmAttribute
from src.basemlm.basemlm_enum_type import BaseMlmEnumType
from src.basemlm.basemlm_link import BaseMlmLink
from src.basemlm.basemlm_object import BaseMlmObject
from src.basemlm.basemlm_slot_link import BaseMlmSlotLink

metaClass = BaseMlmObject("MetaClass",
                          "MetaClass", "99",
                          None, "false",
                          None)


class BaseMlmModel:
    """
    This class serves to represent complete MultiLevelModels. The package src.importers reads files into a model,
    and this class exports the model to XML documents again once processed as intended.
    All elements within a multi-level model are themselves instances of
    Python classes specified in the package src.basemlm
    """

    def __init__(self, file_path: str = "", print_progress: bool = False,
                 selected_csv_columns: Optional[List[str]] = None):
        """
        Creates an empty model and optionally imports a file with the importer for its file ending.

        XModeler version details, imported type references, and diagram data
        are retained so a later export can reproduce the source information.
        """
        self.path_name = ""
        self.mlm_objects: List[BaseMlmObject] = []
        self.enums: List[BaseMlmEnumType] = []
        self.associations: List[BaseMlmAssociation] = []
        self.links: List[BaseMlmLink] = []
        self.diagram_xml = None
        self.imports_xml = None
        self.xml_root_attributes = {}
        self.model_name: str = ""
        self.print_progress = print_progress
        if file_path != "":
            self._import_file(file_path, selected_csv_columns)

    def _import_file(self, file_path: str, selected_csv_columns: Optional[List[str]] = None) -> None:
        """Fills this model with the importer for the file. The import report is not kept."""
        from src.importers.model_importer import importer_for

        importer = importer_for(file_path)
        if selected_csv_columns is not None:
            importer.select_columns(selected_csv_columns)
        importer.import_into(self, file_path)

    def get_model_name(self):
        return self.model_name

    def validate_basemlm_integrity(self):
        """Return all implemented BaseMLM integrity violations for this model."""
        from src.basemlm.integrity import BaseMlmValidator

        return BaseMlmValidator(self).validate()

    def add_mlm_object(self, mlm_object: BaseMlmObject) -> None:
        """Retain an imported class or instance so later references can resolve to the same object."""
        self.mlm_objects.append(mlm_object)

    def add_enum(self, enum: BaseMlmEnumType) -> None:
        """Retain an enumeration so attribute types and slot literals can be resolved."""
        self.enums.append(enum)

    def add_association(self, association: BaseMlmAssociation) -> None:
        """Retain a resolved association so links and association ends can refer to it."""
        self.associations.append(association)

    def add_link(self, link: BaseMlmLink) -> None:
        """Retain an instance relationship so the model can derive its slot links."""
        self.links.append(link)

    def set_path_name(self, path_name: str) -> None:
        """Set the full path of the model, for example Root::Cruise."""
        self.path_name = path_name

    def set_model_name(self, model_name: str) -> None:
        """Keep the display name supplied by the source independently of its qualified model path."""
        self.model_name = model_name

    def set_xml_metadata(self, root_attributes: dict, imports_xml: Optional[ElementTree.Element],
                         diagram_xml: Optional[ElementTree.Element]) -> None:
        """Keeps the parts of an imported XML document that the export writes again."""
        self.xml_root_attributes = root_attributes
        self.imports_xml = imports_xml
        self.diagram_xml = diagram_xml

    def set_instances_of_mlm_objects(self):
        mlm_classes: List[BaseMlmObject] = []
        for mlm_object in self.mlm_objects:
            if mlm_object.level > 0:
                mlm_classes.append(mlm_object)
        for mlm_class in mlm_classes:
            objects_beneath: List[BaseMlmObject] = self.get_all_objects_at_level_x(mlm_class.level - 1)
            for object_beneath in objects_beneath:
                if object_beneath.class_of_object == mlm_class:
                    mlm_class.add_instance(object_beneath)

    def get_all_objects_at_level_x(self, level: int) -> List[BaseMlmObject]:
        objects_at_level_x: List[BaseMlmObject] = []
        for obj in self.mlm_objects:
            if obj.level == level:
                objects_at_level_x.append(obj)
        return objects_at_level_x

    def get_all_flat_classes(self) -> List[BaseMlmObject]:
        return self.get_all_objects_at_level_x(1)

    def get_all_pure_objects(self) -> List[BaseMlmObject]:
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

        # Return the XML root so callers can inspect the exported document.
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

    def _objects_for_export(self, max_instances_per_class: Optional[int]) -> List[BaseMlmObject]:
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
                                 exported_objects: List[BaseMlmObject], diagram_mode: str):
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

    def _diagram_layout_by_level(self, exported_objects: List[BaseMlmObject], project_name: str):
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
    def _estimate_diagram_box_size(mlm_object: BaseMlmObject):
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
            f"{attribute.name}: {attribute.attr_type_str_short} [{attribute.inst_level}]"
            for attribute in direct_attributes
        )
        inherited_attributes, inherited_operations = BaseMlmModel._inherited_diagram_members(mlm_object)
        visible_lines.extend(
            f"{attribute.name}: {attribute.attr_type_str_short} [{attribute.inst_level}] (from {owner_name})"
            for attribute, owner_name in inherited_attributes
        )
        slot_values = {
            slot.name: slot.get_value_as_text()
            for slot in mlm_object.slot_list
            if slot.slot_category != "SLOT-LINK"
        }
        classification_attributes, classification_operations = (
            BaseMlmModel._classification_diagram_members(mlm_object)
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
        visible_lines.extend(BaseMlmModel._operation_diagram_text(operation) for operation in mlm_object.operations_list)
        visible_lines.extend(
            f"{BaseMlmModel._operation_diagram_text(operation)} (from {owner_name})"
            for operation, owner_name in inherited_operations
        )
        visible_lines.extend(
            BaseMlmModel._operation_diagram_text(operation)
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
    def _classification_diagram_members(mlm_object: BaseMlmObject):
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
    def _inherited_diagram_members(mlm_object: BaseMlmObject):
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

    def _diagram_connection_pairs(self, exported_objects: List[BaseMlmObject]):
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

    def _connection_aware_positions(self, exported_objects: List[BaseMlmObject]):
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
        center_x, center_y = BaseMlmModel._box_center(position, size)
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

    @classmethod
    def input_xml_path(cls):
        print("BEGIN MLM EXTRACTION\nEnter the MLM Source Location:")
        loc = input()
        return cls(file_path=loc)

    def import_xml(self, xml_file_path: str) -> None:
        """Loads XML into an empty model and reports completion when requested."""
        if self.path_name != "":
            raise ValueError("Multi-level model is already imported! "
                             "Overriding of existing model is forbidden.")
        self._import_file(xml_file_path)
        if self.print_progress:
            print("Extraction completed successfully!")

    def add_association_ends(self):
        """For every association, this operation adds the respective association ends. It must be executed after
        the associations and links have been retrieved"""
        if len(self.associations) > 0:
            for assoc in self.associations:
                src_assoc_end: BaseMlmAssocEnd = BaseMlmAssocEnd(assoc.get_source_access_name(),
                                                                 assoc.get_target_object().full_name,
                                                                 assoc.get_source_inst_level(),
                                                                 assoc.get_target_object(),
                                                                 assoc, True)
                tgt_assoc_end: BaseMlmAssocEnd = BaseMlmAssocEnd(assoc.get_target_access_name(),
                                                                 assoc.get_source_object().full_name,
                                                                 assoc.get_target_inst_level(),
                                                                 assoc.get_source_object(),
                                                                 assoc, False)
                assoc.get_source_object().add_attr(src_assoc_end)
                assoc.set_source_association_end(src_assoc_end)
                assoc.get_target_object().add_attr(tgt_assoc_end)
                assoc.set_target_association_end(tgt_assoc_end)

    def add_slot_links(self):
        """This operation adds slots for each link the attribute of each is an association end"""
        for link in self.links:
            src_slot_link: BaseMlmSlotLink = BaseMlmSlotLink(link.get_association().get_source_access_name(),
                                                             link.get_target_object().full_name, link, True)
            tgt_slot_link: BaseMlmSlotLink = BaseMlmSlotLink(link.get_association().get_target_access_name(),
                                                             link.get_source_object().full_name, link, False)
            link.get_source_object().add_slot(src_slot_link)
            link.get_target_object().add_slot(tgt_slot_link)

    def parse_attribute_type(self, type_str: str) -> TypeSpec:
        """receives the type as String from the FMMLX XML file and parses it to produce TypeSpec. The type string always
        conforms to the following form: Root::<Model-Name>::<Object-Name>. Accepted predefined Types are specified
        either in XCore or Auxiliary. If no predefined type is detected, the object name must correspond to an enum or
        object of the model"""
        model_of_type: str = type_str.split("::")[1]
        short_name: str = type_str.split("::")[2]

        if model_of_type == "XCore" or model_of_type == "Auxiliary":
            match short_name:
                case "String":
                    return StringType()
                case "Boolean":
                    return BooleanType()
                case "Float":
                    return FloatType()
                case "Integer":
                    return IntegerType()
                case "Date":
                    return DateType()
                case _:
                    return UnknownType()

        else:
            return self.get_object_or_enum_type(short_name)

    def _is_custom_attribute_type_an_enum(self, mlm_attr: BaseMlmAttribute) -> bool:
        # check 1: look if in list of enums
        for enum in self.enums:
            if enum.name == mlm_attr.attr_type_str_short:
                mlm_attr.set_enum_type(enum)
                return True
        return False

    def is_flat(self) -> bool:
        for mlm_object in self.mlm_objects:
            if mlm_object.get_level() > 1:
                return False
        return True

    def get_objects(self) -> List[BaseMlmObject]:
        return self.mlm_objects

    def get_associations(self) -> List[BaseMlmAssociation]:
        return self.associations

    def get_links(self) -> List[BaseMlmLink]:
        return self.links

    def get_object_or_enum_type(self, short_name: str) -> TypeSpec:
        """returns BaseMlmObject or EnumType, used to determine type of an attribute"""
        for obj in self.mlm_objects + self.enums:
            if obj.name == short_name:
                return obj
        raise Exception(f"No matching type found for {short_name}!")

    def get_enum_type(self, enum_name: str) -> BaseMlmEnumType:
        for enum_type in self.enums:
            if enum_type.get_name == enum_name:
                return enum_type
        raise Exception(f"No matching enum type ({enum_name}) found!")

    def only_unique_object_names(self) -> bool:
        all_names = [obj.get_name() for obj in self.get_objects()]
        return len(all_names) == len(set(all_names))

    def valid_associations(self) -> bool:
        for assoc in self.get_associations():
            src_object = assoc.get_source_object()
            tgt_object = assoc.get_target_object()

            src_assoc_ends = src_object.get_assoc_ends()
            tgt_assoc_ends = tgt_object.get_assoc_ends()

            if not any(end.get_association() == assoc and end.get_attr_type() == tgt_object.get_name()
                       for end in src_assoc_ends):
                return False

            if not any(end.get_association == assoc and end.get_attr_type() == src_object.get_name()
                       for end in tgt_assoc_ends):
                return False
        return True

    def valid_links(self) -> bool:
        for link in self.get_links():
            src_object = link.get_source_object()
            tgt_object = link.get_target_object()

            src_slot_links = src_object.get_slot_links()
            tgt_slot_links = tgt_object.get_slot_links()

            if not any(
                    slot_link.get_link() == link
                    and slot_link.get_attr_type() == tgt_object.get_name()
                    for slot_link in src_slot_links
            ):
                return False

            if not any(
                    slot_link.get_link() == link
                    and slot_link.get_attr_type() == src_object.get_name()
                    for slot_link in tgt_slot_links
            ):
                return False

        return True


    def get_mlm_object_by_fullname(self, full_name: str) -> BaseMlmObject:
        for mlm_object in self.mlm_objects:
            if mlm_object.full_name == full_name:
                return mlm_object
        raise Exception(f"No matching MLM object ({full_name}) found!")

    def get_mlm_object_by_shortname(self, short_name: str) -> BaseMlmObject:
        full_name = f"{self.path_name}::{short_name}"
        for mlm_object in self.mlm_objects:
            if mlm_object.full_name == full_name:
                return mlm_object
        raise Exception(f"No matching MLM object ({full_name}) found!")

    def get_enum_types(self) -> List[BaseMlmEnumType]:
        return self.enums

    def get_all_model_elements(self) -> List[ModelElement]:
        """elements include: all connections, objects, enum types, and properties"""
        all_elem: [ModelElement] = self.get_objects() + self.get_associations() + self.get_links() + self.get_enum_types()
        for obj in self.get_objects():
            for prop in obj.get_all_properties():
                all_elem.append(prop)
        return all_elem

    def get_all_objects_for_class(self, search_class: BaseMlmObject) -> List[BaseMlmObject]:
        instances_for_class:List[BaseMlmObject] = []
        for mlm_object in self.mlm_objects:
            if mlm_object.class_of_object == search_class:
                instances_for_class.append(mlm_object)
        return instances_for_class

    def perform_change_operations_for_precedence_analysis(self, fm_object: BaseMlmObject):
        assert fm_object.level == 1, "Change operations performed on L1 classes only"
        assert fm_object.attribute_precedence_graph is not None, ("Precedence graph not detected, "
                                                                  "precedence analysis must be performed first")
        flat_class: BaseMlmObject = self.get_mlm_object_by_fullname(fm_object.full_name)
        max_inst_level: int = flat_class.get_attribute_precedence_graph().get_max_level()
        flat_class.promote_to_level_x(max_inst_level + 1)
        flat_class.promote_attributes()
        while max_inst_level > 0:
            attrs_at_inst_level: [BaseMlmAttribute] = flat_class.get_attributes_at_inst_level_x(max_inst_level)
            for unique_value_slot in attrs_at_inst_level[0].get_slots_for_unique_values():
                new_instance: BaseMlmObject = BaseMlmObject(flat_class.full_name, unique_value_slot.get_value_as_text().upper(),
                                                            str(max_inst_level), flat_class, "false", self)
                self.mlm_objects.append(new_instance)
            max_inst_level -= max_inst_level

    def get_assoc_classification_indicators(self) -> List[BaseMlmAssociation]:
        indicating_associations: List[BaseMlmAssociation] = []
        for mlm_assoc in self.associations:
            if mlm_assoc.is_classification_indicator():
                indicating_associations.append(mlm_assoc)
        return indicating_associations

    def __repr__(self):
        print(f"Multilevel Model <{self.model_name}>")
        print(*self.enums, sep="\n")
        print("\n--------------------------------------------------------------\n")
        print(*self.mlm_objects, sep="----------------------------------------------\n")
        print("\n--------------------------------------------------------------\n")
        print(*self.associations, sep="\n---\n")
        print("\n--------------------------------------------------------------\n")
        print(*self.links, sep="\n---\n")
        return ""

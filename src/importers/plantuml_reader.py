"""Reads the text of a PlantUML class diagram, from a text file or a PNG, into a PlantUmlDiagram."""
import os
import re
import struct
import zlib
from typing import List, Optional, Tuple

from src.importers.plantuml_diagram import (ATTRIBUTE_WITHOUT_TYPE, EXACTLY_ONE, MANY, NOT_UNDERSTOOD, PlantUmlDiagram,
                                            RawRelation, UmlAttribute, UmlClass, UmlEnum, UmlMultiplicity, UmlOperation,
                                            UmlParameter, ZERO_TO_MANY, to_identifier)

PLANTUML_FILE_NAME = "plantuml.txt"
PLANTUML_IMAGE_NAME = "plantuml.png"
DEFAULT_MODEL_NAME = "PlantUmlModel"
DEFAULT_ATTRIBUTE_TYPE = "String"
START_KEYWORD = "@startuml"
END_KEYWORD = "@enduml"
COMMENT_START = "'"
KEYWORD_START = "@"
BODY_END = "}"
ABSTRACT_KEYWORD = "abstract"
ARRAY_SUFFIX = "[]"

PNG_SIGNATURE_LENGTH = 8
PNG_LENGTH_FIELD_SIZE = 4
PNG_TYPE_FIELD_SIZE = 4
PNG_CHECKSUM_FIELD_SIZE = 4
PNG_TEXT_CHUNK_TYPE = b"iTXt"
PNG_TEXT_KEY = b"plantuml"
PNG_COMPRESSED_FLAG = 1

# Recognizes a class line, for example: abstract class Person <<entity>> {
CLASS_PATTERN = re.compile(r'^(abstract\s+class|abstract|class)\s+(\w+)\s*(<<[^>]*>>)?\s*(\{)?\s*(\})?$')
# Recognizes an enum line, for example: enum Color {
ENUM_PATTERN = re.compile(r'^enum\s+(\w+)\s*(<<[^>]*>>)?\s*(\{)?\s*(\})?$')
# Recognizes an operation, for example: int add(int a, int b) or add(a : int) : int
OPERATION_PATTERN = re.compile(r'^(?:(\w+)\s+)?(\w+)\s*\(([^)]*)\)\s*(?::\s*(\w+))?$')
# Recognizes a relation line, for example: Car "1" *-- "0..*" Wheel : has
RELATION_PATTERN = re.compile(
    r'^(\w+)\s*(?:"([^"]*)")?\s*((?:<\||<|\*|o)?(?:-+|\.+)(?:\|>|>|\*|o)?)\s*(?:"([^"]*)")?\s*(\w+)\s*(?::\s*(.+))?$')
# Recognizes an association class, for example: (Flight, Passenger) .. Ticket
ASSOCIATION_CLASS_PATTERN = re.compile(r'^\(\s*(\w+)\s*,\s*(\w+)\s*\)\s*\.+\s*(\w+)$')
# Recognizes an association class written the other way round, for example: Ticket .. (Flight, Passenger)
ASSOCIATION_CLASS_REVERSED_PATTERN = re.compile(r'^(\w+)\s*\.+\s*\(\s*(\w+)\s*,\s*(\w+)\s*\)$')
# Recognizes a note with an alias, for example: note "{XOR}" as N1
NOTE_PATTERN = re.compile(r'^note\s+"([^"]*)"\s+as\s+(\w+)$')
# Recognizes an n-ary diamond, for example: <> Exam
DIAMOND_PATTERN = re.compile(r'^<>\s+(\w+)$')
# Recognizes multiplicity syntax, for example: 1 or 0..*. Bounds are checked separately.
MULTIPLICITY_PATTERN = re.compile(r'^(\d+|\*)(?:\.\.(\d+|\*))?$')
# Recognizes an extra in curly brackets, for example: {static}
CURLY_EXTRA_PATTERN = re.compile(r"\{[^}]*\}")
# Recognizes the word const, for example in: const int size
CONST_PATTERN = re.compile(r"\bconst\b")


def parse_multiplicity(text: str) -> Optional[UmlMultiplicity]:
    """Read numeric lower bounds and optional upper bounds; reject reversed ranges and star lower bounds."""
    match = MULTIPLICITY_PATTERN.match(text.strip())
    if match is None:
        return None
    lower_text = match.group(1)
    upper_text = match.group(2)
    if upper_text is None:
        upper_text = lower_text
    if lower_text == "*":
        return None
    lower = int(lower_text)
    if upper_text == "*":
        upper = MANY
    else:
        upper = int(upper_text)
    if upper != MANY and lower > upper:
        return None
    return UmlMultiplicity(lower, upper)


class PlantUmlReader:
    """Reads one PlantUML file.

    The text comes from the file. An empty plantuml.txt takes it from the plantuml.png in the same
    folder, because PlantUML stores the source of a diagram in that image. The reader only collects
    what is written in the text. The PlantUmlNormalizer rewrites it afterwards.

    Reading starts with source text, then dispatches body and top-level lines. Helpers follow
    their first caller, so the supported syntax can be read along the parsing flow.
    """

    def __init__(self, path: str) -> None:
        """Prepare reading the file. The current class or enum is the one whose body is being read."""
        self._path = path
        self._diagram = PlantUmlDiagram(self.get_model_name(path))
        self._current_class: Optional[UmlClass] = None
        self._current_enum: Optional[UmlEnum] = None

    @staticmethod
    def get_model_name(path: str) -> str:
        """Return the name of the model: the folder for a plantuml.txt, otherwise the file name."""
        folder, file_name = os.path.split(os.path.abspath(path))
        if file_name.lower() == PLANTUML_FILE_NAME:
            name = os.path.basename(folder)
        else:
            name = os.path.splitext(file_name)[0]
        model_name = to_identifier(name)
        if model_name == "":
            return DEFAULT_MODEL_NAME
        return model_name

    def read_diagram(self) -> PlantUmlDiagram:
        """Read the text up to @enduml line by line and return the collected diagram.

        Empty lines, comments such as ' a comment, and lines such as @startuml are skipped.
        """
        for raw_line in self.read_text().splitlines():
            line = raw_line.strip()
            if line.lower().startswith(END_KEYWORD):
                break
            if line == "" or line.startswith(COMMENT_START) or line.startswith(KEYWORD_START):
                continue
            if self._current_class is not None or self._current_enum is not None:
                self._read_body_line(line)
            else:
                self._read_top_level_line(line)
        return self._diagram

    def read_text(self) -> str:
        """Return the PlantUML text of the file. An empty file without an image has an empty text."""
        text = self._read_text_file(self._path)
        if text.strip() != "":
            return text
        image_text = self._read_neighbor_image(self._path)
        if image_text is None or image_text == "":
            return text
        return image_text

    @staticmethod
    def _read_text_file(path: str) -> str:
        """Read a text file. Characters that are not valid UTF-8 do not stop the import."""
        with open(path, "r", encoding="utf-8-sig", errors="replace") as file:
            return file.read()

    @classmethod
    def _read_neighbor_image(cls, path: str) -> Optional[str]:
        """Return the text of the plantuml.png next to an empty plantuml.txt, if there is one."""
        folder, file_name = os.path.split(os.path.abspath(path))
        if file_name.lower() != PLANTUML_FILE_NAME:
            return None
        image_path = os.path.join(folder, PLANTUML_IMAGE_NAME)
        if not os.path.isfile(image_path):
            return None
        return cls._read_image_text(image_path)

    @classmethod
    def _read_image_text(cls, image_path: str) -> Optional[str]:
        """Return the PlantUML source from a PNG file, or None if the image holds no readable source.

        A PNG file is a list of chunks. Each chunk has a length, a type, its data and a checksum.
        """
        with open(image_path, "rb") as file:
            data = file.read()
        header_size = PNG_LENGTH_FIELD_SIZE + PNG_TYPE_FIELD_SIZE
        position = PNG_SIGNATURE_LENGTH
        try:
            while position + header_size <= len(data):
                length = struct.unpack(">I", data[position:position + PNG_LENGTH_FIELD_SIZE])[0]
                chunk_type = data[position + PNG_LENGTH_FIELD_SIZE:position + header_size]
                chunk = data[position + header_size:position + header_size + length]
                position += header_size + length + PNG_CHECKSUM_FIELD_SIZE
                if chunk_type == PNG_TEXT_CHUNK_TYPE:
                    key, _, rest = chunk.partition(b"\0")
                    if key == PNG_TEXT_KEY:
                        return cls._decode_image_text(rest)
        except (IndexError, struct.error, zlib.error):
            return None
        return None

    @staticmethod
    def _decode_image_text(chunk_rest: bytes) -> str:
        """Return the text of an iTXt chunk after its key: a flag, a method, two short texts, the content."""
        is_compressed = chunk_rest[0] == PNG_COMPRESSED_FLAG
        content = chunk_rest[2:].split(b"\0", 2)[2]
        if is_compressed:
            content = zlib.decompress(content)
        return content.decode("utf-8", "replace")

    def _read_body_line(self, line: str) -> None:
        """Read a line in the body of a class or enum: the closing }, a literal, an operation or an attribute.

        An enum line such as RED becomes an addEnumerationValue element in the XML.
        """
        if line == BODY_END:
            self._current_class = None
            self._current_enum = None
        elif self._current_enum is not None:
            self._current_enum.add_literal(line)
        else:
            line = line.lstrip("+-#~").strip()
            if "(" in line:
                self._read_operation(line)
            else:
                self._read_attribute(line)

    def _read_operation(self, line: str) -> None:
        """Recognize an operation, written int add(int a, int b) or add(a : int) : int.

        In the XML it becomes an addOperation element with an empty body.
        """
        match = OPERATION_PATTERN.match(line)
        if match is None:
            self._diagram.add_adaptation(NOT_UNDERSTOOD, self._current_class.get_name(),
                                         f"Operation not understood and skipped: '{line}'")
            return
        type_before, name, parameter_text, type_after = match.groups()
        if type_after is not None:
            return_type = type_after
        else:
            return_type = type_before
        parameters = self._read_parameters(parameter_text)
        self._current_class.add_operation(UmlOperation(name, parameters, return_type))

    @staticmethod
    def _read_parameters(parameter_text: str) -> List[UmlParameter]:
        """Read a parameter list. Each one is written a : int, int a, or as a single word."""
        parameters = []
        for parameter in parameter_text.split(","):
            parameter = parameter.strip()
            if parameter == "":
                continue
            if ":" in parameter:
                name, type_name = parameter.split(":", 1)
                parameters.append(UmlParameter(name.strip(), type_name.strip()))
            elif " " in parameter:
                type_name, name = parameter.split()[-2:]
                parameters.append(UmlParameter(name, type_name))
            else:
                parameters.append(UmlParameter(parameter, None))
        return parameters

    def _read_attribute(self, line: str) -> None:
        """Recognize an attribute, written String name, name : String, name, or tags : String[].

        The extras {static}, {frozen}, const and = value are ignored. Without a type String is used,
        and Type[] means 0..*. In the XML it becomes an addAttribute element.
        """
        text = self._remove_attribute_extras(line)
        class_name = self._current_class.get_name()
        if text == "":
            self._diagram.add_adaptation(NOT_UNDERSTOOD, class_name, f"Line not understood and skipped: '{line}'")
            return
        name, type_name = self._split_attribute(text, class_name)
        multiplicity = EXACTLY_ONE
        if type_name.endswith(ARRAY_SUFFIX):
            type_name = type_name[:-len(ARRAY_SUFFIX)]
            multiplicity = ZERO_TO_MANY
        self._current_class.add_attribute(UmlAttribute(name, type_name, multiplicity))

    @staticmethod
    def _remove_attribute_extras(line: str) -> str:
        """Return an attribute line without {static}, {frozen}, const and a start value such as = 5."""
        text = CURLY_EXTRA_PATTERN.sub("", line)
        text = text.split("=")[0]
        return CONST_PATTERN.sub("", text).strip()

    def _split_attribute(self, text: str, class_name: str) -> Tuple[str, str]:
        """Return the name and the type of an attribute. A missing type is reported and becomes String."""
        if ":" in text:
            name, type_name = text.split(":", 1)
            return name.strip(), type_name.strip()
        parts = text.split()
        if len(parts) == 1:
            name = parts[0]
            self._diagram.add_adaptation(ATTRIBUTE_WITHOUT_TYPE, class_name,
                                         f"Attribute '{class_name}.{name}' has no type; String is used.")
            return name, DEFAULT_ATTRIBUTE_TYPE
        return parts[-1], parts[-2]

    def _read_top_level_line(self, line: str) -> None:
        """Hand a line outside a class body to the first step that recognizes it.

        A line that no step recognizes is reported and skipped.
        """
        if self._read_class_line(line):
            return
        if self._read_enum_line(line):
            return
        if self._read_relation_line(line):
            return
        if self._read_association_class_line(line):
            return
        if self._read_note_line(line):
            return
        if self._read_diamond_line(line):
            return
        self._diagram.add_adaptation(NOT_UNDERSTOOD, "", f"Line not understood and skipped: '{line}'")

    def _read_class_line(self, line: str) -> bool:
        """Recognize a class, written class Person { or abstract class Person.

        In the XML it becomes an addMetaClass element, with abstract="true" for an abstract class.
        Return True if the line was a class.
        """
        match = CLASS_PATTERN.match(line)
        if match is None:
            return False
        keyword, name, _stereotype, opens_body, closes_body = match.groups()
        uml_class = self._diagram.get_or_create_class(name)
        uml_class.set_abstract(keyword.startswith(ABSTRACT_KEYWORD))
        if opens_body is not None and closes_body is None:
            self._current_class = uml_class
        return True

    def _read_enum_line(self, line: str) -> bool:
        """Recognize an enum, written enum Color {, which comes before the attributes that use it as a type.

        In the XML it becomes an addEnumeration element. Return True if the line was an enum.
        """
        match = ENUM_PATTERN.match(line)
        if match is None:
            return False
        name, _stereotype, opens_body, closes_body = match.groups()
        uml_enum = UmlEnum(name)
        self._diagram.add_enum(uml_enum)
        if opens_body is not None and closes_body is None:
            self._current_enum = uml_enum
        return True

    def _read_relation_line(self, line: str) -> bool:
        """Recognize a relation, written A -- B, A --> B, A <|-- B, A "1" *-- "0..*" B or A o-- B : label.

        The normalizer decides what it becomes in the XML. Return True if the line was a relation.
        """
        match = RELATION_PATTERN.match(line)
        if match is None:
            return False
        left, left_multiplicity, arrow, right_multiplicity, right, label = match.groups()
        if label is not None:
            label = label.strip()
        self._diagram.add_relation(RawRelation(left, left_multiplicity, arrow, right_multiplicity, right, label))
        return True

    def _read_association_class_line(self, line: str) -> bool:
        """Recognize an association class, written (A, B) .. C or C .. (A, B).

        The normalizer turns it into two associations. Return True if the line was an association class.
        """
        match = ASSOCIATION_CLASS_PATTERN.match(line)
        if match is not None:
            end_a, end_b, middle = match.groups()
            self._diagram.add_association_class(middle, end_a, end_b)
            return True
        match = ASSOCIATION_CLASS_REVERSED_PATTERN.match(line)
        if match is not None:
            middle, end_a, end_b = match.groups()
            self._diagram.add_association_class(middle, end_a, end_b)
            return True
        return False

    def _read_note_line(self, line: str) -> bool:
        """Recognize a note, written note "{XOR}" as N1.

        It does not reach the XML; the normalizer reports it. Return True if the line was a note.
        """
        match = NOTE_PATTERN.match(line)
        if match is None:
            return False
        text, alias = match.groups()
        self._diagram.add_note(alias, text)
        return True

    def _read_diamond_line(self, line: str) -> bool:
        """Recognize an n-ary diamond, written <> Exam.

        The normalizer turns it into a class with associations. Return True if the line was a diamond.
        """
        match = DIAMOND_PATTERN.match(line)
        if match is None:
            return False
        self._diagram.add_diamond(match.group(1))
        return True

    @classmethod
    def is_plantuml_text_file(cls, path: str) -> bool:
        """Check whether a .txt file holds PlantUML.

        Its first text must be @startuml. An empty plantuml.txt counts if the plantuml.png next to
        it contains a diagram.
        """
        try:
            text = cls._read_text_file(path)
        except OSError:
            return False
        if text.strip() == "":
            return cls._read_neighbor_image(path) is not None
        return text.lstrip().lower().startswith(START_KEYWORD)

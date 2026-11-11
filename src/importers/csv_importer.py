"""Builds a model from a CSV file: one class with one instance per data row."""
import keyword
import os
import re
import unicodedata
from typing import List, Optional, Tuple

from src.basemlm.basemlm_attribute import BaseMlmAttribute
from src.basemlm.basemlm_model import BaseMlmModel
from src.basemlm.basemlm_object import BaseMlmObject
from src.basemlm.basemlm_predefined_type import StringType
from src.basemlm.basemlm_slot import BaseMlmSlot
from src.importers.csv_reader import CsvReader
from src.importers.import_report import ImportReport
from src.importers.model_importer import ModelImporter, register_importer
from src.importers.slot_value_converter import SlotValueConverter

CLASS_LEVEL = "1"
INSTANCE_LEVEL = "0"
ATTRIBUTE_LEVEL = 0
NOT_ABSTRACT = "false"
FIRST_DATA_ROW_NUMBER = 2
FIRST_NUMBER_FOR_UNIQUE_NAME = 2
DEFAULT_CLASS_NAME = "CsvClass"
DEFAULT_ATTRIBUTE_NAME = "attribute"
RESERVED_NAME_SUFFIX = "Attribute"
RESERVED_NAMES = {"self", "super", "null", "true", "false"}
NULL_VALUE = "null"

# Recognizes a small letter or digit followed by a capital, for example eN in: firstName
WORD_BOUNDARY_PATTERN = re.compile(r"([a-z0-9])([A-Z])")
# Recognizes one word of letters and digits, for example first and name in: first-name
WORD_PATTERN = re.compile(r"[A-Za-z0-9]+")
# Recognizes one character that is not a letter, digit or underscore, for example the space in: news decline
NON_WORD_CHARACTER_PATTERN = re.compile(r"\W")
# Recognizes several underscores in a row, for example: news__decline
UNDERSCORES_PATTERN = re.compile(r"_+")


class CsvImporter(ModelImporter):
    """Imports a CSV file as one class with one instance per data row.

    Every heading becomes a unique XModeler-compatible attribute name. Empty cells do not create
    slots because they contain no exportable value. CSV input contains no relationships, so none
    are invented. Data cells are kept exactly as they are in the file; only the headings are cleaned.
    """

    EXTENSIONS = (".csv",)
    SOURCE_FOLDER = "csv_files"
    FORMAT_NAME = "CSV"

    def __init__(self) -> None:
        """Create an importer that imports all columns until others are selected."""
        self._selected_columns: Optional[List[str]] = None

    def select_columns(self, columns: List[str]) -> None:
        """Keep an independent selection so only these columns become model attributes."""
        self._selected_columns = list(columns)

    def import_into(self, model: BaseMlmModel, path: str) -> ImportReport:
        """Fill the given empty model with the content of the CSV file and return the problems found."""
        report = ImportReport()
        converter = SlotValueConverter(model, report, read_xml_expressions=False)
        reader = CsvReader(path)
        model.set_model_name(os.path.basename(path))
        self._check_file(reader)

        header_row = reader.get_header()
        data_rows = reader.get_data_rows()
        if self._selected_columns is not None:
            header_row, data_rows = self._select_csv_columns(header_row, data_rows, self._selected_columns)

        class_name = self._make_csv_class_name(path)
        project_name = f"Root::{class_name}"
        model.set_path_name(project_name)
        mlm_class = BaseMlmObject(f"{project_name}::{class_name}", class_name, CLASS_LEVEL,
                                  BaseMlmObject.meta_class(), NOT_ABSTRACT, model)
        attributes = self._create_attributes(model, mlm_class, header_row, data_rows)
        all_mlm_objects = [mlm_class]
        for row_number, row in enumerate(data_rows, start=1):
            instance_name = f"{class_name.lower()}{row_number}"
            mlm_instance = BaseMlmObject(f"{project_name}::{instance_name}", instance_name, INSTANCE_LEVEL,
                                         mlm_class, NOT_ABSTRACT, model)
            mlm_class.add_instance(mlm_instance)
            all_mlm_objects.append(mlm_instance)
            self._create_slots(mlm_instance, row, attributes, converter)

        for mlm_object in all_mlm_objects:
            model.add_mlm_object(mlm_object)
        return report

    @staticmethod
    def _check_file(reader: CsvReader) -> None:
        """Stop the import if the file has no rows, no valid header, or a row of the wrong length."""
        if reader.is_empty():
            raise ValueError("CSV file must contain at least one row.")
        number_of_columns = len(reader.get_header())
        if number_of_columns == 0:
            raise ValueError("CSV header must contain at least one column.")
        if not reader.first_row_looks_like_header():
            raise ValueError(
                "CSV header does not look valid. The first row seems to contain data instead of attribute names."
            )
        # The header is row 1, so the data rows start with the next number.
        for row_number, row in enumerate(reader.get_data_rows(), start=FIRST_DATA_ROW_NUMBER):
            if len(row) != number_of_columns:
                raise ValueError(
                    f"CSV row {row_number} has {len(row)} values, but the header has {number_of_columns} values."
                )

    def _create_attributes(self, model: BaseMlmModel, mlm_class: BaseMlmObject, header_row: List[str],
                           data_rows: List[List[str]]) -> List[BaseMlmAttribute]:
        """Create one attribute per column. Its type is the one that fits all values of the column."""
        attributes = []
        used_attribute_names = []
        for column_number, raw_attribute_name in enumerate(header_row):
            attribute_name = self._make_csv_attribute_name(raw_attribute_name)
            attribute_name = self._make_unique_csv_attribute_name(attribute_name, used_attribute_names)
            attribute_type = f"Root::XCore::{CsvReader.column_type(self._column_values(data_rows, column_number))}"
            attribute = BaseMlmAttribute(attribute_name, attribute_type, ATTRIBUTE_LEVEL,
                                         model.parse_attribute_type(attribute_type))
            attribute.set_owner(mlm_class)
            attributes.append(attribute)
            mlm_class.add_attr(attribute)
        return attributes

    @staticmethod
    def _column_values(data_rows: List[List[str]], column_number: int) -> List[str]:
        """Return all values of one column."""
        values = []
        for row in data_rows:
            values.append(row[column_number])
        return values

    def _create_slots(self, mlm_instance: BaseMlmObject, row: List[str], attributes: List[BaseMlmAttribute],
                      converter: SlotValueConverter) -> None:
        """Create one slot per non-empty cell. The slot directly gets the attribute of its column."""
        for column_number, value in enumerate(row):
            attribute = attributes[column_number]
            if not self._is_empty_csv_cell(value, attribute):
                slot = BaseMlmSlot(attribute.get_name(), value, xml_value=self._csv_xml_value(value))
                slot.set_owner_object(mlm_instance)
                slot.set_attribute(attribute)
                converter.convert(slot)
                mlm_instance.add_slot(slot)

    def _select_csv_columns(self, header_row: List[str], data_rows: List[List[str]],
                            selected_csv_columns: List[str]) -> Tuple[List[str], List[List[str]]]:
        """Reduce the header and the rows to the selected columns, in the order of the selection.

        Without a selected column the class would have no attributes. All wrong names are collected
        first, so that the error shows them at once.
        """
        if len(selected_csv_columns) == 0:
            raise ValueError("At least one CSV column must be selected.")

        selected_column_numbers = []
        missing_column_names = []
        for selected_column in selected_csv_columns:
            column_number = self._get_csv_column_number(header_row, selected_column)
            if column_number is None:
                missing_column_names.append(selected_column)
            else:
                selected_column_numbers.append(column_number)

        if missing_column_names:
            raise ValueError(f"Selected CSV columns were not found: {missing_column_names}")

        selected_header_row = self._cells_at(header_row, selected_column_numbers)
        selected_data_rows = []
        for row in data_rows:
            selected_data_rows.append(self._cells_at(row, selected_column_numbers))
        return selected_header_row, selected_data_rows

    @staticmethod
    def _cells_at(row: List[str], column_numbers: List[int]) -> List[str]:
        """Return the cells of a row at the given column numbers."""
        cells = []
        for column_number in column_numbers:
            cells.append(row[column_number])
        return cells

    def _get_csv_column_number(self, header_row: List[str], selected_column: str) -> Optional[int]:
        """Return the position of a column, or None if it does not exist.

        The user may enter the original CSV name or the safe attribute name used in the model.
        """
        for column_number, raw_header_name in enumerate(header_row):
            safe_header_name = self._make_csv_attribute_name(raw_header_name)
            if selected_column == raw_header_name or selected_column == safe_header_name:
                return column_number
        return None

    def _make_csv_class_name(self, csv_file_path: str) -> str:
        """Return the class name for a file, for example NewsDecline for news_decline.csv."""
        file_name = os.path.splitext(os.path.basename(csv_file_path))[0]
        safe_name = self._make_safe_name(file_name, DEFAULT_CLASS_NAME)
        class_name = ""
        for name_part in safe_name.split("_"):
            class_name += name_part.capitalize()
        return class_name

    @staticmethod
    def _make_csv_attribute_name(raw_name: str) -> str:
        """Convert a CSV heading to an XModeler-friendly lowerCamelCase name, for example first-name to firstName."""
        ascii_name = unicodedata.normalize("NFKD", raw_name.strip()).encode("ascii", "ignore").decode("ascii")
        separated_words = WORD_BOUNDARY_PATTERN.sub(r"\1 \2", ascii_name)
        words = WORD_PATTERN.findall(separated_words)
        if not words:
            return DEFAULT_ATTRIBUTE_NAME

        attribute_name = words[0].lower()
        for word in words[1:]:
            attribute_name += word.lower().capitalize()
        if attribute_name[0].isdigit():
            attribute_name = DEFAULT_ATTRIBUTE_NAME + attribute_name[0].upper() + attribute_name[1:]

        if keyword.iskeyword(attribute_name) or attribute_name in RESERVED_NAMES:
            attribute_name += RESERVED_NAME_SUFFIX
        return attribute_name

    @staticmethod
    def _make_unique_csv_attribute_name(name: str, already_used_names: List[str]) -> str:
        """Add a number when different CSV headings result in the same attribute name.

        Upper and lower case are not told apart.
        """
        used_lowercase_names = set()
        for used_name in already_used_names:
            used_lowercase_names.add(used_name.lower())
        unique_name = name
        number = FIRST_NUMBER_FOR_UNIQUE_NAME
        while unique_name.lower() in used_lowercase_names:
            unique_name = f"{name}{number}"
            number += 1
        already_used_names.append(unique_name)
        return unique_name

    @staticmethod
    def _make_safe_name(name: str, fallback_name: str) -> str:
        """Replace characters that can cause problems in names by _, and avoid a leading digit or a keyword."""
        safe_name = NON_WORD_CHARACTER_PATTERN.sub("_", name.strip())
        safe_name = UNDERSCORES_PATTERN.sub("_", safe_name).strip("_")
        if safe_name == "":
            safe_name = fallback_name
        if safe_name[0].isdigit():
            safe_name = f"{fallback_name}_{safe_name}"
        if keyword.iskeyword(safe_name):
            safe_name = f"{safe_name}_{fallback_name}"
        return safe_name

    @staticmethod
    def _is_empty_csv_cell(value: str, attribute: BaseMlmAttribute) -> bool:
        """Blanks are text in a String column. In any other column they mean an empty cell."""
        if value == "":
            return True
        return value.strip() == "" and not isinstance(attribute.get_type_spec(), StringType)

    @staticmethod
    def _csv_xml_value(value: str) -> Optional[str]:
        """A CSV cell has no XML expression, except null, which is written as it is on export."""
        if value == NULL_VALUE:
            return NULL_VALUE
        return None


register_importer(CsvImporter)

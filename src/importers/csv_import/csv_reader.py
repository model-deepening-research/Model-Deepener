"""Reads CSV files, checks their header and determines column types, for the import and the preview of the GUI."""
import csv
import io
import re
from typing import List, Pattern, Type, Union

# Recognizes a whole number, for example: -42
INTEGER_EXPRESSION = re.compile(r"[-+]?\d+")
# Recognizes a decimal number, for example: 1.5, .5 or 1.5E3
FLOAT_EXPRESSION = re.compile(r"[-+]?(\d+(\.\d*)?|\.\d+)([eE][-+]?\d+)?")
# Recognizes a number that starts with a zero, for example: 00123
LEADING_ZERO_EXPRESSION = re.compile(r"[-+]?0\d")
# Recognizes a name without spaces or special characters, for example: first_name
SIMPLE_NAME_EXPRESSION = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")

DIALECT_SAMPLE_LENGTH = 2048
NO_VALUE_TEXTS = ("", "null")
BOOLEAN_TEXTS = ("true", "false")


class CsvReader:
    """The rows of one CSV file, split into columns by the delimiter found in the file.

    Data cells stay exactly as they are in the file, including their spaces. Only blanks directly
    before an opening quote are ignored, so that x, "a,b" has two columns.
    """

    DELIMITERS = ",;\t|"

    def __init__(self, file_path: str) -> None:
        """Read the file. utf-8-sig reads UTF-8 and ignores the BOM marker written by Excel."""
        with open(file_path, "r", newline="", encoding="utf-8-sig") as csv_file:
            text = csv_file.read()
        self._dialect = self._detect_dialect(text[:DIALECT_SAMPLE_LENGTH])
        cleaned_text = self._remove_blanks_before_quotes(text)
        reader = csv.reader(io.StringIO(cleaned_text, newline=""), self._dialect, skipinitialspace=False)
        self._rows: List[List[str]] = [row for row in reader if row]

    def is_empty(self) -> bool:
        """Return True if the file has no rows."""
        return len(self._rows) == 0

    def get_delimiter(self) -> str:
        """Return the character that separates the columns."""
        return self._dialect.delimiter

    def get_header(self) -> List[str]:
        """Return the column names of the first row, without surrounding blanks and quotes."""
        return [value.strip().strip('"') for value in self._rows[0]]

    def get_data_rows(self) -> List[List[str]]:
        """Return independent data rows so callers cannot change the reader's stored cells."""
        rows = []
        for row in self._rows[1:]:
            rows.append(list(row))
        return rows

    def first_row_looks_like_header(self) -> bool:
        """Check whether the first row holds column names or normal data.

        Without data rows there is nothing to compare, so the first row is accepted. Names like
        "name" or "city" are valid. Otherwise the first row is a header if a cell looks different
        from the data below it. A row that is too short has no value for that column.
        """
        header = self.get_header()
        data_rows = self.get_data_rows()
        if not data_rows:
            return True
        if self._all_match(SIMPLE_NAME_EXPRESSION, header):
            return True
        for column_index, cell in enumerate(header):
            if self._value_kind(cell) not in self._column_kinds(data_rows, column_index):
                return True
        return False

    def _column_kinds(self, data_rows: List[List[str]], column_index: int) -> List[str]:
        """Return the kinds of the values in one column. A row that is too short has no value there."""
        kinds = []
        for row in data_rows:
            if column_index < len(row):
                kinds.append(self._value_kind(row[column_index]))
        return kinds

    @staticmethod
    def _all_match(expression: Pattern[str], values: List[str]) -> bool:
        """Return True if the regular expression fits every whole value."""
        for value in values:
            if expression.fullmatch(value) is None:
                return False
        return True

    @staticmethod
    def _value_kind(value: str) -> str:
        """Return the simple kind of a cell, which the header check compares."""
        if value == "":
            return "empty"
        if INTEGER_EXPRESSION.fullmatch(value.strip()) is not None:
            return "integer"
        if FLOAT_EXPRESSION.fullmatch(value.strip()) is not None:
            return "float"
        return "string"

    @classmethod
    def column_type(cls, values: List[str]) -> str:
        """Return the type name that fits all values of a column.

        Blanks and null fit every type. A value with a leading zero, like 00123, is an identifier
        and makes the column a String. Only true and false, in any case, make it a Boolean.
        """
        populated_values = []
        for value in values:
            if value.strip() not in NO_VALUE_TEXTS:
                populated_values.append(value.strip())
        if not populated_values:
            return "String"
        if cls._has_leading_zero(populated_values):
            return "String"
        if cls._are_all_booleans(populated_values):
            return "Boolean"
        if cls._all_match(INTEGER_EXPRESSION, populated_values):
            return "Integer"
        if cls._all_match(FLOAT_EXPRESSION, populated_values):
            return "Float"
        return "String"

    @staticmethod
    def _has_leading_zero(values: List[str]) -> bool:
        """Return True if one value starts with a zero followed by another digit."""
        for value in values:
            if LEADING_ZERO_EXPRESSION.match(value) is not None:
                return True
        return False

    @staticmethod
    def _are_all_booleans(values: List[str]) -> bool:
        """Return True if every value is true or false, in any case."""
        for value in values:
            if value.lower() not in BOOLEAN_TEXTS:
                return False
        return True

    @classmethod
    def _detect_dialect(cls, sample: str) -> Union[csv.Dialect, Type[csv.Dialect]]:
        """Return the format of the file, or the most frequent delimiter if it cannot be detected."""
        try:
            return csv.Sniffer().sniff(sample, delimiters=cls.DELIMITERS)
        except csv.Error:
            dialect = csv.excel()
            dialect.delimiter = cls._most_frequent_delimiter(sample)
            return dialect

    @classmethod
    def _most_frequent_delimiter(cls, sample: str) -> str:
        """Return the delimiter that occurs most often. With equal counts the first one in DELIMITERS wins."""
        best_delimiter = cls.DELIMITERS[0]
        for delimiter in cls.DELIMITERS:
            if sample.count(delimiter) > sample.count(best_delimiter):
                best_delimiter = delimiter
        return best_delimiter

    def _remove_blanks_before_quotes(self, text: str) -> str:
        """Return the text without the blanks between the start of a field and its opening quote.

        Text inside a quoted field stays unchanged. A quote in the middle of an unquoted field
        does not open a quoted field, which is how the csv module reads it too.
        """
        delimiter = self._dialect.delimiter
        quote = self._dialect.quotechar
        result: List[str] = []
        blanks = ""
        at_field_start = True
        in_quoted_field = False
        inside_quotes = False
        for character in text:
            if inside_quotes:
                result.append(character)
                inside_quotes = character != quote
            elif at_field_start and character in " \t" and character != delimiter:
                blanks += character
            elif at_field_start and character == quote:
                result.append(character)
                blanks = ""
                at_field_start = False
                in_quoted_field = True
                inside_quotes = True
            else:
                result.append(blanks)
                result.append(character)
                blanks = ""
                at_field_start = character == delimiter or character in "\r\n"
                if at_field_start:
                    in_quoted_field = False
                elif in_quoted_field and character == quote:
                    inside_quotes = True
        result.append(blanks)
        return "".join(result)

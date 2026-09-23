"""Read OpenLab DAT files and user-configured delimited text files."""

from __future__ import annotations

import csv
import io
import math
import re
from dataclasses import dataclass, field
from pathlib import Path


class DataReadError(ValueError):
    """The source cannot be decoded or does not match its read options."""


_DATA_MODES = frozenset(("openlab", "custom"))
_DELIMITERS = frozenset(("comma", "tab", "semicolon", "pipe", "whitespace", "custom"))
_ENCODINGS = frozenset(("auto", "utf-8", "utf-16", "gb18030"))


@dataclass(frozen=True)
class DataFormatOptions:
    """A validated description of one text file's record layout."""

    mode: str = "openlab"
    data_start_line: int = 1
    header_line: int | None = None
    delimiter: str = "comma"
    custom_delimiter: str = ""
    comment_lines: tuple[int, ...] = ()
    comment_prefixes: tuple[str, ...] = ()
    encoding: str = "auto"

    def __post_init__(self) -> None:
        mode = str(self.mode).casefold()
        delimiter = str(self.delimiter).casefold()
        encoding = str(self.encoding).casefold()
        if mode not in _DATA_MODES:
            raise ValueError("Unknown data format mode: %s" % self.mode)
        if delimiter not in _DELIMITERS:
            raise ValueError("Unknown delimiter: %s" % self.delimiter)
        if encoding not in _ENCODINGS:
            raise ValueError("Unknown encoding: %s" % self.encoding)
        if not isinstance(self.data_start_line, int) or self.data_start_line < 1:
            raise ValueError("Data start line must be a positive integer")
        if self.header_line is not None:
            if not isinstance(self.header_line, int) or self.header_line < 1:
                raise ValueError("Header line must be a positive integer")
            if self.header_line >= self.data_start_line:
                raise ValueError("Header line must be before the data start line")
        if delimiter == "custom" and len(self.custom_delimiter) != 1:
            raise ValueError("A custom delimiter must contain exactly one character")
        if any(not isinstance(line, int) or line < 1 for line in self.comment_lines):
            raise ValueError("Comment lines must be positive integers")
        if any(not isinstance(prefix, str) or not prefix for prefix in self.comment_prefixes):
            raise ValueError("Comment prefixes cannot be empty")
        object.__setattr__(self, "mode", mode)
        object.__setattr__(self, "delimiter", delimiter)
        object.__setattr__(self, "encoding", encoding)
        object.__setattr__(self, "comment_lines", tuple(sorted(set(self.comment_lines))))
        object.__setattr__(self, "comment_prefixes", tuple(dict.fromkeys(self.comment_prefixes)))

    @classmethod
    def openlab(cls) -> "DataFormatOptions":
        """Return the reader used by the existing OpenLab DAT workflow."""

        return cls()

    @classmethod
    def custom(cls) -> "DataFormatOptions":
        """Return a neutral custom-text starting point for the import dialog."""

        return cls(mode="custom")


@dataclass(frozen=True)
class DataPoint:
    """One plottable point, retaining its complete source row."""

    x: float
    y: float
    row_index: int
    row: tuple[str, ...]
    source_line_number: int = 0


@dataclass(frozen=True)
class DataDocument:
    """The immutable result of one file read and its file-version snapshot."""

    path: Path
    header_lines: tuple[str, ...]
    columns: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]
    modified_ns: int
    size_bytes: int
    source_line_numbers: tuple[int, ...] = ()
    format_options: DataFormatOptions = field(default_factory=DataFormatOptions.openlab)

    def column_index(self, name: str) -> int:
        try:
            return self.columns.index(name)
        except ValueError as exc:
            raise KeyError(name) from exc

    def source_line_number(self, row_index: int) -> int:
        if self.source_line_numbers:
            return self.source_line_numbers[row_index]
        return row_index + 1

    def numeric_columns(self) -> tuple[str, ...]:
        result = []
        for index, name in enumerate(self.columns):
            if any(_as_float(row[index]) is not None for row in self.rows):
                result.append(name)
        return tuple(result)

    def numeric_series(
        self,
        y_column: str,
        x_column: str | None = None,
    ) -> tuple[tuple[float, float], ...]:
        return tuple((point.x, point.y) for point in self.numeric_points(y_column, x_column))

    def numeric_points(
        self,
        y_column: str,
        x_column: str | None = None,
    ) -> tuple[DataPoint, ...]:
        y_index = self.column_index(y_column)
        x_index = None if x_column is None else self.column_index(x_column)
        result = []
        for row_index, row in enumerate(self.rows):
            y_value = _as_float(row[y_index])
            if y_value is None:
                continue
            x_value = (
                float(row_index + 1)
                if x_index is None
                else _as_float(row[x_index])
            )
            if x_value is not None:
                result.append(
                    DataPoint(
                        x_value,
                        y_value,
                        row_index,
                        row,
                        self.source_line_number(row_index),
                    )
                )
        return tuple(result)


# Compatibility names make the ported plotting code easy to compare with the
# original OpenLab Control implementation.
DatReadError = DataReadError
DatPoint = DataPoint
DatDocument = DataDocument


def parse_line_ranges(value: str) -> tuple[int, ...]:
    """Parse ``1-5,9,12-14`` into sorted one-based physical line numbers."""

    result = set()
    for token in value.split(","):
        token = token.strip()
        if not token:
            continue
        match = re.fullmatch(r"(\d+)(?:\s*-\s*(\d+))?", token)
        if match is None:
            raise ValueError(
                "Invalid line range %r; use numbers separated by commas" % token
            )
        start = int(match.group(1))
        end = int(match.group(2) or start)
        if start < 1 or end < start:
            raise ValueError("Invalid line range %r" % token)
        result.update(range(start, end + 1))
    return tuple(sorted(result))


def _as_float(value: str) -> float | None:
    text = value.strip()
    if not text:
        return None
    try:
        number = float(text)
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def _decode(data: bytes, encoding: str) -> str:
    if encoding == "utf-8":
        encoding = "utf-8-sig"
    if encoding != "auto":
        try:
            return data.decode(encoding)
        except UnicodeDecodeError as exc:
            raise DataReadError("Unable to decode file as %s" % encoding) from exc
    for candidate in ("utf-8-sig", "utf-16", "gb18030"):
        try:
            return data.decode(candidate)
        except UnicodeDecodeError:
            continue
    raise DataReadError("Unable to decode file using the supported encodings")


def _unique_columns(values: list[str]) -> list[str]:
    result = []
    counts = {}
    for index, raw in enumerate(values, start=1):
        base = raw.strip() or "Column %d" % index
        counts[base] = counts.get(base, 0) + 1
        result.append(base if counts[base] == 1 else "%s #%d" % (base, counts[base]))
    return result


def _read_bytes(path: str | Path, allow_unterminated_last_line: bool):
    source = Path(path).resolve()
    try:
        payload = source.read_bytes()
        stat = source.stat()
    except OSError as exc:
        raise DataReadError("Unable to read data file: %s" % source) from exc
    if (
        not allow_unterminated_last_line
        and payload
        and payload[-1:] not in (b"\n", b"\r")
        and payload[-2:] not in (
            b"\n\x00",
            b"\x00\n",
            b"\r\x00",
            b"\x00\r",
        )
    ):
        raise DataReadError("The last line is not terminated; waiting for the writer")
    return source, payload, stat.st_mtime_ns, len(payload)


def _detection_record(line: str, delimiter: str) -> list[str] | None:
    if delimiter == "whitespace":
        if '"' in line:
            return None
        return re.split(r"\s+", line.strip())
    separator = {
        "comma": ",",
        "tab": "\t",
        "semicolon": ";",
        "pipe": "|",
    }[delimiter]
    try:
        return next(csv.reader([line], delimiter=separator, strict=True))
    except (csv.Error, ValueError):
        return None


def detect_data_format(path: str | Path) -> DataFormatOptions | None:
    """Infer a safe OpenLab or common delimited-text format from a file."""

    _, payload, _, _ = _read_bytes(path, True)
    text = _decode(payload, "auto").replace("\x00", "")
    lines = text.splitlines()
    if any(line.strip().casefold() == "[data]" for line in lines):
        return DataFormatOptions.openlab()

    nonempty = [
        (line_number, line)
        for line_number, line in enumerate(lines, start=1)
        if line.strip()
    ]
    best_header = None
    best_data = None
    for delimiter in ("tab", "comma", "semicolon", "pipe", "whitespace"):
        for index, (line_number, line) in enumerate(nonempty):
            header = _detection_record(line, delimiter)
            if header is None or len(header) < 2:
                continue
            if all(_as_float(value) is not None for value in header):
                continue
            records = []
            for _, candidate_line in nonempty[index + 1 : index + 9]:
                record = _detection_record(candidate_line, delimiter)
                if record is None or len(record) != len(header):
                    break
                records.append(record)
            numeric_rows = sum(
                1
                for record in records
                if any(_as_float(value) is not None for value in record)
            )
            if len(records) < 3 or numeric_rows < 3:
                continue
            score = (numeric_rows, len(records), len(header))
            if best_header is None or score > best_header[0]:
                best_header = (
                    score,
                    DataFormatOptions(
                        mode="custom",
                        header_line=line_number,
                        data_start_line=line_number + 1,
                        delimiter=delimiter,
                        encoding="auto",
                    ),
                )

        for index, (line_number, line) in enumerate(nonempty):
            first = _detection_record(line, delimiter)
            if first is None or len(first) < 2:
                continue
            records = [first]
            for _, candidate_line in nonempty[index + 1 : index + 8]:
                record = _detection_record(candidate_line, delimiter)
                if record is None or len(record) != len(first):
                    break
                records.append(record)
            numeric_rows = sum(
                1
                for record in records
                if any(_as_float(value) is not None for value in record)
            )
            if len(records) < 3 or numeric_rows < 3:
                continue
            score = (numeric_rows, len(records), len(first))
            if best_data is None or score > best_data[0]:
                best_data = (
                    score,
                    DataFormatOptions(
                        mode="custom",
                        data_start_line=line_number,
                        delimiter=delimiter,
                        encoding="auto",
                    ),
                )

    if best_header is not None:
        return best_header[1]
    if best_data is not None:
        return best_data[1]
    return None


def _make_document(
    source: Path,
    header_lines: tuple[str, ...],
    header_values: list[str] | None,
    body: list[list[str]],
    body_line_numbers: list[int],
    modified_ns: int,
    size_bytes: int,
    options: DataFormatOptions,
    require_exact_width: bool = False,
) -> DataDocument:
    if header_values is None:
        if not body:
            raise DataReadError("The configured data range does not contain a data row")
        width = max(len(row) for row in body)
        columns = ["Column %d" % index for index in range(1, width + 1)]
    else:
        columns = _unique_columns(header_values)
        width = len(columns)
    normalized = []
    for row, line_number in zip(body, body_line_numbers):
        if require_exact_width and len(row) != width:
            raise DataReadError(
                "Line %d has %d fields; expected exactly %d"
                % (line_number, len(row), width)
            )
        if len(row) > width:
            raise DataReadError(
                "Line %d has %d fields; expected at most %d"
                % (line_number, len(row), width)
            )
        normalized.append(tuple((row + [""] * (width - len(row)))[:width]))
    return DataDocument(
        path=source,
        header_lines=header_lines,
        columns=tuple(columns),
        rows=tuple(normalized),
        modified_ns=modified_ns,
        size_bytes=size_bytes,
        source_line_numbers=tuple(body_line_numbers),
        format_options=options,
    )


def read_dat(
    path: str | Path,
    *,
    allow_unterminated_last_line: bool = True,
) -> DataDocument:
    """Read the existing OpenLab ``[Data]`` DAT format."""

    source, payload, modified_ns, size_bytes = _read_bytes(
        path,
        allow_unterminated_last_line,
    )
    lines = _decode(payload, "auto").replace("\x00", "").splitlines()
    marker = next(
        (
            index
            for index, line in enumerate(lines)
            if line.strip().casefold() == "[data]"
        ),
        None,
    )
    if marker is None:
        raise DataReadError("The file does not contain a [Data] section")
    records = []
    line_numbers = []
    reader = csv.reader(io.StringIO("\n".join(lines[marker + 1 :])))
    previous_reader_line = 0
    try:
        for record in reader:
            start_reader_line = previous_reader_line + 1
            previous_reader_line = reader.line_num
            line_number = marker + 1 + start_reader_line
            if not any(cell.strip() for cell in record):
                continue
            if record and record[0].lstrip().startswith(";"):
                continue
            records.append([cell.strip() for cell in record])
            line_numbers.append(line_number)
    except csv.Error as exc:
        line_number = marker + 1 + max(1, reader.line_num)
        raise DataReadError("Unable to parse line %d: %s" % (line_number, exc)) from exc
    if not records:
        raise DataReadError("The [Data] section does not contain a column header")
    width = max(len(record) for record in records)
    header_values = records[0] + ["Extra %d" % index for index in range(len(records[0]) + 1, width + 1)]
    return _make_document(
        source,
        tuple(lines[:marker]),
        header_values,
        records[1:],
        line_numbers[1:],
        modified_ns,
        size_bytes,
        DataFormatOptions.openlab(),
    )


def _delimiter(options: DataFormatOptions) -> str | None:
    return {
        "comma": ",",
        "tab": "\t",
        "semicolon": ";",
        "pipe": "|",
        "whitespace": None,
        "custom": options.custom_delimiter,
    }[options.delimiter]


def _custom_record(line: str, line_number: int, options: DataFormatOptions):
    if not line.strip() or line_number in options.comment_lines:
        return None
    stripped = line.lstrip()
    if any(stripped.startswith(prefix) for prefix in options.comment_prefixes):
        return None
    delimiter = _delimiter(options)
    if delimiter is None:
        if '"' in line:
            raise DataReadError(
                "Line %d: quoted fields are not supported with whitespace separation"
                % line_number
            )
        return re.split(r"\s+", line.strip())
    try:
        record = next(csv.reader([line], delimiter=delimiter, strict=True))
    except (csv.Error, ValueError) as exc:
        if line.count('"') % 2:
            raise DataReadError(
                "Line %d starts an unterminated quoted field; multiline quoted records are not supported"
                % line_number
            ) from exc
        raise DataReadError("Unable to parse line %d: %s" % (line_number, exc)) from exc
    return [cell.strip() for cell in record]


def read_data(
    path: str | Path,
    options: DataFormatOptions,
    *,
    allow_unterminated_last_line: bool = True,
) -> DataDocument:
    """Read a file with either the legacy OpenLab or custom text options."""

    if options.mode == "openlab":
        return read_dat(
            path,
            allow_unterminated_last_line=allow_unterminated_last_line,
        )
    source, payload, modified_ns, size_bytes = _read_bytes(
        path,
        allow_unterminated_last_line,
    )
    lines = _decode(payload, options.encoding).replace("\x00", "").splitlines()
    header_values = None
    if options.header_line is not None:
        if options.header_line > len(lines):
            raise DataReadError("Header line %d is outside the file" % options.header_line)
        header_values = _custom_record(
            lines[options.header_line - 1],
            options.header_line,
            options,
        )
        if header_values is None:
            raise DataReadError(
                "Header line %d is empty or ignored by the format" % options.header_line
            )
    records = []
    line_numbers = []
    for line_number, line in enumerate(
        lines[options.data_start_line - 1 :],
        start=options.data_start_line,
    ):
        record = _custom_record(line, line_number, options)
        if record is not None:
            records.append(record)
            line_numbers.append(line_number)
    if header_values is None and records:
        header_values = ["Column %d" % index for index in range(1, len(records[0]) + 1)]
    return _make_document(
        source,
        tuple(lines[: options.data_start_line - 1]),
        header_values,
        records,
        line_numbers,
        modified_ns,
        size_bytes,
        options,
        require_exact_width=True,
    )

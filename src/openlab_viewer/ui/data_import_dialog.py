"""Dialog for selecting how a text data file should be read."""

from __future__ import annotations

from pathlib import Path

from PySide2.QtCore import Qt
from PySide2.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from ..data_reader import (
    DataDocument,
    DataFormatOptions,
    DataReadError,
    parse_line_ranges,
    read_data,
)
from .scaling import scaled
from .window_sizing import fit_initial_window_width


class DataImportDialog(QDialog):
    """Choose a read format and preview the resulting records."""

    def __init__(
        self,
        path: str | Path,
        initial_options: DataFormatOptions | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.path = Path(path).resolve()
        self._document: DataDocument | None = None
        options = initial_options or DataFormatOptions.custom()

        self.setWindowTitle("Import Data Settings")
        self.setModal(True)
        layout = QVBoxLayout(self)

        file_label = QLabel("File: %s" % self.path)
        file_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        file_label.setWordWrap(True)
        layout.addWidget(file_label)

        format_box = QGroupBox("File format")
        form = QFormLayout(format_box)
        self.mode_combo = QComboBox()
        self.mode_combo.addItem("OpenLab DAT ([Data] section)", "openlab")
        self.mode_combo.addItem("Custom delimited text", "custom")
        form.addRow("Format:", self.mode_combo)

        self.data_start_spin = self._line_spin()
        form.addRow("Data starts at line:", self.data_start_spin)

        header_row = QGridLayout()
        self.header_check = QCheckBox("Column header is on a separate line")
        self.header_spin = self._line_spin()
        header_row.addWidget(self.header_check, 0, 0)
        header_row.addWidget(QLabel("Header line:"), 0, 1)
        header_row.addWidget(self.header_spin, 0, 2)
        form.addRow("Header:", header_row)

        self.delimiter_combo = QComboBox()
        for label, value in (
            ("Comma (,)", "comma"),
            ("Tab", "tab"),
            ("Semicolon (;)", "semicolon"),
            ("Pipe (|)", "pipe"),
            ("Whitespace", "whitespace"),
            ("Custom character", "custom"),
        ):
            self.delimiter_combo.addItem(label, value)
        form.addRow("Delimiter:", self.delimiter_combo)

        self.custom_delimiter_edit = QLineEdit()
        self.custom_delimiter_edit.setMaxLength(1)
        self.custom_delimiter_edit.setPlaceholderText("One character")
        form.addRow("Custom delimiter:", self.custom_delimiter_edit)

        self.comment_lines_edit = QLineEdit()
        self.comment_lines_edit.setPlaceholderText("For example: 1-3, 8, 12-14")
        form.addRow("Ignore physical lines:", self.comment_lines_edit)

        self.comment_prefixes_edit = QLineEdit()
        self.comment_prefixes_edit.setPlaceholderText("For example: #, //")
        form.addRow("Ignore line prefixes:", self.comment_prefixes_edit)

        self.encoding_combo = QComboBox()
        for label, value in (
            ("Automatic (UTF-8, UTF-16, GB18030)", "auto"),
            ("UTF-8", "utf-8"),
            ("UTF-16", "utf-16"),
            ("GB18030", "gb18030"),
        ):
            self.encoding_combo.addItem(label, value)
        form.addRow("Encoding:", self.encoding_combo)
        layout.addWidget(format_box)

        self.preview_button = QPushButton("Preview")
        self.preview_button.setToolTip("Read the file with the selected settings")
        layout.addWidget(self.preview_button, 0, Qt.AlignLeft)

        self.status_label = QLabel("Choose settings and preview the file.")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        layout.addWidget(QLabel("Source preview (physical line numbers):"))
        self.source_preview = QPlainTextEdit()
        self.source_preview.setReadOnly(True)
        self.source_preview.setMaximumHeight(scaled(190))
        layout.addWidget(self.source_preview)

        layout.addWidget(QLabel("Parsed data preview:"))
        self.preview_table = QTableWidget()
        self.preview_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.preview_table.setSelectionMode(QAbstractItemView.NoSelection)
        self.preview_table.verticalHeader().setVisible(True)
        self.preview_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        layout.addWidget(self.preview_table, 1)

        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttons.accepted.connect(self._apply)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

        self.mode_combo.currentIndexChanged.connect(self._update_enabled_controls)
        self.header_check.toggled.connect(self._update_enabled_controls)
        self.delimiter_combo.currentIndexChanged.connect(self._update_enabled_controls)
        self.preview_button.clicked.connect(self.preview)
        self._set_options(options)
        self._update_enabled_controls()
        fit_initial_window_width(self, preferred_height=scaled(680))

    @staticmethod
    def _line_spin() -> QSpinBox:
        spin = QSpinBox()
        spin.setRange(1, 2147483647)
        return spin

    def _set_options(self, options: DataFormatOptions) -> None:
        mode_index = self.mode_combo.findData(options.mode)
        if mode_index >= 0:
            self.mode_combo.setCurrentIndex(mode_index)
        self.data_start_spin.setValue(options.data_start_line)
        self.header_check.setChecked(options.header_line is not None)
        self.header_spin.setValue(options.header_line or max(1, options.data_start_line - 1))
        delimiter_index = self.delimiter_combo.findData(options.delimiter)
        if delimiter_index >= 0:
            self.delimiter_combo.setCurrentIndex(delimiter_index)
        self.custom_delimiter_edit.setText(options.custom_delimiter)
        self.comment_lines_edit.setText(self._format_line_ranges(options.comment_lines))
        self.comment_prefixes_edit.setText(", ".join(options.comment_prefixes))
        encoding_index = self.encoding_combo.findData(options.encoding)
        if encoding_index >= 0:
            self.encoding_combo.setCurrentIndex(encoding_index)

    @staticmethod
    def _format_line_ranges(lines: tuple[int, ...]) -> str:
        if not lines:
            return ""
        result = []
        start = previous = lines[0]
        for value in lines[1:]:
            if value == previous + 1:
                previous = value
                continue
            result.append(str(start) if start == previous else "%d-%d" % (start, previous))
            start = previous = value
        result.append(str(start) if start == previous else "%d-%d" % (start, previous))
        return ", ".join(result)

    def _update_enabled_controls(self) -> None:
        custom = self.mode_combo.currentData() == "custom"
        for widget in (
            self.data_start_spin,
            self.header_check,
            self.header_spin,
            self.delimiter_combo,
            self.custom_delimiter_edit,
            self.comment_lines_edit,
            self.comment_prefixes_edit,
            self.encoding_combo,
        ):
            widget.setEnabled(custom)
        self.header_spin.setEnabled(custom and self.header_check.isChecked())
        self.custom_delimiter_edit.setEnabled(
            custom and self.delimiter_combo.currentData() == "custom"
        )

    def format_options(self) -> DataFormatOptions:
        """Build validated options from the current controls."""

        prefixes = tuple(
            item.strip()
            for item in self.comment_prefixes_edit.text().split(",")
            if item.strip()
        )
        return DataFormatOptions(
            mode=str(self.mode_combo.currentData()),
            data_start_line=self.data_start_spin.value(),
            header_line=self.header_spin.value() if self.header_check.isChecked() else None,
            delimiter=str(self.delimiter_combo.currentData()),
            custom_delimiter=self.custom_delimiter_edit.text(),
            comment_lines=parse_line_ranges(self.comment_lines_edit.text()),
            comment_prefixes=prefixes,
            encoding=str(self.encoding_combo.currentData()),
        )

    def preview(self) -> bool:
        """Read the file and display a small preview table."""

        options = None
        try:
            options = self.format_options()
            self._show_source_preview(options)
            document = read_data(self.path, options)
        except (DataReadError, ValueError) as exc:
            self._document = None
            self.preview_table.clear()
            self.preview_table.setRowCount(0)
            self.preview_table.setColumnCount(0)
            self.status_label.setText("Preview failed: %s" % exc)
            return False
        self._document = document
        self.preview_table.setColumnCount(len(document.columns))
        self.preview_table.setHorizontalHeaderLabels(list(document.columns))
        rows = document.rows[:20]
        self.preview_table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            self.preview_table.setVerticalHeaderItem(
                row_index,
                QTableWidgetItem(str(document.source_line_number(row_index))),
            )
            for column_index, value in enumerate(row):
                self.preview_table.setItem(row_index, column_index, QTableWidgetItem(value))
        self.preview_table.resizeColumnsToContents()
        self.status_label.setText(
            "Preview: %d rows, %d columns. Physical line numbers are shown on the left."
            % (len(document.rows), len(document.columns))
        )
        return True

    def _show_source_preview(self, options: DataFormatOptions) -> None:
        from ..data_reader import _decode

        try:
            text = _decode(self.path.read_bytes(), options.encoding).replace("\x00", "")
        except (DataReadError, OSError) as exc:
            self.source_preview.setPlainText("Unable to preview source text: %s" % exc)
            return
        lines = text.splitlines()
        preview = "\n".join(
            "%4d | %s" % (line_number, line)
            for line_number, line in enumerate(lines[:80], start=1)
        )
        if len(lines) > 80:
            preview += "\n... (%d more lines)" % (len(lines) - 80)
        self.source_preview.setPlainText(preview)

    def _apply(self) -> None:
        if self.preview():
            self.accept()
        else:
            QMessageBox.warning(
                self,
                "Unable to Import Data",
                "The selected settings do not produce a readable data table.",
            )

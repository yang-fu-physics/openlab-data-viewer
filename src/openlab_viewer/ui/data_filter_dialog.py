"""English five-row data-filter editor with a fixed time row."""

from __future__ import annotations

from typing import Callable, Sequence

from PySide2.QtCore import Signal
from PySide2.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..data_filter import DataFilter, DataFilterRow, FILTER_ROW_COUNT
from ..time_filter import (
    TimeFilterContext,
    format_time_bound,
    parse_time_bound,
)
from .scaling import scaled
from .window_sizing import fit_initial_window_width


class TimeBoundEdit(QLineEdit):
    """A line edit whose displayed value follows the document time semantics."""

    def __init__(self, context: TimeFilterContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.context = context
        self.setPlaceholderText(
            "Wall time" if context.is_wall_time else "Elapsed duration"
        )

    def set_value(self, value: float | None) -> None:
        self.setText("" if value is None else format_time_bound(value, self.context))

    def value(self) -> float | None:
        return parse_time_bound(self.text(), self.context)


class DataFilterDialog(QDialog):
    """Edit one fixed time row and four general rows."""

    filterApplied = Signal(object)

    def __init__(
        self,
        numeric_columns: Sequence[str],
        data_filter: DataFilter | None = None,
        parent: QWidget | None = None,
        apply_callback: Callable[[DataFilter], object] | None = None,
        time_context: TimeFilterContext | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Data Filter")
        self.setMinimumWidth(scaled(560))
        self._apply_callback = apply_callback
        self._time_context = time_context
        self._special_time_row = time_context is not None
        current = data_filter or DataFilter.empty()
        if self._special_time_row:
            current = current.reserve_time_column(time_context.column)
        self._overflow_rows = current.overflow_rows

        layout = QVBoxLayout(self)
        hint = QLabel(
            time_context.help_text
            if time_context is not None
            else "Enabled rows are combined with AND. Blank bounds are unbounded."
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

        grid = QGridLayout()
        grid.setColumnStretch(2, 1)
        grid.setColumnStretch(3, 1)
        grid.addWidget(QLabel("Row"), 0, 0)
        grid.addWidget(QLabel("Enabled"), 0, 1)
        grid.addWidget(QLabel("Data"), 0, 2)
        grid.addWidget(QLabel("Min"), 0, 3)
        grid.addWidget(QLabel("Max"), 0, 4)

        self.enabled_checks: list[QCheckBox] = []
        self.column_combos: list[QComboBox | None] = []
        self.minimum_edits: list[QLineEdit] = []
        self.maximum_edits: list[QLineEdit] = []
        self.time_column_label: QLabel | None = None
        self.time_minimum_edit: TimeBoundEdit | None = None
        self.time_maximum_edit: TimeBoundEdit | None = None

        for row_index in range(FILTER_ROW_COUNT):
            row = current.rows[row_index]
            if self._special_time_row and row_index == 0:
                row_label = "Time"
            elif self._special_time_row:
                row_label = str(row_index)
            else:
                row_label = str(row_index + 1)
            grid.addWidget(QLabel(row_label), row_index + 1, 0)

            enabled = QCheckBox()
            enabled.setChecked(row.enabled)
            enabled.setToolTip("Enable this condition")
            self.enabled_checks.append(enabled)
            grid.addWidget(enabled, row_index + 1, 1)

            if self._special_time_row and row_index == 0:
                if time_context.column is None:
                    column_label = QLabel("Unavailable")
                    column_label.setStyleSheet("color: #657080;")
                    self.time_column_label = column_label
                    grid.addWidget(column_label, row_index + 1, 2)
                    enabled.setEnabled(False)
                else:
                    fixed_column = QComboBox()
                    fixed_column.addItem(time_context.column, time_context.column)
                    fixed_column.setEnabled(False)
                    self.column_combos.append(fixed_column)
                    grid.addWidget(fixed_column, row_index + 1, 2)
                if time_context.column is None:
                    self.column_combos.append(None)
                minimum = TimeBoundEdit(time_context)
                maximum = TimeBoundEdit(time_context)
                minimum.set_value(row.minimum)
                maximum.set_value(row.maximum)
                self.time_minimum_edit = minimum
                self.time_maximum_edit = maximum
                self.minimum_edits.append(minimum)
                self.maximum_edits.append(maximum)
                if time_context.column is None:
                    minimum.setEnabled(False)
                    maximum.setEnabled(False)
                grid.addWidget(minimum, row_index + 1, 3)
                grid.addWidget(maximum, row_index + 1, 4)
                continue

            available_columns = tuple(numeric_columns)
            if self._special_time_row and time_context.column is not None:
                available_columns = tuple(
                    name for name in available_columns if name != time_context.column
                )
            column = QComboBox()
            column.addItem("None", None)
            for name in available_columns:
                column.addItem(str(name), str(name))
            selected_index = column.findData(row.column)
            if selected_index < 0 and row.column is not None:
                column.addItem("%s (unavailable)" % row.column, row.column)
                selected_index = column.findData(row.column)
            column.setCurrentIndex(max(0, selected_index))
            self.column_combos.append(column)
            grid.addWidget(column, row_index + 1, 2)

            minimum = QLineEdit()
            minimum.setPlaceholderText("Unbounded")
            if row.minimum is not None:
                minimum.setText("%.15g" % row.minimum)
            self.minimum_edits.append(minimum)
            grid.addWidget(minimum, row_index + 1, 3)

            maximum = QLineEdit()
            maximum.setPlaceholderText("Unbounded")
            if row.maximum is not None:
                maximum.setText("%.15g" % row.maximum)
            self.maximum_edits.append(maximum)
            grid.addWidget(maximum, row_index + 1, 4)

        layout.addLayout(grid)
        self.error_label = QLabel()
        self.error_label.setWordWrap(True)
        self.error_label.setStyleSheet("color: #b3261e;")
        layout.addWidget(self.error_label)

        buttons = QHBoxLayout()
        self.clear_button = QPushButton("Clear")
        self.apply_button = QPushButton("Apply")
        self.ok_button = QPushButton("OK")
        self.cancel_button = QPushButton("Cancel")
        buttons.addWidget(self.clear_button)
        buttons.addStretch(1)
        buttons.addWidget(self.apply_button)
        buttons.addWidget(self.ok_button)
        buttons.addWidget(self.cancel_button)
        layout.addLayout(buttons)

        self.clear_button.clicked.connect(self.clear)
        self.apply_button.clicked.connect(self.apply)
        self.ok_button.clicked.connect(self.accept)
        self.cancel_button.clicked.connect(self.reject)
        fit_initial_window_width(self, preferred_height=scaled(340))

    def _bound(self, edit: QLineEdit, label: str, row_number: int) -> float | None:
        text = edit.text().strip()
        if not text:
            return None
        try:
            value = float(text)
        except ValueError as exc:
            raise ValueError(
                "Filter row %d: %s must be a finite number" % (row_number, label)
            ) from exc
        if value != value or value in (float("inf"), float("-inf")):
            raise ValueError(
                "Filter row %d: %s must be a finite number" % (row_number, label)
            )
        return value

    def _time_bound(self, edit: TimeBoundEdit, label: str) -> float | None:
        try:
            return edit.value()
        except ValueError as exc:
            raise ValueError("Time row %s: %s" % (label, exc)) from exc

    def _read_filter(self) -> DataFilter:
        rows = []
        if self._special_time_row:
            if self._time_context.column is None:
                rows.append(DataFilterRow())
            else:
                rows.append(
                    DataFilterRow(
                        enabled=self.enabled_checks[0].isChecked(),
                        column=self._time_context.column,
                        minimum=self._time_bound(self.time_minimum_edit, "Min"),
                        maximum=self._time_bound(self.time_maximum_edit, "Max"),
                    )
                )
            start_index = 1
        else:
            start_index = 0

        for index in range(start_index, FILTER_ROW_COUNT):
            row_number = index + 1
            minimum = self._bound(self.minimum_edits[index], "Min", row_number)
            maximum = self._bound(self.maximum_edits[index], "Max", row_number)
            column = self.column_combos[index].currentData()
            if column is None and (minimum is not None or maximum is not None):
                raise ValueError(
                    "Filter row %d: choose a data column or clear Min and Max"
                    % row_number
                )
            try:
                rows.append(
                    DataFilterRow(
                        enabled=self.enabled_checks[index].isChecked(),
                        column=column,
                        minimum=minimum,
                        maximum=maximum,
                    )
                )
            except ValueError as exc:
                raise ValueError("Filter row %d: %s" % (row_number, exc)) from exc
        return DataFilter(tuple(rows), self._overflow_rows)

    def _show_error(self, message: str) -> None:
        self.error_label.setText(message)

    def _commit(self) -> bool:
        try:
            data_filter = self._read_filter()
        except ValueError as exc:
            self._show_error(str(exc))
            return False
        if self._apply_callback is not None:
            try:
                applied = self._apply_callback(data_filter)
            except ValueError as exc:
                self._show_error("Filter not applied: %s" % exc)
                return False
            if applied is False:
                self._show_error("Filter not applied")
                return False
        self.filterApplied.emit(data_filter)
        self.error_label.clear()
        return True

    def apply(self) -> None:
        """Commit valid edits while keeping this dialog open."""

        self._commit()

    def accept(self) -> None:  # noqa: N802
        if self._commit():
            super().accept()

    def clear(self) -> None:
        """Clear the editor; the applied filter changes on Apply or OK."""

        for index, (enabled, column, minimum, maximum) in enumerate(
            zip(
                self.enabled_checks,
                self.column_combos,
                self.minimum_edits,
                self.maximum_edits,
            )
        ):
            enabled.setChecked(False)
            if column is not None and not (
                self._special_time_row and index == 0
            ):
                column.setCurrentIndex(0)
            minimum.clear()
            maximum.clear()
        self.error_label.clear()

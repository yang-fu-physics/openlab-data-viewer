"""Standalone data browser with configurable import and automatic refresh."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide2.QtCore import (
    QObject,
    QSignalBlocker,
    QRunnable,
    QThreadPool,
    Qt,
    QTimer,
    Signal,
)
from PySide2.QtGui import QDragEnterEvent, QDropEvent
from PySide2.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHeaderView,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..data_reader import (
    DataDocument,
    DataFormatOptions,
    DataReadError,
    detect_data_format,
    read_data,
)
from ..plot_format import (
    DisplayFormatTemplate,
    PlotFormatError,
    find_plot_format,
    load_plot_format,
    save_plot_format,
)
from .data_import_dialog import DataImportDialog
from .dat_plot import OVERLAY_LAYOUT, STACKED_LAYOUT, DatPlotCanvas, PlotHit
from .scaling import scaled
from .window_sizing import fit_initial_window_width


class _DataReadSignals(QObject):
    finished = Signal(object, object, int)


class _DataReadTask(QRunnable):
    """Read one automatic refresh without blocking the GUI thread."""

    def __init__(
        self,
        path: Path,
        options: DataFormatOptions,
        generation: int,
    ) -> None:
        super().__init__()
        self.path = path
        self.options = options
        self.generation = generation
        self.signals = _DataReadSignals()

    def run(self) -> None:
        try:
            document = read_data(
                self.path,
                self.options,
                allow_unterminated_last_line=False,
            )
        except (DataReadError, OSError) as exc:
            self.signals.finished.emit(None, exc, self.generation)
            return
        self.signals.finished.emit(document, None, self.generation)


class PointDetailsDialog(QDialog):
    """Show the complete source row represented by a plotted point."""

    def __init__(
        self,
        document: DataDocument,
        hit: PlotHit,
        x_label: str,
        x_value_text: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        point = hit.point
        source_line = point.source_line_number or document.source_line_number(point.row_index)
        self.setWindowTitle("Data Point Details - Source Line %d" % source_line)
        layout = QVBoxLayout(self)
        displayed_x = x_value_text if x_value_text is not None else "%.12g" % point.x
        self.summary_label = QLabel(
            "File: %s\n"
            "Data row: %d    Source line: %d    %s: %s    %s: %.12g"
            % (
                document.path,
                point.row_index + 1,
                source_line,
                x_label,
                displayed_x,
                hit.series,
                point.y,
            )
        )
        self.summary_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.summary_label.setWordWrap(True)
        layout.addWidget(self.summary_label)

        table = QTableWidget(len(document.columns), 2)
        table.setHorizontalHeaderLabels(["Field", "Value"])
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.verticalHeader().setVisible(False)
        for row_index, (column, value) in enumerate(zip(document.columns, point.row)):
            table.setItem(row_index, 0, QTableWidgetItem(column))
            table.setItem(row_index, 1, QTableWidgetItem(value))
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        layout.addWidget(table, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.accept)
        layout.addWidget(buttons)
        fit_initial_window_width(self, preferred_height=scaled(470))


class DatBrowserWidget(QWidget):
    """A file-bound viewer that never follows the measurement controller."""

    fileChanged = Signal(str)
    formatChanged = Signal(object)
    displayFormatChanged = Signal(object)

    def __init__(
        self,
        start_directory: Path,
        parent: QWidget | None = None,
        *,
        allow_import: bool = True,
        explicit_plot_save: bool = True,
        initial_format_options: DataFormatOptions | None = None,
        initial_display_format: DisplayFormatTemplate | None = None,
        open_files_callback=None,
        open_paths_callback=None,
    ) -> None:
        super().__init__(parent)
        self.start_directory = Path(start_directory).resolve()
        self.current_path: Path | None = None
        self._pending_import_path: Path | None = None
        self.document: DataDocument | None = None
        self.format_options = (
            initial_format_options
            if initial_format_options is not None
            else DataFormatOptions.openlab()
        )
        self._signature: tuple[int, int] | None = None
        self._read_generation = 0
        self._refresh_in_flight = False
        self._refresh_task: _DataReadTask | None = None
        self._initial_display_format = initial_display_format
        self._suspend_format_save = False
        self._format_status = ""
        self._schema_status = ""
        self._last_auto_save_error: str | None = None
        self.allow_import = allow_import
        self.explicit_plot_save = explicit_plot_save
        self.open_files_callback = open_files_callback
        self.open_paths_callback = open_paths_callback
        self.setAcceptDrops(True)

        layout = QVBoxLayout(self)
        path_row = QHBoxLayout()
        self.path_label = QLabel("No data file selected - drop a file anywhere in this window")
        self.path_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.path_label.setWordWrap(True)
        path_row.addWidget(self.path_label, 1)
        layout.addLayout(path_row)

        controls = QGridLayout()
        self.layout_combo = QComboBox()
        self.layout_combo.setToolTip("Overlay Y series or stack plots with a shared X axis")
        self.layout_combo.setMinimumWidth(scaled(110))
        self.layout_combo.addItem("Overlay", OVERLAY_LAYOUT)
        self.layout_combo.addItem("Stacked", STACKED_LAYOUT)
        open_button = QPushButton("Open Data")
        import_button = QPushButton("Import Settings")
        reload_button = QPushButton("Reload")
        self.save_format_button = QPushButton("Save PLT")
        reset_button = QPushButton("Reset Zoom")
        self.auto_refresh_checkbox = QCheckBox("Auto-refresh")
        self.auto_refresh_checkbox.setToolTip("Poll the current file every 5 seconds")
        self.auto_refresh_checkbox.setChecked(True)
        controls.addWidget(QLabel("Layout:"), 0, 0)
        controls.addWidget(self.layout_combo, 0, 1)
        controls.addWidget(open_button, 0, 2)
        controls.addWidget(import_button, 0, 3)
        controls.addWidget(reload_button, 0, 4)
        controls.addWidget(self.save_format_button, 1, 0)
        controls.addWidget(reset_button, 1, 1)
        controls.addWidget(self.auto_refresh_checkbox, 1, 2)
        controls.setColumnStretch(5, 1)
        layout.addLayout(controls)

        self.canvas = DatPlotCanvas()
        layout.addWidget(self.canvas, 1)
        self.status_label = QLabel("Waiting for a data file")
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet("color: #5d6672;")
        layout.addWidget(self.status_label)

        open_button.clicked.connect(self.open_dialog)
        import_button.clicked.connect(self.import_settings)
        reload_button.clicked.connect(self.reload)
        self.save_format_button.clicked.connect(
            lambda checked=False: self.save_format(show_errors=True)
        )
        reset_button.clicked.connect(lambda checked=False: self.canvas.reset_zoom())
        self.layout_combo.currentIndexChanged.connect(self._layout_selected)
        self.canvas.openRequested.connect(self.open_dialog)
        self.canvas.reloadRequested.connect(self.reload)
        self.canvas.saveFormatRequested.connect(
            lambda: self.save_format(show_errors=True)
        )
        self.canvas.reloadFormatRequested.connect(self.reload_format)
        self.canvas.axesChanged.connect(self._update_status)
        self.canvas.displayChanged.connect(self._display_changed)
        self.canvas.pointActivated.connect(self._show_point_details)

        self.monitor_timer = QTimer(self)
        self.monitor_timer.setInterval(5000)
        self.monitor_timer.timeout.connect(self._check_for_updates)
        self.auto_refresh_checkbox.toggled.connect(self._toggle_auto_refresh)
        self.monitor_timer.start()

    def canvas_reset_zoom(self) -> None:
        """Reset the active plot range for a parent window menu."""

        self.canvas.reset_zoom()

    def open_dialog(self) -> None:
        """Open one file, or delegate selection to the multi-window session."""

        if self.open_files_callback is not None:
            self.open_files_callback()
            return
        directory = (
            self.current_path.parent
            if self.current_path is not None
            else self.start_directory
        )
        dialog = QFileDialog(self, "Open Data File", str(directory))
        dialog.setOption(QFileDialog.DontUseNativeDialog, True)
        dialog.setFileMode(QFileDialog.ExistingFile)
        dialog.setNameFilter("Data files (*.dat *.csv *.tsv *.txt);;All files (*)")
        if dialog.exec_() == QDialog.Accepted:
            selected = dialog.selectedFiles()
            if selected:
                self.load_path(selected[0], show_errors=True)

    def import_settings(self) -> None:
        """Open the format dialog for the current or failed file."""

        source = self._pending_import_path or self.current_path
        if source is None:
            QMessageBox.information(
                self,
                "Import Data Settings",
                "Open a data file before changing its import settings.",
            )
            return
        self._open_import_dialog(source, self.format_options)

    def _open_import_dialog(
        self,
        source: Path,
        initial_options: DataFormatOptions,
    ) -> bool:
        """Let the user configure the file that automatic detection could not read."""

        self._pending_import_path = source
        self.status_label.setText(
            "Choose import settings for %s" % source.name
        )
        dialog = DataImportDialog(source, initial_options, self)
        try:
            if dialog.exec_() == QDialog.Accepted:
                return self.load_path(
                    source,
                    show_errors=True,
                    format_options=dialog.format_options(),
                    from_import_dialog=True,
                )
        finally:
            dialog.deleteLater()
        return False

    def load_path(
        self,
        path: str | Path,
        show_errors: bool = True,
        *,
        format_options: DataFormatOptions | None = None,
        automatic: bool = False,
        from_import_dialog: bool = False,
    ) -> bool:
        """Read a file and commit the new document only after a complete read."""

        source = Path(path).resolve()
        if not automatic:
            self._read_generation += 1
            self._refresh_in_flight = False
        same_file = self.current_path == source and self.document is not None
        selected_options = format_options
        document = None
        read_error = None
        try:
            if selected_options is None:
                if same_file:
                    selected_options = self.format_options
                else:
                    selected_options = detect_data_format(source)
                    if selected_options is None:
                        self._pending_import_path = source
                        if show_errors and self.allow_import:
                            return self._open_import_dialog(
                                source,
                                self.format_options,
                            )
                        self.status_label.setText(
                            "Unable to determine the format of %s" % source.name
                        )
                        return False
            document = read_data(
                source,
                selected_options,
                allow_unterminated_last_line=not automatic,
            )
        except (DataReadError, OSError) as exc:
            read_error = exc
            if (
                not automatic
                and not from_import_dialog
                and not same_file
                and selected_options is not None
            ):
                try:
                    detected_options = detect_data_format(source)
                except (DataReadError, OSError):
                    detected_options = None
                if (
                    detected_options is not None
                    and detected_options != selected_options
                ):
                    try:
                        document = read_data(
                            source,
                            detected_options,
                            allow_unterminated_last_line=True,
                        )
                    except (DataReadError, OSError) as detected_error:
                        read_error = detected_error
                    else:
                        selected_options = detected_options
                        read_error = None
            if read_error is None:
                return self._commit_document(
                    document,
                    selected_options,
                    show_errors=show_errors,
                )
            if automatic:
                self.status_label.setText(
                    "Waiting for a complete update of %s: %s" % (source.name, exc)
                )
                return False
            self._pending_import_path = source
            if show_errors and self.allow_import and not from_import_dialog:
                return self._open_import_dialog(
                    source,
                    selected_options or self.format_options,
                )
            self.status_label.setText("Unable to read %s: %s" % (source.name, exc))
            if show_errors:
                QMessageBox.warning(self, "Unable to Open Data File", str(exc))
            return False

        return self._commit_document(document, selected_options, show_errors=show_errors)

    def _commit_document(
        self,
        document: DataDocument,
        selected_options: DataFormatOptions,
        *,
        show_errors: bool,
    ) -> bool:
        """Commit a complete read and apply the best available display state."""

        source = document.path
        same_file = self.current_path == source and self.document is not None
        previous_x = self.canvas.x_column
        previous_y = self.canvas.y_columns
        numeric_columns = set(document.numeric_columns())
        schema_changed = same_file and (
            (previous_x is not None and previous_x not in numeric_columns)
            or any(name not in numeric_columns for name in previous_y)
        )
        preserve_view = (
            same_file
            and selected_options == self.format_options
            and not schema_changed
        )
        new_file = not same_file
        self.current_path = source
        self.document = document
        self.format_options = selected_options
        if self._pending_import_path == source:
            self._pending_import_path = None
        self._signature = (document.modified_ns, document.size_bytes)
        self._schema_status = (
            "Schema changed; previous axis selections were adjusted"
            if schema_changed
            else ""
        )
        self.path_label.setText(str(source))

        format_error: str | None = None
        format_loaded = False
        self._suspend_format_save = True
        try:
            self.canvas.set_document(document, preserve_view=preserve_view)
            if new_file:
                settings_path = find_plot_format(source, exact_name=True)
                if settings_path is not None:
                    try:
                        self.canvas.apply_plot_format(load_plot_format(settings_path))
                        self._format_status = "PLT: %s loaded" % settings_path.name
                        format_loaded = True
                    except PlotFormatError as exc:
                        format_error = str(exc)
                        self._format_status = "PLT ignored: %s" % settings_path.name
                elif self._initial_display_format is not None:
                    template = self._initial_display_format
                    columns_applied = self.canvas.try_apply_display_format(template)
                    if columns_applied:
                        self._format_status = "Previous display settings applied"
                    elif len(document.columns) != template.column_count:
                        self._format_status = (
                            "Previous layout applied; column count differs"
                        )
                self._initial_display_format = None
        finally:
            self._suspend_format_save = False

        self._sync_layout_control()
        if new_file and not format_loaded and format_error is None and not self.explicit_plot_save:
            self.save_format(show_errors=False)
        self._update_status(self.canvas.x_label, self.canvas.y_columns)
        self.fileChanged.emit(str(source))
        self.formatChanged.emit(selected_options)
        self._emit_display_format()
        if format_error is not None and show_errors:
            QMessageBox.warning(
                self,
                "Unable to Apply Plot Format",
                "The data file was loaded, but its PLT settings were ignored.\n\n%s"
                % format_error,
            )
        return True

    def reload(self) -> None:
        """Manually read the current file without changing its import settings."""

        if self.current_path is None:
            self.open_dialog()
        else:
            self.load_path(
                self.current_path,
                show_errors=True,
                format_options=self.format_options,
            )

    def save_format(self, show_errors: bool = True) -> bool:
        """Save the current plot state beside the data file."""

        if self.current_path is None or not self.canvas.y_columns:
            if show_errors:
                QMessageBox.information(
                    self,
                    "Save Plot Format",
                    "Open a plottable data file first.",
                )
            return False
        try:
            settings = self.canvas.to_plot_format(self.current_path.name)
            destination = save_plot_format(
                self.current_path,
                settings,
                exact_name=True,
            )
        except PlotFormatError as exc:
            message = str(exc)
            self._format_status = "PLT: save failed"
            if show_errors:
                QMessageBox.warning(self, "Unable to Save Plot Format", message)
            elif message != self._last_auto_save_error:
                self.status_label.setText(message)
            self._last_auto_save_error = message
            return False
        self._last_auto_save_error = None
        self._format_status = "PLT: %s" % destination.name
        if show_errors:
            self._update_status(self.canvas.x_label, self.canvas.y_columns)
        return True

    def reload_format(self) -> None:
        """Apply the matching PLT without rereading the data file."""

        if self.current_path is None:
            QMessageBox.information(self, "Reload Plot Format", "Open a data file first.")
            return
        settings_path = find_plot_format(self.current_path, exact_name=True)
        if settings_path is None:
            QMessageBox.information(
                self,
                "Reload Plot Format",
                "No matching PLT file was found beside this data file.",
            )
            return
        try:
            settings = load_plot_format(settings_path)
            self._suspend_format_save = True
            self.canvas.apply_plot_format(settings)
        except PlotFormatError as exc:
            QMessageBox.warning(self, "Unable to Apply Plot Format", str(exc))
            return
        finally:
            self._suspend_format_save = False
        self._format_status = "PLT: %s loaded" % settings_path.name
        self._sync_layout_control()
        self._update_status(self.canvas.x_label, self.canvas.y_columns)
        self._emit_display_format()

    def _layout_selected(self, index: int) -> None:
        layout = self.layout_combo.itemData(index)
        if layout:
            self.canvas.set_layout(str(layout))

    def _sync_layout_control(self) -> None:
        index = self.layout_combo.findData(self.canvas.layout_mode)
        if index >= 0:
            blocker = QSignalBlocker(self.layout_combo)
            self.layout_combo.setCurrentIndex(index)
            del blocker

    def _display_changed(self) -> None:
        self._sync_layout_control()
        if not self._suspend_format_save and not self.explicit_plot_save:
            self.save_format(show_errors=False)
        self._update_status(self.canvas.x_label, self.canvas.y_columns)
        self._emit_display_format()

    def _emit_display_format(self) -> None:
        if self.current_path is None or self.document is None or not self.canvas.y_columns:
            return
        plot_format = self.canvas.to_plot_format(self.current_path.name)
        columns = self.document.columns
        x_column_index = (
            None
            if self.canvas.x_column is None
            else columns.index(self.canvas.x_column)
        )
        self.displayFormatChanged.emit(
            DisplayFormatTemplate(
                plot_format=plot_format,
                column_count=len(columns),
                x_column_index=x_column_index,
                y_column_indices=tuple(
                    columns.index(name) for name in self.canvas.y_columns
                ),
                stacked_y_ranges=tuple(
                    plot_format.stacked_y_ranges.get(name)
                    for name in self.canvas.y_columns
                ),
            )
        )

    def _toggle_auto_refresh(self, enabled: bool) -> None:
        if enabled:
            self.monitor_timer.start()
        else:
            self.monitor_timer.stop()

    def _check_for_updates(self) -> None:
        if self.current_path is None:
            return
        try:
            stat = self.current_path.stat()
        except OSError:
            self.status_label.setText(
                "File unavailable; waiting to retry: %s" % self.current_path
            )
            return
        signature = (stat.st_mtime_ns, stat.st_size)
        if signature != self._signature and not self._refresh_in_flight:
            self._start_background_reload()

    def _start_background_reload(self) -> None:
        if self.current_path is None:
            return
        self._read_generation += 1
        generation = self._read_generation
        task = _DataReadTask(self.current_path, self.format_options, generation)
        self._refresh_in_flight = True
        self._refresh_task = task
        task.signals.finished.connect(self._background_read_finished)
        QThreadPool.globalInstance().start(task)

    def _background_read_finished(
        self,
        document: DataDocument | None,
        error: DataReadError | None,
        generation: int,
    ) -> None:
        if generation != self._read_generation:
            return
        self._refresh_in_flight = False
        self._refresh_task = None
        if error is not None:
            if self.current_path is not None:
                self.status_label.setText(
                    "Waiting for a complete update of %s: %s"
                    % (self.current_path.name, error)
                )
            return
        self._commit_document(
            document,
            self.format_options,
            show_errors=False,
        )

    def _update_status(self, x_label: str, y_columns: object) -> None:
        if self.document is None:
            return
        names = (
            tuple(str(name) for name in y_columns)
            if isinstance(y_columns, (tuple, list))
            else (str(y_columns),)
        )
        y_text = ", ".join(names) if names else "None"
        layout = "Overlay" if self.canvas.layout_mode == OVERLAY_LAYOUT else "Stacked / Shared X"
        format_text = " | %s" % self._format_status if self._format_status else ""
        schema_text = " | %s" % self._schema_status if self._schema_status else ""
        refresh_text = "on" if self.auto_refresh_checkbox.isChecked() else "off"
        self.status_label.setText(
            "%d rows | X: %s [%s] | Y: %s [%s] | %s | refreshed %s | auto-refresh %s%s%s"
            % (
                len(self.document.rows),
                x_label,
                self.canvas.x_scale.title(),
                y_text,
                self.canvas.y_scale.title(),
                layout,
                datetime.now().strftime("%H:%M:%S"),
                refresh_text,
                format_text,
                schema_text,
            )
        )

    def _show_point_details(self, hit: PlotHit) -> None:
        if self.document is None:
            return
        dialog = PointDetailsDialog(
            self.document,
            hit,
            self.canvas.x_label,
            self.canvas.format_x_value(hit.x, full=True),
            self,
        )
        try:
            dialog.exec_()
        finally:
            dialog.deleteLater()

    @staticmethod
    def _data_paths(event: QDragEnterEvent | QDropEvent) -> tuple[Path, ...]:
        """Return existing local files from a drag-and-drop event."""

        if not event.mimeData().hasUrls():
            return ()
        paths = []
        for url in event.mimeData().urls():
            if url.isLocalFile():
                path = Path(url.toLocalFile())
                if path.is_file():
                    paths.append(path)
        return tuple(paths)

    @classmethod
    def _first_data_path(cls, event: QDragEnterEvent | QDropEvent) -> Path | None:
        paths = cls._data_paths(event)
        return paths[0] if paths else None

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802
        if self._first_data_path(event) is not None:
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802
        paths = self._data_paths(event)
        if not paths:
            event.ignore()
            return
        if self.open_paths_callback is not None:
            self.open_paths_callback(paths)
            event.acceptProposedAction()
            return
        if self.load_path(paths[0], show_errors=True):
            event.acceptProposedAction()
        else:
            event.ignore()

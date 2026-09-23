"""Main window and MDI data-view subwindows."""

from __future__ import annotations

from pathlib import Path

from PySide2.QtCore import QEvent, QTimer, Qt, Signal
from PySide2.QtWidgets import (
    QAction,
    QMainWindow,
    QMdiArea,
    QMdiSubWindow,
    QMessageBox,
)

from ..data_reader import DataFormatOptions
from ..plot_format import DisplayFormatTemplate
from .data_browser import DatBrowserWidget
from .scaling import scaled


class DataViewerMdiArea(QMdiArea):
    """MDI surface that accepts local data-file drops outside child views."""

    filesDropped = Signal(object)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.viewport().setAcceptDrops(True)
        self.viewport().installEventFilter(self)

    def eventFilter(self, watched, event) -> bool:  # noqa: N802
        if watched is self.viewport():
            if event.type() == QEvent.DragEnter:
                self.dragEnterEvent(event)
                return True
            if event.type() == QEvent.DragMove:
                if DatBrowserWidget._first_data_path(event) is not None:
                    event.acceptProposedAction()
                else:
                    event.ignore()
                return True
            if event.type() == QEvent.Drop:
                self.dropEvent(event)
                return True
        return super().eventFilter(watched, event)

    def dragEnterEvent(self, event) -> None:  # noqa: N802
        if DatBrowserWidget._first_data_path(event) is not None:
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event) -> None:  # noqa: N802
        paths = DatBrowserWidget._data_paths(event)
        if not paths:
            event.ignore()
            return
        self.filesDropped.emit(paths)
        event.acceptProposedAction()


class DataViewerWindow(QMainWindow):
    """The application window that owns all independent data views."""

    openFilesRequested = Signal(object)
    openPathsRequested = Signal(object, object)
    newWindowRequested = Signal()
    formatChanged = Signal(object)
    displayFormatChanged = Signal(object)

    def __init__(self, start_directory: Path, parent=None) -> None:
        super().__init__(parent)
        self.start_directory = Path(start_directory).resolve()
        self.mdi_area = DataViewerMdiArea(self)
        self.mdi_area.setViewMode(QMdiArea.SubWindowView)
        self.mdi_area.filesDropped.connect(self._drop_paths)
        self.mdi_area.subWindowActivated.connect(
            self._schedule_minimized_views
        )
        self.setCentralWidget(self.mdi_area)
        self.setAcceptDrops(True)
        self.setMinimumSize(scaled(760), scaled(520))
        self.resize(1280, 820)
        self._build_menu()
        self.setWindowTitle("OpenLab Data Viewer")

    def add_browser(
        self,
        format_options: DataFormatOptions | None = None,
        display_format: DisplayFormatTemplate | None = None,
    ) -> DatBrowserWidget:
        """Add and show one independent data browser subwindow."""

        browser = DatBrowserWidget(
            self.start_directory,
            None,
            allow_import=True,
            explicit_plot_save=True,
            initial_format_options=format_options,
            initial_display_format=display_format,
        )
        browser.open_files_callback = (
            lambda browser=browser: self._request_open_files(browser)
        )
        browser.open_paths_callback = (
            lambda paths, browser=browser: self._request_open_paths(browser, paths)
        )

        subwindow = self.mdi_area.addSubWindow(browser)
        subwindow.setAttribute(Qt.WA_DeleteOnClose)
        subwindow.installEventFilter(self)
        subwindow.resize(980, 660)
        subwindow.setWindowTitle("Data View")
        browser.fileChanged.connect(
            lambda path, subwindow=subwindow: self._subwindow_file_changed(
                subwindow, path
            )
        )
        browser.formatChanged.connect(
            lambda options: self.formatChanged.emit(options)
        )
        browser.displayFormatChanged.connect(
            lambda options: self.displayFormatChanged.emit(options)
        )
        subwindow.show()
        self._place_new_subwindow(subwindow)
        self.mdi_area.setActiveSubWindow(subwindow)
        self._schedule_minimized_views()
        return browser

    def _place_new_subwindow(self, subwindow: QMdiSubWindow) -> None:
        """Offset newly opened views so their titles and status remain visible."""

        index = self.mdi_area.subWindowList().index(subwindow)
        offset = scaled(28)
        area = self.mdi_area.viewport().rect()
        max_x = max(0, area.width() - subwindow.width() - offset)
        max_y = max(0, area.height() - subwindow.height() - offset)
        subwindow.move(
            min(index * offset, max_x),
            min(index * offset, max_y),
        )

    def eventFilter(self, watched, event) -> bool:  # noqa: N802
        if (
            isinstance(watched, QMdiSubWindow)
            and event.type() == QEvent.WindowStateChange
        ):
            self._schedule_minimized_views()
        return super().eventFilter(watched, event)

    def _schedule_minimized_views(self, *args) -> None:
        QTimer.singleShot(0, self._keep_minimized_views_visible)

    def _keep_minimized_views_visible(self) -> None:
        area = self.mdi_area.viewport().rect()
        margin = scaled(6)
        row_height = scaled(28)
        x = margin
        y = max(margin, area.height() - row_height - margin)
        for subwindow in self.mdi_area.subWindowList():
            if not subwindow.isMinimized():
                continue
            width = max(margin, min(subwindow.width(), area.width() - margin * 2))
            if x + width > area.width() - margin:
                x = margin
                y = max(margin, y - row_height - margin)
            subwindow.move(x, y)
            subwindow.raise_()
            x += width + margin

    def active_browser(self) -> DatBrowserWidget | None:
        """Return the browser in the active MDI subwindow."""

        subwindow = self.mdi_area.activeSubWindow()
        if subwindow is None:
            return None
        browser = subwindow.widget()
        return browser if isinstance(browser, DatBrowserWidget) else None

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("File")
        open_action = QAction("Open Files...", self)
        open_action.triggered.connect(
            lambda checked=False: self._request_open_files(self.active_browser())
        )
        file_menu.addAction(open_action)

        new_action = QAction("New Data View", self)
        new_action.triggered.connect(
            lambda checked=False: self.newWindowRequested.emit()
        )
        file_menu.addAction(new_action)

        import_action = QAction("Import Settings", self)
        import_action.triggered.connect(
            lambda checked=False: self._import_active()
        )
        file_menu.addAction(import_action)

        save_action = QAction("Save PLT", self)
        save_action.triggered.connect(
            lambda checked=False: self._save_active_format()
        )
        file_menu.addAction(save_action)

        file_menu.addSeparator()
        close_action = QAction("Close Active Data View", self)
        close_action.triggered.connect(
            lambda checked=False: self._close_active_subwindow()
        )
        file_menu.addAction(close_action)

        close_all_action = QAction("Close All Data Views", self)
        close_all_action.triggered.connect(
            lambda checked=False: self.mdi_area.closeAllSubWindows()
        )
        file_menu.addAction(close_all_action)

        file_menu.addSeparator()
        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(lambda checked=False: self.close())
        file_menu.addAction(exit_action)

        view_menu = self.menuBar().addMenu("View")
        reset_action = QAction("Reset Zoom", self)
        reset_action.triggered.connect(
            lambda checked=False: self._reset_active_zoom()
        )
        view_menu.addAction(reset_action)

        tile_action = QAction("Tile Data Views", self)
        tile_action.triggered.connect(
            lambda checked=False: self.mdi_area.tileSubWindows()
        )
        view_menu.addAction(tile_action)

        cascade_action = QAction("Cascade Data Views", self)
        cascade_action.triggered.connect(
            lambda checked=False: self.mdi_area.cascadeSubWindows()
        )
        view_menu.addAction(cascade_action)

        help_menu = self.menuBar().addMenu("Help")
        about_action = QAction("About OpenLab Data Viewer", self)
        about_action.triggered.connect(lambda checked=False: self._show_about())
        help_menu.addAction(about_action)

    def _request_open_files(self, source_browser: DatBrowserWidget | None) -> None:
        self.openFilesRequested.emit(source_browser)

    def _request_open_paths(
        self,
        source_browser: DatBrowserWidget,
        paths,
    ) -> None:
        self.openPathsRequested.emit(source_browser, tuple(paths))

    def _drop_paths(self, paths) -> None:
        self.openPathsRequested.emit(self.active_browser(), tuple(paths))

    def dragEnterEvent(self, event) -> None:  # noqa: N802
        if DatBrowserWidget._first_data_path(event) is not None:
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event) -> None:  # noqa: N802
        paths = DatBrowserWidget._data_paths(event)
        if not paths:
            event.ignore()
            return
        self._drop_paths(paths)
        event.acceptProposedAction()

    @staticmethod
    def _subwindow_file_changed(subwindow: QMdiSubWindow, path: str) -> None:
        if path:
            subwindow.setWindowTitle("Data View - %s" % Path(path).name)
        else:
            subwindow.setWindowTitle("Data View")

    def _import_active(self) -> None:
        browser = self.active_browser()
        if browser is not None:
            browser.import_settings()

    def _save_active_format(self) -> None:
        browser = self.active_browser()
        if browser is not None:
            browser.save_format(show_errors=True)

    def _reset_active_zoom(self) -> None:
        browser = self.active_browser()
        if browser is not None:
            browser.canvas_reset_zoom()

    def _close_active_subwindow(self) -> None:
        subwindow = self.mdi_area.activeSubWindow()
        if subwindow is not None:
            subwindow.close()

    def _show_about(self) -> None:
        QMessageBox.about(
            self,
            "About OpenLab Data Viewer",
            "OpenLab Data Viewer\n\n"
            "A standalone viewer for OpenLab and delimited text data files.\n"
            "Each data view is an independent subwindow in this application window.",
        )

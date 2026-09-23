"""Application entry point and MDI session manager."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable

from PySide2.QtCore import QTimer, Qt
from PySide2.QtWidgets import QApplication, QFileDialog

from .data_reader import DataFormatOptions
from .plot_format import DisplayFormatTemplate
from .ui.application_style import configure_qt_appearance
from .ui.data_browser import DatBrowserWidget
from .ui.data_viewer_window import DataViewerWindow


DATA_FILE_FILTER = "Data files (*.dat *.csv *.tsv *.txt);;All files (*)"


class DataViewerSession:
    """Own one application window and its independent MDI data views."""

    def __init__(self, start_directory: Path) -> None:
        self.start_directory = Path(start_directory).resolve()
        self.last_format_options = DataFormatOptions.openlab()
        self.last_display_format: DisplayFormatTemplate | None = None
        self.main_window = DataViewerWindow(self.start_directory)
        self.main_window.openFilesRequested.connect(self.open_dialog)
        self.main_window.openPathsRequested.connect(
            lambda source, paths: self.open_paths(paths, source)
        )
        self.main_window.newWindowRequested.connect(self.new_subwindow)
        self.main_window.formatChanged.connect(self._format_changed)
        self.main_window.displayFormatChanged.connect(
            self._display_format_changed
        )

    def new_subwindow(
        self,
        path: str | Path | None = None,
    ) -> DatBrowserWidget:
        """Create a child view using the latest successful import format."""

        browser = self.main_window.add_browser(
            self.last_format_options,
            self.last_display_format,
        )
        if path is not None:
            browser.load_path(path, show_errors=True)
        return browser

    def open_dialog(self, source_browser: DatBrowserWidget | None) -> None:
        directory = (
            source_browser.current_path.parent
            if source_browser is not None and source_browser.current_path is not None
            else self.start_directory
        )
        dialog = QFileDialog(self.main_window, "Open Data Files", str(directory))
        dialog.setOption(QFileDialog.DontUseNativeDialog, True)
        dialog.setFileMode(QFileDialog.ExistingFiles)
        dialog.setNameFilter(DATA_FILE_FILTER)
        paths = dialog.selectedFiles() if dialog.exec_() else []
        if paths:
            self.open_paths(paths, source_browser)

    def open_paths(
        self,
        paths: Iterable[str | Path],
        source_browser: DatBrowserWidget | None = None,
    ) -> None:
        selected = tuple(Path(path) for path in paths)
        if not selected:
            return

        target = (
            source_browser
            if source_browser is not None and source_browser.current_path is None
            else self.new_subwindow()
        )
        target.load_path(selected[0], show_errors=True)
        for path in selected[1:]:
            self.new_subwindow(path)

    def _format_changed(self, options: DataFormatOptions) -> None:
        self.last_format_options = options

    def _display_format_changed(self, template: DisplayFormatTemplate) -> None:
        self.last_display_format = template


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="OpenLab Data Viewer")
    parser.add_argument(
        "--data-file",
        action="append",
        default=[],
        help="Open a data file; repeat the option to open multiple data views.",
    )
    parser.add_argument(
        "--start-directory",
        default=".",
        help="Initial directory used by the file picker.",
    )
    parser.add_argument(
        "--scale",
        type=float,
        default=None,
        help="Override the automatic UI scale.",
    )
    parser.add_argument(
        "--font-scale",
        type=float,
        default=1.0,
        help="Multiply the application font size.",
    )
    parser.add_argument(
        "--gui-smoke",
        action="store_true",
        help="Open the UI briefly and exit; intended for packaging checks.",
    )
    parser.add_argument(
        "--screenshot",
        default=None,
        help="Save the main window screenshot before a GUI smoke exit.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    application = QApplication.instance()
    if application is None:
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps)
        application = QApplication([])
    application.setApplicationName("OpenLab Data Viewer")
    application.setOrganizationName("OpenLab")
    application.setQuitOnLastWindowClosed(True)
    configure_qt_appearance(application, args.scale, args.font_scale)
    session = DataViewerSession(Path(args.start_directory))
    session.main_window.show()
    if args.data_file:
        session.open_paths(args.data_file)
    else:
        session.new_subwindow()

    if args.screenshot or args.gui_smoke:

        def finish_smoke() -> None:
            if args.screenshot:
                session.main_window.grab().save(
                    str(Path(args.screenshot).resolve())
                )
            session.main_window.close()
            application.quit()

        QTimer.singleShot(250 if args.screenshot else 100, finish_smoke)
    return application.exec_()

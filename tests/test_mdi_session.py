from __future__ import annotations

import os
import sys
import tempfile
import time
import unittest
from importlib.util import find_spec
from pathlib import Path


VIEWER_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VIEWER_ROOT / "src"))


@unittest.skipUnless(find_spec("PySide2") is not None, "PySide2 is required")
class MdiSessionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide2.QtWidgets import QApplication

        cls.application = QApplication.instance() or QApplication([])
        from openlab_viewer.data_reader import DataFormatOptions
        from openlab_viewer.data_viewer_app import DataViewerSession
        from openlab_viewer.ui.dat_plot import STACKED_LAYOUT

        cls.DataFormatOptions = DataFormatOptions
        cls.DataViewerSession = DataViewerSession
        cls.STACKED_LAYOUT = STACKED_LAYOUT

    def test_child_views_share_main_window_and_inherit_recent_format(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        path = Path(temporary.name) / "custom.csv"
        path.write_text("metadata\nx;y\n1;2\n3;4\n5;6\n", encoding="utf-8")

        session = self.DataViewerSession(Path("."))
        self.addCleanup(session.main_window.close)
        session.main_window.show()

        first = session.new_subwindow()
        options = self.DataFormatOptions(
            mode="custom",
            header_line=2,
            data_start_line=3,
            delimiter="semicolon",
            encoding="utf-8",
        )
        self.assertTrue(
            first.load_path(path, show_errors=False, format_options=options)
        )
        self.assertEqual(session.last_format_options, options)

        second = session.new_subwindow()
        self.assertEqual(second.format_options, options)
        self.assertEqual(
            len(session.main_window.mdi_area.subWindowList()),
            2,
        )

        self.assertTrue(
            second.load_path(path, show_errors=False, format_options=options)
        )
        session.open_paths((path,), second)
        self.assertEqual(
            len(session.main_window.mdi_area.subWindowList()),
            3,
        )
        self.application.processEvents()

    def test_failed_new_file_keeps_pending_import_target(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        valid_path = Path(temporary.name) / "valid.csv"
        valid_path.write_text("x;y\n1;2\n3;4\n5;6\n", encoding="utf-8")
        ambiguous_path = Path(temporary.name) / "ambiguous.text"
        ambiguous_path.write_text(
            "metadata\none line\nanother line\n",
            encoding="utf-8",
        )

        session = self.DataViewerSession(Path("."))
        self.addCleanup(session.main_window.close)
        browser = session.new_subwindow()
        self.assertTrue(browser.load_path(valid_path, show_errors=False))

        requests = []
        browser._open_import_dialog = (
            lambda source, initial_options: requests.append(
                (source, initial_options)
            )
            or False
        )
        self.assertFalse(browser.load_path(ambiguous_path, show_errors=True))
        self.assertEqual(requests[0][0], ambiguous_path.resolve())
        self.assertEqual(browser._pending_import_path, ambiguous_path.resolve())
        self.assertEqual(browser.current_path, valid_path.resolve())

    def test_new_file_falls_back_to_automatic_format_detection(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        path = Path(temporary.name) / "detected.csv"
        path.write_text("x;y\n1;2\n3;4\n5;6\n", encoding="utf-8")

        session = self.DataViewerSession(Path("."))
        self.addCleanup(session.main_window.close)
        browser = session.new_subwindow()
        self.assertTrue(
            browser.load_path(
                path,
                show_errors=False,
                format_options=self.DataFormatOptions.openlab(),
            )
        )
        self.assertEqual(browser.format_options.mode, "custom")
        self.assertEqual(browser.format_options.delimiter, "semicolon")
        self.assertEqual(browser.format_options.header_line, 1)
        self.assertEqual(browser.format_options.data_start_line, 2)

    def test_new_views_try_to_inherit_display_columns_layout_and_scales(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        first_path = Path(temporary.name) / "sample_003.text"
        second_path = Path(temporary.name) / "sample_006.text"
        first_path.write_text(
            "Timestamp_003\tSignal_003\tOther_003\n"
            "1\t2\t3\n2\t4\t5\n3\t6\t7\n",
            encoding="utf-8",
        )
        second_path.write_text(
            "Timestamp_006\tOther_006\tSignal_006\n"
            "1\t20\t30\n2\t40\t50\n3\t60\t70\n",
            encoding="utf-8",
        )

        session = self.DataViewerSession(Path("."))
        self.addCleanup(session.main_window.close)
        first = session.new_subwindow()
        options = self.DataFormatOptions(
            mode="custom",
            header_line=1,
            data_start_line=2,
            delimiter="tab",
            encoding="utf-8",
        )
        self.assertTrue(
            first.load_path(first_path, show_errors=False, format_options=options)
        )
        self.assertTrue(
            first.canvas.set_axes(
                "Timestamp_003",
                ("Signal_003", "Other_003"),
            )
        )
        self.assertTrue(first.canvas.set_layout(self.STACKED_LAYOUT))
        self.assertTrue(first.canvas.set_x_scale("log"))
        self.assertTrue(first.canvas.set_y_scale("log"))
        self.assertIsNotNone(session.last_display_format)

        second = session.new_subwindow()
        self.assertEqual(second.format_options, options)
        self.assertTrue(
            second.load_path(
                second_path,
                show_errors=False,
                format_options=options,
            )
        )
        self.assertEqual(second.canvas.x_column, second.document.columns[0])
        self.assertEqual(
            second.canvas.y_columns,
            (second.document.columns[1], second.document.columns[2]),
        )
        self.assertEqual(second.canvas.layout_mode, self.STACKED_LAYOUT)
        self.assertEqual(second.canvas.x_scale, "log")
        self.assertEqual(second.canvas.y_scale, "log")

        third_path = Path(temporary.name) / "sample_009.text"
        third_path.write_text(
            "Time(s)\tSignal_009\tOther_009\tExtra_009\n"
            "1\t2\t3\t4\n2\t4\t5\t6\n3\t6\t7\t8\n",
            encoding="utf-8",
        )
        third = session.new_subwindow()
        self.assertTrue(
            third.load_path(
                third_path,
                show_errors=False,
                format_options=options,
            )
        )
        self.assertEqual(third.canvas.x_column, "Time(s)")
        self.assertEqual(third.canvas.y_columns, (third.document.columns[1],))
        self.assertEqual(third.canvas.layout_mode, self.STACKED_LAYOUT)
        self.assertEqual(third.canvas.x_scale, "log")
        self.assertEqual(third.canvas.y_scale, "log")

    def test_mdi_area_accepts_dropped_data_files(self) -> None:
        from PySide2.QtCore import QMimeData, QUrl

        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        path = Path(temporary.name) / "dropped.csv"
        path.write_text("x,y\n1,2\n3,4\n5,6\n", encoding="utf-8")

        class DropEvent:
            def __init__(self, source: Path) -> None:
                self.mime_data = QMimeData()
                self.mime_data.setUrls([QUrl.fromLocalFile(str(source))])
                self.accepted = False

            def mimeData(self):
                return self.mime_data

            def acceptProposedAction(self) -> None:
                self.accepted = True

            def ignore(self) -> None:
                self.accepted = False

        session = self.DataViewerSession(Path("."))
        self.addCleanup(session.main_window.close)
        area = session.main_window.mdi_area
        self.assertTrue(area.acceptDrops())
        event = DropEvent(path)
        area.dropEvent(event)
        self.assertTrue(event.accepted)
        self.assertEqual(len(area.subWindowList()), 1)
        self.assertEqual(
            area.subWindowList()[0].widget().current_path,
            path.resolve(),
        )

    def test_minimized_child_is_kept_visible_above_new_views(self) -> None:
        session = self.DataViewerSession(Path("."))
        self.addCleanup(session.main_window.close)
        session.main_window.show()
        first = session.new_subwindow()
        session.new_subwindow()
        first_window = session.main_window.mdi_area.subWindowList()[0]
        first_window.showMinimized()
        session.main_window._keep_minimized_views_visible()
        self.assertTrue(first_window.isMinimized())
        self.assertTrue(first_window.isVisible())
        self.assertTrue(
            session.main_window.mdi_area.rect().contains(first_window.geometry().center())
        )

    def test_new_child_views_are_staggered(self) -> None:
        session = self.DataViewerSession(Path("."))
        self.addCleanup(session.main_window.close)
        session.main_window.show()
        session.new_subwindow()
        session.new_subwindow()
        windows = session.main_window.mdi_area.subWindowList()
        self.assertNotEqual(windows[0].pos(), windows[1].pos())

    def test_file_refresh_recovers_without_blocking_the_gui_callback(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        path = Path(temporary.name) / "live.csv"
        path.write_text("x,y\n1,2\n3,4\n5,6\n", encoding="utf-8")

        session = self.DataViewerSession(Path("."))
        self.addCleanup(session.main_window.close)
        browser = session.new_subwindow()
        self.assertTrue(browser.load_path(path, show_errors=False))
        self.assertEqual(browser.monitor_timer.interval(), 5000)

        path.write_text("x,y\n1,2\n3,4\n5,6\n7,8\n", encoding="utf-8")
        browser._check_for_updates()
        deadline = time.monotonic() + 2.0
        while browser._refresh_in_flight and time.monotonic() < deadline:
            self.application.processEvents()
            time.sleep(0.01)
        self.application.processEvents()
        self.assertFalse(browser._refresh_in_flight)
        self.assertEqual(len(browser.document.rows), 4)


if __name__ == "__main__":
    unittest.main()

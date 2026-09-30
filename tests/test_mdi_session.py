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
        from PySide2.QtCore import Qt
        from PySide2.QtWidgets import (
            QApplication,
            QCheckBox,
            QDateTimeEdit,
            QLabel,
            QMessageBox,
        )

        cls.application = QApplication.instance() or QApplication([])
        from openlab_viewer.data_reader import DataFormatOptions
        from openlab_viewer.data_viewer_app import DataViewerSession
        from openlab_viewer import __version__
        from openlab_viewer.data_filter import DataFilter, DataFilterRow
        from openlab_viewer.plot_format import PlotFormat
        from openlab_viewer.ui.dat_plot import STACKED_LAYOUT
        from openlab_viewer.ui.data_filter_dialog import DataFilterDialog

        cls.DataFormatOptions = DataFormatOptions
        cls.DataViewerSession = DataViewerSession
        cls.DataFilter = DataFilter
        cls.DataFilterRow = DataFilterRow
        cls.PlotFormat = PlotFormat
        cls.DataFilterDialog = DataFilterDialog
        cls.STACKED_LAYOUT = STACKED_LAYOUT
        cls.QCheckBox = QCheckBox
        cls.QDateTimeEdit = QDateTimeEdit
        cls.QMessageBox = QMessageBox
        cls.Qt = Qt
        cls.QLabel = QLabel
        cls.viewer_version = __version__

    def _filter(self, column: str, minimum: float | None, maximum: float | None):
        return self.DataFilter(
            (
                self.DataFilterRow(True, column, minimum, maximum),
                self.DataFilterRow(),
                self.DataFilterRow(),
                self.DataFilterRow(),
                self.DataFilterRow(),
            )
        )

    def test_about_dialog_contains_dynamic_version_and_external_links(self) -> None:
        session = self.DataViewerSession(Path("."))
        self.addCleanup(session.main_window.close)
        message_box = session.main_window._about_message_box()
        self.addCleanup(message_box.deleteLater)

        label = message_box.findChild(self.QLabel, "qt_msgbox_label")
        self.assertIsNotNone(label)
        self.assertEqual(message_box.standardButtons(), self.QMessageBox.Ok)
        self.assertEqual(message_box.textFormat(), self.Qt.RichText)
        self.assertEqual(label.textFormat(), self.Qt.RichText)
        self.assertEqual(
            label.textInteractionFlags(),
            self.Qt.TextBrowserInteraction,
        )
        self.assertTrue(label.openExternalLinks())
        about_text = label.text()
        self.assertIn("<b>Version:</b> %s" % self.viewer_version, about_text)
        self.assertIn("Author:</b> yangfu", about_text)
        self.assertIn("mailto:yfu.physics@gmail.com", about_text)
        self.assertIn("https://github.com/yang-fu-physics/openlab-data-viewer", about_text)
        self.assertIn(
            "https://github.com/yang-fu-physics/openlab-data-viewer/releases/latest",
            about_text,
        )

    def test_filter_uses_one_original_row_selection_for_multiple_series(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        path = Path(temporary.name) / "filtered.csv"
        path.write_text(
            "x,y1,y2,note\n"
            "1,10,100,first\n"
            "2,20,200,second\n"
            "3,30,300,third\n"
            "4,40,400,fourth\n",
            encoding="utf-8",
        )

        session = self.DataViewerSession(Path("."))
        self.addCleanup(session.main_window.close)
        browser = session.new_subwindow()
        self.assertTrue(browser.load_path(path, show_errors=False))
        self.assertTrue(browser.canvas.set_axes("x", ("y1", "y2")))
        browser.canvas.set_data_filter(self._filter("x", 2, 3))

        self.assertEqual(browser.canvas.matched_row_indices, (1, 2))
        self.assertEqual(
            tuple(point.row_index for point in browser.canvas.points_by_series["y1"]),
            (1, 2),
        )
        self.assertEqual(
            tuple(point.row_index for point in browser.canvas.points_by_series["y2"]),
            (1, 2),
        )
        self.assertEqual(browser.canvas.points[0].row[3], "second")
        self.assertEqual(browser.document.rows[0][3], "first")
        self.assertIn("Filter: 2/4 rows", browser.status_label.text())

        self.assertTrue(browser.save_format(show_errors=False))
        restored = session.new_subwindow()
        self.assertTrue(restored.load_path(path, show_errors=False))
        self.assertEqual(restored.canvas.data_filter, browser.canvas.data_filter)
        self.assertEqual(restored.canvas.matched_row_indices, (1, 2))

        browser.canvas.set_data_filter(self._filter("x", 9, 10))
        self.assertEqual(browser.canvas.matched_row_indices, ())
        self.assertIn("Filter: 0/4 rows (empty result)", browser.status_label.text())

    def test_filter_reapplies_after_refresh_and_invalid_schema_is_reported(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        path = Path(temporary.name) / "live.csv"
        path.write_text("x,y\n1,10\n2,20\n3,30\n", encoding="utf-8")

        session = self.DataViewerSession(Path("."))
        self.addCleanup(session.main_window.close)
        browser = session.new_subwindow()
        self.assertTrue(browser.load_path(path, show_errors=False))
        browser.canvas.set_data_filter(self._filter("x", 2, 3))
        self.assertEqual(browser.monitor_timer.interval(), 5000)

        path.write_text("x,y\n1,10\n2,20\n3,30\n4,40\n", encoding="utf-8")
        browser._check_for_updates()
        deadline = time.monotonic() + 2.0
        while browser._refresh_in_flight and time.monotonic() < deadline:
            self.application.processEvents()
            time.sleep(0.01)
        self.application.processEvents()
        self.assertEqual(browser.canvas.matched_row_indices, (1, 2))
        self.assertEqual(tuple(point.row_index for point in browser.canvas.points), (1, 2))

        browser.canvas.set_data_filter(self._filter("y", 20, 30))
        path.write_text("x,z\n1,10\n2,20\n3,30\n4,40\n", encoding="utf-8")
        self.assertTrue(
            browser.load_path(
                path,
                show_errors=False,
                format_options=browser.format_options,
            )
        )
        self.assertFalse(browser.canvas.data_filter.is_active)
        self.assertIn("Filter disabled", browser.status_label.text())

    def test_filter_state_is_independent_between_views(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        path = Path(temporary.name) / "same.csv"
        path.write_text("x,y\n1,10\n2,20\n3,30\n", encoding="utf-8")

        session = self.DataViewerSession(Path("."))
        self.addCleanup(session.main_window.close)
        first = session.new_subwindow()
        second = session.new_subwindow()
        self.assertTrue(first.load_path(path, show_errors=False))
        self.assertTrue(second.load_path(path, show_errors=False))
        first.canvas.set_data_filter(self._filter("x", 2, 2))
        self.assertEqual(tuple(point.row_index for point in first.canvas.points), (1,))
        self.assertEqual(tuple(point.row_index for point in second.canvas.points), (0, 1, 2))

    def test_noop_missing_filter_columns_are_cleaned_on_refresh_and_plt_apply(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        path = Path(temporary.name) / "schema.csv"
        path.write_text("x,y\n1,10\n2,20\n3,30\n", encoding="utf-8")

        session = self.DataViewerSession(Path("."))
        self.addCleanup(session.main_window.close)
        browser = session.new_subwindow()
        self.assertTrue(browser.load_path(path, show_errors=False))
        browser.canvas.set_data_filter(
            self.DataFilter(
                (
                    self.DataFilterRow(True, "y"),
                    self.DataFilterRow(),
                    self.DataFilterRow(),
                    self.DataFilterRow(),
                    self.DataFilterRow(),
                )
            )
        )

        path.write_text("x,z\n1,100\n2,200\n3,300\n", encoding="utf-8")
        self.assertTrue(
            browser.load_path(
                path,
                show_errors=False,
                format_options=browser.format_options,
            )
        )
        self.assertEqual(browser.canvas.data_filter, self.DataFilter.empty())
        browser._emit_display_format()

        browser.canvas.apply_plot_format(
            self.PlotFormat(
                data_file=path.name,
                layout="overlay",
                x_column="x",
                y_columns=("z",),
                filters=self.DataFilter(
                    (
                        self.DataFilterRow(True, "unknown"),
                        self.DataFilterRow(),
                        self.DataFilterRow(),
                        self.DataFilterRow(),
                        self.DataFilterRow(),
                    )
                ),
            )
        )
        self.assertEqual(browser.canvas.data_filter, self.DataFilter.empty())

    def test_filter_dialog_apply_stays_open_and_rejects_invalid_edits(self) -> None:
        dialog = self.DataFilterDialog(("x", "y"), self.DataFilter.empty())
        self.addCleanup(dialog.deleteLater)
        applied = []
        dialog.filterApplied.connect(applied.append)
        self.assertEqual(len(dialog.column_combos), 5)
        self.assertEqual(dialog.findChildren(self.QCheckBox), [])

        dialog.column_combos[0].setCurrentIndex(1)
        dialog.minimum_edits[0].setText("not-a-number")
        dialog.apply()
        self.assertEqual(applied, [])
        self.assertIn("finite number", dialog.error_label.text())

        dialog.minimum_edits[0].setText("1e0")
        dialog.maximum_edits[0].setText("2")
        dialog.apply()
        self.assertEqual(len(applied), 1)
        self.assertEqual(applied[0].rows[0].minimum, 1.0)
        self.assertEqual(dialog.result(), 0)

        dialog.minimum_edits[0].setText("3")
        dialog.maximum_edits[0].setText("2")
        dialog.accept()
        self.assertEqual(len(applied), 1)
        self.assertEqual(dialog.result(), 0)

    def test_time_filter_dialog_keeps_a_fixed_row_and_supports_unbounded_sides(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        path = Path(temporary.name) / "timestamp.csv"
        path.write_text(
            "Timestamp_003,Signal_003\n"
            ".848,1\n"
            "5.474,2\n"
            "10,3\n",
            encoding="utf-8",
        )

        session = self.DataViewerSession(Path("."))
        self.addCleanup(session.main_window.close)
        browser = session.new_subwindow()
        self.assertTrue(browser.load_path(path, show_errors=False))
        dialog = self.DataFilterDialog(
            browser.document.numeric_columns(),
            browser.canvas.data_filter,
            browser,
            apply_callback=browser._apply_data_filter,
            time_context=browser.canvas.time_filter_context,
        )
        self.addCleanup(dialog.deleteLater)
        applied = []
        dialog.filterApplied.connect(applied.append)

        self.assertEqual(dialog.time_column_label.text(), "Timestamp_003")
        self.assertIsNone(dialog.column_combos[0])
        self.assertEqual(len(dialog.column_combos), 5)
        self.assertEqual(dialog.findChildren(self.QCheckBox), [])
        self.assertTrue(
            any(
                "elapsed time" in label.text()
                for label in dialog.findChildren(type(dialog.error_label))
            )
        )

        dialog.time_minimum_edit.setText("")
        dialog.time_maximum_edit.setText("00:00:05.474")
        dialog.apply()
        self.assertEqual(browser.canvas.matched_row_indices, (0, 1))
        self.assertIsNone(applied[-1].rows[0].minimum)
        self.assertAlmostEqual(applied[-1].rows[0].maximum, 5.474)

        dialog.time_minimum_edit.setText("00:00:05.474")
        dialog.time_maximum_edit.setText("")
        dialog.apply()
        self.assertEqual(browser.canvas.matched_row_indices, (1, 2))
        self.assertAlmostEqual(applied[-1].rows[0].minimum, 5.474)
        self.assertIsNone(applied[-1].rows[0].maximum)

        dialog.time_minimum_edit.clear()
        dialog.time_maximum_edit.clear()
        dialog.apply()
        self.assertFalse(browser.canvas.data_filter.is_active)
        self.assertEqual(browser.canvas.matched_row_indices, (0, 1, 2))

        dialog.time_minimum_edit.setText("00:00:06")
        dialog.time_maximum_edit.setText("00:00:05")
        before_error = len(applied)
        dialog.apply()
        self.assertEqual(len(applied), before_error)
        self.assertIn("minimum", dialog.error_label.text())

    def test_wall_time_row_uses_clearable_millisecond_datetime_edit(self) -> None:
        from datetime import datetime

        from openlab_viewer.axis_ticks import TimestampReference
        from openlab_viewer.time_filter import TimeFilterContext

        context = TimeFilterContext(
            "Timestamp(s)",
            TimestampReference(
                raw_origin=100.0,
                wall_origin=datetime(2026, 9, 14, 23, 59, 59),
                zone_label="UTC+08:00",
                source="test inference",
            ),
            initial_minimum=100.5,
        )
        dialog = self.DataFilterDialog(
            ("Timestamp(s)", "Signal"),
            self.DataFilter.empty(),
            time_context=context,
        )
        self.addCleanup(dialog.deleteLater)
        self.assertIsInstance(dialog.time_minimum_edit, self.QDateTimeEdit)
        self.assertEqual(
            dialog.time_minimum_edit.displayFormat(),
            "yyyy-MM-dd HH:mm:ss.zzz",
        )
        self.assertIn("not verified instrument time", dialog.time_column_label.toolTip())
        self.assertEqual(
            dialog.time_minimum_edit.lineEdit().text(),
            "2026-09-14 23:59:59.500",
        )
        self.assertAlmostEqual(dialog.time_minimum_edit.value(), 100.5)
        self.assertIsNone(dialog.time_maximum_edit.value())
        applied = []
        dialog.filterApplied.connect(applied.append)
        dialog.apply()
        self.assertAlmostEqual(applied[-1].rows[0].minimum, 100.5)
        self.assertIsNone(applied[-1].rows[0].maximum)
        dialog.time_minimum_edit.clear_value()
        self.assertIsNone(dialog.time_minimum_edit.value())
        dialog.apply()
        self.assertIsNone(applied[-1].rows[0].minimum)
        reopened = self.DataFilterDialog(
            ("Timestamp(s)", "Signal"),
            applied[-1],
            time_context=context,
        )
        self.addCleanup(reopened.deleteLater)
        self.assertEqual(reopened.time_minimum_edit.lineEdit().text(), "")
        self.assertIsNone(reopened.time_minimum_edit.value())

    def test_time_filter_minimum_survives_refresh_without_default_reset(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        path = Path(temporary.name) / "refresh-time.csv"
        path.write_text(
            "Timestamp_003,Signal_003\n"
            ".848,1\n"
            "5.474,2\n"
            "10,3\n",
            encoding="utf-8",
        )

        session = self.DataViewerSession(Path("."))
        self.addCleanup(session.main_window.close)
        browser = session.new_subwindow()
        self.assertTrue(browser.load_path(path, show_errors=False))
        first_dialog = self.DataFilterDialog(
            browser.document.numeric_columns(),
            browser.canvas.data_filter,
            browser,
            apply_callback=browser._apply_data_filter,
            time_context=browser.canvas.time_filter_context,
        )
        self.addCleanup(first_dialog.deleteLater)
        self.assertEqual(first_dialog.time_minimum_edit.text(), "00:00:00.848")
        first_dialog.time_minimum_edit.setText("00:00:05.474")
        first_dialog.apply()
        self.assertAlmostEqual(browser.canvas.data_filter.rows[0].minimum, 5.474)

        path.write_text(
            "Timestamp_003,Signal_003\n"
            ".848,1\n"
            "5.474,2\n"
            "10,3\n"
            "12,4\n",
            encoding="utf-8",
        )
        self.assertTrue(
            browser.load_path(
                path,
                show_errors=False,
                format_options=browser.format_options,
            )
        )
        self.assertAlmostEqual(browser.canvas.data_filter.rows[0].minimum, 5.474)
        refreshed_dialog = self.DataFilterDialog(
            browser.document.numeric_columns(),
            browser.canvas.data_filter,
            browser,
            time_context=browser.canvas.time_filter_context,
        )
        self.addCleanup(refreshed_dialog.deleteLater)
        self.assertEqual(
            refreshed_dialog.time_minimum_edit.text(),
            "00:00:05.474",
        )

    def test_time_filter_row_is_visible_but_disabled_without_a_time_column(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        path = Path(temporary.name) / "no-time.csv"
        path.write_text("x,y\n1,10\n2,20\n3,30\n", encoding="utf-8")

        session = self.DataViewerSession(Path("."))
        self.addCleanup(session.main_window.close)
        browser = session.new_subwindow()
        self.assertTrue(browser.load_path(path, show_errors=False))
        dialog = self.DataFilterDialog(
            browser.document.numeric_columns(),
            browser.canvas.data_filter,
            browser,
            time_context=browser.canvas.time_filter_context,
        )
        self.addCleanup(dialog.deleteLater)
        self.assertIsNone(dialog.column_combos[0])
        self.assertEqual(dialog.findChildren(self.QCheckBox), [])
        self.assertFalse(dialog.minimum_edits[0].isEnabled())
        self.assertEqual(dialog.time_column_label.text(), "Unavailable")

    def test_time_filter_row_is_cleaned_when_refresh_removes_the_time_column(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        path = Path(temporary.name) / "time-schema.csv"
        path.write_text(
            "Timestamp_003,y\n.848,10\n5.474,20\n10,30\n",
            encoding="utf-8",
        )

        session = self.DataViewerSession(Path("."))
        self.addCleanup(session.main_window.close)
        browser = session.new_subwindow()
        self.assertTrue(browser.load_path(path, show_errors=False))
        browser.canvas.set_data_filter(self._filter("Timestamp_003", None, 5.474))
        self.assertEqual(browser.canvas.matched_row_indices, (0, 1))

        path.write_text("x,z\n1,10\n2,20\n3,30\n", encoding="utf-8")
        self.assertTrue(
            browser.load_path(
                path,
                show_errors=False,
                format_options=browser.format_options,
            )
        )
        self.assertEqual(browser.canvas.data_filter, self.DataFilter.empty())
        browser._emit_display_format()
        self.assertIn("Filter disabled", browser.status_label.text())

    def test_filter_dialog_rejects_schema_changed_during_apply(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        path = Path(temporary.name) / "dialog.csv"
        path.write_text("x,y\n1,10\n2,20\n3,30\n", encoding="utf-8")

        session = self.DataViewerSession(Path("."))
        self.addCleanup(session.main_window.close)
        browser = session.new_subwindow()
        self.assertTrue(browser.load_path(path, show_errors=False))
        dialog = self.DataFilterDialog(
            ("x", "y"),
            browser.canvas.data_filter,
            browser,
            apply_callback=browser._apply_data_filter,
        )
        self.addCleanup(dialog.deleteLater)
        dialog.column_combos[0].setCurrentIndex(2)
        dialog.minimum_edits[0].setText("10")

        path.write_text("x,z\n1,100\n2,200\n3,300\n", encoding="utf-8")
        self.assertTrue(
            browser.load_path(
                path,
                show_errors=False,
                format_options=browser.format_options,
            )
        )
        dialog.apply()
        self.assertEqual(dialog.result(), 0)
        self.assertIn("Filter not applied", dialog.error_label.text())
        self.assertFalse(browser.canvas.data_filter.is_active)

    def test_filter_dialog_rejects_stale_noop_column_after_schema_change(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        path = Path(temporary.name) / "noop-dialog.csv"
        path.write_text("x,y\n1,10\n2,20\n3,30\n", encoding="utf-8")

        session = self.DataViewerSession(Path("."))
        self.addCleanup(session.main_window.close)
        browser = session.new_subwindow()
        self.assertTrue(browser.load_path(path, show_errors=False))
        dialog = self.DataFilterDialog(
            ("x", "y"),
            browser.canvas.data_filter,
            browser,
            apply_callback=browser._apply_data_filter,
            time_context=browser.canvas.time_filter_context,
        )
        self.addCleanup(dialog.deleteLater)
        dialog.column_combos[1].setCurrentIndex(2)

        path.write_text("x,z\n1,100\n2,200\n3,300\n", encoding="utf-8")
        self.assertTrue(
            browser.load_path(
                path,
                show_errors=False,
                format_options=browser.format_options,
            )
        )
        dialog.apply()
        self.assertEqual(dialog.result(), 0)
        self.assertIn("Filter not applied", dialog.error_label.text())

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
        first.canvas.set_data_filter(self._filter("Timestamp_003", 2, 2))
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
        self.assertEqual(second.canvas.data_filter.rows[0].column, "Timestamp_006")
        self.assertEqual(second.canvas.matched_row_indices, (1,))

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
        self.assertFalse(third.canvas.data_filter.is_active)
        self.assertIn("filters cleared", third.status_label.text())

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

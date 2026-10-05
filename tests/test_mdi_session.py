from __future__ import annotations

import os
import sys
import tempfile
import time
import unittest
from importlib.util import find_spec
from pathlib import Path
from unittest.mock import patch


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
        from openlab_viewer.ui.data_browser import PointDetailsDialog
        from openlab_viewer.ui.data_filter_dialog import DataFilterDialog

        cls.DataFormatOptions = DataFormatOptions
        cls.DataViewerSession = DataViewerSession
        cls.DataFilter = DataFilter
        cls.DataFilterRow = DataFilterRow
        cls.PlotFormat = PlotFormat
        cls.DataFilterDialog = DataFilterDialog
        cls.PointDetailsDialog = PointDetailsDialog
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

    def _double_click_point(self, browser, point):
        """Exercise the canvas double-click path without opening a modal dialog."""

        from PySide2.QtCore import QEvent, QPointF
        from PySide2.QtGui import QMouseEvent

        canvas = browser.canvas
        before = canvas.grab().toImage()
        plot = canvas._plot_rect()
        ranges = canvas._ranges(None)
        self.assertIsNotNone(ranges)
        position = canvas._screen_point(point.x, point.y, plot, ranges)
        self.assertIsNotNone(position)
        self.assertIsNotNone(canvas._nearest_point(QPointF(position)))
        activated = []
        canvas.pointActivated.disconnect(browser._show_point_details)
        canvas.pointActivated.connect(activated.append)
        try:
            event = QMouseEvent(
                QEvent.MouseButtonDblClick,
                QPointF(position),
                self.Qt.LeftButton,
                self.Qt.LeftButton,
                self.Qt.NoModifier,
            )
            self.assertEqual(event.button(), self.Qt.LeftButton)
            self.assertIsNotNone(
                canvas._nearest_point(
                    QPointF(event.localPos().x(), event.localPos().y())
                ),
                "event=%s point=%s plot=%s" % (event.localPos(), position, plot),
            )
            canvas.mouseDoubleClickEvent(event)
            self.application.processEvents()
            after = canvas.grab().toImage()
        finally:
            canvas.pointActivated.disconnect(activated.append)
            canvas.pointActivated.connect(browser._show_point_details)

        device_ratio = max(1.0, float(before.devicePixelRatio()))
        center_x = int(position.x() * device_ratio)
        center_y = int(position.y() * device_ratio)
        changed_pixels = 0
        for x in range(
            max(0, center_x - int(10 * device_ratio)),
            min(before.width(), center_x + int(10 * device_ratio) + 1),
        ):
            for y in range(
                max(0, center_y - int(10 * device_ratio)),
                min(before.height(), center_y + int(10 * device_ratio) + 1),
            ):
                if before.pixel(x, y) != after.pixel(x, y):
                    changed_pixels += 1
        return activated, position, changed_pixels

    def _click_point(self, browser, point):
        """Exercise a left click and confirm its rendered marker change."""

        from PySide2.QtCore import QEvent, QPointF
        from PySide2.QtGui import QMouseEvent

        canvas = browser.canvas
        before = canvas.grab().toImage()
        plot = canvas._plot_rect()
        ranges = canvas._ranges(None)
        self.assertIsNotNone(ranges)
        position = canvas._screen_point(point.x, point.y, plot, ranges)
        self.assertIsNotNone(position)
        canvas.mousePressEvent(
            QMouseEvent(
                QEvent.MouseButtonPress,
                QPointF(position),
                self.Qt.LeftButton,
                self.Qt.LeftButton,
                self.Qt.NoModifier,
            )
        )
        canvas.mouseReleaseEvent(
            QMouseEvent(
                QEvent.MouseButtonRelease,
                QPointF(position),
                self.Qt.LeftButton,
                self.Qt.NoButton,
                self.Qt.NoModifier,
            )
        )
        self.application.processEvents()
        after = canvas.grab().toImage()
        device_ratio = max(1.0, float(before.devicePixelRatio()))
        center_x = int(position.x() * device_ratio)
        center_y = int(position.y() * device_ratio)
        changed_pixels = 0
        for x in range(
            max(0, center_x - int(10 * device_ratio)),
            min(before.width(), center_x + int(10 * device_ratio) + 1),
        ):
            for y in range(
                max(0, center_y - int(10 * device_ratio)),
                min(before.height(), center_y + int(10 * device_ratio) + 1),
            ):
                if before.pixel(x, y) != after.pixel(x, y):
                    changed_pixels += 1
        return position, changed_pixels

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

    def test_large_linear_plot_draws_complete_path_but_hides_markers(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        path = Path(temporary.name) / "large.csv"
        path.write_text(
            "x,y1,y2\n"
            + "\n".join(
                "%d,%d,%d" % (index, index % 1000, (index * 3) % 1000)
                for index in range(1, 20_001)
            )
            + "\n",
            encoding="utf-8",
        )

        session = self.DataViewerSession(Path("."))
        self.addCleanup(session.main_window.close)
        browser = session.new_subwindow()
        self.assertTrue(browser.load_path(path, show_errors=False))
        self.assertTrue(browser.canvas.set_axes("x", ("y1", "y2")))
        browser.canvas.resize(800, 500)
        browser.canvas.show()
        self.application.processEvents()

        screen_calls = []
        browser.canvas._path_cache.clear()
        original_screen_point = browser.canvas._screen_point

        def count_screen_point(*args, **kwargs):
            screen_calls.append(1)
            return original_screen_point(*args, **kwargs)

        browser.canvas._screen_point = count_screen_point
        browser.canvas.grab()

        self.assertEqual(len(browser.canvas.points_by_series["y1"]), 20_000)
        self.assertEqual(len(browser.canvas.points_by_series["y2"]), 20_000)
        self.assertEqual(len(screen_calls), 40_000)
        self.assertEqual(
            sorted(path.elementCount() for path in browser.canvas._path_cache.values()),
            [20_000, 20_000],
        )

    def test_double_click_marks_single_and_large_points(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        single_path = Path(temporary.name) / "single.csv"
        single_path.write_text("x,y\n1,2\n2,3\n3,4\n", encoding="utf-8")

        session = self.DataViewerSession(Path("."))
        self.addCleanup(session.main_window.close)
        single = session.new_subwindow()
        self.assertTrue(single.load_path(single_path, show_errors=False))
        self.assertTrue(single.canvas.set_axes("x", ("y",)))
        single.canvas.resize(800, 500)
        single.canvas.show()
        self.application.processEvents()
        activated, _, changed_pixels = self._double_click_point(
            single,
            single.canvas.points[0],
        )
        self.assertEqual([hit.row_index for hit in activated], [0])
        self.assertEqual(single.canvas.selected_hit.row_index, 0)
        self.assertGreater(changed_pixels, 10)

        dense_path = Path(temporary.name) / "dense.csv"
        dense_path.write_text(
            "x,y\n"
            + "\n".join(
                "%d,%d" % (index, (index * 17) % 1000)
                for index in range(1, 4_001)
            )
            + "\n",
            encoding="utf-8",
        )
        dense = session.new_subwindow()
        self.assertTrue(dense.load_path(dense_path, show_errors=False))
        self.assertTrue(dense.canvas.set_axes("x", ("y",)))
        dense.canvas.resize(800, 500)
        dense.canvas.show()
        self.application.processEvents()
        selected = dense.canvas.points[2_000]
        activated, _, changed_pixels = self._double_click_point(dense, selected)
        self.assertEqual([hit.row_index for hit in activated], [selected.row_index])
        self.assertEqual(dense.canvas.selected_hit.row_index, selected.row_index)
        self.assertGreater(changed_pixels, 10)

    def test_single_click_selects_without_popup_and_drag_does_not_select(self) -> None:
        from PySide2.QtCore import QEvent, QPointF
        from PySide2.QtGui import QMouseEvent

        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        path = Path(temporary.name) / "click.csv"
        path.write_text("x,y\n1,10\n2,20\n3,30\n", encoding="utf-8")

        session = self.DataViewerSession(Path("."))
        self.addCleanup(session.main_window.close)
        browser = session.new_subwindow()
        self.assertTrue(browser.load_path(path, show_errors=False))
        self.assertTrue(browser.canvas.set_axes("x", ("y",)))
        browser.canvas.resize(800, 500)
        browser.canvas.show()
        self.application.processEvents()

        _, changed_pixels = self._click_point(browser, browser.canvas.points[1])
        self.assertEqual(browser.canvas.selected_hit.row_index, 1)
        self.assertIsNone(browser._point_details_dialog)
        self.assertGreater(changed_pixels, 10)

        browser.canvas._selected_hit = None
        before = browser.canvas.points[1]
        plot = browser.canvas._plot_rect()
        ranges = browser.canvas._ranges(None)
        start = browser.canvas._screen_point(before.x, before.y, plot, ranges)
        drag_end = QPointF(start.x() + 30, start.y() + 30)
        browser.canvas.mousePressEvent(
            QMouseEvent(
                QEvent.MouseButtonPress,
                start,
                self.Qt.LeftButton,
                self.Qt.LeftButton,
                self.Qt.NoModifier,
            )
        )
        browser.canvas.mouseMoveEvent(
            QMouseEvent(
                QEvent.MouseMove,
                drag_end,
                self.Qt.NoButton,
                self.Qt.LeftButton,
                self.Qt.NoModifier,
            )
        )
        browser.canvas.mouseReleaseEvent(
            QMouseEvent(
                QEvent.MouseButtonRelease,
                drag_end,
                self.Qt.LeftButton,
                self.Qt.NoButton,
                self.Qt.NoModifier,
            )
        )
        self.assertIsNone(browser.canvas.selected_hit)

    def test_selected_point_is_local_and_reconciles_refresh_and_filter(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        path = Path(temporary.name) / "selected.csv"
        path.write_text("x,y\n1,10\n2,20\n3,30\n", encoding="utf-8")

        session = self.DataViewerSession(Path("."))
        self.addCleanup(session.main_window.close)
        first = session.new_subwindow()
        second = session.new_subwindow()
        self.assertTrue(first.load_path(path, show_errors=False))
        self.assertTrue(second.load_path(path, show_errors=False))
        self.assertTrue(first.canvas.set_axes("x", ("y",)))
        first.canvas.resize(800, 500)
        first.canvas.show()
        self.application.processEvents()
        self._double_click_point(first, first.canvas.points[1])
        self.assertEqual(first.canvas.selected_hit.row_index, 1)
        self.assertIsNone(second.canvas.selected_hit)

        path.write_text(
            "x,y\n1,10\n2,20\n3,30\n4,40\n",
            encoding="utf-8",
        )
        self.assertTrue(
            first.load_path(
                path,
                show_errors=False,
                format_options=first.format_options,
            )
        )
        self.assertEqual(first.canvas.selected_hit.row_index, 1)
        self.assertEqual(first.canvas.selected_hit.row, ("2", "20"))

        first.canvas.set_data_filter(self._filter("x", 3, 4))
        self.assertIsNone(first.canvas.selected_hit)
        first.canvas.set_data_filter(self.DataFilter.empty())
        self._double_click_point(first, first.canvas.points[0])
        self.assertEqual(first.canvas.selected_hit.row_index, 0)

        path.write_text(
            "x,y\n1,11\n2,20\n3,30\n4,40\n",
            encoding="utf-8",
        )
        self.assertTrue(
            first.load_path(
                path,
                show_errors=False,
                format_options=first.format_options,
            )
        )
        self.assertIsNone(first.canvas.selected_hit)

    def test_selected_point_marker_survives_log_repeated_x_and_zoom(self) -> None:
        from PySide2.QtCore import QPointF

        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        path = Path(temporary.name) / "selected-log.csv"
        path.write_text(
            "x,y\n1,10\n1,20\n2,30\n2,40\n",
            encoding="utf-8",
        )

        session = self.DataViewerSession(Path("."))
        self.addCleanup(session.main_window.close)
        browser = session.new_subwindow()
        self.assertTrue(browser.load_path(path, show_errors=False))
        self.assertTrue(browser.canvas.set_axes("x", ("y",)))
        browser.canvas.set_x_scale("log")
        browser.canvas.set_y_scale("log")
        browser.canvas._x_view = (0.9, 2.2)
        browser.canvas._overlay_y_view = (8.0, 50.0)
        browser.canvas._manual_view = True
        browser.canvas.resize(800, 500)
        browser.canvas.show()
        self.application.processEvents()
        selected = browser.canvas.points[1]
        activated, old_position, changed_pixels = self._double_click_point(
            browser,
            selected,
        )
        self.assertEqual([hit.row_index for hit in activated], [1])
        self.assertEqual(browser.canvas.selected_hit.row_index, 1)
        self.assertGreater(changed_pixels, 10)

        browser.canvas._x_view = (0.99, 1.05)
        browser.canvas._overlay_y_view = (19.0, 21.0)
        browser.canvas._path_cache.clear()
        browser.canvas.update()
        self.application.processEvents()
        new_position = browser.canvas._screen_point(
            selected.x,
            selected.y,
            browser.canvas._plot_rect(),
            browser.canvas._ranges(None),
        )
        self.assertNotEqual((old_position.x(), old_position.y()), (new_position.x(), new_position.y()))
        self.assertEqual(browser.canvas.selected_hit.row_index, 1)

    def test_point_details_navigate_filtered_points_in_source_order(self) -> None:
        from openlab_viewer.ui.dat_plot import PlotHit

        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        path = Path(temporary.name) / "details.csv"
        path.write_text(
            "x,y\n5,50\n1,10\n4,40\n2,20\n3,-30\n",
            encoding="utf-8",
        )

        session = self.DataViewerSession(Path("."))
        self.addCleanup(session.main_window.close)
        browser = session.new_subwindow()
        self.assertTrue(browser.load_path(path, show_errors=False))
        self.assertTrue(browser.canvas.set_axes("x", ("y",)))
        browser.canvas.set_data_filter(self._filter("x", 1, 4))
        self.assertEqual(
            tuple(point.row_index for point in browser.canvas.points),
            (1, 2, 3, 4),
        )
        navigation_hits = tuple(
            PlotHit("y", point)
            for point in browser.canvas.points
            if browser.canvas._point_is_plottable(point)
        )
        changed = []
        dialog = self.PointDetailsDialog(
            browser.document,
            navigation_hits[1],
            browser.canvas.x_label,
            parent=browser,
            navigation_hits=navigation_hits,
            current_index=1,
            hit_changed_callback=changed.append,
            x_value_formatter=lambda value: browser.canvas.format_x_value(
                value,
                full=True,
            ),
        )
        self.addCleanup(dialog.deleteLater)
        self.assertTrue(dialog.previous_button.isEnabled())
        self.assertTrue(dialog.next_button.isEnabled())
        dialog._navigate(1)
        self.assertEqual(dialog._hits[dialog._current_index].row_index, 3)
        self.assertEqual(changed[-1].row_index, 3)
        self.assertIn("Data row: 4", dialog.summary_label.text())
        dialog._navigate(-1)
        self.assertEqual(dialog._hits[dialog._current_index].row_index, 2)
        self.assertEqual(changed[-1].row_index, 2)

        browser.canvas.set_x_scale("log")
        browser.canvas.set_y_scale("log")
        log_hits = tuple(
            PlotHit("y", point)
            for point in browser.canvas.points_by_series["y"]
            if browser.canvas._point_is_plottable(point)
        )
        self.assertEqual(tuple(hit.row_index for hit in log_hits), (1, 2, 3))

    def test_point_details_closes_when_filter_or_refresh_rebuilds_points(self) -> None:
        from openlab_viewer.ui.dat_plot import PlotHit

        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        path = Path(temporary.name) / "details-refresh.csv"
        path.write_text("x,y\n1,10\n2,20\n3,30\n", encoding="utf-8")

        session = self.DataViewerSession(Path("."))
        self.addCleanup(session.main_window.close)
        browser = session.new_subwindow()
        self.assertTrue(browser.load_path(path, show_errors=False))
        self.assertTrue(browser.canvas.set_axes("x", ("y",)))
        hit = PlotHit("y", browser.canvas.points[1])
        dialog = self.PointDetailsDialog(browser.document, hit, "x", parent=browser)
        self.addCleanup(dialog.deleteLater)
        browser._point_details_dialog = dialog
        dialog.show()
        browser.canvas.set_data_filter(self._filter("x", 3, 3))
        self.assertIsNone(browser._point_details_dialog)
        self.assertFalse(dialog.isVisible())

        browser.canvas.set_data_filter(self.DataFilter.empty())
        hit = PlotHit("y", browser.canvas.points[1])
        refreshed_dialog = self.PointDetailsDialog(
            browser.document,
            hit,
            "x",
            parent=browser,
        )
        self.addCleanup(refreshed_dialog.deleteLater)
        browser._point_details_dialog = refreshed_dialog
        refreshed_dialog.show()
        path.write_text("x,y\n1,11\n2,20\n3,30\n", encoding="utf-8")
        self.assertTrue(
            browser.load_path(
                path,
                show_errors=False,
                format_options=browser.format_options,
            )
        )
        self.assertIsNone(browser._point_details_dialog)
        self.assertFalse(refreshed_dialog.isVisible())

    def test_raw_file_read_error_is_visible(self) -> None:
        from openlab_viewer.data_reader import DataReadError

        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        path = Path(temporary.name) / "raw-error.csv"
        path.write_text("x,y\n1,10\n2,20\n3,30\n", encoding="utf-8")

        session = self.DataViewerSession(Path("."))
        self.addCleanup(session.main_window.close)
        browser = session.new_subwindow()
        self.assertTrue(browser.load_path(path, show_errors=False))
        with patch.object(self.QMessageBox, "warning") as warning:
            browser._raw_file_read_finished(
                None,
                DataReadError("decode failed"),
                browser._raw_text_generation,
                browser.current_path,
            )
        warning.assert_called_once()
        self.assertIn("decode failed", browser.status_label.text())

    def test_large_raw_file_browse_starts_without_blocking_dispatch(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        path = Path(temporary.name) / "large-raw.csv"
        path.write_text(
            "x,y\n"
            + "\n".join(
                "%d,%d" % (index, index % 1000)
                for index in range(1, 210_001)
            )
            + "\n",
            encoding="utf-8",
        )

        session = self.DataViewerSession(Path("."))
        self.addCleanup(session.main_window.close)
        browser = session.new_subwindow()
        self.assertTrue(browser.load_path(path, show_errors=False))
        menu = browser.canvas.build_context_menu()
        self.addCleanup(menu.deleteLater)
        raw_action = next(
            action
            for action in menu.actions()
            if action.text() == "Browse Raw File"
        )
        started = time.monotonic()
        raw_action.trigger()
        self.assertLess(time.monotonic() - started, 0.2)
        deadline = time.monotonic() + 3.0
        while browser._raw_file_dialog is None and time.monotonic() < deadline:
            self.application.processEvents()
            time.sleep(0.01)
        self.assertIsNotNone(browser._raw_file_dialog)
        self.addCleanup(browser._raw_file_dialog.close)

    def test_context_menu_browses_current_raw_file_and_reuses_filter_entry(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        first_path = Path(temporary.name) / "first.csv"
        second_path = Path(temporary.name) / "second.csv"
        first_text = "x,y\n1,10\n2,20\n3,30\n"
        second_text = "x,y\n7,70\n8,80\n9,90\n"
        first_path.write_text(first_text, encoding="utf-8")
        second_path.write_text(second_text, encoding="utf-8")

        session = self.DataViewerSession(Path("."))
        self.addCleanup(session.main_window.close)
        first = session.new_subwindow()
        second = session.new_subwindow()
        empty = session.new_subwindow()
        self.assertTrue(first.load_path(first_path, show_errors=False))
        self.assertTrue(second.load_path(second_path, show_errors=False))
        first.canvas.set_data_filter(self._filter("x", 2, 2))
        first._pending_import_path = second_path

        def action_named(menu, name):
            return next(action for action in menu.actions() if action.text() == name)

        first_menu = first.canvas.build_context_menu()
        self.addCleanup(first_menu.deleteLater)
        raw_action = action_named(first_menu, "Browse Raw File")
        filter_action = action_named(first_menu, "Data Filter...")
        self.assertTrue(raw_action.isEnabled())
        self.assertTrue(filter_action.isEnabled())

        filter_requests = []
        first.canvas.dataFilterRequested.disconnect(first.open_data_filter)
        first.canvas.dataFilterRequested.connect(lambda: filter_requests.append(first))
        try:
            filter_action.trigger()
        finally:
            first.canvas.dataFilterRequested.disconnect()
            first.canvas.dataFilterRequested.connect(first.open_data_filter)
        self.assertEqual(filter_requests, [first])
        self.assertEqual(first.canvas.matched_row_indices, (1,))

        started = time.monotonic()
        raw_action.trigger()
        self.assertLess(time.monotonic() - started, 0.2)
        deadline = time.monotonic() + 2.0
        while first._raw_file_dialog is None and time.monotonic() < deadline:
            self.application.processEvents()
            time.sleep(0.01)
        self.assertIsNotNone(first._raw_file_dialog)
        first_dialog = first._raw_file_dialog
        self.addCleanup(first_dialog.close)
        self.assertTrue(first_dialog.text_edit.isReadOnly())
        self.assertIn(first_text, first_dialog.text_edit.toPlainText())
        self.assertIn("1,10", first_dialog.text_edit.toPlainText())
        self.assertEqual(first_path.read_text(encoding="utf-8"), first_text)

        second_menu = second.canvas.build_context_menu()
        self.addCleanup(second_menu.deleteLater)
        action_named(second_menu, "Browse Raw File").trigger()
        deadline = time.monotonic() + 2.0
        while second._raw_file_dialog is None and time.monotonic() < deadline:
            self.application.processEvents()
            time.sleep(0.01)
        self.assertIsNotNone(second._raw_file_dialog)
        second_dialog = second._raw_file_dialog
        self.addCleanup(second_dialog.close)
        self.assertIn(second_text, second_dialog.text_edit.toPlainText())
        self.assertNotIn(first_text, second_dialog.text_edit.toPlainText())

        empty_menu = empty.canvas.build_context_menu()
        self.addCleanup(empty_menu.deleteLater)
        self.assertFalse(action_named(empty_menu, "Browse Raw File").isEnabled())
        self.assertFalse(action_named(empty_menu, "Data Filter...").isEnabled())

    def test_background_initial_load_commits_after_gui_events_can_run(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        path = Path(temporary.name) / "background.csv"
        path.write_text(
            "x,y\n"
            + "\n".join("%d,%d" % (index, index) for index in range(1, 10_001))
            + "\n",
            encoding="utf-8",
        )

        session = self.DataViewerSession(Path("."))
        self.addCleanup(session.main_window.close)
        browser = session.new_subwindow()
        events = []
        from PySide2.QtCore import QTimer

        timer = QTimer()
        timer.setInterval(1)
        timer.timeout.connect(lambda: events.append(1))
        timer.start()
        self.assertTrue(browser.load_path(path, show_errors=False, background=True))
        deadline = time.monotonic() + 2.0
        while browser._refresh_in_flight and time.monotonic() < deadline:
            self.application.processEvents()
            time.sleep(0.001)
        timer.stop()
        self.application.processEvents()

        self.assertFalse(browser._refresh_in_flight)
        self.assertEqual(len(browser.document.rows), 10_000)
        self.assertTrue(events)

    def test_background_new_file_keeps_committed_state_until_read_succeeds(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        first_path = Path(temporary.name) / "first.csv"
        second_path = Path(temporary.name) / "second.csv"
        first_path.write_text("x,y\n1,10\n2,20\n", encoding="utf-8")
        second_path.write_text('x,y\n"1,2\n', encoding="utf-8")

        session = self.DataViewerSession(Path("."))
        self.addCleanup(session.main_window.close)
        browser = session.new_subwindow()
        first_options = self.DataFormatOptions(
            mode="custom",
            header_line=1,
            data_start_line=2,
            delimiter="comma",
            encoding="utf-8",
        )
        second_options = self.DataFormatOptions.openlab()
        self.assertTrue(
            browser.load_path(
                first_path,
                show_errors=False,
                format_options=first_options,
            )
        )
        self.assertTrue(
            browser.load_path(
                second_path,
                show_errors=False,
                format_options=second_options,
                background=True,
            )
        )
        self.assertEqual(browser.current_path, first_path.resolve())
        self.assertEqual(browser.format_options, first_options)
        deadline = time.monotonic() + 2.0
        while browser._refresh_in_flight and time.monotonic() < deadline:
            self.application.processEvents()
            time.sleep(0.001)
        self.application.processEvents()
        self.assertEqual(browser.current_path, first_path.resolve())
        self.assertEqual(browser.format_options, first_options)
        self.assertIn(second_path.name, browser.status_label.text())

        second_path.write_text("x;y\n1;100\n2;200\n3;300\n", encoding="utf-8")
        self.assertTrue(
            browser.load_path(
                second_path,
                show_errors=False,
                format_options=second_options,
                background=True,
            )
        )
        deadline = time.monotonic() + 2.0
        while browser._refresh_in_flight and time.monotonic() < deadline:
            self.application.processEvents()
            time.sleep(0.001)
        self.application.processEvents()
        self.assertEqual(browser.current_path, second_path.resolve())
        self.assertEqual(browser.format_options.mode, "custom")
        self.assertEqual(browser.format_options.delimiter, "semicolon")

    def test_late_background_read_cannot_replace_a_newer_file(self) -> None:
        from unittest.mock import patch

        import openlab_viewer.ui.data_browser as data_browser

        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        slow_path = Path(temporary.name) / "slow.csv"
        fast_path = Path(temporary.name) / "fast.csv"
        slow_path.write_text("x,y\n1,10\n2,20\n", encoding="utf-8")
        fast_path.write_text("x,y\n3,30\n4,40\n", encoding="utf-8")
        options = self.DataFormatOptions(
            mode="custom",
            header_line=1,
            data_start_line=2,
            delimiter="comma",
            encoding="utf-8",
        )
        original_read_data = data_browser.read_data

        def delayed_read(path, selected_options, **kwargs):
            if Path(path).name == slow_path.name:
                time.sleep(0.1)
            return original_read_data(path, selected_options, **kwargs)

        session = self.DataViewerSession(Path("."))
        self.addCleanup(session.main_window.close)
        browser = session.new_subwindow()
        with patch.object(data_browser, "read_data", side_effect=delayed_read):
            self.assertTrue(
                browser.load_path(
                    slow_path,
                    show_errors=False,
                    format_options=options,
                    background=True,
                )
            )
            time.sleep(0.02)
            self.assertTrue(
                browser.load_path(
                    fast_path,
                    show_errors=False,
                    format_options=options,
                    background=True,
                )
            )
            deadline = time.monotonic() + 2.0
            while browser._refresh_in_flight and time.monotonic() < deadline:
                self.application.processEvents()
                time.sleep(0.001)
            time.sleep(0.15)
            self.application.processEvents()
        self.assertEqual(browser.current_path, fast_path.resolve())
        self.assertEqual(tuple(row[0] for row in browser.document.rows), ("3", "4"))

    def test_point_hit_testing_matches_brute_force_for_nonmonotonic_repeated_and_log_x(self) -> None:
        from PySide2.QtCore import QPointF

        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        path = Path(temporary.name) / "hit.csv"
        path.write_text(
            "x,y\n10,100\n1,10\n8,80\n3,30\n1,20\n2,40\n",
            encoding="utf-8",
        )

        session = self.DataViewerSession(Path("."))
        self.addCleanup(session.main_window.close)
        browser = session.new_subwindow()
        self.assertTrue(browser.load_path(path, show_errors=False))
        self.assertTrue(browser.canvas.set_axes("x", ("y",)))
        browser.canvas.resize(800, 500)
        browser.canvas.show()
        self.application.processEvents()

        def assert_hits_match_bruteforce() -> None:
            plot = browser.canvas._plot_rect()
            ranges = browser.canvas._ranges(None)
            self.assertIsNotNone(ranges)
            for point in browser.canvas.points:
                position = browser.canvas._screen_point(point.x, point.y, plot, ranges)
                self.assertIsNotNone(position)
                expected = min(
                    browser.canvas.points,
                    key=lambda candidate: (
                        browser.canvas._screen_point(
                            candidate.x,
                            candidate.y,
                            plot,
                            ranges,
                        ).x()
                        - position.x()
                    )
                    ** 2
                    + (
                        browser.canvas._screen_point(
                            candidate.x,
                            candidate.y,
                            plot,
                            ranges,
                        ).y()
                        - position.y()
                    )
                    ** 2,
                )
                hit = browser.canvas._nearest_point(QPointF(position))
                self.assertIsNotNone(hit)
                self.assertEqual(hit.row_index, expected.row_index)

        assert_hits_match_bruteforce()
        self.assertEqual(
            browser.canvas._sorted_x_values_by_series,
            {},
        )

        browser.canvas.set_x_scale("log")
        browser.canvas.set_y_scale("log")
        browser.canvas._x_view = (0.9, 11.0)
        browser.canvas._overlay_y_view = (8.0, 120.0)
        browser.canvas._manual_view = True
        browser.canvas._path_cache.clear()
        browser.canvas.grab()
        self.assertEqual(
            [path.elementCount() for path in browser.canvas._path_cache.values()],
            [6],
        )
        assert_hits_match_bruteforce()

        path.write_text(
            "x,y\n1,10\n1,20\n2,30\n2,40\n",
            encoding="utf-8",
        )
        self.assertTrue(
            browser.load_path(
                path,
                show_errors=False,
                format_options=browser.format_options,
            )
        )
        browser.canvas.set_x_scale("log")
        browser.canvas.set_y_scale("log")
        browser.canvas._x_view = (0.9, 2.2)
        browser.canvas._overlay_y_view = (8.0, 50.0)
        browser.canvas._manual_view = True
        assert_hits_match_bruteforce()

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
        browser = area.subWindowList()[0].widget()
        deadline = time.monotonic() + 2.0
        while browser._refresh_in_flight and time.monotonic() < deadline:
            self.application.processEvents()
            time.sleep(0.001)
        self.application.processEvents()
        self.assertEqual(
            browser.current_path,
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

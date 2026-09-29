from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


VIEWER_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VIEWER_ROOT / "src"))

from openlab_viewer.data_filter import (  # noqa: E402
    DataFilter,
    DataFilterRow,
    matching_row_indices,
)
from openlab_viewer.data_reader import DataFormatOptions, read_data  # noqa: E402


class DataFilterTests(unittest.TestCase):
    def _document(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "filter.csv"
            path.write_text(
                "x,y,tag\n"
                "1,10,first\n"
                "2,20,second\n"
                "3,not-a-number,third\n"
                "4,40,fourth\n",
                encoding="utf-8",
            )
            return read_data(
                path,
                DataFormatOptions(
                    mode="custom",
                    header_line=1,
                    data_start_line=2,
                    delimiter="comma",
                    encoding="utf-8",
                ),
            )

    def test_inclusive_bounds_and_multiple_rows_use_and(self) -> None:
        document = self._document()
        data_filter = DataFilter(
            (
                DataFilterRow(True, "x", 2, 4),
                DataFilterRow(True, "y", 20, 40),
                DataFilterRow(),
                DataFilterRow(),
                DataFilterRow(),
            )
        )
        self.assertEqual(matching_row_indices(document, data_filter), (1, 3))

    def test_non_numeric_values_fail_a_bounded_condition_and_identity_is_original(self) -> None:
        document = self._document()
        data_filter = DataFilter(
            (
                DataFilterRow(True, "y", 20, None),
                DataFilterRow(),
                DataFilterRow(),
                DataFilterRow(),
                DataFilterRow(),
            )
        )
        self.assertEqual(matching_row_indices(document, data_filter), (1, 3))
        self.assertEqual(document.rows[1][2], "second")
        self.assertEqual(document.rows[3][2], "fourth")

    def test_blank_bounds_are_a_noop_and_empty_result_is_explicit(self) -> None:
        document = self._document()
        noop = DataFilter(
            (
                DataFilterRow(True, "x"),
                DataFilterRow(),
                DataFilterRow(),
                DataFilterRow(),
                DataFilterRow(),
            )
        )
        self.assertFalse(noop.is_active)
        self.assertEqual(matching_row_indices(document, noop), (0, 1, 2, 3))

        empty = DataFilter(
            (
                DataFilterRow(True, "x", 9, 10),
                DataFilterRow(),
                DataFilterRow(),
                DataFilterRow(),
                DataFilterRow(),
            )
        )
        self.assertTrue(empty.is_active)
        self.assertEqual(matching_row_indices(document, empty), ())

    def test_finite_scientific_bounds_and_invalid_order(self) -> None:
        row = DataFilterRow(True, "x", "1e0", "4.0E+0")
        self.assertEqual((row.minimum, row.maximum), (1.0, 4.0))
        with self.assertRaises(ValueError):
            DataFilterRow(True, "x", 4, 1)
        with self.assertRaises(ValueError):
            DataFilterRow(True, "x", "nan", None)
        with self.assertRaises(ValueError):
            DataFilterRow(True, "x", "1e309", None)

    def test_invalid_schema_columns_are_disabled_without_changing_document(self) -> None:
        data_filter = DataFilter(
            (
                DataFilterRow(True, "gone", 1, 2),
                DataFilterRow(),
                DataFilterRow(),
                DataFilterRow(),
                DataFilterRow(),
            )
        )
        updated, invalid = data_filter.disable_invalid_columns(
            ("x", "y"),
            ("x", "y"),
        )
        self.assertEqual(invalid, ("gone",))
        self.assertFalse(updated.rows[0].enabled)
        self.assertIsNone(updated.rows[0].column)
        self.assertEqual(data_filter.rows[0].column, "gone")

    def test_invalid_noop_columns_are_cleared_without_notification(self) -> None:
        data_filter = DataFilter(
            (
                DataFilterRow(True, "gone"),
                DataFilterRow(False, "also-gone"),
                DataFilterRow(),
                DataFilterRow(),
                DataFilterRow(),
            ),
            overflow_rows=(DataFilterRow(True, "overflow-gone"),),
        )
        self.assertEqual(
            data_filter.invalid_columns(("x",), ("x",)),
            ("gone", "also-gone", "overflow-gone"),
        )
        updated, invalid = data_filter.disable_invalid_columns(
            ("x",),
            ("x",),
        )
        self.assertEqual(invalid, ())
        self.assertEqual(updated, DataFilter.empty())

    def test_overflow_rows_still_use_original_document_indices(self) -> None:
        document = self._document()
        data_filter = DataFilter(
            tuple(DataFilterRow() for _ in range(5)),
            overflow_rows=(DataFilterRow(True, "x", 2, 3),),
        )
        self.assertEqual(matching_row_indices(document, data_filter), (1, 2))

    def test_reserving_time_row_moves_legacy_first_row_without_losing_it(self) -> None:
        legacy = DataFilter(
            (
                DataFilterRow(True, "signal", 1, 2),
                DataFilterRow(),
                DataFilterRow(),
                DataFilterRow(),
                DataFilterRow(),
            )
        )
        reserved = legacy.reserve_time_column("Timestamp_003")
        self.assertIsNone(reserved.rows[0].column)
        self.assertEqual(reserved.rows[1].column, "signal")
        self.assertEqual(reserved.active_rows, (legacy.rows[0],))

    def test_reserving_time_row_uses_overflow_when_all_rows_are_occupied(self) -> None:
        legacy = DataFilter(
            tuple(DataFilterRow(True, "column%d" % index, 0, 1) for index in range(5))
        )
        reserved = legacy.reserve_time_column("Timestamp_003")
        self.assertIsNone(reserved.rows[0].column)
        self.assertEqual(reserved.overflow_rows, (legacy.rows[0],))


if __name__ == "__main__":
    unittest.main()

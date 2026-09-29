from __future__ import annotations

import sys
import unittest
from datetime import datetime
from pathlib import Path


VIEWER_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VIEWER_ROOT / "src"))

from openlab_viewer.axis_ticks import TimestampReference  # noqa: E402
from openlab_viewer.data_filter import DataFilter, DataFilterRow, matching_row_indices  # noqa: E402
from openlab_viewer.data_reader import DataDocument  # noqa: E402
from openlab_viewer.time_filter import (  # noqa: E402
    TimeFilterContext,
    discover_time_column,
    format_time_bound,
    parse_time_bound,
    time_filter_context,
)


class TimeFilterTests(unittest.TestCase):
    def _elapsed_document(self) -> DataDocument:
        return DataDocument(
            path=Path("Test.003.text"),
            header_lines=(
                "Test.003.text Mon, Sep 14, 2026 11:43:19 PM The Scientist",
            ),
            columns=("Timestamp_003", "Signal_003"),
            rows=((".848", "1"), ("5.474", "2"), ("10", "3")),
            modified_ns=0,
            size_bytes=0,
        )

    def test_timestamp_suffix_discovery_uses_elapsed_duration_without_mapping(self) -> None:
        document = self._elapsed_document()
        context = time_filter_context(document)
        self.assertEqual(discover_time_column(document.columns), "Timestamp_003")
        self.assertEqual(context.column, "Timestamp_003")
        self.assertIsNone(context.reference)
        self.assertEqual(parse_time_bound("26:00:00", context), 26 * 3_600)
        self.assertEqual(format_time_bound(26 * 3_600, context), "26:00:00")

    def test_wall_time_conversion_is_inverse_across_midnight(self) -> None:
        context = TimeFilterContext(
            "Timestamp_003",
            TimestampReference(
                raw_origin=10.0,
                wall_origin=datetime(2026, 9, 14, 23, 59, 59, 750000),
                zone_label="instrument time",
                source="test",
            ),
        )
        displayed = format_time_bound(10.25, context)
        self.assertEqual(displayed, "2026-09-15 00:00:00")
        self.assertAlmostEqual(parse_time_bound(displayed, context), 10.25)

    def test_timestamp_header_mapping_is_used_for_suffix_column(self) -> None:
        document = DataDocument(
            path=Path("mapped.text"),
            header_lines=("FILEOPENTIME,100,09/14/2026,11:59:59 PM",),
            columns=("Timestamp_003", "Signal_003"),
            rows=(("100", "1"), ("101", "2")),
            modified_ns=0,
            size_bytes=0,
        )
        context = time_filter_context(document)
        self.assertTrue(context.is_wall_time)
        self.assertEqual(
            format_time_bound(101.0, context),
            "2026-09-15 00:00:00",
        )

    def test_single_and_both_empty_bounds_have_expected_meaning(self) -> None:
        document = self._elapsed_document()
        maximum_only = DataFilter(
            (
                DataFilterRow(True, "Timestamp_003", None, 5.474),
                DataFilterRow(),
                DataFilterRow(),
                DataFilterRow(),
                DataFilterRow(),
            )
        )
        minimum_only = DataFilter(
            (
                DataFilterRow(True, "Timestamp_003", 5.474, None),
                DataFilterRow(),
                DataFilterRow(),
                DataFilterRow(),
                DataFilterRow(),
            )
        )
        both_empty = DataFilter(
            (
                DataFilterRow(True, "Timestamp_003"),
                DataFilterRow(),
                DataFilterRow(),
                DataFilterRow(),
                DataFilterRow(),
            )
        )
        self.assertEqual(matching_row_indices(document, maximum_only), (0, 1))
        self.assertEqual(matching_row_indices(document, minimum_only), (1, 2))
        self.assertEqual(matching_row_indices(document, both_empty), (0, 1, 2))

    def test_no_time_column_stays_explicitly_unavailable(self) -> None:
        document = self._elapsed_document()
        document = DataDocument(
            path=document.path,
            header_lines=document.header_lines,
            columns=("x", "y"),
            rows=document.rows,
            modified_ns=document.modified_ns,
            size_bytes=document.size_bytes,
        )
        context = time_filter_context(document)
        self.assertIsNone(context.column)
        self.assertIn("disabled", context.help_text)


if __name__ == "__main__":
    unittest.main()

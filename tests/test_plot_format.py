from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


VIEWER_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VIEWER_ROOT / "src"))

from openlab_viewer.plot_format import (  # noqa: E402
    PlotFormat,
    PlotFormatError,
    find_plot_format,
    load_plot_format,
    plot_format_path,
    save_plot_format,
)
from openlab_viewer.data_filter import DataFilter, DataFilterRow  # noqa: E402


class PlotFormatTests(unittest.TestCase):
    def test_v3_round_trip_serializes_five_filter_rows(self) -> None:
        settings = PlotFormat(
            data_file="sample.csv",
            layout="overlay",
            x_column="x",
            y_columns=("y",),
            filters=DataFilter(
                (
                    DataFilterRow(True, "x", 1.0, 2.0),
                    DataFilterRow(),
                    DataFilterRow(),
                    DataFilterRow(),
                    DataFilterRow(),
                )
            ),
        )
        payload = settings.to_dict()
        self.assertEqual(payload["version"], 3)
        self.assertEqual(len(payload["filters"]), 5)
        self.assertEqual(PlotFormat.from_dict(payload), settings)

    def test_v1_and_v2_have_no_filters(self) -> None:
        for version in (1, 2):
            raw = {
                "format": "OpenLab Control Plot Format",
                "version": version,
                "data_file": "legacy.dat",
                "layout": "overlay",
                "x_axis": "x",
                "y_axes": ["y"],
                "filters": [{"enabled": True, "column": "x", "min": 1, "max": 2}],
                "zoom": {
                    "x_range": None,
                    "overlay_y_range": None,
                    "stacked_y_ranges": {},
                },
            }
            self.assertEqual(PlotFormat.from_dict(raw).filters, DataFilter.empty())

    def test_v3_rejects_invalid_filter_payload(self) -> None:
        raw = {
            "format": "OpenLab Control Plot Format",
            "version": 3,
            "data_file": "sample.dat",
            "layout": "overlay",
            "x_axis": "x",
            "y_axes": ["y"],
            "filters": [{"enabled": True, "column": "x", "min": 3, "max": 1}]
            * 5,
        }
        with self.assertRaises(PlotFormatError):
            PlotFormat.from_dict(raw)

        raw.pop("filters")
        with self.assertRaises(PlotFormatError):
            PlotFormat.from_dict(raw)

    def test_exact_sidecar_names_do_not_collide(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            data_path = Path(directory) / "sample.csv"
            data_path.write_text("x,y\n0,1\n", encoding="utf-8")
            settings = PlotFormat(
                data_file=data_path.name,
                layout="overlay",
                x_column="x",
                y_columns=("y",),
            )
            destination = save_plot_format(data_path, settings, exact_name=True)
            self.assertEqual(destination, Path(str(data_path) + ".plt").resolve())
            self.assertEqual(find_plot_format(data_path, exact_name=True), destination)
            self.assertEqual(load_plot_format(destination), settings)

    def test_dat_viewer_accepts_legacy_sidecar(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            data_path = Path(directory) / "sample.dat"
            legacy_path = plot_format_path(data_path)
            legacy_path.write_text("{}", encoding="utf-8")
            self.assertEqual(find_plot_format(data_path, exact_name=True), legacy_path.resolve())


if __name__ == "__main__":
    unittest.main()

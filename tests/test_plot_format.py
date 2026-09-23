from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


VIEWER_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VIEWER_ROOT / "src"))

from openlab_viewer.plot_format import (  # noqa: E402
    PlotFormat,
    find_plot_format,
    load_plot_format,
    plot_format_path,
    save_plot_format,
)


class PlotFormatTests(unittest.TestCase):
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

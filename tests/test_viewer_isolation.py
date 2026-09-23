from __future__ import annotations

import unittest
from pathlib import Path


VIEWER_ROOT = Path(__file__).resolve().parents[1]


class ViewerIsolationTests(unittest.TestCase):
    def test_viewer_does_not_depend_on_modern_main_app_modules(self) -> None:
        source_files = tuple((VIEWER_ROOT / "src").rglob("*.py"))
        self.assertTrue(source_files)
        for source_file in source_files:
            source = source_file.read_text(encoding="utf-8")
            self.assertNotIn("PySide6", source, source_file.name)
            self.assertNotIn("labcontrol.app", source, source_file.name)
            self.assertNotIn("labcontrol.runtime", source, source_file.name)
            self.assertNotIn("from ..dat_reader", source, source_file.name)


if __name__ == "__main__":
    unittest.main()

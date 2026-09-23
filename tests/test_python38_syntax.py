from __future__ import annotations

import ast
import unittest
from pathlib import Path


VIEWER_ROOT = Path(__file__).resolve().parents[1]


class Python38SyntaxTests(unittest.TestCase):
    def test_viewer_sources_parse_as_python_38(self) -> None:
        for source_file in (VIEWER_ROOT / "src").rglob("*.py"):
            ast.parse(
                source_file.read_text(encoding="utf-8"),
                filename=str(source_file),
                feature_version=(3, 8),
            )


if __name__ == "__main__":
    unittest.main()

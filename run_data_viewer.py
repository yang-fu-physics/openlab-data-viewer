"""Run the standalone OpenLab Data Viewer from a source checkout."""

from __future__ import annotations

import sys
from pathlib import Path


VIEWER_SRC = Path(__file__).resolve().parent / "src"
if str(VIEWER_SRC) not in sys.path:
    sys.path.insert(0, str(VIEWER_SRC))

from openlab_viewer.data_viewer_app import main


if __name__ == "__main__":
    raise SystemExit(main())

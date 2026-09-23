# OpenLab Data Viewer

OpenLab Data Viewer is a standalone Windows desktop viewer for OpenLab DAT files
and ordinary delimited text files. It is intentionally isolated from the main
OpenLab Control runtime so it can be released as its own executable.

## Features

- Open the existing OpenLab DAT format with its `[Data]` section.
- Import custom text files by selecting the first data line, an optional header
  line, delimiter, ignored physical lines, ignored line prefixes, and encoding.
- Preview the parsed rows before applying custom import settings.
- Refresh the active file every 5 seconds while preserving the current plot
  view when the file is updated completely.
- Keep the last complete document visible while a writer is still producing a
  partial final line.
- Open several files as independent child windows inside one application window.
- Drop one or more local data files onto the MDI surface or a data view to open them.
- Tile or cascade the child windows, and open multiple views of the same file.
- Reuse the most recently successful data import format for each new child window
  during the current application run.
- Try to reuse the most recent X/Y columns, layout, axis scales, and zoom state
  for each new file. X/Y columns are reused by position only when the new file
  has the same total column count; otherwise column selection falls back to
  automatic numeric columns while layout and axis scales are retained.
- Detect OpenLab and common delimited text layouts automatically before showing
  the import settings dialog.
- Plot multiple numeric columns in overlay or stacked/shared-X layouts, with
  linear or logarithmic axes and PLT sidecar state.
- Use English labels, dialogs, status messages, and error messages throughout
  the viewer.

## Windows 7 build target

The viewer target is Python 3.8.x with PySide2 5.15.2.1 (Qt 5.15) and
PyInstaller 5.13.2. The main repository application remains on its existing
modern Python/Qt stack and is not imported by this subproject.

The first required release check is a packaged GUI smoke test on the actual
Windows 7 target or an equivalent virtual machine. A successful build on a
newer Windows version does not prove Windows 7 compatibility.

## Build

Install Python 3.8.x, then run `build.bat` from this directory. The script
creates `.venv-win7`, installs `requirements-win7-lock.txt`, runs the viewer
unit tests, and creates `dist\\OpenLabDataViewer.exe`.

For a source checkout, run:

```text
python run_data_viewer.py
python run_data_viewer.py --data-file C:\\path\\to\\sample.dat
python run_data_viewer.py --data-file first.csv --data-file second.tsv
```

The `--gui-smoke` option opens the interface briefly and exits. Add
`--screenshot path.png` to save a screenshot during that check.

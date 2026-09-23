# OpenLab Data Viewer User Guide

## Open a file

Start `OpenLabDataViewer.exe`, choose `File > Open Files...`, and select one or
more data files. You can also drag local data files onto the MDI surface or a
data view. Each selected file opens in its own child window inside the
same application window. Use View > Tile Data Views or View > Cascade Data
Views to arrange them.

Choose File > New Data View to create an empty child window. New child windows
start with the most recently successful data import format and try to reuse the
most recent display state from the current application run. This includes the
selected X/Y column positions, layout, axis scales, and zoom state when the new
file has the same total column count. If the count differs, column selection
falls back to automatic numeric columns while layout and axis scales are
retained. Plot state remains independent for each child window. A matching
per-file PLT sidecar takes precedence over this session template.

The viewer first detects an OpenLab `[Data]` section or a common delimited
text layout. If detection is inconclusive or the detected layout cannot read
the file, it opens `Import Data Settings` for that specific file. The dialog
starts with the most recently successful format, which you can change before
previewing and applying it.

## Configure a text file

Choose `Custom delimited text`, then set:

- `Data starts at line`: the one-based physical line where records begin.
- `Column header is on a separate line` and `Header line`: optional column names.
- `Delimiter`: comma, tab, semicolon, pipe, whitespace, or one custom character.
- `Ignore physical lines`: absolute line numbers or ranges such as `1-3, 8, 12-14`.
- `Ignore line prefixes`: comma-separated prefixes such as `#` or `//`; leading whitespace is ignored.
- `Encoding`: automatic detection, UTF-8, UTF-16, or GB18030.

`Preview` shows the original physical line numbers and the first parsed rows.
The entire file is parsed before the preview is accepted, so an invalid row
later in the file is still reported. `Apply` changes the window only after a
complete read succeeds. Without a header, generated names such as `Column 1`
are used and the first data row is retained.

Custom records use one physical line per record. CSV-style quoted delimiters
and escaped double quotes are supported. Multiline quoted records and quoted
whitespace fields are reported as unsupported instead of being guessed.

## Live updates

`Auto-refresh (5 s)` is enabled by default. The viewer keeps the last
complete document visible while a writer is appending an unfinished final
record. When a complete replacement or append is available, the data is
reloaded while the current axes, layout, scales, and manual zoom are retained.
Refresh reads run outside the GUI thread so a large file update does not block
interaction. Temporary read failures are shown in the status line and retried
without repeated modal dialogs.

Each child window has independent import settings and plot state. Use `File >
New Data View` and open the same file again to create another independent view
of that file.

## Plot settings

Use the plot context menu to select X/Y columns, overlay or stacked/shared-X
layout, and linear or logarithmic scales. Drag inside a plot to zoom and
double-click a point for its complete source row and physical line number.

`File > Save PLT` writes an explicit sidecar using the complete data filename,
for example `sample.csv.plt`. OpenLab DAT files also accept the legacy
`sample.plt` sidecar when no full-name sidecar exists.

## Windows 7 support boundary

The release target is Windows 7 SP1 with the tested architecture recorded in
the release report. The executable must be tested on that target or an
equivalent virtual machine after packaging. A successful build or a test on a
newer Windows version alone is not a Windows 7 compatibility claim.

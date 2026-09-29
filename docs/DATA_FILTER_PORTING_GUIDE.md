# Data Filter Porting Guide

This task changes only the independent `openlab-control/viewer` repository.
The parent OpenLab Control source tree was read for this mapping and was not
modified.

## Module mapping

| Viewer implementation | Parent target | Porting note |
| --- | --- | --- |
| `src/openlab_viewer/data_filter.py` | `src/labcontrol/data_filter.py` | Copy the Qt-independent `DataFilterRow`, `DataFilter`, finite-bound validation, schema invalidation, and shared original-row selection. Keep the five-row model independent of either Qt binding. |
| `src/openlab_viewer/data_reader.py` | `src/labcontrol/dat_reader.py` | Viewer uses `DataDocument`/`DataPoint`, `source_line_numbers`, and configurable custom text formats. Parent uses `DatDocument`/`DatPoint` and OpenLab DAT-only reading. Adapt the selection helper’s document access rather than changing either reader contract. |
| `src/openlab_viewer/plot_format.py` | `src/labcontrol/plot_format.py` | Viewer PLT is v3 and stores `filters`; v1/v2 are accepted with `DataFilter.empty()`. Parent’s existing sidecar naming and save policy are different, so port the field validation and explicitly choose the parent compatibility policy. |
| `src/openlab_viewer/ui/data_filter_dialog.py` | `src/labcontrol/ui/data_filter_dialog.py` | Port the five-row English dialog and Apply/OK/Cancel/Clear semantics. The callback must commit only after dialog validation and keep the dialog open when the current schema rejects the candidate. |
| `src/openlab_viewer/ui/dat_plot.py` | `src/labcontrol/ui/dat_plot.py` | Compute one row-index tuple in the document/axis rebuild, filter every selected series by `point.row_index`, and let autoscaling and hit testing consume the rebuilt points. Do not filter in paint or once per series. |
| `src/openlab_viewer/ui/data_browser.py` | `src/labcontrol/ui/data_browser.py` | Add the Data Filter button, status counts, schema invalidation message, refresh reapplication, and PLT/template handoff. Parent’s browser has no standalone import-options state, so retain the parent’s load path. |
| `src/openlab_viewer/ui/data_viewer_window.py` | `src/labcontrol/ui/data_viewer_window.py` | Port only if the parent window exposes the same per-view display-template signal. The viewer’s narrow-window child fitting is independent of filtering. |

## Qt and runtime differences

- The viewer runs Python 3.8 with PySide2 5.15.2.1. The parent runs its
  existing modern Python/PySide6 stack.
- Viewer dialogs use `exec_()`, Qt 5 enum values such as `Qt.Checked`, and the
  Qt 5 widget imports. In PySide6, use the parent’s scoped enums and `exec()`.
- Preserve the viewer’s Python 3.8-compatible dataclass and typing style when
  moving the model; do not introduce parent-only `slots=True`, `zip(strict=…)`,
  or runtime-only generic aliases into the viewer.

## Refresh and zoom behavior

The standalone viewer keeps its existing five-second signature poll and reads a
complete document in a background task. A successful refresh rebuilds the
shared filtered row selection. With unchanged filter settings it preserves a
user zoom; changing filter settings resets zoom. If a selected filter column
disappears or becomes nonnumeric, the viewer clears that selection and reports
the column only when it was an active bounded condition.

The parent browser currently uses a 750 ms poll and its own reload path. Port the
selection rebuild into that path, but preserve the parent’s existing threading,
signature, and transient-read behavior rather than copying the viewer timer.

## PLT and autosave differences

The viewer uses complete-filename sidecars such as `sample.csv.plt` and keeps
the existing explicit `Save PLT` behavior (`explicit_plot_save=True`). Filter
changes therefore update in-memory state and session templates without writing
an automatic sidecar. The parent browser currently auto-saves display changes
from `_display_changed` and uses its established DAT sidecar lookup. Decide
whether parent users should retain that automatic save policy; do not silently
inherit the standalone viewer’s multi-view naming policy.

When porting v3, preserve old v1/v2 reads as no filters and reject malformed v3
filter arrays, non-finite bounds, and Min > Max. A direct PLT load should reject
an enabled bounded filter whose named column is absent/non-numeric, while
clearing unknown no-op selections. A session display template may translate
filter columns by position only when the column count matches; clear them for a
different count.

## Verification checklist

Run the viewer’s `tests/test_data_filter.py`, PLT tests, and PySide2 MDI tests
as a behavioral reference. Add equivalent parent tests for inclusive bounds,
AND conditions, nonnumeric values, original row identity, multiple series,
independent views, refresh, schema invalidation, v1/v2 PLT, and same-count versus
different-count template inheritance. Inspect both the five-row dialog and the
status/footer empty-result message after adapting PySide6 APIs.

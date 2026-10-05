# Data Filter Porting Guide

This task changes only the independent `openlab-control/viewer` repository.
The parent OpenLab Control source tree was read for this mapping and was not
modified.

## Module mapping

| Viewer implementation | Parent target | Porting note |
| --- | --- | --- |
| `src/openlab_viewer/data_filter.py` | `src/labcontrol/data_filter.py` | Copy the Qt-independent `DataFilterRow`, `DataFilter`, finite-bound validation, schema invalidation, and shared original-row selection. Keep five visible rows independent of either Qt binding; preserve a legacy first-row condition in `overflow_rows` when row zero is reserved for time. Retain `enabled` only for legacy PLT reads; new matching uses column plus at least one bound. |
| `src/openlab_viewer/data_reader.py` | `src/labcontrol/dat_reader.py` | Viewer uses `DataDocument`/`DataPoint`, `source_line_numbers`, and configurable custom text formats. Parent uses `DatDocument`/`DatPoint` and OpenLab DAT-only reading. Adapt the selection helper’s document access rather than changing either reader contract. |
| `src/openlab_viewer/time_filter.py` | `src/labcontrol/time_filter.py` | Keep timestamp/time discovery separate from axis positional matching. Discover names such as `Timestamp_003` only for the fixed filter row; use `axis_ticks.TimestampReference` when a reliable mapping exists, otherwise expose elapsed duration. |
| `src/openlab_viewer/plot_format.py` | `src/labcontrol/plot_format.py` | Viewer PLT is v5 and stores five `filters` rows plus optional `filter_overflow`; v1/v2 have no filters and v3/v4 retain legacy enable semantics. Parent’s existing sidecar naming and save policy are different, so port the field validation and explicitly choose the parent compatibility policy. |
| `src/openlab_viewer/ui/data_filter_dialog.py` | `src/labcontrol/ui/data_filter_dialog.py` | Port the five-row English dialog with an always-visible fixed Time row plus four general rows and no Enabled column. The callback must commit only after dialog validation, keep the dialog open when the current schema rejects the candidate, and show the time-row help/unavailable state when no time column exists. |
| `src/openlab_viewer/ui/dat_plot.py` | `src/labcontrol/ui/dat_plot.py` | Compute one row-index tuple in the document/axis rebuild, filter every selected series by `point.row_index`, and let autoscaling and hit testing consume the rebuilt points. Do not filter in paint or once per series. Keep the single-click selected-point marker local to each canvas; double-click only adds the existing details action, and neither state is part of PLT. |
| `src/openlab_viewer/ui/data_browser.py` | `src/labcontrol/ui/data_browser.py` | Add the Data Filter button, status counts, schema invalidation message, refresh reapplication, PLT/template handoff, filtered source-order point navigation, and background raw-file browsing. Parent’s browser has no standalone import-options state, so retain the parent’s load path. |
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

The fixed Time row is rebuilt against each document schema. A modal dialog can
outlive a background refresh, so the apply callback must compare the committed
filter with the candidate and reject stale column selections visibly instead of
reporting a false success. Invalid no-op columns are still cleared so display
format/template emission cannot call `columns.index()` on a removed selection.

Background file reads carry their source path and format options with the task.
Until a task succeeds, the committed document, path, and import options remain
unchanged; a failed new-file request remains the pending target for Import
Settings, while an automatic refresh reports a transient-read error against the
currently committed file. A newer request invalidates an older result, and a
closed view invalidates all queued results. Initial format detection and the
existing automatic import-format retry run in the worker as well.

The plot retains every finite source point in its path, including log-scale
paths. Series larger than 3,000 points hide only the individual marker layer;
that threshold is not a path downsampling rule. Cached full paths and natural
ranges are keyed by the immutable point set, axes/scales, data ranges, plot
geometry, and device-pixel ratio; rebuilds, filtering, zoom, scale/layout
changes, and resize invalidate the affected cache. Numeric column conversion is
cached on the immutable document and warmed by the background reader. This
keeps spikes, repeated or non-monotonic X values, original row identity, and
zoomed-in detail intact while avoiding repeated conversion/path construction.

On the Python 3.8/PySide2 test machine, a temporary 3,202,716-byte,
210,000-row, two-Y CSV measured a 0.0003 s background scheduling return,
1.0771 s until the initial commit, 1.1211 s for the first full-path render,
1.3789 s after one appended row, 0.6611 s to apply an X filter selecting
199,001 rows, and 0.0350 s for a point hit test. Two cached paths contained
210,000 vertices each. Two hundred unchanged polls took 0.0051 s total. These
figures are a reference for this environment, not a Windows 7 guarantee.

Single-clicking a hit point selects it on that child view and draws a
high-contrast marker on top of the source curve even when the normal
large-series markers are hidden. Double-clicking selects the point and emits
the existing full-row details signal. Repaints, zoom,
scale changes, and resize recompute the marker from the selected point. A
successful refresh replaces the selected point with the same series and
original row only when its row index and complete source row still match;
filtering it out, changing that row, removing its series, or loading another
file clears the marker. The selection is intentionally transient and is not
serialized to PLT or shared with another child view.

The plot context menu exposes the same `Data Filter...` callback as the
browser button and a `Browse Raw File` action. Raw browsing uses only the
successfully committed path and its selected decoder, reads bytes in a worker,
and shows them in a read-only text window; it never displays filtered rows or
writes the source file. A detail window offers `Previous Point` and `Next
Point` over the current series after filtering, in original row order. It
closes when a refresh or point rebuild changes the available records so it
cannot silently display a different source row.

## Time-row behavior

The viewer always renders five rows. Row zero is labeled `Time` and uses the
first discovered timestamp/time column as a fixed label; rows one through four
remain general numeric filters. If no such column exists, row zero stays
visible but its editors are disabled with an explanation. `Timestamp_003` and
similar names are recognized for this dialog only; axis selection and
positional inheritance keep their existing rules.

If `TimestampReference` supplies a mapping, the editor uses a clearable
millisecond date-time picker and converts bounds back to raw seconds. The UI
identifies the mapping source and displayed timezone as inferred metadata, not
verified instrument time. The conversion handles midnight crossings. Without
a reliable mapping, the editor explicitly says elapsed time and accepts seconds
or `HH:MM:SS`/`days HH:MM:SS`; hours may exceed 24. It does not infer an epoch
from small values or from an export/end-time header. On first use for a loaded
document, Min is initialized from the first parsed data record in the time
column, not from a header or the whole-column minimum; Max is blank. The
initial default is only used when no time bound has been initialized. Applied
edits, deliberate clears, PLT-restored bounds, and refreshes must preserve the
existing row state.

Bounds are inclusive. Blank Min means `value <= Max`, blank Max means
`value >= Min`, and both blank mean no filtering. A row applies only when its
column is valid and at least one bound is present. `Min > Max` is an English
validation error. The parent port should preserve these semantics and add
conversion tests for both wall-time and elapsed-time documents.

## PLT and autosave differences

The viewer uses complete-filename sidecars such as `sample.csv.plt` and keeps
the existing explicit `Save PLT` behavior (`explicit_plot_save=True`). Filter
changes therefore update in-memory state and session templates without writing
an automatic sidecar. The parent browser currently auto-saves display changes
from `_display_changed` and uses its established DAT sidecar lookup. Decide
whether parent users should retain that automatic save policy; do not silently
inherit the standalone viewer’s multi-view naming policy.

When porting v3/v4/v5, preserve old v1/v2 reads as no filters and reject
malformed filter arrays, non-finite bounds, and Min > Max. For v3/v4, clear
disabled rows with bounds while loading so removing the Enabled control cannot
silently activate an old condition. New v5 saves and templates do not depend on
the enabled flag. A direct PLT load should reject
a bounded filter whose named column is absent/non-numeric, while
clearing unknown no-op selections. When reserving row zero for time, move an
existing arbitrary first-row condition into an available general row or the
serialized `filter_overflow` list; never silently discard it. A session display
template may translate filter columns by position only when the column count
matches; clear them for a different count.

## Verification checklist

Run the viewer’s `tests/test_data_filter.py`, `tests/test_time_filter.py`, PLT
tests, and PySide2 MDI tests as a behavioral reference. Add equivalent parent
tests for inclusive bounds, one-sided/empty bounds, wall-time inverse conversion,
elapsed durations over 24 hours, nonnumeric values, original row identity,
multiple series, independent views, refresh/schema invalidation, v1/v2/v3/v4/v5
PLT, no-Enabled dialog controls, and same-count versus different-count template
inheritance. Inspect the fixed Time row, its first-record Min default,
stale-dialog rejection, and status/footer empty-result message after adapting
PySide6 APIs. Exercise single-click marker visibility for a single point,
double-click details and navigation, large full-point paths,
repeated/non-monotonic X, log axes, zoom/resize, drag-versus-click handling,
context-menu raw browsing/filter reuse, multi-window isolation, and
refresh/filter row reconciliation.

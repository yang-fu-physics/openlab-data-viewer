"""Portable ``.plt`` plot-format support for the standalone viewer.

PLT stores the selected data file, columns, layout, axis scales, and zoom
ranges without binding to an active measurement. Reads validate the version,
unique columns, and finite increasing ranges; writes use an atomic sidecar
replacement.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Tuple


PLOT_FORMAT_MARKER = "OpenLab Control Plot Format"
PLOT_FORMAT_VERSION = 2
SUPPORTED_PLOT_FORMAT_VERSIONS = {1, PLOT_FORMAT_VERSION}
PLOT_LAYOUTS = {"overlay", "stacked"}
LINEAR_SCALE = "linear"
LOG_SCALE = "log"
PLOT_SCALES = {LINEAR_SCALE, LOG_SCALE}


class PlotFormatError(ValueError):
    """The PLT content is invalid, unsupported, or not safely readable."""


Range = Tuple[float, float]


def _validated_range(value: Any, field_name: str) -> Range | None:
    """Parse an optional finite increasing axis range."""

    if value is None:
        return None
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise PlotFormatError(f"{field_name} must contain exactly two numbers")
    try:
        low, high = float(value[0]), float(value[1])
    except (TypeError, ValueError) as exc:
        raise PlotFormatError(f"{field_name} must contain numbers") from exc
    if not math.isfinite(low) or not math.isfinite(high) or low >= high:
        raise PlotFormatError(f"{field_name} must be a finite increasing range")
    return low, high


@dataclass(frozen=True)
class PlotFormat:
    """A validated and serializable viewer plot state."""

    data_file: str
    layout: str
    x_column: str | None
    y_columns: tuple[str, ...]
    x_range: Range | None = None
    overlay_y_range: Range | None = None
    stacked_y_ranges: dict[str, Range] = field(default_factory=dict)
    x_scale: str = LINEAR_SCALE
    y_scale: str = LINEAR_SCALE

    def __post_init__(self) -> None:
        """Apply layout, axis-scale, and range constraints at construction."""

        if self.layout not in PLOT_LAYOUTS:
            raise PlotFormatError(f"Unknown plot layout: {self.layout}")
        if not self.y_columns:
            raise PlotFormatError("At least one Y column is required")
        if len(self.y_columns) != len(set(self.y_columns)):
            raise PlotFormatError("Y columns must be unique")
        if self.x_scale not in PLOT_SCALES:
            raise PlotFormatError(f"Unknown X scale: {self.x_scale}")
        if self.y_scale not in PLOT_SCALES:
            raise PlotFormatError(f"Unknown Y scale: {self.y_scale}")
        _validated_range(self.x_range, "x_range")
        _validated_range(self.overlay_y_range, "overlay_y_range")
        for name, value in self.stacked_y_ranges.items():
            _validated_range(value, f"stacked_y_ranges.{name}")
        if self.x_scale == LOG_SCALE and self.x_range is not None and self.x_range[0] <= 0:
            raise PlotFormatError("x_range must be positive for logarithmic X scale")
        if self.y_scale == LOG_SCALE:
            if self.overlay_y_range is not None and self.overlay_y_range[0] <= 0:
                raise PlotFormatError(
                    "overlay_y_range must be positive for logarithmic Y scale"
                )
            if any(value[0] <= 0 for value in self.stacked_y_ranges.values()):
                raise PlotFormatError(
                    "stacked_y_ranges must be positive for logarithmic Y scale"
                )

    def to_dict(self) -> dict[str, Any]:
        """Convert to a JSON object with format marker and version."""

        return {
            "format": PLOT_FORMAT_MARKER,
            "version": PLOT_FORMAT_VERSION,
            "data_file": self.data_file,
            "layout": self.layout,
            "x_axis": self.x_column,
            "y_axes": list(self.y_columns),
            "x_scale": self.x_scale,
            "y_scale": self.y_scale,
            "zoom": {
                "x_range": list(self.x_range) if self.x_range is not None else None,
                "overlay_y_range": (
                    list(self.overlay_y_range) if self.overlay_y_range is not None else None
                ),
                "stacked_y_ranges": {
                    name: list(value) for name, value in self.stacked_y_ranges.items()
                },
            },
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> PlotFormat:
        """Build and validate a plot state from a supported JSON version."""

        if raw.get("format") != PLOT_FORMAT_MARKER:
            raise PlotFormatError("Not an OpenLab Control PLT file")
        version = raw.get("version")
        if version not in SUPPORTED_PLOT_FORMAT_VERSIONS:
            raise PlotFormatError(f"Unsupported PLT version: {raw.get('version')}")
        layout = str(raw.get("layout", "overlay")).lower()
        x_raw = raw.get("x_axis")
        x_column = None if x_raw is None else str(x_raw)
        y_raw = raw.get("y_axes")
        if not isinstance(y_raw, list):
            raise PlotFormatError("y_axes must be a list")
        y_columns = tuple(str(value) for value in y_raw if str(value))
        zoom = raw.get("zoom", {})
        if not isinstance(zoom, dict):
            raise PlotFormatError("zoom must be an object")
        stacked_raw = zoom.get("stacked_y_ranges", {})
        if not isinstance(stacked_raw, dict):
            raise PlotFormatError("stacked_y_ranges must be an object")
        stacked = {
            str(name): value
            for name, raw_range in stacked_raw.items()
            if (value := _validated_range(raw_range, f"stacked_y_ranges.{name}")) is not None
        }
        return cls(
            data_file=str(raw.get("data_file", "")),
            layout=layout,
            x_column=x_column,
            y_columns=y_columns,
            x_range=_validated_range(zoom.get("x_range"), "x_range"),
            overlay_y_range=_validated_range(
                zoom.get("overlay_y_range"), "overlay_y_range"
            ),
            stacked_y_ranges=stacked,
            x_scale=str(raw.get("x_scale", LINEAR_SCALE)).casefold(),
            y_scale=str(raw.get("y_scale", LINEAR_SCALE)).casefold(),
        )


@dataclass(frozen=True)
class DisplayFormatTemplate:
    """In-memory display state matched by column count and position."""

    plot_format: PlotFormat
    column_count: int
    x_column_index: int | None
    y_column_indices: tuple[int, ...]
    stacked_y_ranges: tuple[Range | None, ...] = ()


def plot_format_path(data_path: str | Path, *, exact_name: bool = False) -> Path:
    """Return the sidecar path for a data file.

    The standalone viewer uses the complete filename plus ``.plt`` so files such
    as ``sample.dat`` and ``sample.csv`` cannot collide. The legacy path remains
    the default for the main OpenLab Control application.
    """

    source = Path(data_path).resolve()
    return (
        source.with_name(source.name + ".plt")
        if exact_name
        else source.with_suffix(".plt")
    )


def find_plot_format(
    data_path: str | Path,
    *,
    exact_name: bool = False,
    allow_legacy: bool = True,
) -> Path | None:
    """Find a sidecar, optionally accepting the legacy extension-only path."""

    source = Path(data_path).resolve()
    canonical = plot_format_path(source, exact_name=exact_name)
    if canonical.exists():
        return canonical
    if exact_name and allow_legacy and source.suffix.casefold() == ".dat":
        legacy = plot_format_path(source)
        if legacy.exists():
            return legacy
    if not exact_name:
        additive = Path(str(source) + ".plt")
        return additive if additive.exists() else None
    return None


def save_plot_format(
    data_path: str | Path,
    plot_format: PlotFormat,
    *,
    exact_name: bool = False,
) -> Path:
    """Save a PLT as UTF-8 JSON using an atomic sidecar replacement."""

    destination = plot_format_path(data_path, exact_name=exact_name)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    payload = json.dumps(plot_format.to_dict(), ensure_ascii=False, indent=2) + "\n"
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as stream:
            stream.write(payload)
        temporary.replace(destination)
    except OSError as exc:
        raise PlotFormatError(f"Unable to save PLT file: {destination}") from exc
    return destination


def load_plot_format(path: str | Path) -> PlotFormat:
    """Read the root object and validate PLT content."""

    source = Path(path).resolve()
    try:
        raw = json.loads(source.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PlotFormatError(f"Unable to read PLT file: {source}") from exc
    if not isinstance(raw, dict):
        raise PlotFormatError("PLT root must be an object")
    return PlotFormat.from_dict(raw)

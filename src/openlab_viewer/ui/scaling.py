"""Small display scaling helpers shared by the viewer widgets."""

from __future__ import annotations

import math

from PySide2.QtGui import QScreen
from PySide2.QtWidgets import QApplication


BASE_WIDTH = 1920.0
BASE_HEIGHT = 1080.0
MIN_AUTO_SCALE = 1.0
MAX_AUTO_SCALE = 1.4


def automatic_ui_scale(pixel_width: float, pixel_height: float) -> float:
    """Return a conservative scale rounded to 0.05 increments."""

    if pixel_width <= 0 or pixel_height <= 0:
        return MIN_AUTO_SCALE
    resolution_ratio = min(pixel_width / BASE_WIDTH, pixel_height / BASE_HEIGHT)
    scale = math.sqrt(max(1.0, resolution_ratio))
    scale = min(MAX_AUTO_SCALE, max(MIN_AUTO_SCALE, scale))
    return round(scale * 20.0) / 20.0


def screen_ui_scale(screen: QScreen | None) -> float:
    """Estimate a scale from the available screen pixels and device ratio."""

    if screen is None:
        return MIN_AUTO_SCALE
    geometry = screen.availableGeometry()
    pixel_ratio = max(1.0, float(screen.devicePixelRatio()))
    return automatic_ui_scale(
        geometry.width() * pixel_ratio,
        geometry.height() * pixel_ratio,
    )


def current_ui_scale() -> float:
    """Read the scale stored on the QApplication instance."""

    application = QApplication.instance()
    if application is None:
        return 1.0
    value = application.property("openlabUiScale")
    try:
        return float(value)
    except (TypeError, ValueError):
        return 1.0


def scaled(value: float, scale: float | None = None) -> int:
    """Scale a fixed pixel dimension for Qt geometry."""

    return max(1, round(value * (current_ui_scale() if scale is None else scale)))


def scaled_float(value: float, scale: float | None = None) -> float:
    """Scale a floating-point drawing dimension for Qt painting."""

    return value * (current_ui_scale() if scale is None else scale)

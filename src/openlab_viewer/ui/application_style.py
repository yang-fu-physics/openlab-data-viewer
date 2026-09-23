"""English-neutral Qt appearance setup without OpenLab Control imports."""

from __future__ import annotations

import os
from pathlib import Path

from PySide2.QtGui import QColor, QFont, QFontDatabase, QPalette

from .scaling import screen_ui_scale


def configure_qt_font(application, point_size: float = 10.0) -> None:
    """Prefer a Windows font that renders Unicode data labels."""

    fonts_dir = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
    for file_name in ("segoeui.ttf", "msyh.ttc", "simhei.ttf"):
        candidate = fonts_dir / file_name
        if not candidate.exists():
            continue
        font_id = QFontDatabase.addApplicationFont(str(candidate))
        families = QFontDatabase.applicationFontFamilies(font_id)
        if families:
            font = QFont(families[-1])
            font.setPointSizeF(point_size)
            application.setFont(font)
            return
    font = application.font()
    font.setPointSizeF(point_size)
    application.setFont(font)


def configure_qt_appearance(
    application,
    requested_scale: float | None = None,
    font_scale: float = 1.0,
) -> float:
    """Apply the viewer palette and fixed-pixel scaling."""

    scale = requested_scale if requested_scale is not None else screen_ui_scale(application.primaryScreen())
    application.setProperty("openlabUiScale", scale)
    application.setProperty("openlabUiScaleMode", "manual" if requested_scale is not None else "auto")
    application.setProperty("openlabFontScale", float(font_scale))
    application.setStyle("Fusion")
    palette = application.palette()
    palette.setColor(QPalette.Highlight, QColor("#5c6b79"))
    palette.setColor(QPalette.HighlightedText, QColor("#ffffff"))
    palette.setColor(QPalette.AlternateBase, QColor("#f7f9fa"))
    application.setPalette(palette)
    configure_qt_font(application, 10.0 * scale * float(font_scale))
    return scale

"""Conservative initial sizing for standalone viewer dialogs."""

from __future__ import annotations

from PySide2.QtWidgets import QWidget

from .scaling import scaled


def fit_initial_window_width(widget: QWidget, preferred_height: int = 470) -> None:
    """Give a dialog enough room for its controls without forcing a large window."""

    widget.adjustSize()
    widget.resize(
        max(widget.width(), scaled(720)),
        max(widget.height(), preferred_height),
    )

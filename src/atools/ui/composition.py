from __future__ import annotations

from PySide6.QtWidgets import QWidget


def apply_blur(widget: QWidget):
    # The redesigned UI uses fully styled matte surfaces instead of OS blur.
    # Keeping this as a no-op avoids composition glitches on some systems.
    _ = widget

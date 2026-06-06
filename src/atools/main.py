from __future__ import annotations

import sys

from PySide6.QtCore import QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from atools.logging_setup import configure_logging
from atools.paths import asset_path
from atools.settings import load_settings
from atools.theme import apply_theme
from atools.updater import maybe_prompt_for_update
from atools.ui.main_window import MainWindow


def run() -> int:
    configure_logging()
    app = QApplication(sys.argv)
    app.setApplicationName("RichCore V12")
    icon_path = asset_path("iconka.ico")
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))
    settings = load_settings()
    apply_theme(app, settings.theme_mode)
    window = MainWindow()
    window.show()
    QTimer.singleShot(1400, lambda: maybe_prompt_for_update(window))
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(run())

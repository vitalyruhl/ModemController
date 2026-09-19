"""Application entry points for the desktop modem terminal."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from modem_controller.catalog.storage import (
    SettingsStore,
    remember_settings_location,
    resolve_settings_location,
)
from modem_controller.ui.main_window import MainWindow


def create_main_window() -> MainWindow:
    """Create the UI without opening a port or sending any bytes."""

    application_directory = Path(sys.argv[0]).resolve().parent
    user_directory = (
        Path(os.environ.get("LOCALAPPDATA", Path.home())) / "ModemController"
    )
    location = resolve_settings_location(application_directory, user_directory)
    return MainWindow(
        settings_store=SettingsStore(location.directory),
        remember_location=lambda path: remember_settings_location(user_directory, path),
        settings_message=location.fallback_message
        or f"Settings location: {location.directory}",
    )


def main() -> int:
    app = QApplication(sys.argv)
    window = create_main_window()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

"""Application entry points for the desktop modem terminal."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from modem_controller.catalog.models import load_starter_catalog
from modem_controller.catalog.portable import load_portable_catalog, seed_catalog_files
from modem_controller.catalog.storage import (
    SettingsStore,
    StorageError,
    remember_settings_location,
    resolve_settings_location,
)
from modem_controller.paths import application_directory
from modem_controller.ui.main_window import MainWindow


def create_main_window() -> MainWindow:
    """Create the UI without opening a port or sending any bytes."""

    user_directory = (
        Path(os.environ.get("LOCALAPPDATA", Path.home())) / "ModemController"
    )
    location = resolve_settings_location(application_directory(), user_directory)
    message = (
        location.fallback_message + f" Settings/catalog location: {location.directory}"
    )
    try:
        seed_catalog_files(location.directory)
        catalog = load_portable_catalog(location.directory)
    except (StorageError, OSError) as error:
        catalog = load_starter_catalog()
        message += f" Catalog not loaded; bundled defaults are shown. {error}"
    return MainWindow(
        catalog=catalog,
        settings_store=SettingsStore(location.directory),
        remember_location=lambda path: remember_settings_location(user_directory, path),
        settings_message=message,
    )


def main() -> int:
    app = QApplication(sys.argv)
    window = create_main_window()
    window.show()
    if "--smoke-test" in sys.argv:
        QTimer.singleShot(150, window.close)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

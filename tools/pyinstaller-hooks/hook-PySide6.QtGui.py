"""The text-only desktop needs native/offscreen platforms, not media/QML plugins."""

from pathlib import Path

from PyInstaller.utils.hooks.qt import add_qt6_dependencies

hiddenimports, binaries, datas = add_qt6_dependencies(__file__)
hiddenimports = [
    name
    for name in hiddenimports
    if name in {"PySide6.QtCore", "PySide6.QtGui", "PySide6.QtWidgets"}
]
binaries = [
    (source, destination)
    for source, destination in binaries
    if "plugins" not in destination.replace("\\", "/")
    or Path(source).name.lower() in {"qwindows.dll", "qoffscreen.dll", "qminimal.dll"}
]

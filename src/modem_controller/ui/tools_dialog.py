"""A small launcher for independent portable plugins."""

import sys
from importlib.resources import files
from pathlib import Path

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from modem_controller.workflows.plugins import discover_plugins, launch_plugin


class ToolsDialog(QDialog):
    def __init__(self, directory: Path, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Plugins")
        self.resize(420, 180)
        root = directory / "plugins"
        if not root.exists() and not getattr(sys, "frozen", False):
            root = Path(str(files("modem_controller").joinpath("tool_data", "plugins")))
        self.plugins = discover_plugins(root)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Choose a plugin to open its own window.", self))
        self.selector = QComboBox(self)
        for plugin in self.plugins:
            self.selector.addItem(plugin.name)
        layout.addWidget(self.selector)
        self.run_button = QPushButton("Start plugin", self)
        self.run_button.setEnabled(bool(self.plugins))
        self.run_button.clicked.connect(self._run)
        layout.addWidget(self.run_button)
        self.message = QLabel("" if self.plugins else "No plugins found.", self)
        self.message.setWordWrap(True)
        layout.addWidget(self.message)
        buttons = QDialogButtonBox(QDialogButtonBox.Close, self)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _run(self):
        index = self.selector.currentIndex()
        if index < 0:
            return
        plugin = self.plugins[index]
        try:
            launch_plugin(plugin)
        except (OSError, ValueError, RuntimeError) as error:
            self.message.setText(str(error))
        else:
            self.message.setText(f"{plugin.name} started in its own window.")

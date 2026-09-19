"""Explicit review and asynchronous execution of selected local tool definitions."""

import json
from dataclasses import asdict, replace
from importlib.resources import files
from pathlib import Path
from threading import Event

from PySide6.QtCore import QThread
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)

from modem_controller.catalog.storage import SettingsStore
from modem_controller.ui.ras_options import RasOptionsDialog
from modem_controller.workflows.tools import load_tool_registry, review_tool, run_tool


class _ToolThread(QThread):
    def __init__(self, definition, parent=None):
        super().__init__(parent)
        self.definition = definition
        self.cancelled = Event()
        self.result = None

    def run(self):
        self.result = run_tool(self.definition, cancelled=self.cancelled)


class ToolsDialog(QDialog):
    def __init__(self, directory: Path, parent=None):
        super().__init__(parent)
        self.directory = directory
        self.definitions = ()
        self.reviewed = None
        self.thread = None
        self.close_pending = False
        self.setWindowTitle("Local tools - serial connection released")
        self.resize(850, 650)
        layout = QVBoxLayout(self)
        notice = QLabel(
            "Local scripts run under your account and are not sandboxed. "
            "Review the script and arguments. Cancellation stops owned processes "
            "but cannot undo external effects. Never pass secrets in arguments.",
            self,
        )
        notice.setWordWrap(True)
        layout.addWidget(notice)
        self.selector = QComboBox(self)
        self.interpreter = QLineEdit(self)
        self.arguments = QPlainTextEdit(self)
        self.arguments.setMaximumHeight(80)
        self.working_directory = QLineEdit(self)
        form = QFormLayout()
        for label, widget in (
            ("Tool", self.selector),
            ("Interpreter (local executable)", self.interpreter),
            ("Arguments (JSON list, no secrets)", self.arguments),
            ("Working directory", self.working_directory),
        ):
            form.addRow(label, widget)
        layout.addLayout(form)
        self.preview = QPlainTextEdit(self)
        self.preview.setReadOnly(True)
        layout.addWidget(self.preview)
        actions = QHBoxLayout()
        self.import_button = QPushButton("Import definitions...", self)
        self.save_button = QPushButton("Save definitions...", self)
        self.review_button = QPushButton("Confirm script review", self)
        self.scope_button = QPushButton("Collection options...", self)
        self.scope_button.clicked.connect(self._collection_options)
        self.run_button = QPushButton("Run selected tool", self)
        self.cancel_button = QPushButton("Cancel running tool", self)
        self.cancel_button.setEnabled(False)
        for button in (
            self.import_button,
            self.save_button,
            self.review_button,
            self.scope_button,
            self.run_button,
            self.cancel_button,
        ):
            actions.addWidget(button)
        layout.addLayout(actions)
        self.output = QPlainTextEdit(self)
        self.output.setReadOnly(True)
        self.output.setMaximumBlockCount(1500)
        layout.addWidget(self.output)
        self.import_button.clicked.connect(self._import)
        self.save_button.clicked.connect(self._save)
        self.review_button.clicked.connect(self._review)
        self.run_button.clicked.connect(self._run)
        self.cancel_button.clicked.connect(
            lambda: self.thread and self.thread.cancelled.set()
        )
        self.selector.currentIndexChanged.connect(self._selected)
        for widget in (self.interpreter, self.arguments, self.working_directory):
            widget.textChanged.connect(self._invalidate)
        self.run_button.setEnabled(False)
        path = directory / "tools.json"
        if path.exists():
            self._load(path)
        else:
            self._load(
                Path(str(files("modem_controller").joinpath("tool_data", "tools.json")))
            )

    def _load(self, path):
        try:
            self.definitions = load_tool_registry(path)
            self.selector.clear()
            for definition in self.definitions:
                self.selector.addItem(definition.label)
            self._selected()
        except (OSError, ValueError, TypeError, KeyError) as error:
            self.output.setPlainText(f"Definitions unavailable: {error}")

    def _selected(self):
        index = self.selector.currentIndex()
        if index < 0:
            self._invalidate()
            return
        tool = self.definitions[index]
        self.scope_button.setEnabled(tool.id == "windows-ras-collector")
        self.interpreter.setText(str(tool.interpreter or ""))
        self.arguments.setPlainText(json.dumps(tool.arguments, indent=2))
        self.working_directory.setText(
            str(tool.working_directory or tool.script.parent)
        )
        try:
            with tool.script.open("r", encoding="utf-8-sig") as stream:
                source = stream.read(65537)
            if len(source) > 65536:
                source = (
                    source[:65536]
                    + "\n[Preview truncated: review the full file externally]"
                )
        except (OSError, UnicodeError) as error:
            source = f"Script unavailable: {error}"
        self.preview.setPlainText(
            f"Script: {tool.script}\nType: {tool.kind}\nEffects: {tool.effects}\n"
            f"Deadline: {tool.timeout_seconds}s\n"
            f"Output limit: {tool.output_limit} bytes\n"
            f"Serial: {tool.serial_requirement}\n\n{source}"
        )
        self._invalidate()

    def _invalidate(self):
        self.reviewed = None
        self.run_button.setEnabled(False)

    def _candidate(self):
        if self.selector.currentIndex() < 0:
            raise ValueError("Import or select a tool definition first")
        arguments = json.loads(self.arguments.toPlainText())
        if not isinstance(arguments, list):
            raise ValueError("Arguments must be a JSON list")
        return replace(
            self.definitions[self.selector.currentIndex()],
            arguments=tuple(arguments),
            interpreter=Path(self.interpreter.text())
            if self.interpreter.text()
            else None,
            working_directory=Path(self.working_directory.text()),
            reviewed_fingerprint="",
        )

    def _collection_options(self):
        dialog = RasOptionsDialog(self.directory, self)
        if dialog.exec():
            self.arguments.setPlainText(json.dumps(dialog.arguments(), indent=2))

    def _review(self):
        try:
            self.reviewed = review_tool(self._candidate())
            self.run_button.setEnabled(True)
            self.output.setPlainText(
                "Review recorded for these exact bytes and arguments. "
                "Select Run to execute once."
            )
        except (OSError, ValueError, TypeError) as error:
            self.output.setPlainText(str(error))

    def _run(self):
        if self.reviewed is None or (self.thread and self.thread.isRunning()):
            return
        self.thread = _ToolThread(self.reviewed, self)
        self.thread.finished.connect(self._finished)
        for widget in (
            self.selector,
            self.interpreter,
            self.arguments,
            self.working_directory,
            self.import_button,
            self.save_button,
            self.review_button,
            self.run_button,
        ):
            widget.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.scope_button.setEnabled(False)
        self.output.setPlainText(
            "Running... Output is bounded and shown on completion."
        )
        self.thread.start()

    def _finished(self):
        result = self.thread.result
        self.output.setPlainText(
            f"Status: {result.status}\nExit code: {result.exit_code}\n"
            f"Truncated: {result.truncated}\n\nSTDOUT\n{result.stdout}\n"
            f"STDERR\n{result.stderr}"
        )
        for widget in (
            self.selector,
            self.interpreter,
            self.arguments,
            self.working_directory,
            self.import_button,
            self.save_button,
            self.review_button,
        ):
            widget.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.scope_button.setEnabled(
            self.selector.currentIndex() >= 0
            and self.definitions[self.selector.currentIndex()].id
            == "windows-ras-collector"
        )
        self._invalidate()
        if self.close_pending:
            self.close()

    def _import(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Import tool definitions", str(self.directory), "JSON (*.json)"
        )
        if path:
            self._load(Path(path))

    def _save(self):
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save tool definitions",
            str(self.directory / "tools.json"),
            "JSON (*.json)",
        )
        if path:
            try:
                definitions = list(self.definitions)
                if self.selector.currentIndex() >= 0:
                    definitions[self.selector.currentIndex()] = self._candidate()
                payload = {
                    "schema_version": 1,
                    "tools": [
                        asdict(replace(t, reviewed_fingerprint="")) for t in definitions
                    ],
                }
                SettingsStore(Path(path).parent, Path(path).name).save_raw(
                    json.dumps(payload, default=str, indent=2)
                )
            except (OSError, ValueError, RuntimeError) as error:
                self.output.setPlainText(str(error))

    def closeEvent(self, event):
        if self.thread and self.thread.isRunning():
            self.close_pending = True
            self.thread.cancelled.set()
            event.ignore()
            return
        super().closeEvent(event)

    def done(self, result):
        if self.thread and self.thread.isRunning():
            self.close_pending = True
            self.thread.cancelled.set()
            return
        super().done(result)

"""Ordinary catalog fields and explicit local import/export; never device execution."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from modem_controller.catalog.models import (
    CommandCatalog,
    CommandKind,
    ParameterDefinition,
    RiskLevel,
    VerificationStatus,
)
from modem_controller.catalog.storage import (
    export_catalog_json,
    import_catalog_json,
    validate_persisted_catalog,
)


class CatalogEditor(QWidget):
    """Edits a validated local catalog without any serial or process dependency."""

    catalog_changed = Signal(object)
    favorite_changed = Signal(str, bool)
    directory_used = Signal(str, str)
    notes_saved = Signal(str, str)

    def __init__(self, catalog: CommandCatalog, parent=None) -> None:
        super().__init__(parent)
        self.catalog = catalog
        self._loading = True
        self._dirty = False
        self.directories: dict[str, str] = {}
        self.favorites: set[str] = set()
        self.setWindowTitle("Catalog editor")
        self.profile_selector = QComboBox(self)
        self.command_selector = QComboBox(self)
        self.search = QLineEdit(self)
        self.search.setPlaceholderText("Search name, category or command")
        self.label = QLineEdit(self)
        self.category = QLineEdit(self)
        self.payload = QLineEdit(self)
        self.help_text = QPlainTextEdit(self)
        self.help_text.setMaximumHeight(65)
        self.expected_response = QLineEdit(self)
        self.applicability = QLineEdit(self)
        self.references = QLineEdit(self)
        self.timeout = QDoubleSpinBox(self)
        self.timeout.setRange(0.01, 300)
        self.kind = QComboBox(self)
        self.kind.addItems([x.value for x in CommandKind])
        self.risk = QComboBox(self)
        self.risk.addItems([x.value for x in RiskLevel])
        self.verification = QComboBox(self)
        self.verification.addItems([x.value for x in VerificationStatus])
        self.favorite = QCheckBox("Favorite", self)
        self.notes = QPlainTextEdit(self)
        self.notes.setMaximumHeight(65)
        self.shipped_notes = QLabel(self)
        self.shipped_notes.setWordWrap(True)
        self.parameters = QTableWidget(0, 5, self)
        self.parameters.setHorizontalHeaderLabels(
            ["Name", "Label", "Required", "Secret", "Pattern"]
        )
        self.parameters.setMaximumHeight(110)
        self.message = QLabel(self)
        self.message.setWordWrap(True)
        form = QFormLayout()
        for name, widget in (
            ("Profile", self.profile_selector),
            ("Filter", self.search),
            ("Command", self.command_selector),
            ("Name", self.label),
            ("Category", self.category),
            ("Kind", self.kind),
            ("Command / exact hex", self.payload),
            ("Help", self.help_text),
            ("Expected response", self.expected_response),
            ("Timeout (seconds)", self.timeout),
            ("Applies to (comma separated)", self.applicability),
            ("Reference IDs", self.references),
            ("Risk", self.risk),
            ("Verification", self.verification),
            ("", self.favorite),
            ("Parameters (true/false flags)", self.parameters),
            ("Shipped notes", self.shipped_notes),
            ("User notes", self.notes),
        ):
            form.addRow(name, widget)
        self.save_button = QPushButton("Apply fields", self)
        actions = QHBoxLayout()
        self._navigation_buttons = []
        for label, callback in (
            ("Add parameter", self.add_parameter),
            ("Duplicate", self.duplicate_selected),
            ("Move up", lambda: self.move_selected(-1)),
            ("Move down", lambda: self.move_selected(1)),
            ("Import JSON", self._import),
            ("Export profile", self._export),
        ):
            button = QPushButton(label, self)
            button.clicked.connect(callback)
            actions.addWidget(button)
            if label != "Add parameter":
                self._navigation_buttons.append(button)
        layout = QVBoxLayout(self)
        content = QWidget(self)
        content.setLayout(form)
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setWidget(content)
        layout.addWidget(scroll)
        layout.addWidget(self.save_button)
        discard = QPushButton("Discard field changes", self)
        discard.clicked.connect(self._load_profile)
        layout.addWidget(discard)
        layout.addLayout(actions)
        layout.addWidget(self.message)
        for profile in catalog.profiles:
            self.profile_selector.addItem(profile.name, profile.id)
        self.profile_selector.currentIndexChanged.connect(self._load_profile)
        self.command_selector.currentIndexChanged.connect(self._load_command)
        self.search.textChanged.connect(self._load_commands)
        self.save_button.clicked.connect(self._save)
        for widget in (
            self.label,
            self.category,
            self.payload,
            self.expected_response,
            self.applicability,
            self.references,
            self.help_text,
            self.notes,
        ):
            widget.textChanged.connect(self._mark_dirty)
        for widget in (self.kind, self.risk, self.verification):
            widget.currentTextChanged.connect(self._mark_dirty)
        self.timeout.valueChanged.connect(self._mark_dirty)
        self.favorite.toggled.connect(self._mark_dirty)
        self.parameters.itemChanged.connect(self._mark_dirty)
        self._load_profile()
        self.resize(800, 720)

    def _mark_dirty(self, *args) -> None:
        if not self._loading:
            self._set_dirty(True)

    def _set_dirty(self, dirty: bool) -> None:
        self._dirty = dirty
        for widget in (
            self.profile_selector,
            self.command_selector,
            self.search,
            *self._navigation_buttons,
        ):
            widget.setEnabled(not dirty)
        if dirty:
            self.message.setText(
                "Apply or discard field changes before switching commands."
            )

    def closeEvent(self, event) -> None:
        if self._dirty:
            answer = QMessageBox.question(
                self,
                "Unsaved catalog fields",
                "Apply these changes before closing?",
                QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
                QMessageBox.Cancel,
            )
            if answer == QMessageBox.Cancel or (
                answer == QMessageBox.Save and not self._save()
            ):
                event.ignore()
                return
            if answer == QMessageBox.Discard:
                self._load_profile()
        super().closeEvent(event)

    def select_profile(self, profile_id: str) -> None:
        self.profile_selector.setCurrentIndex(
            self.profile_selector.findData(profile_id)
        )

    def select_command(self, command_id: str) -> None:
        self.command_selector.setCurrentIndex(
            self.command_selector.findData(command_id)
        )

    def _profile(self):
        return self.catalog.profile(self.profile_selector.currentData())

    def _load_profile(self) -> None:
        self._loading = True
        self.notes.setPlainText(self._profile().user_notes)
        self.shipped_notes.setText(self._profile().shipped_notes)
        self._load_commands()

    def _load_commands(self) -> None:
        selected = self.command_selector.currentData()
        self.command_selector.blockSignals(True)
        self.command_selector.clear()
        query = self.search.text().casefold()
        for command in self._profile().commands:
            if (
                query
                in f"{command.label} {command.category} {command.payload}".casefold()
            ):
                self.command_selector.addItem(command.label, command.id)
        index = self.command_selector.findData(selected)
        if index >= 0:
            self.command_selector.setCurrentIndex(index)
        self.command_selector.blockSignals(False)
        self._load_command()

    def _load_command(self) -> None:
        self._loading = True
        command_id = self.command_selector.currentData()
        if command_id is None:
            self._loading = False
            self._set_dirty(False)
            return
        command = self._profile().command(command_id)
        for widget, value in (
            (self.label, command.label),
            (self.category, command.category),
            (self.payload, command.payload or ""),
            (self.expected_response, command.expected_response),
            (self.applicability, ",".join(command.applicability)),
            (self.references, ",".join(command.references)),
        ):
            widget.setText(value)
        self.help_text.setPlainText(command.help_text)
        self.timeout.setValue(command.timeout_seconds)
        self.kind.setCurrentText(command.kind.value)
        self.risk.setCurrentText(command.risk.value)
        self.verification.setCurrentText(command.verification.value)
        self.favorite.setChecked(f"{self._profile().id}/{command.id}" in self.favorites)
        self.parameters.setRowCount(len(command.parameters))
        for row, parameter in enumerate(command.parameters):
            for column, value in enumerate(
                (
                    parameter.name,
                    parameter.label,
                    str(parameter.required).lower(),
                    str(parameter.secret).lower(),
                    parameter.pattern or "",
                )
            ):
                self.parameters.setItem(row, column, QTableWidgetItem(value))
        self._loading = False
        self._set_dirty(False)

    def add_parameter(self) -> None:
        row = self.parameters.rowCount()
        self.parameters.insertRow(row)
        for column, value in enumerate(("argument", "Argument", "true", "false", "")):
            self.parameters.setItem(row, column, QTableWidgetItem(value))

    def _replace_profile(self, profile) -> None:
        candidate = replace(
            self.catalog,
            profiles=tuple(
                profile if p.id == profile.id else p for p in self.catalog.profiles
            ),
        )
        validate_persisted_catalog(candidate)
        self.catalog = candidate
        self.catalog_changed.emit(candidate)
        self._load_commands()

    def _save(self) -> bool:
        try:
            profile = self._profile()
            if self.command_selector.currentData() is None:
                self._replace_profile(
                    replace(profile, user_notes=self.notes.toPlainText())
                )
                return True
            old = profile.command(self.command_selector.currentData())
            parameters = []
            for row in range(self.parameters.rowCount()):
                values = [
                    (
                        self.parameters.item(row, col).text().strip()
                        if self.parameters.item(row, col)
                        else ""
                    )
                    for col in range(5)
                ]
                if not any(values):
                    continue
                if values[2] not in {"true", "false"} or values[3] not in {
                    "true",
                    "false",
                }:
                    raise ValueError("Required and Secret must be true or false")
                parameters.append(
                    ParameterDefinition(
                        values[0],
                        values[1],
                        values[2] == "true",
                        values[3] == "true",
                        values[4] or None,
                    )
                )
            command = replace(
                old,
                label=self.label.text(),
                category=self.category.text(),
                payload=self.payload.text() or None,
                help_text=self.help_text.toPlainText(),
                expected_response=self.expected_response.text(),
                timeout_seconds=self.timeout.value(),
                applicability=tuple(
                    v.strip() for v in self.applicability.text().split(",") if v.strip()
                ),
                references=tuple(
                    v.strip() for v in self.references.text().split(",") if v.strip()
                ),
                kind=CommandKind(self.kind.currentText()),
                risk=RiskLevel(self.risk.currentText()),
                verification=VerificationStatus(self.verification.currentText()),
                parameters=tuple(parameters),
            )
            execution_changed = any(
                getattr(command, field) != getattr(old, field)
                for field in ("payload", "kind", "risk", "parameters", "applicability")
            )
            if execution_changed:
                command = replace(command, verification=VerificationStatus.UNVERIFIED)
            elif command.is_visible and not old.is_visible:
                answer = QMessageBox.question(
                    self,
                    "Review command before enabling",
                    f"Command: {command.payload}\nRisk: {command.risk.value}\n"
                    "Have you checked the command, risk and applicability against "
                    "the device documentation? Read-only entries send on one click.",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No,
                )
                if answer != QMessageBox.Yes:
                    return False
            favorite_key = f"{profile.id}/{old.id}"
            favorite_value = self.favorite.isChecked()
            self._replace_profile(
                replace(
                    profile,
                    user_notes=self.notes.toPlainText(),
                    commands=tuple(
                        command if c.id == old.id else c for c in profile.commands
                    ),
                )
            )
            if favorite_value:
                self.favorites.add(favorite_key)
            else:
                self.favorites.discard(favorite_key)
            self.favorite_changed.emit(favorite_key, favorite_value)
            self.notes_saved.emit(profile.id, self.notes.toPlainText())
            self.message.setText(
                "Applied as unverified. Review before enabling."
                if execution_changed
                else "Applied locally. No command was sent."
            )
            self._set_dirty(False)
            return True
        except (ValueError, KeyError) as error:
            self.message.setText(str(error))
            return False

    def duplicate_selected(self) -> None:
        if self.command_selector.currentData() is None:
            return
        profile = self._profile()
        original = profile.command(self.command_selector.currentData())
        ids = {c.id for c in profile.commands}
        suffix = 1
        while f"{original.id}-copy-{suffix}" in ids:
            suffix += 1
        copied = replace(
            original,
            id=f"{original.id}-copy-{suffix}",
            label=original.label + " copy",
            verification=VerificationStatus.UNVERIFIED,
        )
        self._replace_profile(replace(profile, commands=(*profile.commands, copied)))
        self.select_command(copied.id)

    def move_selected(self, offset: int) -> None:
        profile = self._profile()
        commands = list(profile.commands)
        index = next(
            (
                i
                for i, c in enumerate(commands)
                if c.id == self.command_selector.currentData()
            ),
            -1,
        )
        if index < 0 or not 0 <= index + offset < len(commands):
            return
        commands[index], commands[index + offset] = (
            commands[index + offset],
            commands[index],
        )
        self._replace_profile(replace(profile, commands=tuple(commands)))

    def _directory(self, purpose: str) -> str:
        saved = Path(self.directories.get(purpose, str(Path.home())))
        return str(saved if saved.is_dir() else Path.home())

    def _import(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self, "Import native catalog", self._directory("import"), "JSON (*.json)"
        )
        if not filename:
            return
        try:
            imported = import_catalog_json(Path(filename))
            if (
                QMessageBox.question(
                    self,
                    "Review catalog",
                    f"Import {len(imported.profiles)} profiles? "
                    "Imported commands remain unverified until reviewed here.",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No,
                )
                != QMessageBox.Yes
            ):
                return
            references = dict(self.catalog.references)
            for key, value in imported.references.items():
                if key in references and references[key] != value:
                    raise ValueError(f"Conflicting reference: {key}")
                references[key] = value
            profiles = {p.id: p for p in self.catalog.profiles}
            for profile in imported.profiles:
                profiles[profile.id] = replace(
                    profile,
                    commands=tuple(
                        replace(c, verification=VerificationStatus.UNVERIFIED)
                        for c in profile.commands
                    ),
                )
            self.catalog = replace(
                self.catalog, references=references, profiles=tuple(profiles.values())
            )
            self.catalog_changed.emit(self.catalog)
            self.profile_selector.blockSignals(True)
            self.profile_selector.clear()
            for profile in self.catalog.profiles:
                self.profile_selector.addItem(profile.name, profile.id)
            self.profile_selector.blockSignals(False)
            self._load_profile()
            self.directory_used.emit("import", str(Path(filename).parent))
        except (ValueError, OSError, RuntimeError) as error:
            self.message.setText(str(error))

    def _export(self) -> None:
        filename, _ = QFileDialog.getSaveFileName(
            self, "Export selected profile", self._directory("export"), "JSON (*.json)"
        )
        if not filename:
            return
        try:
            export_catalog_json(
                replace(self.catalog, profiles=(self._profile(),)), Path(filename)
            )
            self.directory_used.emit("export", str(Path(filename).parent))
        except (ValueError, OSError, RuntimeError) as error:
            self.message.setText(str(error))

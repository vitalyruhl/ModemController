"""The compact desktop shell for manual terminal work."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtGui import QAction, QActionGroup, QCloseEvent
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QInputDialog,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from modem_controller.catalog.models import (
    CatalogCommand,
    CommandCatalog,
    CommandKind,
    RiskLevel,
    load_starter_catalog,
)
from modem_controller.catalog.storage import Settings, SettingsStore, StorageError
from modem_controller.transport.serial_port import available_ports
from modem_controller.ui.connection_controller import ConnectionController
from modem_controller.ui.connection_panel import ConnectionPanel
from modem_controller.ui.session_log import LogMode, LogWriteError, SessionLog
from modem_controller.ui.sms_dialog import SmsDialog
from modem_controller.ui.terminal_view import TerminalWorkspace
from modem_controller.workflows.connection_search import ConnectionSearchResult
from modem_controller.workflows.diagnostics import DiagnosticResult
from modem_controller.workflows.maintenance import MaintenanceResult, MaintenanceRunner
from modem_controller.workflows.sms import SmsSendResult


class MainWindow(QMainWindow):
    """Composes catalog selection and terminal intent without performing I/O."""

    text_send_requested = Signal(str, bytes, bool)
    bytes_send_requested = Signal(bytes)
    preset_requested = Signal(object)

    def __init__(
        self,
        catalog: CommandCatalog | None = None,
        *,
        port_provider: Callable[[], list[str]] = available_ports,
        connection_controller: ConnectionController | None = None,
        settings_store: SettingsStore | None = None,
    ) -> None:
        super().__init__()
        self._catalog = catalog or load_starter_catalog()
        self._port_provider = port_provider
        self._connection_controller = connection_controller
        self._settings_store = settings_store
        self._settings = Settings()
        self._session_log = SessionLog()
        self._workflow_active = False
        self._preset_execution_enabled = False
        self.setWindowTitle("Modem Controller")
        self.resize(1_080, 720)

        self.connection_panel = ConnectionPanel(self)
        self.profile_selector = QComboBox(self)
        self.profile_selector.setObjectName("profileSelector")
        self.category_selector = QComboBox(self)
        self.category_selector.setObjectName("categorySelector")
        self.notes = QPlainTextEdit(self)
        self.notes.setReadOnly(True)
        self.notes.setMaximumBlockCount(20)
        self.notes.setObjectName("profileNotes")
        self.command_group = QGroupBox("Commands", self)
        self.command_layout = QGridLayout(self.command_group)
        self.terminal = TerminalWorkspace(parent=self)
        self.sms_dialog = SmsDialog(self)
        self.sms_dialog.status_requested.connect(self._query_sms_status)
        self.sms_dialog.read_requested.connect(self._read_sms)
        self.sms_dialog.send_requested.connect(self._send_sms)
        self.sms_action = QAction("SMS...", self)
        self.sms_action.triggered.connect(self._show_sms_dialog)
        self.menuBar().addMenu("Messaging").addAction(self.sms_action)
        self._create_logging_menu()
        self._set_sms_enabled(False)

        for profile in self._catalog.profiles:
            self.profile_selector.addItem(profile.name, profile.id)
        self.profile_selector.currentIndexChanged.connect(self._change_profile)
        self.category_selector.currentTextChanged.connect(self._render_commands)
        self.connection_panel.refresh_requested.connect(self.refresh_ports)
        self.connection_panel.connect_requested.connect(self._connect)
        self.connection_panel.disconnect_requested.connect(self._disconnect)
        self.connection_panel.find_settings_requested.connect(self._find_settings)
        self.connection_panel.diagnostics_requested.connect(self._run_diagnostics)
        self.connection_panel.cancel_requested.connect(self._cancel_workflow)
        self.terminal.text_submitted.connect(self._send_text)
        self.terminal.bytes_submitted.connect(self._send_bytes)
        self.terminal.clear_requested.connect(self._terminal_cleared)
        if self._connection_controller is not None:
            self._bind_connection_controller(self._connection_controller)

        sidebar = QWidget(self)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.addWidget(self.connection_panel)
        sidebar_layout.addWidget(self.profile_selector)
        sidebar_layout.addWidget(self.category_selector)
        sidebar_layout.addWidget(self.notes)
        sidebar_layout.addWidget(self.command_group, 1)

        splitter = QSplitter(self)
        splitter.addWidget(sidebar)
        splitter.addWidget(self.terminal)
        splitter.setSizes([330, 750])
        self.setCentralWidget(splitter)
        self._load_preferences()
        self.refresh_ports()
        self.connection_panel.apply_preferences(self._settings.connection)

    def refresh_ports(self) -> None:
        """Refresh port choices without opening or connecting to a serial port."""

        try:
            self.connection_panel.set_ports(self._port_provider())
        except OSError as error:
            self.connection_panel.show_error(str(error))

    def set_workflow_active(self, active: bool) -> None:
        self._workflow_active = active
        self.terminal.set_workflow_active(active)
        self.connection_panel.set_workflow_active(active)
        self._set_sms_enabled(self._preset_execution_enabled)
        self._render_commands()

    def set_preset_execution_enabled(self, enabled: bool) -> None:
        self._preset_execution_enabled = enabled
        self._render_commands()

    def _change_profile(self) -> None:
        profile = self._selected_profile()
        self.notes.setPlainText(
            profile.shipped_notes + self._user_notes(profile.user_notes)
        )
        current = self.category_selector.currentText()
        categories = sorted({command.category for command in profile.visible_commands})
        self.category_selector.blockSignals(True)
        self.category_selector.clear()
        self.category_selector.addItems(categories)
        if current in categories:
            self.category_selector.setCurrentText(current)
        self.category_selector.blockSignals(False)
        self._render_commands()

    def _render_commands(self) -> None:
        while self.command_layout.count():
            item = self.command_layout.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()

        category = self.category_selector.currentText()
        commands = [
            command
            for command in self._selected_profile().visible_commands
            if command.category == category
        ]
        for index, command in enumerate(commands):
            button = QPushButton(command.label, self.command_group)
            button.setToolTip(command.help_text)
            button.setEnabled(
                self._preset_execution_enabled
                and not self._workflow_active
                and (
                    command.risk is RiskLevel.READ_ONLY
                    or command.kind in {CommandKind.AT, CommandKind.BYTES}
                )
            )
            button.clicked.connect(
                lambda checked=False, selected=command: self._request_preset(selected)
            )
            self.command_layout.addWidget(button, index // 2, index % 2)

    def _request_preset(self, command: CatalogCommand) -> None:
        if not self._preset_execution_enabled or self._workflow_active:
            return
        if command.risk is RiskLevel.READ_ONLY:
            payload = command.render()
            if command.kind is CommandKind.AT:
                payload += self.terminal.selected_terminator
            self.terminal.append_transmitted(payload)
            self._record_log(
                self._session_log.record_preset_requested, command.label, payload
            )
            self.preset_requested.emit(command)
            self._controller().send(payload)
            return
        if command.kind is CommandKind.BYTES:
            self._request_control_bytes(command)
            return
        self._request_maintenance(command)

    def _request_control_bytes(self, command: CatalogCommand) -> None:
        answer = QMessageBox.warning(
            self,
            "Send control bytes",
            f"{command.help_text}\n\nSend {command.label} exactly once?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer is not QMessageBox.Yes:
            return
        payload = command.render()
        self.terminal.append_info(
            f"Control byte send requested: {payload.hex(' ').upper()}"
        )
        self._record_log(
            self._session_log.record_preset_requested, command.label, payload
        )
        self.preset_requested.emit(command)
        self._controller().send_control_bytes(payload)

    def _connect(self) -> None:
        try:
            settings = self.connection_panel.selected_settings()
        except ValueError as error:
            self.connection_panel.show_error(str(error))
            return
        self.terminal.append_info(
            f"Connect requested: {_format_connection_settings(settings)}"
        )
        self._record_log(
            self._session_log.record_connect_requested,
            _format_connection_settings(settings),
        )
        self.connection_panel.set_connecting()
        self._controller().open(settings)

    def _disconnect(self) -> None:
        if self._connection_controller is not None:
            self.terminal.append_info("Disconnect requested")
            self._record_log(self._session_log.record_disconnect_requested)
            self._connection_controller.close()

    def _send_text(self, command: str, terminator: bytes, sensitive: bool) -> None:
        self.text_send_requested.emit(command, terminator, sensitive)
        payload = command.encode("ascii", errors="replace") + terminator
        self._controller().send(payload, sensitive=sensitive)

    def _send_bytes(self, payload: bytes) -> None:
        self.bytes_send_requested.emit(payload)
        self._controller().send(payload)

    def _controller(self) -> ConnectionController:
        if self._connection_controller is None:
            self._connection_controller = ConnectionController(parent=self)
            self._bind_connection_controller(self._connection_controller)
        return self._connection_controller

    def _bind_connection_controller(self, controller: ConnectionController) -> None:
        controller.connected.connect(self._connected)
        controller.disconnected.connect(self._disconnected)
        controller.received.connect(self._received)
        controller.session_received.connect(self._log_received)
        controller.transmitted.connect(self._log_transmitted)
        if hasattr(controller, "capture_gap"):
            controller.capture_gap.connect(self._capture_gap)
        controller.control_bytes_sent.connect(self._show_control_bytes_sent)
        controller.error.connect(self._show_connection_error)
        controller.diagnostics_completed.connect(self._show_diagnostics)
        controller.search_completed.connect(self._show_search_result)
        controller.maintenance_completed.connect(self._show_maintenance_result)
        controller.sms_completed.connect(self._show_sms_result)
        controller.sms_status_completed.connect(self._show_sms_status)
        controller.workflow_finished.connect(lambda: self.set_workflow_active(False))

    def _connected(self, settings: str) -> None:
        self.connection_panel.set_connected(True, settings)
        self.set_preset_execution_enabled(True)
        self._set_sms_enabled(True)
        self._record_log(self._session_log.record_connected, settings)

    def _disconnected(self) -> None:
        self.connection_panel.set_connected(False)
        self.set_preset_execution_enabled(False)
        self._set_sms_enabled(False)
        self._record_log(self._session_log.record_disconnected)

    def _received(self, payload: bytes) -> None:
        self.terminal.append_received(payload)
        self._record_log(self._session_log.record_received, payload)

    def _log_transmitted(self, payload: bytes) -> None:
        self._record_log(self._session_log.record_sent, payload)

    def _log_received(self, payload: bytes) -> None:
        self._record_log(self._session_log.record_received, payload)

    def _capture_gap(self, message: str) -> None:
        self.terminal.append_info(message)
        self._record_log(self._session_log.record_gap, message)

    def _run_diagnostics(self) -> None:
        self.set_workflow_active(True)
        self._controller().run_diagnostics(self._selected_profile())

    def _cancel_workflow(self) -> None:
        if self._connection_controller is not None:
            self._connection_controller.cancel_workflow()

    def _find_settings(self) -> None:
        port = self.connection_panel.port_selector.currentText()
        if port == "No port":
            self.connection_panel.show_error("Select a COM port first.")
            return
        self.set_workflow_active(True)
        self._controller().search_settings(port)

    def _show_search_result(self, result: ConnectionSearchResult) -> None:
        selected = result.selected
        if selected is None:
            self.connection_panel.show_error(
                "No repeatedly confirmed settings were found."
            )
            return
        settings = selected.settings
        answer = QMessageBox.question(
            self,
            "Settings found",
            (
                f"{settings.port} at {settings.baud_rate} Bd was confirmed twice. "
                "Apply and save these settings?"
            ),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        if answer is QMessageBox.Yes:
            self.connection_panel.apply_settings(settings)
            self._save_preferences()

    def _request_maintenance(self, command: CatalogCommand) -> None:
        preview = MaintenanceRunner.preview(command)
        answer = QMessageBox.warning(
            self,
            "Confirm maintenance action",
            f"{preview.risk_summary}\n\nRun '{command.label}' once?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer is not QMessageBox.Yes:
            return
        values: dict[str, str] = {}
        for parameter in command.parameters:
            value, accepted = QInputDialog.getText(
                self,
                "Maintenance parameter",
                parameter.label,
                QLineEdit.Password if parameter.secret else QLineEdit.Normal,
            )
            if not accepted:
                return
            values[parameter.name] = value
        self.set_workflow_active(True)
        self._controller().run_maintenance(command, values)

    def _show_maintenance_result(self, result: MaintenanceResult | None) -> None:
        if result is None:
            return
        self.terminal.append_info(
            f"{result.command_id}: {result.outcome.value}\n{result.next_action}"
        )

    def _show_control_bytes_sent(self, payload: bytes) -> None:
        hexadecimal = payload.hex(" ").upper()
        self.terminal.append_transmitted(payload, force_hex=True)
        self.terminal.append_info(
            f"Control bytes written to serial port: {hexadecimal}"
        )

    def _terminal_cleared(self) -> None:
        self._record_log(self._session_log.record_terminal_cleared)

    def _show_connection_error(self, message: str) -> None:
        self.connection_panel.show_error(message)
        self.terminal.append_info(f"Serial error: {message}")
        self._record_log(self._session_log.record_error, message)

    def _query_sms_status(self) -> None:
        self.set_workflow_active(True)
        self._controller().query_sms_status()

    def _read_sms(self, index: int) -> None:
        self.set_workflow_active(True)
        self._controller().read_sms(index)

    def _send_sms(self, recipient: str, body: str) -> None:
        self.set_workflow_active(True)
        self._controller().send_sms(recipient, body)

    def _show_sms_result(self, result: SmsSendResult | None) -> None:
        if result is not None:
            self.terminal.append_info(
                f"SMS: {result.outcome.value}\n{result.next_action}"
            )

    def _show_sms_status(self, exchanges: tuple[object, ...]) -> None:
        for exchange in exchanges:
            evidence = b" | ".join(exchange.response_lines).decode(
                "ascii", errors="replace"
            )
            self.terminal.append_info(evidence or exchange.outcome.value)

    def _set_sms_enabled(self, enabled: bool) -> None:
        self.sms_action.setEnabled(enabled and not self._workflow_active)
        self.sms_dialog.set_available(enabled, self._workflow_active)

    def _show_diagnostics(self, results: tuple[DiagnosticResult, ...]) -> None:
        for result in results:
            evidence = b" | ".join(result.evidence).decode("ascii", errors="replace")
            self.terminal.append_info(
                f"{result.command_id}: {result.state.value}\n{evidence}\n"
                f"{result.next_check}"
            )

    def _show_sms_dialog(self) -> None:
        self.sms_dialog.show()
        self.sms_dialog.raise_()
        self.sms_dialog.activateWindow()

    def _create_logging_menu(self) -> None:
        menu = self.menuBar().addMenu("Logging")
        self.enable_logging_action = QAction("Enable file logging", self)
        self.enable_logging_action.setCheckable(True)
        self.select_log_file_action = QAction("Select log file...", self)
        self.normal_logging_action = QAction("Normal", self)
        self.normal_logging_action.setCheckable(True)
        self.verbose_logging_action = QAction("Verbose", self)
        self.verbose_logging_action.setCheckable(True)
        self.normal_logging_action.setChecked(True)
        mode_group = QActionGroup(self)
        mode_group.setExclusive(True)
        mode_group.addAction(self.normal_logging_action)
        mode_group.addAction(self.verbose_logging_action)
        menu.addAction(self.enable_logging_action)
        menu.addAction(self.select_log_file_action)
        menu.addSeparator()
        menu.addAction(self.normal_logging_action)
        menu.addAction(self.verbose_logging_action)
        self.enable_logging_action.toggled.connect(self._set_logging_enabled)
        self.select_log_file_action.triggered.connect(self._select_log_file)
        self.normal_logging_action.triggered.connect(
            lambda checked: checked and self._set_logging_mode(LogMode.NORMAL)
        )
        self.verbose_logging_action.triggered.connect(
            lambda checked: checked and self._set_logging_mode(LogMode.VERBOSE)
        )

    def _select_log_file(self) -> None:
        current_path = self._session_log.path
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Select log file",
            str(current_path) if current_path is not None else "modem-session.log",
            "Log files (*.log);;All files (*)",
        )
        if not filename:
            return
        self._configure_logging(Path(filename), self.enable_logging_action.isChecked())
        self._save_preferences()

    def _set_logging_enabled(self, enabled: bool) -> None:
        if enabled and self._session_log.path is None:
            self._select_log_file()
            if (
                self._session_log.path is None
                or not self.enable_logging_action.isChecked()
            ):
                self._set_logging_checked(False)
            return
        self._configure_logging(self._session_log.path, enabled)
        self._save_preferences()

    def _set_logging_mode(self, mode: LogMode) -> None:
        self._configure_logging(
            self._session_log.path, self.enable_logging_action.isChecked()
        )
        self._save_preferences()

    def _configure_logging(self, path: Path | None, enabled: bool) -> None:
        try:
            self._session_log.configure(
                path, enabled=enabled, mode=self._selected_logging_mode()
            )
        except LogWriteError as error:
            self._set_logging_checked(False)
            self.connection_panel.show_error(str(error))
            self.terminal.append_info(f"Logging disabled: {error}")

    def _restore_logging_preferences(self) -> None:
        path = Path(self._settings.log_file) if self._settings.log_file else None
        mode = LogMode(self._settings.logging_mode)
        self.normal_logging_action.setChecked(mode is LogMode.NORMAL)
        self.verbose_logging_action.setChecked(mode is LogMode.VERBOSE)
        self._set_logging_checked(self._settings.logging_enabled)
        self._configure_logging(path, self._settings.logging_enabled)

    def _set_logging_checked(self, checked: bool) -> None:
        self.enable_logging_action.blockSignals(True)
        self.enable_logging_action.setChecked(checked)
        self.enable_logging_action.blockSignals(False)

    def _selected_logging_mode(self) -> LogMode:
        if self.verbose_logging_action.isChecked():
            return LogMode.VERBOSE
        return LogMode.NORMAL

    def _record_log(self, record, *args) -> None:
        try:
            record(*args)
        except LogWriteError as error:
            self._set_logging_checked(False)
            self.connection_panel.show_error(str(error))
            self.terminal.append_info(f"Logging disabled: {error}")

    def closeEvent(self, event: QCloseEvent) -> None:
        self._save_preferences()
        if self._connection_controller is not None:
            self._connection_controller.shutdown()
        try:
            self._session_log.close()
        except LogWriteError as error:
            self.connection_panel.show_error(str(error))
        super().closeEvent(event)

    def _load_preferences(self) -> None:
        store = self._settings_store
        if store is not None:
            try:
                loaded = store.load()
            except StorageError as error:
                self.connection_panel.show_error(str(error))
            else:
                self._settings = loaded.settings
                if loaded.recovered:
                    self.connection_panel.show_error(loaded.message)
        profile_index = self.profile_selector.findData(self._settings.selected_profile)
        if profile_index >= 0:
            self.profile_selector.setCurrentIndex(profile_index)
        self._change_profile()
        if self.category_selector.findText(self._settings.selected_category) >= 0:
            self.category_selector.setCurrentText(self._settings.selected_category)
        self._restore_logging_preferences()

    def _save_preferences(self) -> None:
        store = self._settings_store
        if store is None:
            return
        settings = Settings(
            selected_profile=self.profile_selector.currentData(),
            selected_category=self.category_selector.currentText(),
            connection=self.connection_panel.preferences(),
            last_directories=self._settings.last_directories,
            favorites=self._settings.favorites,
            profile_notes=self._settings.profile_notes,
            log_file=str(self._session_log.path or ""),
            logging_enabled=self.enable_logging_action.isChecked(),
            logging_mode=self._selected_logging_mode().value,
        )
        try:
            store.save(settings)
        except StorageError as error:
            self.connection_panel.show_error(str(error))

    def _selected_profile(self):
        return self._catalog.profile(self.profile_selector.currentData())

    @staticmethod
    def _user_notes(notes: str) -> str:
        return f"\n\n{notes}" if notes else ""


def _format_connection_settings(settings) -> str:
    return (
        f"{settings.port} | {settings.baud_rate} Bd | "
        f"{settings.data_bits}{settings.parity.value}{settings.stop_bits:g} | "
        f"{settings.flow_control.value}"
    )

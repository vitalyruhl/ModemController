from unittest.mock import patch

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QApplication, QMessageBox

from modem_controller.ui.connection_panel import ConnectionPanel
from modem_controller.ui.main_window import MainWindow
from modem_controller.ui.session_log import LogMode
from modem_controller.ui.terminal_view import TerminalDirection, TerminalWorkspace


def test_history_navigation_filters_and_never_recalls_credentials(qtbot):
    terminal = TerminalWorkspace()
    qtbot.addWidget(terminal)
    for command in ("AT", "AT+CSQ", "AT+CPIN=1234"):
        terminal.command_input.setText(command)
        terminal.submit_text()
    qtbot.keyClick(terminal.command_input, Qt.Key_Up)
    assert terminal.command_input.text() == "AT+CSQ"
    qtbot.keyClick(terminal.command_input, Qt.Key_Up)
    assert terminal.command_input.text() == "AT"
    terminal.history_filter.setText("CSQ")
    qtbot.keyClick(terminal.command_input, Qt.Key_Up)
    assert terminal.command_input.text() == "AT+CSQ"


def test_non_ascii_send_is_rejected_and_display_options_preserve_bytes(qtbot):
    terminal = TerminalWorkspace()
    qtbot.addWidget(terminal)
    sent = []
    terminal.text_submitted.connect(lambda *args: sent.append(args))
    terminal.command_input.setText("ATä")
    assert not terminal.submit_text()
    assert not sent
    raw = b"one\r\n\r\n\r\ntwo\xff\x1b"
    terminal.append_received(raw)
    terminal.compact_blanks.setChecked(True)
    terminal.show_controls.setChecked(True)
    terminal.timestamps.setChecked(True)
    terminal.encoding.setCurrentText("latin-1")
    assert terminal.entries[0].data == raw
    assert "<ESC>" in terminal.transcript.toPlainText()
    assert "bytes" in terminal.counts.text()


def test_response_timeout_does_not_change_write_timeout(qtbot):
    panel = ConnectionPanel()
    qtbot.addWidget(panel)
    panel.set_ports(["COM10"])
    panel.deadline.setValue(5000)
    settings = panel.selected_settings()
    assert settings.response_timeout == 5
    assert settings.write_timeout == 1


def test_secret_input_is_transient_and_not_retained_in_entries(qtbot) -> None:
    terminal = TerminalWorkspace()
    qtbot.addWidget(terminal)
    terminal.command_input.setText("AT+CPIN=1234")
    assert terminal.submit_text()
    assert terminal.command_input.text() == ""
    assert b"1234" not in repr(terminal.entries).encode()
    terminal.hex_input.setText("41 54 2b 43 50 49 4e 3d 31 32 33 34 0d")
    assert terminal.submit_hex()
    assert b"1234" not in repr(terminal.entries).encode()


def test_startup_and_profile_selection_do_not_emit_send_intents(qtbot) -> None:
    window = MainWindow()
    qtbot.addWidget(window)
    text_intents: list[tuple[str, bytes, bool]] = []
    byte_intents: list[bytes] = []
    window.text_send_requested.connect(lambda *intent: text_intents.append(intent))
    window.bytes_send_requested.connect(byte_intents.append)

    window.profile_selector.setCurrentIndex(0)
    window.category_selector.setCurrentIndex(0)

    assert text_intents == []
    assert byte_intents == []


def test_terminal_has_read_only_transcript_and_one_enter_emits_one_terminated_intent(
    qtbot,
) -> None:
    terminal = TerminalWorkspace()
    qtbot.addWidget(terminal)
    intents: list[tuple[str, bytes, bool]] = []
    terminal.text_submitted.connect(lambda *intent: intents.append(intent))
    terminal.command_input.setText("AT")

    qtbot.keyClick(terminal.command_input, Qt.Key_Return)

    assert terminal.transcript.isReadOnly()
    assert terminal.command_input.isEnabled()
    assert intents == [("AT", b"\r", False)]
    assert terminal.entries[-1].direction is TerminalDirection.TRANSMITTED


def test_malformed_hex_is_rejected_without_a_send_intent(qtbot) -> None:
    terminal = TerminalWorkspace()
    qtbot.addWidget(terminal)
    intents: list[bytes] = []
    terminal.bytes_submitted.connect(intents.append)
    terminal.hex_input.setText("4G")

    assert not terminal.submit_hex()
    assert intents == []
    assert "invalid" in terminal.validation_message.text()


def test_terminal_bounds_history_and_pauses_autoscroll(qtbot) -> None:
    terminal = TerminalWorkspace(max_entries=2)
    qtbot.addWidget(terminal)
    terminal.set_auto_scroll_paused(True)
    terminal.append_received(b"first")
    terminal.append_received(b"second")
    terminal.append_received(b"third")

    assert [entry.data for entry in terminal.entries] == [b"second", b"third"]
    assert terminal.is_auto_scroll_paused


def test_clear_button_removes_terminal_entries_and_emits_a_clear_intent(qtbot) -> None:
    terminal = TerminalWorkspace()
    qtbot.addWidget(terminal)
    cleared: list[bool] = []
    terminal.clear_requested.connect(lambda: cleared.append(True))
    terminal.append_received(b"old output")

    terminal.clear_button.click()

    assert terminal.entries == ()
    assert terminal.transcript.toPlainText() == ""
    assert cleared == [True]


def test_active_workflow_prevents_manual_interleaving_and_port_errors_are_visible(
    qtbot,
) -> None:
    window = MainWindow()
    qtbot.addWidget(window)
    intents: list[tuple[str, bytes, bool]] = []
    window.text_send_requested.connect(lambda *intent: intents.append(intent))
    window.set_workflow_active(True)
    window.terminal.command_input.setText("AT")

    assert not window.terminal.submit_text()
    window.connection_panel.show_error("COM7 belegt")

    assert intents == []
    assert "COM7 belegt" in window.connection_panel.status.text()


def test_selected_text_can_be_copied_and_pasted_into_terminal_input(qtbot) -> None:
    terminal = TerminalWorkspace()
    qtbot.addWidget(terminal)
    terminal.append_received(b"AT+CSQ")
    cursor = terminal.transcript.textCursor()
    cursor.select(QTextCursor.LineUnderCursor)
    terminal.transcript.setTextCursor(cursor)
    QApplication.clipboard().setText(cursor.selectedText())

    terminal.command_input.clear()
    terminal.paste_into_input()

    assert terminal.command_input.text() == "RX  AT+CSQ"


def test_selected_terminal_line_resends_text_or_exact_bytes(qtbot) -> None:
    terminal = TerminalWorkspace()
    qtbot.addWidget(terminal)
    text_intents: list[tuple[str, bytes, bool]] = []
    byte_intents: list[bytes] = []
    terminal.text_submitted.connect(lambda *intent: text_intents.append(intent))
    terminal.bytes_submitted.connect(byte_intents.append)
    terminal.append_received(b"AT+CSQ\r")
    terminal.append_received(b"\xff\x00")

    cursor = terminal.transcript.textCursor()
    cursor.movePosition(QTextCursor.Start)
    terminal.transcript.setTextCursor(cursor)
    assert terminal.resend_selected_line()
    terminal.transcript.setTextCursor(
        QTextCursor(terminal.transcript.document().findBlockByNumber(1))
    )
    assert terminal.resend_selected_line()

    assert text_intents == [("AT+CSQ", b"\r", False)]
    assert byte_intents == [b"\xff\x00"]


def test_startup_and_refresh_enumerate_ports_without_connecting(qtbot) -> None:
    ports = ["COM1"]
    window = MainWindow(port_provider=lambda: ports)
    qtbot.addWidget(window)

    assert window.connection_panel.port_selector.currentText() == "COM1"
    ports.append("COM4")
    window.connection_panel.refresh_button.click()

    assert window.connection_panel.port_selector.count() == 2
    assert not window.connection_panel.disconnect_button.isEnabled()


def test_advanced_connection_controls_are_hidden_until_checked(qtbot) -> None:
    panel = ConnectionPanel()
    qtbot.addWidget(panel)

    assert panel.advanced.title() == "Advanced connection"
    assert panel.baud_rate.isHidden()

    panel.advanced.setChecked(True)

    assert not panel.baud_rate.isHidden()


def test_sms_is_a_separate_menu_dialog_and_terminal_accepts_info(qtbot) -> None:
    window = MainWindow()
    qtbot.addWidget(window)

    assert window.command_group.title() == "Commands"
    assert not window.sms_action.isEnabled()
    assert not hasattr(window, "diagnostic_results")
    window._connected("COM10 | 19200 Bd")
    window.sms_action.trigger()
    window.terminal.append_info("Diagnostics complete")

    assert window.sms_dialog.isVisible()
    assert window.sms_dialog.parent() is window
    assert window.terminal.entries[-1].direction is TerminalDirection.INFORMATION
    assert not window.terminal.resend_selected_line()


def test_control_byte_presets_send_exact_bytes_after_confirmation(qtbot) -> None:
    controller = FakeConnectionController()
    window = MainWindow(connection_controller=controller)
    qtbot.addWidget(window)
    window._connected("COM10 | 19200 Bd")
    window.category_selector.setCurrentText("Control bytes")

    buttons = [
        window.command_layout.itemAt(index).widget()
        for index in range(window.command_layout.count())
    ]

    assert buttons
    assert all(button.isEnabled() for button in buttons)
    with patch(
        "modem_controller.ui.main_window.QMessageBox.warning",
        return_value=QMessageBox.Yes,
    ):
        buttons[0].click()
    assert controller.sent == [(b"\r", False)]
    assert "TX  HEX 0D" in window.terminal.transcript.toPlainText()
    assert "Control byte send requested: 0D" in window.terminal.transcript.toPlainText()
    assert (
        "Control bytes written to serial port: 0D"
        in window.terminal.transcript.toPlainText()
    )


def test_verbose_log_records_connection_intents_and_terminal_clear(
    qtbot, tmp_path
) -> None:
    controller = FakeConnectionController()
    window = MainWindow(
        port_provider=lambda: ["COM10"], connection_controller=controller
    )
    qtbot.addWidget(window)
    log_path = tmp_path / "session.log"
    window._session_log.configure(log_path, enabled=True, mode=LogMode.VERBOSE)

    window.connection_panel.connect_button.click()
    window.terminal.append_received(b"old output")
    window.terminal.clear_button.click()
    window.connection_panel.disconnect_button.click()

    content = log_path.read_text(encoding="utf-8")
    assert "CONNECT REQUESTED COM10 | 115200 Bd | 8N1 | none" in content
    assert "CONNECTED COM10 | 115200 Bd" in content
    assert "TERMINAL CLEARED" in content
    assert "DISCONNECT REQUESTED" in content
    assert "DISCONNECTED" in content


class FakeConnectionController(QObject):
    connected = Signal(str)
    disconnected = Signal()
    received = Signal(bytes)
    session_received = Signal(bytes)
    transmitted = Signal(bytes)
    control_bytes_sent = Signal(bytes)
    error = Signal(str)
    diagnostics_completed = Signal(object)
    search_completed = Signal(object)
    maintenance_completed = Signal(object)
    sms_completed = Signal(object)
    sms_status_completed = Signal(object)
    workflow_finished = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.opened = []
        self.sent: list[tuple[bytes, bool]] = []
        self.closed = False

    def open(self, settings) -> None:
        self.opened.append(settings)
        self.connected.emit(f"{settings.port} | {settings.baud_rate} Bd")

    def close(self) -> None:
        self.closed = True
        self.disconnected.emit()

    def send(self, payload: bytes, *, sensitive: bool = False) -> None:
        self.sent.append((payload, sensitive))

    def send_control_bytes(self, payload: bytes) -> None:
        self.sent.append((payload, False))
        self.control_bytes_sent.emit(payload)

    def shutdown(self) -> None:
        self.close()


def test_connection_and_terminal_intents_are_forwarded_to_controller(qtbot) -> None:
    controller = FakeConnectionController()
    window = MainWindow(
        port_provider=lambda: ["COM10"], connection_controller=controller
    )
    qtbot.addWidget(window)
    window.connection_panel.baud_rate.setCurrentText("19200")

    window.connection_panel.connect_button.click()
    window.terminal.command_input.setText("AT")
    assert window.terminal.submit_text()
    controller.received.emit(b"\r\nOK\r\n")
    window.connection_panel.disconnect_button.click()

    assert controller.opened[0].port == "COM10"
    assert controller.opened[0].baud_rate == 19200
    assert controller.sent == [(b"AT\r", False)]
    assert any(entry.data == b"\r\nOK\r\n" for entry in window.terminal.entries)
    assert controller.closed

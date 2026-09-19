"""Secret metadata takes precedence over a custom command's risk label."""

from dataclasses import replace
from unittest.mock import Mock

from PySide6.QtWidgets import QInputDialog, QLineEdit, QMessageBox
from test_connection_controller import FakePort

from modem_controller.catalog.models import RiskLevel, load_starter_catalog
from modem_controller.transport.serial_port import SerialSettings
from modem_controller.ui.connection_controller import SerialConnectionWorker
from modem_controller.ui.main_window import MainWindow


def secret_read_only_command():
    return replace(
        load_starter_catalog().profile("generic-at").command("unlock-sim"),
        id="custom-auth",
        payload="AT+AUTH={pin}",
        risk=RiskLevel.READ_ONLY,
        direct_send=True,
    )


def test_read_only_secret_preset_uses_confirmed_password_workflow(qtbot, monkeypatch):
    window = MainWindow(port_provider=lambda: [])
    qtbot.addWidget(window)
    window.set_preset_execution_enabled(True)
    controller = Mock()
    monkeypatch.setattr(window, "_controller", lambda: controller)
    prompts = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: QMessageBox.Yes)
    monkeypatch.setattr(
        QInputDialog,
        "getText",
        lambda parent, title, label, mode: prompts.append(mode) or ("1234", True),
    )
    command = secret_read_only_command()
    window._request_preset(command)
    assert prompts == [QLineEdit.Password]
    controller.run_maintenance.assert_called_once_with(command, {"pin": "1234"})
    controller.send.assert_not_called()
    assert "1234" not in window.terminal.transcript.toPlainText()
    assert window.terminal.command_input.text() == ""


def test_secret_parameter_cannot_be_requested_by_ordinary_preparation(
    qtbot, monkeypatch
):
    window = MainWindow(port_provider=lambda: [])
    qtbot.addWidget(window)
    prompt = Mock()
    monkeypatch.setattr(QInputDialog, "getText", prompt)
    assert window._preset_parameters(secret_read_only_command()) is None
    prompt.assert_not_called()


def test_worker_read_only_secret_action_marks_sensitive_io_and_clears_values(qtbot):
    port = FakePort()
    port.open(SerialSettings(port="COM10"))
    port.received.append(b"AT+AUTH=1234\r\nOK\r\n")
    worker = SerialConnectionWorker(lambda: port)
    worker._port = port
    transmitted = []
    completed = []
    worker.transmitted.connect(transmitted.append)
    worker.maintenance_completed.connect(completed.append)
    values = {"pin": "1234"}
    worker.run_maintenance(secret_read_only_command(), values)
    assert port.writes == [(b"AT+AUTH=1234\r", True)]
    assert transmitted == []
    assert "1234" not in str(completed)
    assert values == {}
    assert not port.is_open

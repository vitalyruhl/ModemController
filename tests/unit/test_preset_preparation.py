"""Preparation-only UI contracts for state-changing AT presets."""

from __future__ import annotations

from dataclasses import replace
from unittest.mock import Mock

from PySide6.QtWidgets import QMessageBox

from modem_controller.catalog.models import (
    RiskLevel,
    load_starter_catalog,
)
from modem_controller.ui import main_window as module
from modem_controller.ui.main_window import MainWindow


def _prepare_window(
    qtbot, monkeypatch, *, execution_enabled: bool = False
) -> tuple[MainWindow, Mock]:
    window = MainWindow()
    qtbot.addWidget(window)
    controller = Mock()
    monkeypatch.setattr(window, "_controller", lambda: controller)
    monkeypatch.setattr(module.QMessageBox, "warning", lambda *args: QMessageBox.Yes)
    window.set_preset_execution_enabled(execution_enabled)
    return window, controller


def _prepared_command(command_id: str, payload: str, parameters=()):
    base = load_starter_catalog().profile("generic-at").command("attention")
    return replace(
        base,
        id=command_id,
        label=command_id,
        category="Maintenance",
        payload=payload,
        risk=RiskLevel.STATE_CHANGING,
        parameters=parameters,
    )


def test_dial_preset_collects_value_then_only_prepares_terminal_input(
    qtbot, monkeypatch
) -> None:
    window, controller = _prepare_window(qtbot, monkeypatch)
    dial = load_starter_catalog().profile("generic-at").command("dial-voice")
    monkeypatch.setattr(module.QInputDialog, "getText", lambda *args: ("+49123", True))

    window._request_preset(dial)

    assert window.terminal.command_input.text() == "ATD+49123;"
    controller.send.assert_not_called()
    controller.run_maintenance.assert_not_called()


def test_sms_text_mode_preset_prepares_command_while_disconnected(
    qtbot, monkeypatch
) -> None:
    window, controller = _prepare_window(qtbot, monkeypatch)
    sms_text_mode = _prepared_command("sms-text-mode", "AT+CMGF=1")

    window._request_preset(sms_text_mode)

    assert window.terminal.command_input.text() == "AT+CMGF=1"
    controller.send.assert_not_called()
    controller.run_maintenance.assert_not_called()


def test_secret_pin_preset_keeps_transient_maintenance_workflow(
    qtbot, monkeypatch
) -> None:
    window, controller = _prepare_window(qtbot, monkeypatch, execution_enabled=True)
    pin_command = load_starter_catalog().profile("generic-at").command("unlock-sim")
    monkeypatch.setattr(module.QInputDialog, "getText", lambda *args: ("1234", True))

    window._request_preset(pin_command)

    assert window.terminal.command_input.text() == ""
    controller.send.assert_not_called()
    controller.run_maintenance.assert_called_once_with(pin_command, {"pin": "1234"})


def test_cancelled_or_invalid_preparation_keeps_existing_draft_without_io(
    qtbot, monkeypatch
) -> None:
    window, controller = _prepare_window(qtbot, monkeypatch)
    dial = load_starter_catalog().profile("generic-at").command("dial-voice")
    window.terminal.command_input.setText("AT+CSQ")
    monkeypatch.setattr(module.QInputDialog, "getText", lambda *args: ("", False))

    window._request_preset(dial)

    assert window.terminal.command_input.text() == "AT+CSQ"
    controller.send.assert_not_called()
    controller.run_maintenance.assert_not_called()

    monkeypatch.setattr(module.QInputDialog, "getText", lambda *args: ("invalid", True))
    window._request_preset(dial)

    assert window.terminal.command_input.text() == "AT+CSQ"
    assert window.terminal.validation_message.text()
    controller.send.assert_not_called()
    controller.run_maintenance.assert_not_called()


def test_borrowed_unverified_query_prepares_without_automatic_diagnostics(
    qtbot, monkeypatch
) -> None:
    window, controller = _prepare_window(qtbot, monkeypatch)
    window.profile_selector.setCurrentIndex(
        window.profile_selector.findData("mc55i-qw")
    )
    borrowed = load_starter_catalog().profile("generic-at").command("sms-format")

    window._request_preset(borrowed)

    assert window.terminal.command_input.text() == "AT+CMGF?"
    controller.send.assert_not_called()
    controller.run_diagnostics.assert_not_called()


def test_workflow_blocks_preparation_without_replacing_existing_draft(
    qtbot, monkeypatch
) -> None:
    window, controller = _prepare_window(qtbot, monkeypatch)
    window.terminal.command_input.setText("AT+CSQ")
    window.set_workflow_active(True)
    sms_text_mode = _prepared_command("sms-text-mode", "AT+CMGF=1")

    window._request_preset(sms_text_mode)

    assert window.terminal.command_input.text() == "AT+CSQ"
    controller.send.assert_not_called()
    controller.run_maintenance.assert_not_called()


def test_prepare_sms_button_opens_dialog_without_enabling_or_sending_sms(
    qtbot, monkeypatch
) -> None:
    window, controller = _prepare_window(qtbot, monkeypatch)
    requested: list[tuple[str, str]] = []
    window.sms_dialog.send_requested.connect(lambda *values: requested.append(values))

    assert window.prepare_sms_button.isEnabled()
    assert not window.sms_dialog.send_button.isEnabled()
    window.prepare_sms_button.click()

    assert window.sms_dialog.isVisible()
    assert not window.sms_dialog.send_button.isEnabled()
    assert requested == []
    controller.send.assert_not_called()

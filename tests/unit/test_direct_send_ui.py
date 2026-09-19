"""Explicit per-command preparation versus execution, with no real transport."""

from dataclasses import replace
from unittest.mock import Mock

from modem_controller.catalog.models import load_starter_catalog
from modem_controller.ui.catalog_editor import CatalogEditor
from modem_controller.ui.main_window import MainWindow


def test_direct_send_checkbox_is_beside_favorite_and_preserves_verification(qtbot):
    editor = CatalogEditor(load_starter_catalog())
    qtbot.addWidget(editor)
    editor.select_profile("generic-at")
    editor.select_command("attention")
    editor.show()
    assert editor.direct_send.isChecked()
    assert abs(editor.direct_send.y() - editor.favorite.y()) <= 2
    editor.direct_send.setChecked(False)
    assert editor._save()
    command = editor.catalog.profile("generic-at").command("attention")
    assert command.direct_send is False
    assert command.is_visible


def test_read_only_can_be_prepared_or_sent_by_its_explicit_flag(qtbot, monkeypatch):
    window = MainWindow(port_provider=lambda: [])
    qtbot.addWidget(window)
    controller = Mock()
    monkeypatch.setattr(window, "_controller", lambda: controller)
    window.set_preset_execution_enabled(True)
    command = window._catalog.profile("generic-at").command("attention")
    window._request_preset(replace(command, direct_send=False))
    assert window.terminal.command_input.text() == "AT"
    controller.send.assert_not_called()
    window._request_preset(replace(command, direct_send=True))
    controller.send.assert_called_once_with(b"AT\r")


def test_byte_preparation_uses_hex_field_without_a_terminator(qtbot, monkeypatch):
    window = MainWindow(port_provider=lambda: [])
    qtbot.addWidget(window)
    controller = Mock()
    monkeypatch.setattr(window, "_controller", lambda: controller)
    command = window._catalog.profile("generic-at").command("send-at-cr")
    window._request_preset(replace(command, direct_send=False))
    assert window.terminal.hex_input.text() == "41 54 0D"
    assert window.terminal.command_input.text() == ""
    assert not controller.mock_calls


def test_unverified_direct_flag_does_not_bypass_review(qtbot, monkeypatch):
    window = MainWindow(port_provider=lambda: [])
    qtbot.addWidget(window)
    controller = Mock()
    monkeypatch.setattr(window, "_controller", lambda: controller)
    window.set_preset_execution_enabled(True)
    command = window._catalog.profile("generic-at").command("sms-text-mode")
    window._request_preset(replace(command, direct_send=True))
    assert window.terminal.command_input.text() == "AT+CMGF=1"
    assert not controller.mock_calls


def test_secret_commands_keep_their_own_transient_workflow(qtbot):
    editor = CatalogEditor(load_starter_catalog())
    qtbot.addWidget(editor)
    editor.select_profile("generic-at")
    editor.select_command("unlock-sim")
    assert not editor.direct_send.isEnabled()

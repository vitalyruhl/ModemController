"""Queued transmit acknowledgments retain their manual or workflow origin."""

from collections import deque
from dataclasses import replace
from threading import Event

from modem_controller.transport.serial_port import SerialIOError, SerialSettings
from modem_controller.ui.connection_controller import ConnectionController
from modem_controller.ui.main_window import MainWindow
from modem_controller.ui.terminal_view import TerminalDirection


class DelayedManualPort:
    """Hold one manual write while the GUI schedules a diagnostic workflow."""

    def __init__(self):
        self.is_open = False
        self.manual_started = Event()
        self.release_manual = Event()
        self.received = deque()
        self.writes = []

    def open(self, settings):
        self.is_open = True

    def close(self):
        self.is_open = False

    def read_available(self):
        return self.received.popleft() if self.received else b""

    def write(self, payload):
        self.writes.append(payload)
        if payload == b"AT+CUSTOM\r":
            self.manual_started.set()
            if not self.release_manual.wait(3):
                raise SerialIOError("Synthetic manual write was not released")
        else:
            self.received.append(b"\r\nOK\r\n")
        return len(payload)

    write_sensitive = write


def test_delayed_manual_ack_is_not_redisplayed_when_workflow_becomes_active(qtbot):
    port = DelayedManualPort()
    controller = ConnectionController(port_factory=lambda: port)
    window = None
    try:
        window = MainWindow(port_provider=lambda: [], connection_controller=controller)
        qtbot.addWidget(window)
        controller.open(SerialSettings(port="FAKE", response_timeout=0.5))
        qtbot.waitUntil(lambda: window._preset_execution_enabled, timeout=2000)

        window.terminal.command_input.setText("AT+CUSTOM")
        assert window.terminal.submit_text()
        qtbot.waitUntil(port.manual_started.is_set, timeout=2000)

        # The manual write has not yet emitted its acknowledgment. A subsequent
        # workflow is queued, so GUI state alone cannot identify that earlier TX.
        profile = window._catalog.profile("generic-at")
        profile = replace(profile, commands=(profile.command("attention"),))
        window.set_workflow_active(True)
        controller.run_diagnostics(profile)
        port.release_manual.set()
        qtbot.waitUntil(lambda: not window._workflow_active, timeout=3000)

        transmitted = [
            entry.data
            for entry in window.terminal.entries
            if entry.direction is TerminalDirection.TRANSMITTED
        ]
        assert port.writes == [b"AT+CUSTOM\r", b"AT\r"]
        assert transmitted == port.writes
    finally:
        port.release_manual.set()
        controller.shutdown()
        if window is not None:
            window.close()
    assert not port.is_open

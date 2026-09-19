"""Regression tests for worker cancellation, stale replies, and secret boundaries."""

from __future__ import annotations

from collections import deque
from dataclasses import replace
from threading import Event

from modem_controller.catalog.models import load_starter_catalog
from modem_controller.transport.serial_port import SerialPortError, SerialSettings
from modem_controller.ui.connection_controller import SerialConnectionWorker


class FakePort:
    def __init__(self) -> None:
        self.is_open = False
        self.received: deque[bytes] = deque()
        self.writes: list[tuple[bytes, bool]] = []

    def open(self, settings: SerialSettings) -> None:
        self.is_open = True

    def close(self) -> None:
        self.is_open = False

    def read_available(self) -> bytes:
        return self.received.popleft() if self.received else b""

    def write(self, payload: bytes) -> int:
        if not self.is_open:
            raise SerialPortError("port is closed")
        self.writes.append((payload, False))
        return len(payload)

    def write_sensitive(self, payload: bytes) -> int:
        if not self.is_open:
            raise SerialPortError("port is closed")
        self.writes.append((payload, True))
        return len(payload)


def test_reconnect_clears_controller_close_cancellation_before_control_byte_send(
    qtbot,
) -> None:
    cancelled = Event()
    first, reconnected = FakePort(), FakePort()
    ports = deque((first, reconnected))
    worker = SerialConnectionWorker(lambda: ports.popleft(), cancel_requested=cancelled)

    worker.open(SerialSettings(port="COM10"))
    cancelled.set()  # ConnectionController.close() sets this shared event.
    worker.close()
    worker.open(SerialSettings(port="COM10"))
    worker.send_control_bytes(b"\x1b")

    assert reconnected.is_open
    assert reconnected.writes == [(b"\x1b", False)]


def test_diagnostic_timeout_closes_connection_before_late_ok_can_poison_next_run(
    qtbot,
) -> None:
    port = FakePort()
    worker = SerialConnectionWorker(lambda: port)
    completed: list[object] = []
    worker.diagnostics_completed.connect(completed.append)
    profile = load_starter_catalog().profile("generic-at")
    profile = replace(profile, commands=(profile.command("attention"),))

    worker.open(SerialSettings(port="COM10", response_timeout=0.01))
    worker.run_diagnostics(profile)

    assert not port.is_open
    assert completed[0][0].reason == "timeout"
    assert len(port.writes) == 1
    port.received.append(b"\r\nOK\r\n")
    worker.run_diagnostics(profile)

    assert len(port.writes) == 1
    assert len(completed) == 1


def test_privacy_paused_pin_echo_blocks_diagnostics_until_reconnect(qtbot) -> None:
    pin = b"1234"
    port = FakePort()
    worker = SerialConnectionWorker(lambda: port)
    results: list[object] = []
    errors: list[str] = []
    worker.diagnostics_completed.connect(results.append)
    worker.error.connect(errors.append)
    profile = load_starter_catalog().profile("generic-at")
    profile = replace(profile, commands=(profile.command("attention"),))

    worker.open(SerialSettings(port="COM10"))
    worker.send(b"AT+CPIN=" + pin + b"\r", False)
    port.received.append(b"AT+CPIN=" + pin + b"\r\nOK\r\n")
    worker.run_diagnostics(profile)

    assert port.writes == [(b"AT+CPIN=1234\r", True)]
    assert b"1234" not in repr(results).encode()
    assert any("reconnect" in message.casefold() for message in errors)

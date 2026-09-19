from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from modem_controller.transport.capture import CaptureDirection
from modem_controller.transport.serial_port import (
    ControlLinePolicy,
    FlowControl,
    PartialWriteError,
    PortAlreadyOpenError,
    PortNotOpenError,
    SerialEventKind,
    SerialIOError,
    SerialOpenError,
    SerialPort,
    SerialSettings,
)


class FakeClock:
    def __init__(self) -> None:
        self._value = datetime(2026, 9, 19, tzinfo=UTC)

    def __call__(self) -> datetime:
        value = self._value
        self._value += timedelta(milliseconds=1)
        return value


class FakeSerialBackend:
    def __init__(self) -> None:
        self.is_open = False
        self.dtr = False
        self.rts = False
        self.received = bytearray()
        self.writes: list[bytes] = []
        self.write_result: int | None = None
        self.open_error: OSError | None = None
        self.read_error: OSError | None = None
        self.write_error: OSError | None = None
        self.close_error: OSError | None = None
        self.cancel_error: OSError | None = None
        self.cancel_read_calls = 0
        self.cancel_write_calls = 0

    @property
    def in_waiting(self) -> int:
        return len(self.received)

    def open(self) -> None:
        if self.open_error:
            raise self.open_error
        self.is_open = True

    def close(self) -> None:
        if self.close_error:
            raise self.close_error
        self.is_open = False

    def read(self, size: int) -> bytes:
        if self.read_error:
            raise self.read_error
        data = bytes(self.received[:size])
        del self.received[:size]
        return data

    def write(self, data: bytes) -> int:
        if self.write_error:
            raise self.write_error
        self.writes.append(data)
        return len(data) if self.write_result is None else self.write_result

    def cancel_read(self) -> None:
        self.cancel_read_calls += 1
        if self.cancel_error:
            raise self.cancel_error

    def cancel_write(self) -> None:
        self.cancel_write_calls += 1
        if self.cancel_error:
            raise self.cancel_error


def make_port(backend: FakeSerialBackend, **port_options: Any) -> SerialPort:
    return SerialPort(
        backend_factory=lambda settings: backend,
        clock=FakeClock(),
        **port_options,
    )


def open_port(port: SerialPort, **settings_options: Any) -> None:
    port.open(SerialSettings(port="COM7", **settings_options))


def test_line_controls_are_explicit_and_unavailable_inputs_stay_unknown():
    backend = FakeSerialBackend()
    port = make_port(backend)
    open_port(port)
    assert port.status_lines() == dict.fromkeys(("cts", "dsr", "ri", "cd"))
    port.set_control_lines(ControlLinePolicy(dtr=True, rts=False))
    assert backend.dtr is True
    assert backend.rts is False
    assert not backend.writes
    port.close()
    open_port(port, flow_control=FlowControl.RTS_CTS)
    with pytest.raises(SerialIOError, match="flow control"):
        port.set_control_lines(ControlLinePolicy(rts=False))
    port.close()


@pytest.mark.parametrize(
    "payload",
    [b"\r", b"\n", b"\r\n", b"\x1b", b"\x1a", b"AT\r"],
)
def test_write_preserves_exact_bytes_without_implicit_terminator(
    payload: bytes,
) -> None:
    backend = FakeSerialBackend()
    port = make_port(backend)
    open_port(port)

    assert port.write(payload) == len(payload)

    assert backend.writes == [payload]
    records = port.capture.snapshot()
    assert records[-1].direction is CaptureDirection.TRANSMITTED
    assert records[-1].data == payload


def test_sensitive_write_keeps_bytes_out_of_capture_and_events() -> None:
    backend = FakeSerialBackend()
    port = make_port(backend)
    open_port(port)

    assert port.write_sensitive(b"secret message\x1a") == len(b"secret message\x1a")

    assert backend.writes == [b"secret message\x1a"]
    assert port.capture.snapshot() == ()
    assert port.capture.sensitive_gaps == 1
    assert port.capture.sensitive_bytes == len(b"secret message\x1a")
    event = port.drain_events()[-1]
    assert event.kind is SerialEventKind.SENSITIVE_TRANSMISSION
    assert event.data == b""
    assert "secret" not in event.detail


def test_pin_assignment_suppresses_capture_and_fragmented_echo_until_reconnect() -> (
    None
):
    backend = FakeSerialBackend()
    port = make_port(backend)
    open_port(port)
    port.write(b"AT+CPIN=1234\r")
    for fragment in (b"AT+CP", b"IN=1234\r\n", b"OK\r\n"):
        backend.received.extend(fragment)
        assert port.read_available() == fragment
    assert port.capture.snapshot() == ()
    assert port.capture.sensitive_gaps == 4
    assert all(event.data == b"" for event in port.drain_events())
    port.close()
    open_port(port)
    port.write(b"AT\r")
    assert port.capture.snapshot()[-1].data == b"AT\r"


def test_open_applies_control_line_and_flow_control_policy() -> None:
    backend = FakeSerialBackend()
    port = make_port(backend)

    open_port(
        port,
        flow_control=FlowControl.RTS_CTS,
        control_lines=ControlLinePolicy(dtr=True, rts=True),
    )

    assert port.is_open
    assert port.settings is not None
    assert backend.dtr
    assert backend.rts


def test_open_rejects_existing_port_owner_and_reports_busy_error() -> None:
    backend = FakeSerialBackend()
    port = make_port(backend)
    open_port(port)

    with pytest.raises(PortAlreadyOpenError):
        open_port(port)

    busy_backend = FakeSerialBackend()
    busy_backend.open_error = OSError("Access is denied")
    busy_port = make_port(busy_backend)

    with pytest.raises(SerialOpenError):
        open_port(busy_port)

    assert SerialEventKind.ERROR in [event.kind for event in busy_port.drain_events()]


def test_read_retains_partial_reads_in_order() -> None:
    backend = FakeSerialBackend()
    backend.received.extend(b"OK\r\n")
    port = make_port(backend)
    open_port(port)

    assert port.read_available(max_bytes=2) == b"OK"
    assert port.read_available(max_bytes=2) == b"\r\n"

    assert [record.data for record in port.capture.snapshot()] == [b"OK", b"\r\n"]


def test_partial_write_is_captured_and_reported() -> None:
    backend = FakeSerialBackend()
    backend.write_result = 1
    port = make_port(backend)
    open_port(port)

    with pytest.raises(PartialWriteError) as error:
        port.write(b"AT\r")

    assert error.value.written == 1
    assert port.capture.snapshot()[-1].data == b"A"
    assert SerialEventKind.ERROR in [event.kind for event in port.drain_events()]


def test_failed_write_disconnects_without_capturing_unwritten_bytes() -> None:
    backend = FakeSerialBackend()
    backend.write_error = OSError("device disconnected")
    port = make_port(backend)
    open_port(port)

    with pytest.raises(SerialIOError):
        port.write(b"AT\r")

    assert not port.is_open
    assert port.capture.snapshot() == ()
    assert [event.kind for event in port.drain_events()][-2:] == [
        SerialEventKind.ERROR,
        SerialEventKind.DISCONNECTED,
    ]


def test_unplugged_read_disconnects_the_port_and_reports_an_error() -> None:
    backend = FakeSerialBackend()
    backend.received.extend(b"OK")
    backend.read_error = OSError("device disconnected")
    port = make_port(backend)
    open_port(port)

    with pytest.raises(SerialIOError):
        port.read_available()

    assert not port.is_open
    assert [event.kind for event in port.drain_events()][-2:] == [
        SerialEventKind.ERROR,
        SerialEventKind.DISCONNECTED,
    ]


def test_capture_and_event_overflow_are_explicit() -> None:
    backend = FakeSerialBackend()
    port = make_port(
        backend,
        max_capture_records=1,
        max_capture_bytes=1,
        max_events=1,
    )
    open_port(port)
    port.write(b"A")
    port.write(b"B")

    assert [record.data for record in port.capture.snapshot()] == [b"A"]
    kinds = [event.kind for event in port.drain_events()]
    assert SerialEventKind.CAPTURE_OVERFLOW in kinds
    assert SerialEventKind.EVENT_OVERFLOW in kinds


def test_cancel_releases_port_and_cancels_both_operations() -> None:
    backend = FakeSerialBackend()
    port = make_port(backend)
    open_port(port)

    port.cancel()

    assert backend.cancel_read_calls == 1
    assert backend.cancel_write_calls == 1
    assert not port.is_open
    assert [event.kind for event in port.drain_events()][-2:] == [
        SerialEventKind.CANCELLED,
        SerialEventKind.DISCONNECTED,
    ]


def test_io_requires_an_open_port() -> None:
    port = make_port(FakeSerialBackend())

    with pytest.raises(PortNotOpenError):
        port.read_available()
    with pytest.raises(PortNotOpenError):
        port.write(b"AT\r")

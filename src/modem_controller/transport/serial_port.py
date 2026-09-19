"""Exclusive, byte-oriented serial-port access built on pySerial."""

from __future__ import annotations

from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from threading import RLock
from typing import Protocol

import serial
from serial.tools import list_ports

from modem_controller.transport.capture import (
    CaptureBuffer,
    CaptureDirection,
    CaptureRecord,
)
from modem_controller.transport.privacy import contains_secret_input


class FlowControl(str, Enum):
    NONE = "none"
    RTS_CTS = "rts_cts"
    DSR_DTR = "dsr_dtr"


class Parity(str, Enum):
    NONE = "N"
    EVEN = "E"
    ODD = "O"
    MARK = "M"
    SPACE = "S"


@dataclass(frozen=True, slots=True)
class ControlLinePolicy:
    """Requested DTR and RTS states after a port has been opened."""

    dtr: bool | None = None
    rts: bool | None = None


@dataclass(frozen=True, slots=True)
class SerialSettings:
    """PC-side settings used to open one serial port."""

    port: str
    baud_rate: int = 115200
    data_bits: int = 8
    parity: Parity = Parity.NONE
    stop_bits: float = 1
    flow_control: FlowControl = FlowControl.NONE
    read_timeout: float = 0.1
    write_timeout: float = 1.0
    control_lines: ControlLinePolicy = ControlLinePolicy()
    response_timeout: float = 2.0
    inter_byte_delay: float = 0.0

    def __post_init__(self) -> None:
        if not self.port.strip():
            raise ValueError("port must not be empty")
        if self.baud_rate <= 0:
            raise ValueError("baud_rate must be positive")
        if self.data_bits not in (5, 6, 7, 8):
            raise ValueError("data_bits must be 5, 6, 7, or 8")
        if self.stop_bits not in (1, 1.5, 2):
            raise ValueError("stop_bits must be 1, 1.5, or 2")
        if self.read_timeout < 0 or self.write_timeout < 0:
            raise ValueError("timeouts must not be negative")
        if not 0 < self.response_timeout <= 60 or not 0 <= self.inter_byte_delay <= 0.1:
            raise ValueError("response timeout or pacing is outside its bounded range")


class SerialEventKind(str, Enum):
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    RECEIVED = "received"
    TRANSMITTED = "transmitted"
    ERROR = "error"
    CAPTURE_OVERFLOW = "capture_overflow"
    EVENT_OVERFLOW = "event_overflow"
    CANCELLED = "cancelled"
    SENSITIVE_TRANSMISSION = "sensitive_transmission"


@dataclass(frozen=True, slots=True)
class SerialEvent:
    timestamp: datetime
    kind: SerialEventKind
    data: bytes = b""
    detail: str = ""


class SerialPortError(RuntimeError):
    """Base class for serial-port lifecycle and I/O failures."""


class PortAlreadyOpenError(SerialPortError):
    """Raised when another connection is already owned by this instance."""


class PortNotOpenError(SerialPortError):
    """Raised when I/O is requested without an open connection."""


class SerialOpenError(SerialPortError):
    """Raised when a configured serial port cannot be opened."""


class SerialIOError(SerialPortError):
    """Raised when a serial operation disconnects or otherwise fails."""


class PartialWriteError(SerialIOError):
    """Raised when the backend accepts fewer bytes than requested."""

    def __init__(self, written: int, expected: int) -> None:
        super().__init__(f"serial write accepted {written} of {expected} bytes")
        self.written = written
        self.expected = expected


class SerialBackend(Protocol):
    """Minimal adapter contract used by the transport and its offline fakes."""

    @property
    def is_open(self) -> bool: ...

    @property
    def in_waiting(self) -> int: ...

    @property
    def dtr(self) -> bool: ...

    @dtr.setter
    def dtr(self, value: bool) -> None: ...

    @property
    def rts(self) -> bool: ...

    @rts.setter
    def rts(self, value: bool) -> None: ...

    def open(self) -> None: ...

    def close(self) -> None: ...

    def read(self, size: int) -> bytes: ...

    def write(self, data: bytes) -> int: ...

    def cancel_read(self) -> None: ...

    def cancel_write(self) -> None: ...


class PySerialBackend:
    """Adapter that delays pySerial's physical port open until requested."""

    def __init__(self, settings: SerialSettings) -> None:
        self._serial = serial.Serial(
            port=None,
            baudrate=settings.baud_rate,
            bytesize=settings.data_bits,
            parity=settings.parity.value,
            stopbits=settings.stop_bits,
            timeout=settings.read_timeout,
            write_timeout=settings.write_timeout,
            rtscts=settings.flow_control is FlowControl.RTS_CTS,
            dsrdtr=settings.flow_control is FlowControl.DSR_DTR,
        )
        self._serial.port = settings.port

    @property
    def is_open(self) -> bool:
        return self._serial.is_open

    @property
    def in_waiting(self) -> int:
        return self._serial.in_waiting

    @property
    def dtr(self) -> bool:
        return self._serial.dtr

    @dtr.setter
    def dtr(self, value: bool) -> None:
        self._serial.dtr = value

    @property
    def rts(self) -> bool:
        return self._serial.rts

    @rts.setter
    def rts(self, value: bool) -> None:
        self._serial.rts = value

    def open(self) -> None:
        self._serial.open()

    def close(self) -> None:
        self._serial.close()

    def read(self, size: int) -> bytes:
        return self._serial.read(size)

    def write(self, data: bytes) -> int:
        return self._serial.write(data)

    def cancel_read(self) -> None:
        self._serial.cancel_read()

    def cancel_write(self) -> None:
        self._serial.cancel_write()

    def status_lines(self) -> dict[str, bool | None]:
        result = {}
        for name in ("cts", "dsr", "ri", "cd"):
            try:
                result[name] = bool(getattr(self._serial, name))
            except (
                OSError,
                serial.SerialException,
                AttributeError,
                NotImplementedError,
            ):
                result[name] = None
        return result


BackendFactory = Callable[[SerialSettings], SerialBackend]
Clock = Callable[[], datetime]


def available_ports() -> list[str]:
    """List host serial ports without opening or changing any of them."""

    return [port.device for port in list_ports.comports()]


class SerialPort:
    """The sole owner of one port handle, its capture, and its event queue."""

    def __init__(
        self,
        *,
        backend_factory: BackendFactory = PySerialBackend,
        clock: Clock | None = None,
        max_capture_records: int = 10_000,
        max_capture_bytes: int = 4 * 1024 * 1024,
        max_events: int = 1_000,
    ) -> None:
        if max_events <= 0:
            raise ValueError("max_events must be positive")

        self._backend_factory = backend_factory
        self._clock = clock or (lambda: datetime.now(UTC))
        self._capture = CaptureBuffer(
            max_records=max_capture_records,
            max_bytes=max_capture_bytes,
        )
        self._events: deque[SerialEvent] = deque()
        self._max_events = max_events
        self._dropped_events = 0
        self._unreported_capture_records = 0
        self._unreported_capture_bytes = 0
        self._backend: SerialBackend | None = None
        self._settings: SerialSettings | None = None
        self._secret_capture_paused = False
        self._lock = RLock()

    @property
    def is_open(self) -> bool:
        with self._lock:
            return self._backend is not None and self._backend.is_open

    @property
    def settings(self) -> SerialSettings | None:
        with self._lock:
            return self._settings

    @property
    def capture(self) -> CaptureBuffer:
        return self._capture

    def open(self, settings: SerialSettings) -> None:
        with self._lock:
            if self._backend is not None:
                raise PortAlreadyOpenError("a serial port is already open")

            try:
                backend = self._backend_factory(settings)
                backend.open()
                self._apply_control_lines(backend, settings.control_lines)
            except (OSError, serial.SerialException) as error:
                self._queue_event(SerialEventKind.ERROR, detail=str(error))
                raise SerialOpenError(
                    f"could not open {settings.port}: {error}"
                ) from error

            self._backend = backend
            self._settings = settings
            self._secret_capture_paused = False
            self._queue_event(SerialEventKind.CONNECTED, detail=settings.port)

    def close(self) -> None:
        with self._lock:
            backend = self._backend
            if backend is None:
                return

            self._backend = None
            self._settings = None
            try:
                backend.close()
            except (OSError, serial.SerialException) as error:
                self._queue_event(SerialEventKind.ERROR, detail=str(error))
            finally:
                self._queue_event(SerialEventKind.DISCONNECTED)

    def set_control_lines(self, policy: ControlLinePolicy) -> None:
        with self._lock:
            backend = self._require_backend()
            if self._settings is not None:
                if (
                    self._settings.flow_control is FlowControl.RTS_CTS
                    and policy.rts is not None
                ):
                    raise SerialIOError("RTS is owned by hardware flow control")
                if (
                    self._settings.flow_control is FlowControl.DSR_DTR
                    and policy.dtr is not None
                ):
                    raise SerialIOError("DTR is owned by hardware flow control")
            try:
                self._apply_control_lines(backend, policy)
            except (OSError, serial.SerialException, NotImplementedError) as error:
                raise SerialIOError(
                    f"Could not change control lines: {error}"
                ) from error

    def status_lines(self) -> dict[str, bool | None]:
        with self._lock:
            backend = self._require_backend()
            read = getattr(backend, "status_lines", None)
            if read is None:
                return dict.fromkeys(("cts", "dsr", "ri", "cd"))
            return read()

    def cancel(self) -> None:
        """Cancel backend I/O where supported and deterministically release the port."""

        with self._lock:
            backend = self._require_backend()
            try:
                backend.cancel_read()
                backend.cancel_write()
            except (OSError, serial.SerialException) as error:
                self._disconnect_after_failure(error)
                raise SerialIOError(f"could not cancel serial I/O: {error}") from error

            self._queue_event(SerialEventKind.CANCELLED)
            self.close()

    def read_available(self, max_bytes: int = 4096) -> bytes:
        if max_bytes <= 0:
            raise ValueError("max_bytes must be positive")

        with self._lock:
            backend = self._require_backend()
            try:
                byte_count = min(max_bytes, max(0, backend.in_waiting))
                data = backend.read(byte_count) if byte_count else b""
            except (OSError, serial.SerialException) as error:
                self._disconnect_after_failure(error)
                raise SerialIOError(f"could not read serial data: {error}") from error

            if data:
                if self._secret_capture_paused:
                    self._capture.record_sensitive_gap(len(data))
                    self._queue_event(
                        SerialEventKind.SENSITIVE_TRANSMISSION,
                        detail="Sensitive receive gap; reconnect to resume capture.",
                    )
                else:
                    self._record(CaptureDirection.RECEIVED, data)
                    self._queue_event(SerialEventKind.RECEIVED, data=data)
            return data

    def write(self, data: bytes | bytearray | memoryview) -> int:
        return self._write(data, sensitive=False)

    def write_sensitive(self, data: bytes | bytearray | memoryview) -> int:
        """Write sensitive bytes without retaining contents in capture or events."""

        return self._write(data, sensitive=True)

    def pause_sensitive_capture(self) -> None:
        """Suppress payload capture until reconnect; reads still serve the session."""
        with self._lock:
            self._secret_capture_paused = True

    def _write(self, data: bytes | bytearray | memoryview, *, sensitive: bool) -> int:
        if not isinstance(data, bytes | bytearray | memoryview):
            raise TypeError("data must be bytes-like")
        payload = bytes(data)
        if not payload:
            return 0

        with self._lock:
            backend = self._require_backend()
            if contains_secret_input(payload):
                self._secret_capture_paused = True
            sensitive = sensitive or self._secret_capture_paused
            try:
                written = backend.write(payload)
            except (OSError, serial.SerialException) as error:
                self._disconnect_after_failure(error)
                raise SerialIOError(f"could not write serial data: {error}") from error

            if not isinstance(written, int) or not 0 <= written <= len(payload):
                error = SerialIOError("backend returned an invalid write count")
                self._disconnect_after_failure(error)
                raise error

            if written:
                accepted = payload[:written]
                if sensitive:
                    self._capture.record_sensitive_gap(len(accepted))
                    self._queue_event(
                        SerialEventKind.SENSITIVE_TRANSMISSION,
                        detail=f"excluded {len(accepted)} sensitive transmitted bytes",
                    )
                else:
                    self._record(CaptureDirection.TRANSMITTED, accepted)
                    self._queue_event(SerialEventKind.TRANSMITTED, data=accepted)

            if written != len(payload):
                error = PartialWriteError(written, len(payload))
                self._queue_event(SerialEventKind.ERROR, detail=str(error))
                raise error
            return written

    def drain_events(self) -> tuple[SerialEvent, ...]:
        with self._lock:
            events = list(self._events)
            self._events.clear()
            if self._unreported_capture_records:
                events.insert(
                    0,
                    SerialEvent(
                        timestamp=self._clock(),
                        kind=SerialEventKind.CAPTURE_OVERFLOW,
                        detail=(
                            f"dropped {self._unreported_capture_bytes} bytes in "
                            f"{self._unreported_capture_records} capture records "
                            "because capture limits were reached"
                        ),
                    ),
                )
                self._unreported_capture_records = 0
                self._unreported_capture_bytes = 0
            if self._dropped_events:
                events.insert(
                    0,
                    SerialEvent(
                        timestamp=self._clock(),
                        kind=SerialEventKind.EVENT_OVERFLOW,
                        detail=f"dropped {self._dropped_events} queued events",
                    ),
                )
                self._dropped_events = 0
            return tuple(events)

    def _apply_control_lines(
        self, backend: SerialBackend, policy: ControlLinePolicy
    ) -> None:
        if policy.dtr is not None:
            backend.dtr = policy.dtr
        if policy.rts is not None:
            backend.rts = policy.rts

    def _require_backend(self) -> SerialBackend:
        if self._backend is None or not self._backend.is_open:
            raise PortNotOpenError("serial port is not open")
        return self._backend

    def _record(self, direction: CaptureDirection, data: bytes) -> None:
        result = self._capture.append(
            CaptureRecord(
                timestamp=self._clock(),
                direction=direction,
                data=bytes(data),
            )
        )
        if not result.accepted:
            self._unreported_capture_records += result.dropped_records
            self._unreported_capture_bytes += result.dropped_bytes

    def _queue_event(
        self, kind: SerialEventKind, *, data: bytes = b"", detail: str = ""
    ) -> None:
        if len(self._events) >= self._max_events:
            self._events.popleft()
            self._dropped_events += 1
        self._events.append(
            SerialEvent(
                timestamp=self._clock(),
                kind=kind,
                data=bytes(data),
                detail=detail,
            )
        )

    def _disconnect_after_failure(self, error: BaseException) -> None:
        self._queue_event(SerialEventKind.ERROR, detail=str(error))
        self.close()

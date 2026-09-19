"""Append-only logging for explicit modem sessions."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from pathlib import Path

from modem_controller.transport.privacy import contains_secret_input


class LogMode(str, Enum):
    NORMAL = "normal"
    VERBOSE = "verbose"


class LogWriteError(RuntimeError):
    """Raised when an explicitly selected log file cannot be written."""


class SessionLog:
    """Writes selected session events to an explicitly chosen local file."""

    def __init__(self) -> None:
        self._path: Path | None = None
        self._mode = LogMode.NORMAL
        self._enabled = False
        self._secret = False

    @property
    def path(self) -> Path | None:
        return self._path

    @property
    def mode(self) -> LogMode:
        return self._mode

    @property
    def enabled(self) -> bool:
        return self._enabled

    def configure(self, path: Path | None, *, enabled: bool, mode: LogMode) -> None:
        self._path = path
        self._mode = mode
        self._enabled = enabled
        if enabled:
            self._write("LOGGING", f"enabled mode={mode.value}")

    def close(self) -> None:
        if self._enabled:
            self._write("LOGGING", "disabled")
        self._enabled = False

    def record_connected(self, settings: str) -> None:
        self._secret = False
        self._record_verbose("CONNECTED", settings)

    def record_connect_requested(self, settings: str) -> None:
        self._record_verbose("CONNECT REQUESTED", settings)

    def record_disconnected(self) -> None:
        self._record_verbose("DISCONNECTED", "")

    def record_disconnect_requested(self) -> None:
        self._record_verbose("DISCONNECT REQUESTED", "")

    def record_preset_requested(self, label: str, payload: bytes) -> None:
        if contains_secret_input(payload):
            self.record_gap("Sensitive preset omitted; reconnect to resume capture.")
            return
        self._record_verbose("PRESET REQUESTED", f"{label}: {payload.hex(' ').upper()}")

    def record_terminal_cleared(self) -> None:
        self._record_verbose("TERMINAL CLEARED", "")

    def record_sent(self, payload: bytes) -> None:
        self._record_payload("TX", payload)

    def record_received(self, payload: bytes) -> None:
        self._record_payload("RX", payload)

    def record_error(self, message: str) -> None:
        self._write("ERROR", "Sensitive operation failed." if self._secret else message)

    def record_gap(self, message: str) -> None:
        self._secret = True
        self._write("CAPTURE GAP", message)

    def _record_payload(self, direction: str, payload: bytes) -> None:
        if contains_secret_input(payload) and not self._secret:
            self.record_gap("Sensitive input/echo omitted until reconnect.")
        if self._secret:
            return
        self._write(direction, repr(payload.decode("utf-8", errors="replace")))
        if self._mode is LogMode.VERBOSE:
            self._write(f"{direction} HEX", payload.hex(" ").upper())

    def _record_verbose(self, event: str, message: str) -> None:
        if self._mode is LogMode.VERBOSE:
            self._write(event, message)

    def _write(self, event: str, message: str) -> None:
        if not self._enabled:
            return
        path = self._path
        if path is None:
            self._enabled = False
            raise LogWriteError("select a log file before enabling logging")
        line = f"{_timestamp()} {event} {message}\n"
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(line)
        except OSError as error:
            self._enabled = False
            raise LogWriteError(f"could not write log file: {error}") from error


def _timestamp() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")

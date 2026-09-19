"""Exclusive command scheduling and evidence-preserving AT response processing."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import timedelta
from enum import Enum
from typing import Protocol

from modem_controller.protocol.framing import AtFrame, AtFramer, FrameKind
from modem_controller.transport.privacy import contains_secret_input
from modem_controller.transport.serial_port import PortNotOpenError


class SessionTransport(Protocol):
    """The P02 operations required by a scheduled AT exchange."""

    @property
    def is_open(self) -> bool: ...

    def read_available(self, max_bytes: int = 4096) -> bytes: ...

    def write(self, data: bytes | bytearray | memoryview) -> int: ...


Clock = Callable[[], float]
UrcMatcher = Callable[[bytes], bool]


class SessionState(str, Enum):
    READY = "ready"
    AWAITING_RESPONSE = "awaiting_response"
    RESYNCHRONIZING = "resynchronizing"
    DISCONNECTED = "disconnected"


class ExchangeOutcome(str, Enum):
    COMPLETED = "completed"
    TIMED_OUT = "timed_out"
    CANCELLED = "cancelled"
    DISCONNECTED = "disconnected"


class AtSessionError(RuntimeError):
    """Base class for AT scheduler errors."""


class SessionBusyError(AtSessionError):
    """Raised when another exchange owns the session."""


class SessionResynchronizationRequiredError(AtSessionError):
    """Raised before reuse after timeout or cancellation."""


class SessionDisconnectedError(AtSessionError):
    """Raised when starting an exchange without a live serial connection."""


class PromptNotReceivedError(AtSessionError):
    """Raised when a prompt continuation is attempted before the modem prompt."""


class PromptAlreadySubmittedError(AtSessionError):
    """Raised when a prompt exchange would receive more than one continuation."""


@dataclass(frozen=True, slots=True)
class AtExchange:
    """Immutable evidence collected for a single scheduled command."""

    command: bytes
    started_at: float
    deadline_at: float
    frames: tuple[AtFrame, ...]
    response_lines: tuple[bytes, ...]
    command_echoes: tuple[bytes, ...]
    unsolicited: tuple[bytes, ...]
    prompt_received: bool
    outcome: ExchangeOutcome | None = None
    final_result: bytes | None = None


@dataclass(slots=True)
class _PendingExchange:
    command: bytes
    started_at: float
    deadline_at: float
    frames: list[AtFrame] = field(default_factory=list)
    response_lines: list[bytes] = field(default_factory=list)
    command_echoes: list[bytes] = field(default_factory=list)
    unsolicited: list[bytes] = field(default_factory=list)
    prompt_received: bool = False
    prompt_payload_submitted: bool = False
    secret: bool = False

    def snapshot(
        self,
        *,
        outcome: ExchangeOutcome | None = None,
        final_result: bytes | None = None,
    ) -> AtExchange:
        return AtExchange(
            command=b"" if self.secret else self.command,
            started_at=self.started_at,
            deadline_at=self.deadline_at,
            frames=() if self.secret else tuple(self.frames),
            response_lines=() if self.secret else tuple(self.response_lines),
            command_echoes=() if self.secret else tuple(self.command_echoes),
            unsolicited=() if self.secret else tuple(self.unsolicited),
            prompt_received=self.prompt_received,
            outcome=outcome,
            final_result=final_result,
        )


def default_urc_matcher(line: bytes) -> bool:
    """Classify unambiguous unsolicited notifications without guessing responses."""

    return line in {b"RING", b"NO CARRIER"} or line.startswith((b"+CMTI:", b"+CMT:"))


class AtSession:
    """Serializes commands and quarantines late replies after an aborted exchange."""

    def __init__(
        self,
        transport: SessionTransport,
        *,
        clock: Clock,
        urc_matcher: UrcMatcher = default_urc_matcher,
        resynchronization_quiet_period: float = 0.1,
    ) -> None:
        if resynchronization_quiet_period < 0:
            raise ValueError("resynchronization_quiet_period must not be negative")

        self._transport = transport
        self._clock = clock
        self._urc_matcher = urc_matcher
        self._quiet_period = resynchronization_quiet_period
        self._framer = AtFramer()
        self._state = SessionState.READY
        self._pending: _PendingExchange | None = None
        self._completed: list[AtExchange] = []
        self._discarded_frames: list[AtFrame] = []
        self._resynchronization_started_at: float | None = None
        self._last_resynchronization_data_at: float | None = None
        self._secret_session = False

    @property
    def state(self) -> SessionState:
        return self._state

    @property
    def active_exchange(self) -> AtExchange | None:
        if self._pending is None:
            return None
        return self._pending.snapshot()

    def start(
        self,
        command: bytes,
        *,
        timeout: timedelta,
        sensitive: bool = False,
        redact_evidence: bool = False,
    ) -> AtExchange:
        """Write a command exactly once and claim exclusive ownership until it ends."""

        if not isinstance(command, bytes):
            raise TypeError("command must be bytes")
        if not command:
            raise ValueError("command must not be empty")
        if timeout.total_seconds() <= 0:
            raise ValueError("timeout must be positive")
        if self._state is SessionState.RESYNCHRONIZING:
            raise SessionResynchronizationRequiredError(
                "resynchronize before starting another command"
            )
        if self._state is SessionState.AWAITING_RESPONSE:
            raise SessionBusyError("another command is awaiting a response")
        if self._state is SessionState.DISCONNECTED or not self._transport.is_open:
            self._state = SessionState.DISCONNECTED
            raise SessionDisconnectedError("serial transport is not connected")

        started_at = self._clock()
        secret = redact_evidence or contains_secret_input(command)
        self._secret_session = self._secret_session or secret
        pending = _PendingExchange(
            command=command,
            started_at=started_at,
            deadline_at=started_at + timeout.total_seconds(),
            secret=secret,
        )
        try:
            written = self._write(command, sensitive=sensitive or secret)
        except PortNotOpenError as error:
            self._state = SessionState.DISCONNECTED
            raise SessionDisconnectedError("serial transport disconnected") from error
        if written != len(command):
            raise AtSessionError("transport did not accept the complete command")

        self._pending = pending
        self._state = SessionState.AWAITING_RESPONSE
        return pending.snapshot()

    def submit_prompt_payload(
        self, payload: bytes, *, sensitive: bool = False
    ) -> AtExchange:
        """Submit one exact payload after a received prompt without a terminator."""

        if not payload:
            raise ValueError("prompt payload must not be empty")
        pending = self._pending
        if self._state is not SessionState.AWAITING_RESPONSE or pending is None:
            raise AtSessionError("there is no active prompt exchange")
        if not pending.prompt_received:
            raise PromptNotReceivedError("the modem prompt has not been received")
        if pending.prompt_payload_submitted:
            raise PromptAlreadySubmittedError(
                "the prompt payload was already submitted"
            )
        try:
            written = self._write(payload, sensitive=sensitive)
        except PortNotOpenError as error:
            self._state = SessionState.DISCONNECTED
            raise SessionDisconnectedError("serial transport disconnected") from error
        if written != len(payload):
            raise AtSessionError("transport did not accept the complete prompt payload")
        pending.prompt_payload_submitted = True
        return pending.snapshot()

    def poll(self) -> AtExchange | None:
        """Read and classify currently available bytes, then enforce deadlines."""

        if self._state is SessionState.DISCONNECTED:
            return None
        if not self._transport.is_open:
            return self._finish_disconnect()

        try:
            data = self._transport.read_available()
        except PortNotOpenError:
            return self._finish_disconnect()

        if self._state is SessionState.RESYNCHRONIZING:
            self._discard_for_resynchronization(data)
            return None
        if self._state is not SessionState.AWAITING_RESPONSE:
            return None

        if data:
            result = self._handle_frames(self._framer.feed(data))
            if result is not None:
                return result

        pending = self._pending
        if pending is not None and self._clock() >= pending.deadline_at:
            return self._finish(ExchangeOutcome.TIMED_OUT)
        return None

    def cancel(self) -> AtExchange:
        """Cancel the active exchange without sending an escape byte or retrying."""

        if self._state is not SessionState.AWAITING_RESPONSE:
            raise AtSessionError("there is no active command to cancel")
        return self._finish(ExchangeOutcome.CANCELLED)

    def resynchronize(self) -> bool:
        """Discard stale data until a configured quiet period proves the stream idle."""

        if self._state is not SessionState.RESYNCHRONIZING:
            raise AtSessionError("resynchronization is not required")
        if not self._transport.is_open:
            self._state = SessionState.DISCONNECTED
            return False

        try:
            data = self._transport.read_available()
        except PortNotOpenError:
            self._state = SessionState.DISCONNECTED
            return False
        self._discard_for_resynchronization(data)

        last_data_at = self._last_resynchronization_data_at
        if last_data_at is None:
            last_data_at = self._resynchronization_started_at
        if (
            last_data_at is not None
            and self._clock() - last_data_at >= self._quiet_period
        ):
            self._framer.reset()
            self._state = SessionState.READY
            self._resynchronization_started_at = None
            self._last_resynchronization_data_at = None
            return True
        return False

    def drain_completed(self) -> tuple[AtExchange, ...]:
        completed = tuple(self._completed)
        self._completed.clear()
        return completed

    def drain_discarded_frames(self) -> tuple[AtFrame, ...]:
        discarded = tuple(self._discarded_frames)
        self._discarded_frames.clear()
        return discarded

    def _handle_frames(self, frames: tuple[AtFrame, ...]) -> AtExchange | None:
        pending = self._pending
        if pending is None:
            return None

        command_echo = pending.command.rstrip(b"\r\n")
        for frame in frames:
            pending.frames.append(frame)
            if frame.kind is FrameKind.PROMPT:
                pending.prompt_received = True
                continue
            if frame.data == command_echo:
                pending.command_echoes.append(frame.data)
                continue
            if self._urc_matcher(frame.data):
                pending.unsolicited.append(frame.data)
                continue
            if self._is_final_result(frame.data):
                return self._finish(ExchangeOutcome.COMPLETED, frame.data)
            pending.response_lines.append(frame.data)
        return None

    @staticmethod
    def _is_final_result(line: bytes) -> bool:
        return line in {b"OK", b"ERROR"} or line.startswith(
            (b"+CME ERROR:", b"+CMS ERROR:")
        )

    def _finish(
        self, outcome: ExchangeOutcome, final_result: bytes | None = None
    ) -> AtExchange:
        pending = self._pending
        if pending is None:
            raise AtSessionError("no active exchange to finish")
        exchange = pending.snapshot(outcome=outcome, final_result=final_result)
        self._pending = None
        self._completed.append(exchange)
        if outcome in {ExchangeOutcome.TIMED_OUT, ExchangeOutcome.CANCELLED}:
            self._state = SessionState.RESYNCHRONIZING
            self._resynchronization_started_at = self._clock()
            self._last_resynchronization_data_at = None
        elif outcome is ExchangeOutcome.DISCONNECTED:
            self._state = SessionState.DISCONNECTED
        else:
            self._state = SessionState.READY
        return exchange

    def _finish_disconnect(self) -> AtExchange | None:
        if self._pending is None:
            self._state = SessionState.DISCONNECTED
            return None
        return self._finish(ExchangeOutcome.DISCONNECTED)

    def _discard_for_resynchronization(self, data: bytes) -> None:
        if not data:
            return
        frames = self._framer.feed(data)
        if not self._secret_session:
            self._discarded_frames.extend(frames)
        self._last_resynchronization_data_at = self._clock()

    def _write(self, data: bytes, *, sensitive: bool) -> int:
        if sensitive:
            writer = getattr(self._transport, "write_sensitive", None)
            if writer is not None:
                return writer(data)
        return self._transport.write(data)

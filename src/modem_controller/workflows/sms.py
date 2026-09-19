"""Explicit text-mode SMS status, reading, and one-message sending."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import timedelta
from enum import Enum

from modem_controller.protocol.at_session import AtExchange, AtSession, ExchangeOutcome

_RECIPIENT = re.compile(r"\+?[0-9]{3,15}")


class SmsOutcome(str, Enum):
    CANCELLED = "cancelled"
    SENT = "sent"
    INDETERMINATE = "indeterminate"
    NOT_READY = "not_ready"


class SmsConfirmationRequiredError(ValueError):
    """Raised when a potentially state-changing SMS read was not confirmed."""


@dataclass(frozen=True, slots=True)
class SmsMessage:
    recipient: str
    body: str

    def __post_init__(self) -> None:
        if _RECIPIENT.fullmatch(self.recipient) is None:
            raise ValueError("recipient must contain 3 to 15 digits with an optional +")
        if not self.body or len(self.body) > 160:
            raise ValueError("text-mode SMS body must contain 1 to 160 characters")
        if not self.body.isascii() or any(
            not 32 <= ord(character) < 127 for character in self.body
        ):
            raise ValueError("only printable ASCII text-mode SMS bodies are supported")


@dataclass(frozen=True, slots=True)
class SmsSendResult:
    outcome: SmsOutcome
    evidence: tuple[bytes, ...]
    next_action: str


class SmsInspector:
    """Builds explicit SMS queries without deleting or changing configuration."""

    @staticmethod
    def status_commands() -> tuple[bytes, ...]:
        return (b"AT+CMGF?\r", b"AT+CSCS?\r", b"AT+CPMS?\r")

    @staticmethod
    def read_message(index: int, *, confirmed: bool) -> bytes:
        if index <= 0:
            raise ValueError("SMS index must be positive")
        if not confirmed:
            raise SmsConfirmationRequiredError(
                "reading an SMS may change its read/unread state"
            )
        return f"AT+CMGR={index}\r".encode("ascii")


class SmsSendWorkflow:
    """Sends exactly one confirmed text-mode SMS and never retries delivery."""

    def __init__(self, session: AtSession, *, completion_timeout: timedelta) -> None:
        if completion_timeout.total_seconds() <= 0:
            raise ValueError("completion_timeout must be positive")
        self._session = session
        self._completion_timeout = completion_timeout
        self._message: SmsMessage | None = None
        self._submitted = False
        self._preflight_index = 0
        self._checking = False

    def begin(
        self, message: SmsMessage, *, confirmed: bool, profile_supported: bool = True
    ) -> SmsSendResult | None:
        if not confirmed:
            return SmsSendResult(
                SmsOutcome.CANCELLED,
                (),
                "Review the recipient and text, then confirm before sending.",
            )
        self._message = message
        self._submitted = False
        if not profile_supported:
            return SmsSendResult(
                SmsOutcome.NOT_READY,
                (),
                "The selected profile has no reviewed SMS support. Nothing sent.",
            )
        self._preflight_index = 0
        self._checking = True
        self._start_check()
        return None

    def _start_check(self) -> None:
        self._session.start(
            (b"AT+CPIN?\r", b"AT+CMGF?\r", b"AT+CSCS?\r")[self._preflight_index],
            timeout=min(self._completion_timeout, timedelta(seconds=5)),
        )

    def _start_submission(self) -> None:
        message = self._message
        if message is None:
            raise RuntimeError("SMS message is missing")
        self._session.start(
            f'AT+CMGS="{message.recipient}"\r'.encode("ascii"),
            timeout=self._completion_timeout,
            sensitive=True,
        )

    def poll(self) -> SmsSendResult | None:
        completed = self._session.poll()
        if completed is not None:
            if self._checking:
                return self._check_result(completed)
            return self._result(completed)
        active = self._session.active_exchange
        if active is not None and active.prompt_received and not self._submitted:
            message = self._message
            if message is None:
                raise RuntimeError("SMS message is missing")
            self._session.submit_prompt_payload(
                message.body.encode("ascii") + b"\x1a", sensitive=True
            )
            self._submitted = True
        return None

    def cancel(self) -> SmsSendResult:
        return self._result(self._session.cancel())

    def _check_result(self, exchange: AtExchange) -> SmsSendResult | None:
        expected = (rb"\+CPIN:\s*READY", rb"\+CMGF:\s*1", rb'\+CSCS:\s*"IRA"')[
            self._preflight_index
        ]
        if (
            exchange.outcome is not ExchangeOutcome.COMPLETED
            or exchange.final_result != b"OK"
            or not any(
                re.fullmatch(expected, line.strip(), re.I)
                for line in exchange.response_lines
            )
        ):
            labels = (
                "SIM must be present and READY",
                "SMS mode must already be text mode",
                "Only the IRA character set is supported",
            )
            return SmsSendResult(
                SmsOutcome.NOT_READY,
                exchange.response_lines,
                labels[self._preflight_index]
                + ". No SMS submitted; no configuration changed.",
            )
        self._preflight_index += 1
        if self._preflight_index < 3:
            self._start_check()
        else:
            # Avoid ambiguous extension characters in the initial sender.
            if self._message is None or not re.fullmatch(
                r"""[A-Za-z0-9 !"#%&'()*+,\-./:;<=>?]+""", self._message.body
            ):
                return SmsSendResult(
                    SmsOutcome.NOT_READY,
                    (),
                    "Use letters, digits and basic ASCII punctuation. "
                    "No SMS submitted.",
                )
            self._checking = False
            self._start_submission()
        return None

    def _result(self, exchange: AtExchange) -> SmsSendResult:
        evidence = exchange.response_lines + (
            (exchange.final_result,) if exchange.final_result is not None else ()
        )
        if (
            exchange.outcome is ExchangeOutcome.COMPLETED
            and exchange.final_result == b"OK"
            and self._submitted
            and any(
                re.fullmatch(rb"\+CMGS:\s*\d+", line.strip())
                for line in exchange.response_lines
            )
        ):
            return SmsSendResult(
                SmsOutcome.SENT,
                evidence,
                (
                    "Modem submission acknowledged. Delivery to the recipient is not "
                    "confirmed. No automatic resend."
                ),
            )
        if exchange.outcome is ExchangeOutcome.CANCELLED and not self._submitted:
            return SmsSendResult(
                SmsOutcome.CANCELLED,
                evidence,
                "Send cancelled; reconnect or resynchronize before another action.",
            )
        return SmsSendResult(
            SmsOutcome.INDETERMINATE,
            evidence,
            "Submission/delivery outcome is unknown; do not resend automatically.",
        )

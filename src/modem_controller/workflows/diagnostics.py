"""Bounded, read-only AT diagnostics with query-specific evidence interpretation."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, replace
from enum import Enum
from time import monotonic

from modem_controller.catalog.models import (
    CatalogCommand,
    CommandKind,
    DeviceProfile,
    RiskLevel,
    VerificationStatus,
)
from modem_controller.protocol.at_session import AtExchange, ExchangeOutcome


class DiagnosticState(str, Enum):
    OK = "ok"
    ATTENTION = "attention"
    UNKNOWN = "unknown"
    UNSUPPORTED = "unsupported"
    SKIPPED = "skipped"


@dataclass(frozen=True, slots=True)
class DiagnosticResult:
    command_id: str
    state: DiagnosticState
    evidence: tuple[bytes, ...]
    next_check: str
    reason: str = ""
    observed_at: float | None = None


Execute = Callable[[CatalogCommand], AtExchange]
Cancelled = Callable[[], bool]
_ALLOWED = frozenset(
    {
        "AT",
        "ATI",
        "AT+CGMI",
        "AT+CGMM",
        "AT+CGMR",
        "AT+CGSN",
        "AT+GMI",
        "AT+GMM",
        "AT+GMR",
        "AT+GSN",
        "AT+CPIN?",
        "AT+CREG?",
        "AT+CGREG?",
        "AT+CEREG?",
        "AT+CSQ",
        "AT+COPS?",
        "AT+IPR?",
        "AT+CMGF?",
        "AT+CSCS?",
        "AT+CPMS?",
        "AT+CSCA?",
        "AT+CMEE?",
        "AT+QNWINFO",
    }
)
_SIM_DEPENDENT = {"AT+COPS?", "AT+CPMS?", "AT+CSCA?"}


class DiagnosticRunner:
    """A fresh run invalidates previous observations and never initiates repairs."""

    def __init__(
        self,
        execute: Execute,
        *,
        cancelled: Cancelled = lambda: False,
        clock: Callable[[], float] = monotonic,
        total_timeout: float = 30.0,
    ) -> None:
        if total_timeout <= 0:
            raise ValueError("total_timeout must be positive")
        self._execute = execute
        self._cancelled = cancelled
        self._clock = clock
        self._total_timeout = total_timeout

    def run(self, profile: DeviceProfile) -> tuple[DiagnosticResult, ...]:
        results: list[DiagnosticResult] = []
        deadline = self._clock() + self._total_timeout
        sim_unavailable = False
        stopped = ""
        for command in profile.commands:
            if (
                command.kind is not CommandKind.AT
                or command.risk is not RiskLevel.READ_ONLY
            ):
                continue
            payload = (command.payload or "").upper()
            reason = stopped
            if self._cancelled():
                reason = "cancelled"
            elif self._clock() >= deadline:
                reason = "run_budget_exhausted"
            elif sim_unavailable and payload in _SIM_DEPENDENT:
                reason = "sim_unavailable"
            if reason:
                results.append(
                    DiagnosticResult(
                        command.id,
                        DiagnosticState.SKIPPED,
                        (),
                        "Resolve the blocking condition before another diagnostic run.",
                        reason,
                        self._clock(),
                    )
                )
                continue
            if (
                command.verification is not VerificationStatus.SUPPORTED
                or payload not in _ALLOWED
                or command.parameters
            ):
                results.append(
                    DiagnosticResult(
                        command.id,
                        DiagnosticState.UNSUPPORTED,
                        (),
                        "Review command applicability; no bytes were sent.",
                        "not_approved",
                        self._clock(),
                    )
                )
                continue
            bounded = replace(
                command,
                timeout_seconds=min(
                    command.timeout_seconds, max(0.001, deadline - self._clock())
                ),
            )
            exchange = self._execute(bounded)
            result = replace(
                self._interpret(command, exchange), observed_at=self._clock()
            )
            results.append(result)
            if payload == "AT+CPIN?":
                sim_unavailable = result.state is not DiagnosticState.OK
            if exchange.outcome in {
                ExchangeOutcome.DISCONNECTED,
                ExchangeOutcome.CANCELLED,
                ExchangeOutcome.TIMED_OUT,
            }:
                stopped = result.reason
        return tuple(results)

    @staticmethod
    def _interpret(command: CatalogCommand, exchange: AtExchange) -> DiagnosticResult:
        evidence = exchange.response_lines + (
            (exchange.final_result,) if exchange.final_result else ()
        )

        def result(
            state: DiagnosticState, reason: str, next_check: str
        ) -> DiagnosticResult:
            return DiagnosticResult(command.id, state, evidence, next_check, reason)

        outcomes = {
            ExchangeOutcome.TIMED_OUT: "timeout",
            ExchangeOutcome.DISCONNECTED: "disconnected",
            ExchangeOutcome.CANCELLED: "cancelled",
        }
        if exchange.outcome is not ExchangeOutcome.COMPLETED:
            return result(
                DiagnosticState.UNKNOWN,
                outcomes.get(exchange.outcome, "incomplete"),
                "Check the connection before retrying deliberately.",
            )
        if exchange.final_result != b"OK":
            return result(
                DiagnosticState.UNKNOWN,
                "modem_error",
                "Inspect the exact modem error; no repair was attempted.",
            )
        payload = (command.payload or "").upper()
        lines = exchange.response_lines
        if payload == "AT+CPIN?":
            states = [
                line.removeprefix(b"+CPIN:").strip()
                for line in lines
                if line.startswith(b"+CPIN:")
            ]
            if states:
                ready = states[-1] == b"READY"
                return result(
                    DiagnosticState.OK if ready else DiagnosticState.ATTENTION,
                    "sim_ready" if ready else "sim_unavailable",
                    "SIM is ready."
                    if ready
                    else "Inspect the SIM; never retry a PIN automatically.",
                )
        elif payload in {"AT+CREG?", "AT+CGREG?", "AT+CEREG?"}:
            domain = payload[2:-1].encode()
            for line in lines:
                match = re.fullmatch(
                    re.escape(domain) + rb":\s*([0-9]+),\s*([0-9]+)(?:,.*)?", line
                )
                if match:
                    status = int(match[2])
                    if status in {1, 5}:
                        return result(
                            DiagnosticState.OK,
                            domain.decode() + ":registered",
                            "Registration is reported for this domain only.",
                        )
                    if status in {0, 2, 3, 4}:
                        return result(
                            DiagnosticState.ATTENTION,
                            domain.decode() + ":not_registered",
                            "Check registration, SIM and coverage manually.",
                        )
        elif payload == "AT+CSQ":
            for line in lines:
                match = re.fullmatch(rb"\+CSQ:\s*([0-9]+),\s*([0-9]+)", line)
                if match:
                    signal = int(match[1])
                    quality = int(match[2])
                    if signal == 99:
                        return result(
                            DiagnosticState.UNKNOWN,
                            "signal_unavailable",
                            "Signal is unavailable, not zero.",
                        )
                    if 0 <= signal <= 31 and (0 <= quality <= 7 or quality == 99):
                        return result(
                            DiagnosticState.OK,
                            "signal_available",
                            f"CSQ RSSI code {signal}; inspect registration separately.",
                        )
        elif payload == "AT+QNWINFO":
            if any(b"No Service" in line for line in lines):
                return result(
                    DiagnosticState.ATTENTION,
                    "no_service",
                    "Check registration; the cause remains unknown.",
                )
            if any(line.startswith(b"+QNWINFO:") for line in lines):
                return result(
                    DiagnosticState.OK,
                    "network_information",
                    "Inspect technology information within this profile's scope.",
                )
        elif payload == "AT":
            return result(
                DiagnosticState.OK,
                "command_completed",
                "The modem accepted this query.",
            )
        elif lines:
            return result(
                DiagnosticState.OK,
                "query_evidence",
                "Inspect the recorded query response; no root cause is inferred.",
            )
        return result(
            DiagnosticState.UNKNOWN,
            "unrecognized_response",
            "Keep the raw reply and verify its format against the device reference.",
        )

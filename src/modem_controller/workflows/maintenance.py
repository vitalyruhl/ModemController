"""Explicit, one-shot execution of reviewed state-changing AT actions."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from time import monotonic, sleep

from modem_controller.catalog.models import (
    CatalogCommand,
    CommandKind,
    CommandUnavailableError,
    DeviceProfile,
    RiskLevel,
)
from modem_controller.protocol.at_session import AtExchange, ExchangeOutcome


class MaintenanceOutcome(str, Enum):
    CANCELLED = "cancelled"
    COMPLETED = "completed"
    INCONCLUSIVE = "inconclusive"


@dataclass(frozen=True, slots=True)
class MaintenancePreview:
    command_id: str
    risk: RiskLevel
    risk_summary: str
    contains_secret: bool


@dataclass(frozen=True, slots=True)
class MaintenanceResult:
    command_id: str
    outcome: MaintenanceOutcome
    evidence: tuple[bytes, ...]
    session_invalidated: bool
    capture_gap: str | None
    next_action: str


Execute = Callable[[bytes], AtExchange]


class MaintenanceRunner:
    """Runs one explicitly confirmed action and never retries it automatically."""

    def __init__(self, execute: Execute, *, terminator: bytes = b"\r") -> None:
        if terminator not in {b"\r", b"\n", b"\r\n"}:
            raise ValueError("terminator must be CR, LF, or CRLF")
        self._execute = execute
        self._terminator = terminator

    @staticmethod
    def preview(command: CatalogCommand) -> MaintenancePreview:
        MaintenanceRunner._validate_command(command)
        return MaintenancePreview(
            command.id,
            command.risk,
            command.help_text,
            any(parameter.secret for parameter in command.parameters),
        )

    def run(
        self,
        command: CatalogCommand,
        values: dict[str, str],
        *,
        confirmed: bool,
    ) -> MaintenanceResult:
        preview = self.preview(command)
        if not confirmed:
            return MaintenanceResult(
                command.id,
                MaintenanceOutcome.CANCELLED,
                (),
                False,
                None,
                "Review the risk preview and confirm before sending this action.",
            )

        payload = command.render(values) + self._terminator
        exchange = self._execute(payload)
        evidence = exchange.response_lines + (
            (exchange.final_result,) if exchange.final_result is not None else ()
        )
        if (
            exchange.outcome is ExchangeOutcome.COMPLETED
            and exchange.final_result == b"OK"
        ):
            outcome = MaintenanceOutcome.COMPLETED
            next_action = "Reconnect or resynchronize before another action."
        else:
            outcome = MaintenanceOutcome.INCONCLUSIVE
            next_action = "Do not retry automatically; reconnect or inspect evidence."
        capture_gap = None
        if preview.contains_secret:
            capture_gap = "Sensitive maintenance input was excluded from capture."
        return MaintenanceResult(
            command.id,
            outcome,
            evidence,
            True,
            capture_gap,
            next_action,
        )

    @staticmethod
    def _validate_command(command: CatalogCommand) -> None:
        if not command.is_visible:
            raise CommandUnavailableError("maintenance action is not verified")
        if command.kind is not CommandKind.AT:
            raise CommandUnavailableError(
                "maintenance actions must be individual AT commands"
            )
        if command.risk is RiskLevel.READ_ONLY:
            raise ValueError("read-only commands do not need maintenance confirmation")


class SequenceRunner:
    """Bounded, cancellable command references with no retries or resume mechanism."""

    def __init__(self, execute, *, cancelled=lambda: False, clock=monotonic, wait=None):
        self._execute = execute
        self._cancelled = cancelled
        self._clock = clock
        self._wait = wait or self._interruptible_wait

    def _interruptible_wait(self, seconds: float) -> None:
        until = self._clock() + seconds
        while not self._cancelled() and self._clock() < until:
            sleep(min(0.01, max(0, until - self._clock())))

    @staticmethod
    def validate(sequence: CatalogCommand, profile: DeviceProfile) -> None:
        if sequence.kind is not CommandKind.SEQUENCE or not sequence.is_visible:
            raise CommandUnavailableError("sequence must be reviewed before execution")
        for index, step in enumerate(sequence.sequence_steps):
            command = profile.command(step.command_id)
            if not command.is_visible or command.kind not in {
                CommandKind.AT,
                CommandKind.BYTES,
            }:
                raise CommandUnavailableError(
                    "sequence step is not a reviewed AT/byte action"
                )
            if any(p.secret for p in command.parameters) and (
                index != len(sequence.sequence_steps) - 1 or step.expected_contains
            ):
                raise ValueError("secret step must be last without a text condition")

    def run(
        self, sequence, profile, values, *, confirmed: bool, total_timeout: float = 30.0
    ) -> MaintenanceResult:
        self.validate(sequence, profile)
        if not 0 < total_timeout <= 120:
            raise ValueError("sequence total budget must be within 120 seconds")
        commands = [
            profile.command(step.command_id) for step in sequence.sequence_steps
        ]
        arguments = [
            {p.name: values[p.name] for p in command.parameters if p.name in values}
            for command in commands
        ]
        # Validate all parameters before the first byte; do not retain rendered secrets.
        for command, args in zip(commands, arguments, strict=True):
            command.render(args)
        evidence = []
        sent = False
        secret_used = False
        outcome = MaintenanceOutcome.CANCELLED
        progress = "Sequence was not confirmed."
        deadline = self._clock() + total_timeout
        if confirmed:
            outcome = MaintenanceOutcome.COMPLETED
            for index, (step, command, args) in enumerate(
                zip(sequence.sequence_steps, commands, arguments, strict=True), 1
            ):
                progress = f"Stopped at step {index} ({command.id})."
                if self._cancelled():
                    outcome = MaintenanceOutcome.CANCELLED
                    progress += " Cancelled before sending."
                    break
                remaining = deadline - self._clock()
                if remaining <= 0:
                    outcome = MaintenanceOutcome.INCONCLUSIVE
                    progress += " Total time budget exhausted before sending."
                    break
                sent = True
                secret = any(p.secret for p in command.parameters)
                secret_used |= secret
                exchange = self._execute(
                    command, args, min(step.timeout_seconds, remaining)
                )
                if not secret:
                    evidence.extend(exchange.response_lines)
                if (
                    exchange.outcome is not ExchangeOutcome.COMPLETED
                    or exchange.final_result != b"OK"
                    or self._clock() > deadline
                    or (
                        step.expected_contains
                        and step.expected_contains.encode("ascii")
                        not in b"\n".join(exchange.response_lines)
                    )
                ):
                    outcome = MaintenanceOutcome.INCONCLUSIVE
                    if secret:
                        progress += " Sensitive step did not complete successfully."
                    elif exchange.final_result == b"ERROR":
                        progress += " Modem returned ERROR."
                    elif exchange.final_result != b"OK":
                        progress += (
                            " No successful final OK response "
                            f"({exchange.outcome.value})."
                        )
                    else:
                        progress += " Response condition or time budget not met."
                    break
                remaining = deadline - self._clock()
                if step.delay_seconds > remaining:
                    outcome = MaintenanceOutcome.INCONCLUSIVE
                    progress += " Delay exceeds remaining time budget."
                    break
                if step.delay_seconds:
                    self._wait(step.delay_seconds)
                if self._cancelled():
                    outcome = MaintenanceOutcome.CANCELLED
                    progress += " Cancelled after sending."
                    break
            else:
                progress = f"Completed all {len(commands)} steps."
        return MaintenanceResult(
            sequence.id,
            outcome,
            tuple(evidence),
            sent,
            "Sensitive step excluded from capture." if secret_used else None,
            progress
            + " Reconnect before another action. No automatic retry or resume.",
        )

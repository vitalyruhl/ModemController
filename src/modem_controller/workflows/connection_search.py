"""Bounded, non-destructive probing of serial settings."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from enum import Enum
from itertools import product
from time import monotonic

from modem_controller.protocol.at_session import AtExchange, ExchangeOutcome
from modem_controller.transport.serial_port import (
    ControlLinePolicy,
    FlowControl,
    Parity,
    SerialSettings,
)


class SearchPhase(str, Enum):
    QUICK = "quick"
    EXTENDED = "extended"


class SearchOutcome(str, Enum):
    CONFIRMED = "confirmed"
    INCONCLUSIVE = "inconclusive"
    CANCELLED = "cancelled"
    DISCONNECTED = "disconnected"


@dataclass(frozen=True, slots=True)
class SearchCandidate:
    """One host-side setting combination to probe with a harmless AT command."""

    settings: SerialSettings
    phase: SearchPhase


@dataclass(frozen=True, slots=True)
class SearchAttempt:
    candidate: SearchCandidate
    exchanges: tuple[AtExchange, ...]
    outcome: SearchOutcome
    explanation: str


@dataclass(frozen=True, slots=True)
class ConnectionSearchResult:
    attempts: tuple[SearchAttempt, ...]
    selected: SearchCandidate | None

    @property
    def was_cancelled(self) -> bool:
        return (
            bool(self.attempts) and self.attempts[-1].outcome is SearchOutcome.CANCELLED
        )


Probe = Callable[[SerialSettings, bytes], AtExchange]
Cancelled = Callable[[], bool]
Apply = Callable[[SerialSettings], None]
Save = Callable[[SerialSettings], None]


def settings_from_preferences(
    base: SerialSettings, preferences: dict[str, str]
) -> SerialSettings:
    flows = {
        "None": FlowControl.NONE,
        "RTS/CTS": FlowControl.RTS_CTS,
        "DSR/DTR": FlowControl.DSR_DTR,
    }
    controls = {"Driver default": None, "On": True, "Off": False}
    flow = flows.get(preferences.get("flow_control"), base.flow_control)
    return replace(
        base,
        baud_rate=int(preferences.get("baud_rate", base.baud_rate)),
        data_bits=int(preferences.get("data_bits", base.data_bits)),
        parity=Parity(preferences.get("parity", base.parity.value)),
        stop_bits=float(preferences.get("stop_bits", base.stop_bits)),
        flow_control=flow,
        control_lines=ControlLinePolicy(
            None
            if flow is FlowControl.DSR_DTR
            else controls.get(preferences.get("dtr"), base.control_lines.dtr),
            None
            if flow is FlowControl.RTS_CTS
            else controls.get(preferences.get("rts"), base.control_lines.rts),
        ),
    )


class ConnectionSearchRunner:
    """Evaluate supplied serial settings without reconfiguring the modem itself."""

    def __init__(
        self,
        probe: Probe,
        *,
        cancelled: Cancelled = lambda: False,
        terminator: bytes = b"\r",
        confirmations_required: int = 2,
        clock=monotonic,
        total_timeout: float = 120.0,
        progress=lambda index, total, candidate: None,
    ) -> None:
        if terminator not in {b"\r", b"\n", b"\r\n"}:
            raise ValueError("terminator must be CR, LF, or CRLF")
        if confirmations_required < 2:
            raise ValueError("at least two confirmations are required")
        if not 0 < total_timeout <= 300:
            raise ValueError("search budget must be within 300 seconds")
        self._clock = clock
        self._total_timeout = total_timeout
        self._progress = progress
        self._probe = probe
        self._cancelled = cancelled
        self._command = b"AT" + terminator
        self._confirmations_required = confirmations_required

    @staticmethod
    def quick_candidates(
        port: str, *, preferred=(), base=None
    ) -> tuple[SearchCandidate, ...]:
        baseline = base or SerialSettings(port=port)
        settings = (
            *preferred,
            *(
                replace(baseline, port=port, baud_rate=rate)
                for rate in (9600, 19200, 38400, 57600, 115200)
            ),
        )
        return tuple(
            SearchCandidate(item, SearchPhase.QUICK)
            for item in dict.fromkeys(settings)
            if item.port == port
        )

    @staticmethod
    def extended_candidates(
        base: SerialSettings,
        *,
        baud_rates=(9600, 19200, 38400, 57600, 115200),
        data_bits=(8,),
        parities=(Parity.NONE,),
        stop_bits=(1,),
        flow_controls=(FlowControl.NONE,),
    ) -> tuple[SearchCandidate, ...]:
        options = (baud_rates, data_bits, parities, stop_bits, flow_controls)
        count = 1
        for option in options:
            count *= len(option)
        if not 1 <= count <= 60:
            raise ValueError("select between 1 and 60 extended combinations")
        return tuple(
            SearchCandidate(
                replace(
                    base,
                    baud_rate=rate,
                    data_bits=bits,
                    parity=parity,
                    stop_bits=stops,
                    flow_control=flow,
                    control_lines=ControlLinePolicy(
                        None if flow is FlowControl.DSR_DTR else base.control_lines.dtr,
                        None if flow is FlowControl.RTS_CTS else base.control_lines.rts,
                    ),
                ),
                SearchPhase.EXTENDED,
            )
            for rate, bits, parity, stops, flow in product(*options)
        )

    def run(self, candidates: tuple[SearchCandidate, ...]) -> ConnectionSearchResult:
        if len(candidates) > 70:
            raise ValueError("search candidate limit exceeded")
        deadline = self._clock() + self._total_timeout
        attempts: list[SearchAttempt] = []
        for index, candidate in enumerate(candidates):
            self._progress(index + 1, len(candidates), candidate)
            exchanges: list[AtExchange] = []
            for _ in range(self._confirmations_required):
                if self._cancelled():
                    attempts.append(
                        SearchAttempt(
                            candidate,
                            tuple(exchanges),
                            SearchOutcome.CANCELLED,
                            "Search cancelled before another probe was sent.",
                        )
                    )
                    return ConnectionSearchResult(tuple(attempts), None)
                remaining = deadline - self._clock()
                if remaining <= 0:
                    attempts.append(
                        SearchAttempt(
                            candidate,
                            tuple(exchanges),
                            SearchOutcome.INCONCLUSIVE,
                            "Search total deadline expired.",
                        )
                    )
                    return ConnectionSearchResult(tuple(attempts), None)
                settings = replace(
                    candidate.settings,
                    response_timeout=min(
                        candidate.settings.response_timeout, remaining
                    ),
                )
                exchange = self._probe(settings, self._command)
                if self._cancelled() or exchange.outcome is ExchangeOutcome.CANCELLED:
                    attempts.append(
                        SearchAttempt(
                            candidate,
                            tuple((*exchanges, exchange)),
                            SearchOutcome.CANCELLED,
                            "Search cancelled; port is released.",
                        )
                    )
                    return ConnectionSearchResult(tuple(attempts), None)
                if self._clock() > deadline:
                    attempts.append(
                        SearchAttempt(
                            candidate,
                            tuple((*exchanges, exchange)),
                            SearchOutcome.INCONCLUSIVE,
                            "Response exceeded the total deadline.",
                        )
                    )
                    return ConnectionSearchResult(tuple(attempts), None)
                exchanges.append(exchange)
                if exchange.outcome is ExchangeOutcome.DISCONNECTED:
                    attempts.append(
                        SearchAttempt(
                            candidate,
                            tuple(exchanges),
                            SearchOutcome.DISCONNECTED,
                            "The port disconnected while its settings were probed.",
                        )
                    )
                    return ConnectionSearchResult(tuple(attempts), None)
                if not self._is_confirmation(exchange):
                    break
            if len(exchanges) == self._confirmations_required and all(
                self._is_confirmation(exchange) for exchange in exchanges
            ):
                attempt = SearchAttempt(
                    candidate,
                    tuple(exchanges),
                    SearchOutcome.CONFIRMED,
                    "Two independent AT replies confirmed these host-side settings.",
                )
                return ConnectionSearchResult(tuple((*attempts, attempt)), candidate)
            attempts.append(
                SearchAttempt(
                    candidate,
                    tuple(exchanges),
                    SearchOutcome.INCONCLUSIVE,
                    "No repeated, command-correlated AT response was observed.",
                )
            )
        return ConnectionSearchResult(tuple(attempts), None)

    @staticmethod
    def use(result: ConnectionSearchResult, apply: Apply) -> SerialSettings:
        """Apply only a repeated-confirmed candidate; saving is a separate action."""

        if result.selected is None:
            raise ValueError("an inconclusive search result cannot be used")
        settings = result.selected.settings
        apply(settings)
        return settings

    @staticmethod
    def save(result: ConnectionSearchResult, save: Save) -> SerialSettings:
        """Persist only a repeated-confirmed candidate after explicit caller intent."""

        if result.selected is None:
            raise ValueError("an inconclusive search result cannot be saved")
        settings = result.selected.settings
        save(settings)
        return settings

    def _is_confirmation(self, exchange: AtExchange) -> bool:
        return (
            exchange.command == self._command
            and exchange.outcome is ExchangeOutcome.COMPLETED
            and exchange.final_result == b"OK"
        )

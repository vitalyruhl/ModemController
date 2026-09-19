from dataclasses import replace

import pytest

from modem_controller.catalog.models import (
    CatalogCommand,
    CatalogValidationError,
    CommandKind,
    RiskLevel,
    SequenceStep,
    VerificationStatus,
    load_starter_catalog,
)
from modem_controller.protocol.at_session import AtExchange, ExchangeOutcome
from modem_controller.workflows.maintenance import (
    MaintenanceOutcome,
    SequenceRunner,
)


def exchange(
    *lines: bytes,
    final: bytes | None = b"OK",
    outcome: ExchangeOutcome = ExchangeOutcome.COMPLETED,
) -> AtExchange:
    return AtExchange(b"", 0, 1, (), tuple(lines), (), (), False, outcome, final)


def profile_with(sequence: CatalogCommand):
    profile = load_starter_catalog().profile("generic-at")
    return replace(profile, commands=(*profile.commands, sequence))


def reviewed_sequence(*steps: SequenceStep) -> CatalogCommand:
    attention = load_starter_catalog().profile("generic-at").command("attention")
    return replace(
        attention,
        id="reviewed-check",
        label="Reviewed check",
        kind=CommandKind.SEQUENCE,
        payload=None,
        sequence_steps=steps,
        risk=RiskLevel.STATE_CHANGING,
        verification=VerificationStatus.SUPPORTED,
    )


def test_sequence_catalog_round_trip_preserves_declarative_steps() -> None:
    catalog = load_starter_catalog()
    sequence = reviewed_sequence(
        SequenceStep("attention", expected_contains="OK", timeout_seconds=1.5),
        SequenceStep("identity", delay_seconds=0.25),
    )
    profile = profile_with(sequence)
    changed = replace(
        catalog,
        profiles=tuple(
            profile if item.id == profile.id else item for item in catalog.profiles
        ),
    )

    restored = type(changed).from_json(changed.to_json())

    assert restored.profile("generic-at").command("reviewed-check") == sequence


@pytest.mark.parametrize("confirmed,cancelled", [(False, False), (True, True)])
def test_sequence_needs_confirmation_and_honors_cancel_before_io(
    confirmed: bool, cancelled: bool
) -> None:
    sequence = reviewed_sequence(SequenceStep("attention"))
    calls: list[tuple[str, dict[str, str], float]] = []
    result = SequenceRunner(
        lambda command, values, timeout: calls.append((command.id, values, timeout))
        or exchange(),
        cancelled=lambda: cancelled,
    ).run(sequence, profile_with(sequence), {}, confirmed=confirmed)

    assert result.outcome is MaintenanceOutcome.CANCELLED
    assert calls == []


@pytest.mark.parametrize("invalid_step", ["missing", "ras-collector", "nested"])
def test_sequence_prevalidates_all_steps_before_any_io(invalid_step: str) -> None:
    nested = reviewed_sequence(SequenceStep("attention"))
    nested = replace(nested, id="nested")
    sequence = reviewed_sequence(SequenceStep("attention"), SequenceStep(invalid_step))
    calls: list[str] = []

    with pytest.raises(CatalogValidationError):
        if invalid_step == "nested":
            profile = load_starter_catalog().profile("generic-at")
            replace(profile, commands=(*profile.commands, nested, sequence))
        else:
            profile_with(sequence)
    assert calls == []


def test_sequence_rejects_nonfinal_or_conditioned_secret_step_before_io() -> None:
    sequence = reviewed_sequence(
        SequenceStep("unlock-sim", expected_contains="OK"),
        SequenceStep("attention"),
    )
    calls: list[str] = []

    with pytest.raises(ValueError):
        SequenceRunner(
            lambda command, values, timeout: calls.append(command.id) or exchange()
        ).run(sequence, profile_with(sequence), {"pin": "1234"}, confirmed=True)
    assert calls == []


@pytest.mark.parametrize(
    "first_exchange",
    [exchange(final=b"ERROR"), exchange(b"different", final=b"OK")],
)
def test_sequence_stops_on_failed_final_or_missing_expected_evidence(
    first_exchange: AtExchange,
) -> None:
    sequence = reviewed_sequence(
        SequenceStep("attention", expected_contains="expected"),
        SequenceStep("identity"),
    )
    calls: list[str] = []

    result = SequenceRunner(
        lambda command, values, timeout: calls.append(command.id) or first_exchange
    ).run(sequence, profile_with(sequence), {}, confirmed=True)

    assert result.outcome is MaintenanceOutcome.INCONCLUSIVE
    assert calls == ["attention"]


def test_sequence_clamps_step_timeout_to_total_budget_without_retry() -> None:
    sequence = reviewed_sequence(
        SequenceStep("attention", timeout_seconds=5), SequenceStep("identity")
    )
    now = [0.0]
    calls: list[tuple[str, float]] = []

    def execute(command: CatalogCommand, values: dict[str, str], timeout: float):
        calls.append((command.id, timeout))
        now[0] += 1.0
        return exchange()

    result = SequenceRunner(execute, clock=lambda: now[0]).run(
        sequence, profile_with(sequence), {}, confirmed=True, total_timeout=1.0
    )

    assert result.outcome is MaintenanceOutcome.INCONCLUSIVE
    assert calls == [("attention", 1.0)]

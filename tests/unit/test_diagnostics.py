from dataclasses import replace

import pytest

from modem_controller.catalog.models import (
    CatalogCommand,
    DeviceProfile,
    VerificationStatus,
    load_starter_catalog,
)
from modem_controller.protocol.at_session import AtExchange, ExchangeOutcome
from modem_controller.workflows.diagnostics import DiagnosticRunner, DiagnosticState


def exchange(
    *lines: bytes,
    final: bytes | None = b"OK",
    outcome: ExchangeOutcome = ExchangeOutcome.COMPLETED,
) -> AtExchange:
    return AtExchange(b"", 0, 1, (), tuple(lines), (), (), False, outcome, final)


def generic_profile() -> DeviceProfile:
    return load_starter_catalog().profile("generic-at")


def diagnostic_profile(*commands: CatalogCommand) -> DeviceProfile:
    return replace(generic_profile(), commands=commands)


def result_for(results: tuple, command_id: str):
    return next(result for result in results if result.command_id == command_id)


def test_diagnostics_execute_only_allowlisted_commands_and_skip_after_sim_pin() -> None:
    profile = generic_profile()
    sent: list[str] = []

    def execute(command: CatalogCommand) -> AtExchange:
        sent.append(command.id)
        return exchange(b"+CPIN: SIM PIN") if command.id == "sim-status" else exchange()

    results = DiagnosticRunner(execute).run(profile)

    assert sent == [
        "attention",
        "identity",
        "sim-status",
        "registration-status",
        "signal-quality",
        "serial-baud-rate",
    ]
    assert "unlock-sim" not in sent
    assert result_for(results, "sim-status").state is DiagnosticState.ATTENTION
    assert result_for(results, "operator").state is DiagnosticState.SKIPPED
    assert result_for(results, "sms-storage").state is DiagnosticState.SKIPPED


@pytest.mark.parametrize(
    ("command_id", "payload", "reply", "expected_state"),
    [
        ("signal-quality", "AT+CSQ", b"+CSQ: 18,2", DiagnosticState.OK),
        ("signal-quality", "AT+CSQ", b"+CSQ: 99,99", DiagnosticState.UNKNOWN),
        ("registration-status", "AT+CREG?", b"+CREG: 0,0", DiagnosticState.ATTENTION),
        ("registration-status", "AT+CREG?", b"+CREG: 0,1", DiagnosticState.OK),
        ("registration-status", "AT+CREG?", b"+CREG: 0,2", DiagnosticState.ATTENTION),
        ("registration-status", "AT+CREG?", b"+CREG: 0,5", DiagnosticState.OK),
        ("eps-registration", "AT+CEREG?", b"+CEREG: 0,2", DiagnosticState.ATTENTION),
        ("packet-registration", "AT+CGREG?", b"+CGREG: 0,1", DiagnosticState.OK),
    ],
)
def test_diagnostics_interpret_each_measurement_without_substring_guesses(
    command_id: str,
    payload: str,
    reply: bytes,
    expected_state: DiagnosticState,
) -> None:
    registration = generic_profile().command("registration-status")
    command = replace(registration, id=command_id, payload=payload)
    results = DiagnosticRunner(lambda _: exchange(reply)).run(
        diagnostic_profile(command)
    )

    result = result_for(results, command_id)
    assert result.state is expected_state
    assert result.evidence == (reply, b"OK")
    assert result.reason
    assert result.observed_at is not None


@pytest.mark.parametrize(
    ("reply", "final", "outcome", "expected_reason"),
    [
        (
            b"+CREG: malformed",
            b"OK",
            ExchangeOutcome.COMPLETED,
            "unrecognized_response",
        ),
        (b"", b"ERROR", ExchangeOutcome.COMPLETED, "modem_error"),
        (b"", b"+CME ERROR: 13", ExchangeOutcome.COMPLETED, "modem_error"),
        (b"", b"+CMS ERROR: 500", ExchangeOutcome.COMPLETED, "modem_error"),
        (b"", None, ExchangeOutcome.TIMED_OUT, "timeout"),
    ],
)
def test_diagnostics_keep_errors_and_timeouts_distinct(
    reply: bytes,
    final: bytes | None,
    outcome: ExchangeOutcome,
    expected_reason: str,
) -> None:
    command = generic_profile().command("registration-status")
    lines = (reply,) if reply else ()
    results = DiagnosticRunner(
        lambda _: exchange(*lines, final=final, outcome=outcome)
    ).run(diagnostic_profile(command))

    result = result_for(results, command.id)
    assert result.state is DiagnosticState.UNKNOWN
    assert result.reason == expected_reason


def test_diagnostics_mark_catalog_unavailable_commands_unsupported_without_io() -> None:
    base = generic_profile().command("registration-status")
    unavailable = replace(base, id="eps-registration", payload="AT+CEREG?")
    unavailable = replace(unavailable, verification=VerificationStatus.UNSUPPORTED)
    sent: list[str] = []

    results = DiagnosticRunner(lambda command: sent.append(command.id)).run(
        diagnostic_profile(unavailable)
    )

    assert sent == []
    result = result_for(results, unavailable.id)
    assert result.state is DiagnosticState.UNSUPPORTED
    assert result.reason


@pytest.mark.parametrize("sim_reply", [b"+CPIN: SIM PIN", b"+CPIN: NOT INSERTED"])
def test_diagnostics_stop_sim_dependent_queries_for_locked_or_missing_sim(
    sim_reply: bytes,
) -> None:
    profile = generic_profile()
    sent: list[str] = []

    def execute(command: CatalogCommand) -> AtExchange:
        sent.append(command.id)
        return exchange(sim_reply) if command.id == "sim-status" else exchange()

    results = DiagnosticRunner(execute).run(profile)

    assert result_for(results, "sim-status").state is DiagnosticState.ATTENTION
    assert result_for(results, "operator").state is DiagnosticState.SKIPPED
    assert result_for(results, "sms-storage").state is DiagnosticState.SKIPPED
    assert "operator" not in sent
    assert "sms-storage" not in sent


def test_diagnostics_preserve_partial_results_and_skip_rest_after_disconnect() -> None:
    first, second, third = generic_profile().diagnostic_commands[:3]
    sent: list[str] = []

    def execute(command: CatalogCommand) -> AtExchange:
        sent.append(command.id)
        if command.id == second.id:
            return exchange(outcome=ExchangeOutcome.DISCONNECTED, final=None)
        return exchange()

    results = DiagnosticRunner(execute).run(diagnostic_profile(first, second, third))

    assert sent == [first.id, second.id]
    assert result_for(results, first.id).state is DiagnosticState.OK
    assert result_for(results, second.id).state is DiagnosticState.UNKNOWN
    assert result_for(results, second.id).reason == "disconnected"
    assert result_for(results, third.id).state is DiagnosticState.SKIPPED


def test_diagnostics_enforce_one_total_run_budget_with_fake_clock() -> None:
    commands = generic_profile().diagnostic_commands[:3]
    now = [0.0]
    sent: list[str] = []

    def clock() -> float:
        return now[0]

    def execute(command: CatalogCommand) -> AtExchange:
        sent.append(command.id)
        now[0] += 2.0
        return exchange()

    results = DiagnosticRunner(execute, clock=clock, total_timeout=1.0).run(
        diagnostic_profile(*commands)
    )

    assert sent == [commands[0].id]
    assert result_for(results, commands[0].id).state is DiagnosticState.OK
    assert [result.state for result in results[1:]] == [
        DiagnosticState.SKIPPED,
        DiagnosticState.SKIPPED,
    ]
    assert all(result.reason for result in results[1:])


def test_diagnostics_clamp_query_deadline_and_cancel_remaining_work() -> None:
    calls = []
    stop = [False]

    def execute(command):
        calls.append(command)
        stop[0] = True
        return exchange()

    results = DiagnosticRunner(
        execute, cancelled=lambda: stop[0], clock=lambda: 0.0, total_timeout=0.25
    ).run(generic_profile())
    assert len(calls) == 1
    assert calls[0].timeout_seconds == 0.25
    assert all(item.reason == "cancelled" for item in results[1:])


def test_diagnostics_reject_mislabeled_reset_and_do_not_reuse_sim_state() -> None:
    base = generic_profile().command("attention")
    reset = replace(base, payload="AT&F")
    assert (
        DiagnosticRunner(lambda _: pytest.fail("must not send"))
        .run(diagnostic_profile(reset))[0]
        .state
        is DiagnosticState.UNSUPPORTED
    )
    sim = generic_profile().command("sim-status")
    states = iter((b"+CPIN: SIM PIN", b"+CPIN: READY"))
    runner = DiagnosticRunner(lambda _: exchange(next(states)))
    assert runner.run(diagnostic_profile(sim))[0].state is DiagnosticState.ATTENTION
    assert runner.run(diagnostic_profile(sim))[0].state is DiagnosticState.OK

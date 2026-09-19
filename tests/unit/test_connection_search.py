import pytest

from modem_controller.protocol.at_session import AtExchange, ExchangeOutcome
from modem_controller.transport.serial_port import FlowControl, Parity, SerialSettings
from modem_controller.workflows.connection_search import (
    ConnectionSearchRunner,
    SearchCandidate,
    SearchOutcome,
    SearchPhase,
)


def exchange(
    command: bytes,
    *,
    outcome: ExchangeOutcome = ExchangeOutcome.COMPLETED,
    final: bytes | None = b"OK",
) -> AtExchange:
    return AtExchange(command, 0, 1, (), (), (), (), False, outcome, final)


def test_quick_search_sends_only_repeated_at_and_allows_explicit_use_save() -> None:
    sent: list[tuple[int, bytes]] = []
    applied: list[int] = []
    saved: list[int] = []

    def probe(settings, command):
        sent.append((settings.baud_rate, command))
        return exchange(command)

    result = ConnectionSearchRunner(probe).run(
        ConnectionSearchRunner.quick_candidates("COM4")
    )

    assert [command for _, command in sent] == [b"AT\r", b"AT\r"]
    assert result.selected is not None
    assert result.selected.settings.baud_rate == 9600
    ConnectionSearchRunner.use(
        result, lambda settings: applied.append(settings.baud_rate)
    )
    ConnectionSearchRunner.save(
        result, lambda settings: saved.append(settings.baud_rate)
    )
    assert applied == [9600]
    assert saved == [9600]


def test_echo_or_stale_result_does_not_confirm_a_candidate() -> None:
    candidate = SearchCandidate(
        ConnectionSearchRunner.quick_candidates("COM4")[0].settings,
        SearchPhase.QUICK,
    )
    sent: list[bytes] = []

    def probe(settings, command):
        sent.append(command)
        return exchange(b"AT\r", final=None)

    result = ConnectionSearchRunner(probe).run((candidate,))

    assert result.selected is None
    assert result.attempts[0].outcome is SearchOutcome.INCONCLUSIVE
    assert sent == [b"AT\r"]


def test_cancel_before_probe_sends_nothing_and_cannot_be_used_or_saved() -> None:
    candidate = ConnectionSearchRunner.quick_candidates("COM4")[0]
    sent: list[bytes] = []
    runner = ConnectionSearchRunner(
        lambda settings, command: sent.append(command) or exchange(command),
        cancelled=lambda: True,
    )

    result = runner.run((candidate,))

    assert result.was_cancelled
    assert sent == []
    for action in (ConnectionSearchRunner.use, ConnectionSearchRunner.save):
        try:
            action(result, lambda settings: None)
        except ValueError:
            pass
        else:
            raise AssertionError("inconclusive results must not be applied or saved")


def test_disconnect_stops_search_without_trying_another_candidate() -> None:
    candidates = ConnectionSearchRunner.quick_candidates("COM4")[:2]
    calls = 0

    def probe(settings, command):
        nonlocal calls
        calls += 1
        return exchange(command, outcome=ExchangeOutcome.DISCONNECTED, final=None)

    result = ConnectionSearchRunner(probe).run(candidates)

    assert calls == 1
    assert result.attempts[0].outcome is SearchOutcome.DISCONNECTED


def test_quick_candidates_try_preferred_settings_first_without_duplicates() -> None:
    preferred = SerialSettings("COM4", baud_rate=38_400, parity=Parity.EVEN)
    base = SerialSettings("COM4", baud_rate=9_600, parity=Parity.EVEN)

    candidates = ConnectionSearchRunner.quick_candidates(
        "COM4", preferred=(preferred, base, preferred), base=base
    )

    assert [candidate.settings.baud_rate for candidate in candidates] == [
        38_400,
        9_600,
        19_200,
        57_600,
        115_200,
    ]
    assert all(candidate.phase is SearchPhase.QUICK for candidate in candidates)
    assert all(candidate.settings.parity is Parity.EVEN for candidate in candidates)


def test_extended_candidates_cover_combinations_and_limit_search() -> None:
    base = SerialSettings("COM4")

    candidates = ConnectionSearchRunner.extended_candidates(
        base,
        baud_rates=(9_600, 19_200),
        data_bits=(7, 8),
        parities=(Parity.NONE, Parity.EVEN),
        stop_bits=(1,),
        flow_controls=(FlowControl.NONE,),
    )

    assert len(candidates) == 8
    assert {candidate.phase for candidate in candidates} == {SearchPhase.EXTENDED}
    assert {
        (
            candidate.settings.baud_rate,
            candidate.settings.data_bits,
            candidate.settings.parity,
        )
        for candidate in candidates
    } == {
        (baud_rate, data_bits, parity)
        for baud_rate in (9_600, 19_200)
        for data_bits in (7, 8)
        for parity in (Parity.NONE, Parity.EVEN)
    }
    with pytest.raises(ValueError):
        ConnectionSearchRunner.extended_candidates(
            base,
            baud_rates=(9_600, 19_200, 38_400, 57_600, 115_200),
            data_bits=(5, 6, 7, 8),
            parities=tuple(Parity),
            stop_bits=(1, 1.5, 2),
            flow_controls=tuple(FlowControl),
        )


@pytest.mark.parametrize("terminator", [b"\n", b"\r\n"])
def test_search_uses_the_selected_terminator_for_every_probe(terminator: bytes) -> None:
    candidate = ConnectionSearchRunner.quick_candidates("COM4")[0]
    sent: list[bytes] = []

    result = ConnectionSearchRunner(
        lambda settings, command: sent.append(command) or exchange(command),
        terminator=terminator,
    ).run((candidate,))

    assert result.selected == candidate
    assert sent == [b"AT" + terminator, b"AT" + terminator]


def test_total_budget_clamps_response_timeout_and_prevents_more_io() -> None:
    candidates = ConnectionSearchRunner.quick_candidates("COM4")[:2]
    now = [0.0]
    observed: list[float] = []
    progress: list[tuple[int, int, int]] = []

    def probe(settings: SerialSettings, command: bytes) -> AtExchange:
        observed.append(settings.response_timeout)
        now[0] += 1.0
        return exchange(command)

    result = ConnectionSearchRunner(
        probe,
        clock=lambda: now[0],
        total_timeout=1.0,
        progress=lambda index, total, candidate: progress.append(
            (index, total, candidate.settings.baud_rate)
        ),
    ).run(candidates)

    assert result.selected is None
    assert observed == [1.0]
    assert progress == [(1, 2, candidates[0].settings.baud_rate)]


def test_cancellation_after_a_probe_returns_cancelled_without_another_probe() -> None:
    candidate = ConnectionSearchRunner.quick_candidates("COM4")[0]
    sent: list[bytes] = []

    result = ConnectionSearchRunner(
        lambda settings, command: sent.append(command) or exchange(command),
        cancelled=lambda: bool(sent),
    ).run((candidate,))

    assert sent == [b"AT\r"]
    assert result.was_cancelled
    assert result.attempts[-1].outcome is SearchOutcome.CANCELLED

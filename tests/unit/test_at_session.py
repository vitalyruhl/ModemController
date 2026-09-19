from __future__ import annotations

from collections import deque
from datetime import timedelta

import pytest

from modem_controller.protocol.at_session import (
    AtSession,
    ExchangeOutcome,
    PromptAlreadySubmittedError,
    PromptNotReceivedError,
    SessionBusyError,
    SessionDisconnectedError,
    SessionResynchronizationRequiredError,
    SessionState,
)


class FakeClock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


class FakeTransport:
    def __init__(self) -> None:
        self.is_open = True
        self.writes: list[bytes] = []
        self.incoming: deque[bytes] = deque()

    def read_available(self, max_bytes: int = 4096) -> bytes:
        if not self.is_open:
            raise RuntimeError("port closed")
        if not self.incoming:
            return b""
        return self.incoming.popleft()

    def write(self, data: bytes | bytearray | memoryview) -> int:
        if not self.is_open:
            raise RuntimeError("port closed")
        payload = bytes(data)
        self.writes.append(payload)
        return len(payload)


def make_session() -> tuple[AtSession, FakeTransport, FakeClock]:
    clock = FakeClock()
    transport = FakeTransport()
    return (
        AtSession(
            transport,
            clock=clock,
            resynchronization_quiet_period=1.0,
        ),
        transport,
        clock,
    )


def test_pin_session_snapshots_do_not_retain_secret_echo_or_command() -> None:
    session, transport, _ = make_session()
    started = session.start(b"AT+CPIN=1234\r", timeout=timedelta(seconds=1))
    assert b"1234" not in repr(started).encode()
    transport.incoming.extend((b"AT+CP", b"IN=1234\r\n", b"OK\r\n"))
    session.poll()
    session.poll()
    result = session.poll()
    assert result.final_result == b"OK"
    assert b"1234" not in repr(session.drain_completed()).encode()
    assert result.response_lines == result.command_echoes == ()


def test_exchange_handles_echo_response_urc_and_standalone_final_result() -> None:
    session, transport, _ = make_session()
    session.start(b"AT+CSQ\r", timeout=timedelta(seconds=2))
    transport.incoming.append(b'AT+CSQ\r\n+CMTI: "SM",1\r\n+CSQ: 20,99\r\nOK\r\n')

    result = session.poll()

    assert result is not None
    assert result.outcome is ExchangeOutcome.COMPLETED
    assert result.final_result == b"OK"
    assert result.command_echoes == (b"AT+CSQ",)
    assert result.unsolicited == (b'+CMTI: "SM",1',)
    assert result.response_lines == (b"+CSQ: 20,99",)
    assert transport.writes == [b"AT+CSQ\r"]


def test_embedded_ok_text_does_not_complete_an_exchange() -> None:
    session, transport, _ = make_session()
    session.start(b"AT+INFO\r", timeout=timedelta(seconds=2))
    transport.incoming.append(b"value contains OK text\r\n")

    assert session.poll() is None
    assert session.state is SessionState.AWAITING_RESPONSE

    transport.incoming.append(b"OK\r\n")
    assert session.poll() is not None


@pytest.mark.parametrize("result", [b"+CME ERROR: 13", b"+CMS ERROR: 500"])
def test_extended_error_results_complete_an_exchange(result: bytes) -> None:
    session, transport, _ = make_session()
    session.start(b"AT+TEST\r", timeout=timedelta(seconds=2))
    transport.incoming.append(result + b"\r\n")

    completed = session.poll()

    assert completed is not None
    assert completed.outcome is ExchangeOutcome.COMPLETED
    assert completed.final_result == result


def test_timeout_requires_quiet_resynchronization_and_discards_late_reply() -> None:
    session, transport, clock = make_session()
    session.start(b"AT\r", timeout=timedelta(seconds=1))
    clock.advance(1)

    timed_out = session.poll()

    assert timed_out is not None
    assert timed_out.outcome is ExchangeOutcome.TIMED_OUT
    with pytest.raises(SessionResynchronizationRequiredError):
        session.start(b"ATI\r", timeout=timedelta(seconds=1))

    transport.incoming.append(b"OK\r\n")
    assert not session.resynchronize()
    assert [frame.data for frame in session.drain_discarded_frames()] == [b"OK"]
    clock.advance(1)
    assert session.resynchronize()

    session.start(b"ATI\r", timeout=timedelta(seconds=1))
    transport.incoming.append(b"ATI\r\nOK\r\n")
    completed = session.poll()
    assert completed is not None
    assert completed.command == b"ATI\r"
    assert completed.final_result == b"OK"


def test_cancel_requires_resynchronization_before_reuse() -> None:
    session, _, clock = make_session()
    session.start(b"AT\r", timeout=timedelta(seconds=1))

    cancelled = session.cancel()

    assert cancelled.outcome is ExchangeOutcome.CANCELLED
    with pytest.raises(SessionResynchronizationRequiredError):
        session.start(b"ATI\r", timeout=timedelta(seconds=1))
    clock.advance(1)
    assert session.resynchronize()


def test_session_rejects_interleaving_and_reports_disconnect() -> None:
    session, transport, _ = make_session()
    session.start(b"AT\r", timeout=timedelta(seconds=1))

    with pytest.raises(SessionBusyError):
        session.start(b"ATI\r", timeout=timedelta(seconds=1))

    transport.is_open = False
    disconnected = session.poll()

    assert disconnected is not None
    assert disconnected.outcome is ExchangeOutcome.DISCONNECTED
    with pytest.raises(SessionDisconnectedError):
        session.start(b"AT\r", timeout=timedelta(seconds=1))


def test_prompt_is_exposed_without_completing_the_exchange() -> None:
    session, transport, _ = make_session()
    session.start(b'AT+CMGS="123"\r', timeout=timedelta(seconds=2))
    transport.incoming.append(b"> ")

    assert session.poll() is None
    assert session.active_exchange is not None
    assert session.active_exchange.prompt_received


def test_prompt_payload_is_sent_once_and_requires_a_received_prompt() -> None:
    session, transport, _ = make_session()
    session.start(b'AT+CMGS="123"\r', timeout=timedelta(seconds=2))

    with pytest.raises(PromptNotReceivedError):
        session.submit_prompt_payload(b"text\x1a")

    transport.incoming.append(b"> ")
    assert session.poll() is None
    session.submit_prompt_payload(b"text\x1a")

    with pytest.raises(PromptAlreadySubmittedError):
        session.submit_prompt_payload(b"another\x1a")
    assert transport.writes == [b'AT+CMGS="123"\r', b"text\x1a"]

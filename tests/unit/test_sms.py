from collections import deque
from datetime import timedelta

import pytest

from modem_controller.protocol.at_session import AtSession
from modem_controller.workflows.sms import (
    SmsConfirmationRequiredError,
    SmsInspector,
    SmsMessage,
    SmsOutcome,
    SmsSendWorkflow,
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
        self.incoming: deque[bytes] = deque()
        self.writes: list[bytes] = []
        self.sensitive_writes: list[bytes] = []

    def read_available(self, max_bytes: int = 4096) -> bytes:
        return self.incoming.popleft() if self.incoming else b""

    def write(self, data: bytes) -> int:
        self.writes.append(data)
        return len(data)

    def write_sensitive(self, data: bytes) -> int:
        self.sensitive_writes.append(data)
        return len(data)


def make_workflow() -> tuple[SmsSendWorkflow, FakeTransport, FakeClock]:
    clock = FakeClock()
    transport = FakeTransport()
    session = AtSession(transport, clock=clock)
    return (
        SmsSendWorkflow(session, completion_timeout=timedelta(seconds=30)),
        transport,
        clock,
    )


@pytest.mark.parametrize(
    "responses",
    [
        (b"+CPIN: SIM PIN\r\nOK\r\n",),
        (b"+CME ERROR: 10\r\n",),
        (b"+CPIN: READY\r\nOK\r\n", b"+CMGF: 0\r\nOK\r\n"),
        (b"+CPIN: READY\r\nOK\r\n", b"+CMGF: 1\r\nOK\r\n", b'+CSCS: "UCS2"\r\nOK\r\n'),
    ],
)
def test_preflight_failure_never_sends_cmgs_or_body(responses):
    workflow, transport, _ = make_workflow()
    workflow.begin(SmsMessage("123456", "Hello"), confirmed=True)
    result = None
    for response in responses:
        transport.incoming.append(response)
        result = workflow.poll()
    assert result is not None
    assert result.outcome is SmsOutcome.NOT_READY
    assert not transport.sensitive_writes
    assert all(b"CMGS=" not in command for command in transport.writes)


def test_unsupported_profile_and_delete_control_never_submit():
    workflow, transport, _ = make_workflow()
    result = workflow.begin(
        SmsMessage("123456", "Hello"), confirmed=True, profile_supported=False
    )
    assert result.outcome is SmsOutcome.NOT_READY
    assert transport.writes == transport.sensitive_writes == []
    with pytest.raises(ValueError, match="printable ASCII"):
        SmsMessage("123456", "Hello\x7f")


def test_plain_ok_without_message_reference_never_claims_submission():
    workflow, transport, _ = make_workflow()
    begin_ready(workflow, transport, SmsMessage("123456", "Hello"))
    transport.incoming.append(b"> ")
    assert workflow.poll() is None
    transport.incoming.append(b"\r\nOK\r\n")
    result = workflow.poll()
    assert result.outcome is SmsOutcome.INDETERMINATE


def begin_ready(workflow, transport, message):
    assert workflow.begin(message, confirmed=True) is None
    for response in (
        b"+CPIN: READY\r\nOK\r\n",
        b"+CMGF: 1\r\nOK\r\n",
        b'+CSCS: "IRA"\r\nOK\r\n',
    ):
        transport.incoming.append(response)
        assert workflow.poll() is None


def test_text_mode_sms_sends_exact_ctrl_z_after_a_split_prompt() -> None:
    workflow, transport, _ = make_workflow()

    begin_ready(workflow, transport, SmsMessage("+491234567", "Status OK"))
    transport.incoming.extend((b">", b" "))
    assert workflow.poll() is None
    assert transport.sensitive_writes == [b'AT+CMGS="+491234567"\r', b"Status OK\x1a"]
    assert transport.writes == [b"AT+CPIN?\r", b"AT+CMGF?\r", b"AT+CSCS?\r"]

    assert workflow.poll() is None
    transport.incoming.append(b"+CMGS: 7\r\nOK\r\n")
    result = workflow.poll()

    assert result is not None
    assert result.outcome is SmsOutcome.SENT
    assert result.evidence == (b"+CMGS: 7", b"OK")
    assert "Delivery to the recipient is not confirmed" in result.next_action


def test_cancel_before_and_after_prompt_submission_never_adds_escape_or_retries() -> (
    None
):
    workflow, transport, _ = make_workflow()
    cancelled = workflow.begin(SmsMessage("123456", "Hello"), confirmed=False)
    assert cancelled is not None
    assert cancelled.outcome is SmsOutcome.CANCELLED
    assert transport.sensitive_writes == []

    begin_ready(workflow, transport, SmsMessage("123456", "Hello"))
    cancelled = workflow.cancel()
    assert cancelled.outcome is SmsOutcome.CANCELLED
    assert transport.sensitive_writes == [b'AT+CMGS="123456"\r']

    workflow, transport, _ = make_workflow()
    begin_ready(workflow, transport, SmsMessage("123456", "Hello"))
    transport.incoming.append(b"> ")
    assert workflow.poll() is None
    cancelled = workflow.cancel()
    assert cancelled.outcome is SmsOutcome.INDETERMINATE
    assert transport.sensitive_writes == [b'AT+CMGS="123456"\r', b"Hello\x1a"]


def test_timeout_and_unsupported_body_are_not_sent_or_retried() -> None:
    workflow, transport, clock = make_workflow()
    with pytest.raises(ValueError, match="printable ASCII"):
        SmsMessage("123456", "Gruesse \u20ac")

    begin_ready(workflow, transport, SmsMessage("123456", "Hello"))
    clock.advance(30)
    result = workflow.poll()

    assert result is not None
    assert result.outcome is SmsOutcome.INDETERMINATE
    assert transport.sensitive_writes == [b'AT+CMGS="123456"\r']


def test_sms_status_and_read_are_explicit_without_deletion() -> None:
    assert SmsInspector.status_commands() == (
        b"AT+CMGF?\r",
        b"AT+CSCS?\r",
        b"AT+CPMS?\r",
    )
    with pytest.raises(SmsConfirmationRequiredError):
        SmsInspector.read_message(1, confirmed=False)
    assert SmsInspector.read_message(1, confirmed=True) == b"AT+CMGR=1\r"


def test_cms_error_and_disconnect_leave_delivery_indeterminate() -> None:
    workflow, transport, _ = make_workflow()
    begin_ready(workflow, transport, SmsMessage("123456", "Hello"))
    transport.incoming.append(b"> ")
    assert workflow.poll() is None
    transport.incoming.append(b"+CMS ERROR: 500\r\n")

    result = workflow.poll()

    assert result is not None
    assert result.outcome is SmsOutcome.INDETERMINATE
    assert result.evidence == (b"+CMS ERROR: 500",)

    workflow, transport, _ = make_workflow()
    begin_ready(workflow, transport, SmsMessage("123456", "Hello"))
    transport.is_open = False
    result = workflow.poll()

    assert result is not None
    assert result.outcome is SmsOutcome.INDETERMINATE
    assert transport.sensitive_writes == [b'AT+CMGS="123456"\r']

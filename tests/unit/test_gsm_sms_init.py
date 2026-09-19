"""Contract tests for the explicitly destructive GSM SMS initialization sequence."""

import pytest

from modem_controller.catalog.models import (
    CommandKind,
    RiskLevel,
    load_starter_catalog,
)
from modem_controller.protocol.at_session import AtExchange, ExchangeOutcome
from modem_controller.workflows.maintenance import (
    MaintenanceOutcome,
    SequenceRunner,
)

STEP_IDS = (
    "restore-defaults",
    "registration-notifications",
    "extended-ring",
    "caller-id",
    "sms-text-mode",
    "sms-notification-enable",
    "sms-storage-mt",
    "packet-detach",
    "pdp-context-clear",
    "save-profile",
)
STEP_PAYLOADS = (
    b"AT&F",
    b"AT+CREG=1",
    b"AT+CRC=1",
    b"AT+CLIP=1",
    b"AT+CMGF=1",
    b"AT+CNMI=1,1",
    b'AT+CPMS="MT"',
    b"AT+CGATT=0",
    b'AT+CGDCONT=1,"IP",""',
    b"AT&W",
)


def completed_exchange() -> AtExchange:
    return AtExchange(
        b"", 0, 1, (), (), (), (), False, ExchangeOutcome.COMPLETED, b"OK"
    )


def gsm_sms_init():
    profile = load_starter_catalog().profile("generic-at")
    return profile, profile.command("gsm-sms-init")


def test_gsm_sms_initialization_is_the_reviewed_destructive_ten_step_sequence():
    profile, sequence = gsm_sms_init()

    assert sequence.kind is CommandKind.SEQUENCE
    assert sequence.risk is RiskLevel.DESTRUCTIVE
    assert sequence.is_visible
    assert sequence.direct_send is False
    assert tuple(step.command_id for step in sequence.sequence_steps) == STEP_IDS
    assert tuple(profile.command(step_id).render() for step_id in STEP_IDS) == (
        STEP_PAYLOADS
    )
    for step_id in STEP_IDS:
        command = profile.command(step_id)
        assert command.risk in {RiskLevel.STATE_CHANGING, RiskLevel.DESTRUCTIVE}
        assert command.direct_send is False
        assert not command.uses_direct_send
        assert command not in profile.diagnostic_commands


def test_gsm_sms_initialization_sends_exactly_one_cr_per_step_through_adapter():
    profile, sequence = gsm_sms_init()
    sent: list[bytes] = []

    def adapter(command, values, timeout):
        assert values == {}
        assert timeout > 0
        sent.append(command.render(values) + b"\r")
        return completed_exchange()

    result = SequenceRunner(adapter).run(sequence, profile, {}, confirmed=True)

    assert result.outcome is MaintenanceOutcome.COMPLETED
    assert sent == [payload + b"\r" for payload in STEP_PAYLOADS]


def test_gsm_sms_initialization_requires_confirmation_before_any_adapter_call():
    profile, sequence = gsm_sms_init()
    sent: list[bytes] = []

    result = SequenceRunner(
        lambda command, values, timeout: sent.append(command.render(values))
        or completed_exchange()
    ).run(sequence, profile, {}, confirmed=False)

    assert result.outcome is MaintenanceOutcome.CANCELLED
    assert sent == []


@pytest.mark.parametrize("failed_index", range(len(STEP_IDS)))
def test_gsm_sms_initialization_stops_at_each_error_without_sending_later_steps(
    failed_index: int,
):
    profile, sequence = gsm_sms_init()
    sent: list[str] = []

    def adapter(command, values, timeout):
        sent.append(command.id)
        final = b"ERROR" if len(sent) - 1 == failed_index else b"OK"
        return AtExchange(
            b"", 0, 1, (), (), (), (), False, ExchangeOutcome.COMPLETED, final
        )

    result = SequenceRunner(adapter).run(sequence, profile, {}, confirmed=True)

    assert result.outcome is MaintenanceOutcome.INCONCLUSIVE
    assert sent == list(STEP_IDS[: failed_index + 1])
    assert f"step {failed_index + 1} ({STEP_IDS[failed_index]})" in result.next_action
    assert "ERROR" in result.next_action


def test_initialization_preview_shows_exact_commands_and_cancel_sends_nothing(
    qtbot, monkeypatch
):
    from unittest.mock import Mock

    from PySide6.QtWidgets import QMessageBox

    from modem_controller.ui.main_window import MainWindow

    window = MainWindow(port_provider=lambda: [])
    qtbot.addWidget(window)
    window.set_preset_execution_enabled(True)
    controller = Mock()
    monkeypatch.setattr(window, "_controller", lambda: controller)
    previews = []
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda parent, title, text, *args: previews.append(text) or QMessageBox.No,
    )
    profile, sequence = gsm_sms_init()
    window._request_preset(sequence)
    assert len(previews) == 1
    assert all(payload.decode() in previews[0] for payload in STEP_PAYLOADS)
    assert "factory settings" in previews[0]
    assert not controller.mock_calls

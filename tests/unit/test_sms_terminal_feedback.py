"""Guided SMS traffic and failures must be visible in the shared terminal."""

import pytest
from test_connection_controller import FakePort
from test_sms import make_workflow

from modem_controller.transport.serial_port import SerialIOError, SerialSettings
from modem_controller.ui.connection_controller import SerialConnectionWorker
from modem_controller.ui.main_window import MainWindow
from modem_controller.ui.session_log import LogMode
from modem_controller.workflows.sms import SmsMessage, SmsOutcome


def test_basic_sms_accepts_gsm_without_changing_character_set():
    workflow, transport, _ = make_workflow()
    workflow.begin(SmsMessage("123456", "test sms"), confirmed=True)
    for response in (
        b"+CPIN: READY\r\nOK\r\n",
        b"+CMGF: 1\r\nOK\r\n",
        b'+CSCS: "GSM"\r\nOK\r\n',
        b"> ",
    ):
        transport.incoming.append(response)
        assert workflow.poll() is None
    assert transport.sensitive_writes == [b'AT+CMGS="123456"\r', b"test sms\x1a"]
    assert transport.writes == [b"AT+CPIN?\r", b"AT+CMGF?\r", b"AT+CSCS?\r"]
    transport.incoming.append(b"+CMGS: 7\r\nOK\r\n")
    assert workflow.poll().outcome is SmsOutcome.SENT


def test_sms_preflight_failure_is_visible_in_terminal_dialog_and_log(
    qtbot, monkeypatch, tmp_path
):
    window = MainWindow(port_provider=lambda: [])
    qtbot.addWidget(window)
    port = FakePort()
    port.open(SerialSettings(port="FAKE"))
    port.received.extend(
        (
            b"+CPIN: READY\r\nOK\r\n",
            b"+CMGF: 1\r\nOK\r\n",
            b'+CSCS: "UCS2"\r\nOK\r\n',
        )
    )
    worker = SerialConnectionWorker(lambda: port)
    worker._port = port
    monkeypatch.setattr(window, "_controller", lambda: worker)
    window._bind_connection_controller(worker)
    window.set_preset_execution_enabled(True)
    logfile = tmp_path / "session.log"
    window._session_log.configure(logfile, enabled=True, mode=LogMode.NORMAL)
    window._send_sms("123456", "test sms")
    text = window.terminal.transcript.toPlainText()
    assert "AT+CPIN?" in text
    assert "AT+CSCS?" in text
    assert '+CSCS: "UCS2"' in text
    assert "No SMS submitted" in text
    assert "No SMS submitted" in window.sms_dialog.validation_message.text()
    assert "No SMS submitted" in logfile.read_text(encoding="utf-8")
    assert all(b"CMGS=" not in payload for payload, _ in port.writes)


def test_manual_send_is_not_duplicated_by_transmission_logging(qtbot):
    window = MainWindow(port_provider=lambda: [])
    qtbot.addWidget(window)
    window.terminal.append_transmitted(b"AT\r")
    window._log_transmitted(b"AT\r")
    assert window.terminal.transcript.toPlainText().count("TX  AT") == 1


def test_gsm_ambiguous_ascii_characters_are_not_submitted():
    workflow, transport, _ = make_workflow()
    workflow.begin(SmsMessage("123456", "test @"), confirmed=True)
    result = None
    for response in (
        b"+CPIN: READY\r\nOK\r\n",
        b"+CMGF: 1\r\nOK\r\n",
        b'+CSCS: "GSM"\r\nOK\r\n',
    ):
        transport.incoming.append(response)
        result = workflow.poll()
    assert result.outcome is SmsOutcome.NOT_READY
    assert not transport.sensitive_writes


@pytest.mark.parametrize("failed_write", [1, 2])
def test_sms_submission_write_failure_never_retries_and_releases_worker(
    qtbot, failed_write
):
    port = FakePort()
    port.open(SerialSettings(port="FAKE"))
    port.received.extend(
        (
            b"+CPIN: READY\r\nOK\r\n",
            b"+CMGF: 1\r\nOK\r\n",
            b'+CSCS: "GSM"\r\nOK\r\n',
            b"> ",
        )
    )
    sensitive_writes = []

    def write_sensitive(payload):
        sensitive_writes.append(payload)
        if len(sensitive_writes) == failed_write:
            raise SerialIOError("Synthetic SMS write failure")
        return len(payload)

    port.write_sensitive = write_sensitive
    worker = SerialConnectionWorker(lambda: port)
    worker._port = port
    results, finished, errors = [], [], []
    worker.sms_completed.connect(results.append)
    worker.workflow_finished.connect(lambda: finished.append(True))
    worker.error.connect(errors.append)
    worker.send_sms("123456", "test sms")
    assert results == [None]
    assert finished == [True]
    assert errors == ["Synthetic SMS write failure"]
    assert len(sensitive_writes) == failed_write
    assert not port.is_open


def test_confirmed_sms_shows_cmgs_body_and_acknowledgement(qtbot, monkeypatch):
    window = MainWindow(port_provider=lambda: [])
    qtbot.addWidget(window)
    port = FakePort()
    port.open(SerialSettings(port="FAKE"))
    port.received.extend(
        (
            b"+CPIN: READY\r\nOK\r\n",
            b"+CMGF: 1\r\nOK\r\n",
            b'+CSCS: "GSM"\r\nOK\r\n',
            b"> ",
            b"+CMGS: 7\r\nOK\r\n",
        )
    )
    worker = SerialConnectionWorker(lambda: port)
    worker._port = port
    monkeypatch.setattr(window, "_controller", lambda: worker)
    window._bind_connection_controller(worker)
    window.set_preset_execution_enabled(True)
    window._send_sms("123456", "test sms")
    text = window.terminal.transcript.toPlainText()
    assert 'AT+CMGS="123456"' in text
    assert "test sms" in text
    assert "+CMGS: 7" in text
    assert "Delivery to the recipient is not confirmed" in text
    assert "SMS: sent" in window.sms_dialog.validation_message.text()
    assert not window._workflow_active
    assert len(port.writes) == 5


@pytest.mark.parametrize("connected", [False, True])
def test_sms_port_failure_leaves_visible_result_and_releases_workflow(
    qtbot, monkeypatch, connected
):
    window = MainWindow(port_provider=lambda: [])
    qtbot.addWidget(window)
    port = FakePort()
    if connected:
        port.open(SerialSettings(port="FAKE"))

    def fail_write(payload):
        raise SerialIOError("Synthetic disconnected backend")

    port.write = fail_write
    worker = SerialConnectionWorker(lambda: port)
    worker._port = port if connected else None
    monkeypatch.setattr(window, "_controller", lambda: worker)
    window._bind_connection_controller(worker)
    window.set_preset_execution_enabled(True)
    window._send_sms("123456", "test sms")
    assert not window._workflow_active
    assert "failed" in window.sms_dialog.validation_message.text()
    assert not port.is_open

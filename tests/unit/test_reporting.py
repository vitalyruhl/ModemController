from datetime import UTC, datetime

import pytest

from modem_controller.transport.capture import CaptureDirection, CaptureRecord
from modem_controller.workflows.diagnostics import DiagnosticResult, DiagnosticState
from modem_controller.workflows.reporting import export_raw_capture, render_report


def test_report_redacts_every_field_and_preserves_gap_evidence():
    from modem_controller.transport.capture import CaptureSnapshot
    from modem_controller.workflows.reporting import report_text

    result = DiagnosticResult(
        "sms-read",
        DiagnosticState.UNKNOWN,
        (b"private message body",),
        "username=PrivateUser\nhttps://internal.invalid/info\nAT+CPIN=1234",
        reason="endpoint=http://private.invalid",
    )
    report = render_report(
        (result,),
        {"username": "Alice"},
        capture=CaptureSnapshot(dropped_records=1, sensitive_gaps=2),
    )
    text = report_text(report)
    for private in (
        "PrivateUser",
        "internal.invalid",
        "private.invalid",
        "1234",
        "Alice",
        "private message body",
    ):
        assert private not in text
    assert report["capture"]["incomplete"] is True
    assert report["capture"]["sensitive_gaps"] == 2
    assert report["app_version"]


def test_atomic_export_failure_preserves_previous_file(tmp_path, monkeypatch):
    from modem_controller.catalog import storage
    from modem_controller.catalog.storage import StorageError
    from modem_controller.workflows.reporting import save_report

    destination = tmp_path / "report.json"
    destination.write_text("previous")

    def fail(*args):
        raise OSError("disk full")

    monkeypatch.setattr(storage.os, "replace", fail)
    with pytest.raises(StorageError, match="disk full"):
        save_report(destination, render_report((), {}))
    assert destination.read_text() == "previous"
    assert list(tmp_path.iterdir()) == [destination]


def test_preview_and_cancelled_export_do_not_write(qtbot, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog, QMessageBox

    from modem_controller.transport.capture import CaptureSnapshot
    from modem_controller.ui.report_dialog import ReportDialog

    dialog = ReportDialog(render_report((), {}), CaptureSnapshot(), tmp_path)
    qtbot.addWidget(dialog)
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a: ("", ""))
    monkeypatch.setattr(QMessageBox, "warning", lambda *a: QMessageBox.No)
    dialog._export(False)
    dialog._raw()
    assert list(tmp_path.iterdir()) == []


def test_report_redacts_phone_numbers_and_paths() -> None:
    result = DiagnosticResult(
        "identity",
        DiagnosticState.OK,
        (b"IMEI 123456789012345 +491234567",),
        "Check C:\\Users\\Name",
    )
    report = render_report((result,), {"path": "C:\\Users\\Name", "port": "COM7"})
    assert "123456789012345" not in str(report)
    assert "C:\\Users\\Name" not in str(report)


def test_raw_export_requires_confirmation(tmp_path) -> None:
    record = CaptureRecord(
        datetime(2026, 9, 19, tzinfo=UTC), CaptureDirection.RECEIVED, b"AT\r"
    )
    with pytest.raises(PermissionError):
        export_raw_capture(tmp_path / "raw.bin", (record,), confirmed=False)
    export_raw_capture(tmp_path / "raw.bin", (record,), confirmed=True)
    assert (tmp_path / "raw.bin").read_bytes() == b"AT\r"

"""Qt button-return regression coverage for guided SMS confirmation dialogs."""

import pytest
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QMessageBox

from modem_controller.ui.sms_dialog import SmsDialog


def _click_modal_button(
    button: QMessageBox.StandardButton,
) -> tuple[list[bool], QTimer]:
    clicked: list[bool] = []

    def click() -> None:
        modal = QApplication.activeModalWidget()
        if isinstance(modal, QMessageBox):
            modal.button(button).click()
            clicked.append(True)

    def reject_failsafe() -> None:
        modal = QApplication.activeModalWidget()
        if isinstance(modal, QMessageBox):
            modal.reject()

    QTimer.singleShot(0, click)
    failsafe = QTimer()
    failsafe.setSingleShot(True)
    failsafe.timeout.connect(reject_failsafe)
    failsafe.start(1_000)
    return clicked, failsafe


@pytest.mark.parametrize("method_name", ["warning", "question"])
def test_real_static_confirmation_returns_standard_button_after_timer_click(
    qtbot, method_name
):
    clicked, failsafe = _click_modal_button(QMessageBox.Yes)

    answer = getattr(QMessageBox, method_name)(
        None,
        "Synthetic confirmation",
        "Synthetic message",
        QMessageBox.Yes | QMessageBox.No,
        QMessageBox.No,
    )
    failsafe.stop()

    assert clicked == [True]
    assert type(answer) is int
    assert answer == QMessageBox.Yes.value


def test_integer_yes_from_static_warning_emits_one_sms_request(qtbot, monkeypatch):
    dialog = SmsDialog()
    qtbot.addWidget(dialog)
    dialog.recipient.setText("123456")
    dialog.body.setPlainText("Synthetic status")
    requested = []
    dialog.send_requested.connect(
        lambda recipient, body: requested.append((recipient, body))
    )
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: QMessageBox.Yes.value)

    dialog._request_send()

    assert requested == [("123456", "Synthetic status")]


def test_integer_no_from_static_warning_does_not_emit_sms_request(qtbot, monkeypatch):
    dialog = SmsDialog()
    qtbot.addWidget(dialog)
    dialog.recipient.setText("123456")
    dialog.body.setPlainText("Synthetic status")
    requested = []
    dialog.send_requested.connect(lambda *values: requested.append(values))
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: QMessageBox.No.value)

    dialog._request_send()

    assert requested == []


def test_integer_confirmation_values_apply_to_read_requests(qtbot, monkeypatch):
    dialog = SmsDialog()
    qtbot.addWidget(dialog)
    dialog.index.setValue(17)
    requested = []
    dialog.read_requested.connect(requested.append)
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.Yes.value)

    dialog._request_read()

    assert requested == [17]

    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.No.value)
    dialog._request_read()
    assert requested == [17]


def test_invalid_recipient_sets_feedback_without_opening_confirmation_or_emitting(
    qtbot, monkeypatch
):
    dialog = SmsDialog()
    qtbot.addWidget(dialog)
    dialog.recipient.setText("invalid")
    dialog.body.setPlainText("Synthetic status")
    requested = []
    dialog.send_requested.connect(lambda *values: requested.append(values))
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda *args: (_ for _ in ()).throw(AssertionError("confirmation opened")),
    )

    dialog._request_send()

    assert requested == []
    assert dialog.validation_message.text()

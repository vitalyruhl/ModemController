"""Dialog for the deliberately limited text-mode SMS workflows."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from modem_controller.workflows.sms import SmsMessage


class SmsDialog(QDialog):
    """Collect explicit user intent for status, reading, and one-message sending."""

    status_requested = Signal()
    read_requested = Signal(int)
    send_requested = Signal(str, str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("smsDialog")
        self.setWindowTitle("SMS")
        self.setModal(False)

        self.recipient = QLineEdit(self)
        self.recipient.setObjectName("smsRecipient")
        self.body = QPlainTextEdit(self)
        self.body.setObjectName("smsBody")
        self.body.setMaximumBlockCount(8)
        self.index = QSpinBox(self)
        self.index.setRange(1, 999)
        self.status_button = QPushButton("Check status", self)
        self.read_button = QPushButton("Read message", self)
        self.send_button = QPushButton("Send message", self)
        self.validation_message = QLabel(self)
        self.validation_message.setWordWrap(True)
        self.availability_message = QLabel(self)
        self.availability_message.setWordWrap(True)

        self.status_button.clicked.connect(self.status_requested)
        self.read_button.clicked.connect(self._request_read)
        self.send_button.clicked.connect(self._request_send)

        form = QFormLayout()
        form.addRow("Recipient", self.recipient)
        form.addRow("Message", self.body)
        hint = QLabel(
            "Sending requires SIM READY, text mode and GSM or IRA. "
            "Use basic ASCII text; no automatic mode changes.",
            self,
        )
        hint.setWordWrap(True)
        form.addRow(hint)
        form.addRow("Message index", self.index)
        buttons = QHBoxLayout()
        buttons.addWidget(self.status_button)
        buttons.addWidget(self.read_button)
        buttons.addWidget(self.send_button)
        layout = QVBoxLayout(self)
        layout.addWidget(self.availability_message)
        layout.addLayout(form)
        layout.addLayout(buttons)
        layout.addWidget(self.validation_message)
        self.set_available(False, False)

    def set_available(self, connected: bool, workflow_active: bool) -> None:
        enabled = connected and not workflow_active
        for button in (self.status_button, self.read_button, self.send_button):
            button.setEnabled(enabled)

    def _request_read(self) -> None:
        answer = QMessageBox.question(
            self,
            "Read SMS",
            "Reading a message can change its read status. Continue?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer == QMessageBox.Yes:
            self.read_requested.emit(self.index.value())

    def _request_send(self) -> None:
        try:
            message = SmsMessage(self.recipient.text(), self.body.toPlainText())
        except ValueError as error:
            self.validation_message.setText(str(error))
            return
        answer = QMessageBox.warning(
            self,
            "Send SMS",
            f"Send one SMS to {message.recipient}?\n\n{message.body}",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer == QMessageBox.Yes:
            self.validation_message.clear()
            self.send_requested.emit(message.recipient, message.body)

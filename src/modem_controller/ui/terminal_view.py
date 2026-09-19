"""Shared terminal transcript and command input widgets."""

from __future__ import annotations

import re
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from modem_controller.transport.privacy import contains_secret_input


class DisplayMode(str, Enum):
    TEXT = "Text"
    HEX = "Hex"
    COMBINED = "Text + Hex"


class TerminalDirection(str, Enum):
    RECEIVED = "RX"
    TRANSMITTED = "TX"
    INFORMATION = "INFO"


@dataclass(frozen=True, slots=True)
class TerminalEntry:
    direction: TerminalDirection
    data: bytes
    sensitive: bool = False
    force_hex: bool = False
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


_TERMINATORS = {"None": b"", "CR": b"\r", "LF": b"\n", "CRLF": b"\r\n"}


class TerminalWorkspace(QWidget):
    """A bounded transcript and one explicit text or exact-byte send intent."""

    text_submitted = Signal(str, bytes, bool)
    bytes_submitted = Signal(bytes)
    clear_requested = Signal()

    def __init__(
        self, *, max_entries: int = 1_000, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        if max_entries <= 0:
            raise ValueError("max_entries must be positive")

        self._entries: deque[TerminalEntry] = deque(maxlen=max_entries)
        self._auto_scroll = True
        self._workflow_active = False
        self._secret = False
        self._history: deque[str] = deque(maxlen=100)
        self._history_index = 0
        self._history_draft = ""
        self._block_entries: list[TerminalEntry] = []

        self.transcript = QPlainTextEdit(self)
        self.transcript.setReadOnly(True)
        self.transcript.setObjectName("terminalTranscript")
        self.transcript.verticalScrollBar().valueChanged.connect(self._track_scroll)
        self.transcript.setContextMenuPolicy(Qt.CustomContextMenu)
        self.transcript.customContextMenuRequested.connect(self._show_transcript_menu)

        self.display_mode = QComboBox(self)
        self.display_mode.addItems([mode.value for mode in DisplayMode])
        self.display_mode.currentTextChanged.connect(lambda _: self._render())

        self.command_input = QLineEdit(self)
        self.command_input.setObjectName("terminalInput")
        self.command_input.setPlaceholderText("AT command")
        self.command_input.returnPressed.connect(self.submit_text)
        self.command_input.installEventFilter(self)

        self.terminator = QComboBox(self)
        self.terminator.addItems(_TERMINATORS)
        self.terminator.setCurrentText("CR")

        self.send_button = QPushButton("Send", self)
        self.send_button.clicked.connect(self.submit_text)
        self.clear_button = QPushButton("Clear", self)
        self.clear_button.clicked.connect(self._request_clear)

        self.hex_input = QLineEdit(self)
        self.hex_input.setObjectName("hexInput")
        self.hex_input.setPlaceholderText("41 54 0D")
        self.hex_input.returnPressed.connect(self.submit_hex)
        self.hex_send_button = QPushButton("Send hex", self)
        self.hex_send_button.clicked.connect(self.submit_hex)
        self.validation_message = QLabel(self)
        self.validation_message.setObjectName("terminalValidation")

        input_layout = QHBoxLayout()
        input_layout.addWidget(self.command_input, 1)
        input_layout.addWidget(self.terminator)
        input_layout.addWidget(self.send_button)
        input_layout.addWidget(self.clear_button)

        hex_layout = QHBoxLayout()
        hex_layout.addWidget(self.hex_input, 1)
        hex_layout.addWidget(self.hex_send_button)

        controls = QFormLayout()
        controls.addRow("Display", self.display_mode)
        controls.addRow("Command", input_layout)
        controls.addRow("Exact bytes", hex_layout)
        controls.addRow("", self.validation_message)
        self.inspection = QGroupBox("Terminal options", self)
        self.inspection.setCheckable(True)
        self.inspection.setChecked(False)
        options = QFormLayout(self.inspection)
        self.encoding = QComboBox(self)
        self.encoding.addItems(["utf-8", "ascii", "latin-1"])
        self.compact_blanks = QCheckBox("Compact blank lines (display only)", self)
        self.show_controls = QCheckBox("Show control characters", self)
        self.timestamps = QCheckBox("Show UTC timestamps and byte counts", self)
        self.history_filter = QLineEdit(self)
        self.history_filter.setPlaceholderText("Filter history, then use Up / Down")
        for name, widget in (
            ("Decode", self.encoding),
            ("", self.compact_blanks),
            ("", self.show_controls),
            ("", self.timestamps),
            ("History", self.history_filter),
        ):
            options.addRow(name, widget)
        self.counts = QLabel(self)
        self.encoding.currentTextChanged.connect(self._render)
        for option in (self.compact_blanks, self.show_controls, self.timestamps):
            option.toggled.connect(self._render)
        self.history_filter.textChanged.connect(self._reset_history_index)
        self.inspection.toggled.connect(self._show_options)
        self._show_options(False)

        layout = QVBoxLayout(self)
        layout.addWidget(self.transcript, 1)
        layout.addLayout(controls)
        layout.addWidget(self.inspection)
        layout.addWidget(self.counts)

    def _show_options(self, visible: bool) -> None:
        layout = self.inspection.layout()
        for index in range(layout.count()):
            widget = layout.itemAt(index).widget()
            if widget is not None:
                widget.setVisible(visible)

    def _reset_history_index(self) -> None:
        self._history_index = len(self._filtered_history())

    def _filtered_history(self) -> list[str]:
        query = self.history_filter.text().casefold()
        return [value for value in self._history if query in value.casefold()]

    def eventFilter(self, watched, event) -> bool:
        if (
            watched is self.command_input
            and event.type() == QEvent.KeyPress
            and event.key() in (Qt.Key_Up, Qt.Key_Down)
        ):
            history = self._filtered_history()
            if self._history_index >= len(history):
                draft = self.command_input.text()
                self._history_draft = (
                    ""
                    if self._secret or contains_secret_input(draft.encode("utf-8"))
                    else draft
                )
            change = -1 if event.key() == Qt.Key_Up else 1
            self._history_index = min(
                len(history), max(0, self._history_index + change)
            )
            self.command_input.setText(
                history[self._history_index]
                if self._history_index < len(history)
                else self._history_draft
            )
            return True
        return super().eventFilter(watched, event)

    def preferences(self) -> dict[str, str]:
        return {
            "terminal_encoding": self.encoding.currentText(),
            "terminal_display": self.display_mode.currentText(),
            "terminal_terminator": self.terminator.currentText(),
            "terminal_compact": str(self.compact_blanks.isChecked()),
            "terminal_controls": str(self.show_controls.isChecked()),
            "terminal_timestamps": str(self.timestamps.isChecked()),
        }

    def apply_preferences(self, values: dict[str, str]) -> None:
        for key, widget in (
            ("encoding", self.encoding),
            ("display", self.display_mode),
            ("terminator", self.terminator),
        ):
            text = values.get("terminal_" + key, "")
            if widget.findText(text) >= 0:
                widget.setCurrentText(text)
        for key, widget in (
            ("compact", self.compact_blanks),
            ("controls", self.show_controls),
            ("timestamps", self.timestamps),
        ):
            widget.setChecked(values.get("terminal_" + key) == "True")

    @property
    def entries(self) -> tuple[TerminalEntry, ...]:
        return tuple(self._entries)

    @property
    def is_auto_scroll_paused(self) -> bool:
        return not self._auto_scroll

    @property
    def selected_terminator(self) -> bytes:
        return _TERMINATORS[self.terminator.currentText()]

    def set_workflow_active(self, active: bool) -> None:
        self._workflow_active = active
        self.command_input.setEnabled(not active)
        self.send_button.setEnabled(not active)
        self.hex_input.setEnabled(not active)
        self.hex_send_button.setEnabled(not active)

    def set_auto_scroll_paused(self, paused: bool) -> None:
        self._auto_scroll = not paused

    def append_received(self, data: bytes) -> None:
        self._append(TerminalDirection.RECEIVED, data, sensitive=self._secret)

    def pause_sensitive_capture(self) -> None:
        self._secret = True
        self._history_draft = ""

    def reset_privacy_context(self) -> None:
        """Start a new connection without carrying transient secret drafts forward."""
        self._secret = False
        self._history_draft = ""
        self.command_input.clear()
        self.hex_input.clear()

    def append_transmitted(
        self, data: bytes, *, sensitive: bool = False, force_hex: bool = False
    ) -> None:
        if sensitive or contains_secret_input(data):
            self.pause_sensitive_capture()
        self._append(
            TerminalDirection.TRANSMITTED,
            data,
            sensitive=self._secret,
            force_hex=force_hex,
        )

    def append_info(self, message: str) -> None:
        self._append(TerminalDirection.INFORMATION, message.encode("utf-8"))

    def clear(self) -> None:
        self._entries.clear()
        self._block_entries.clear()
        self.transcript.clear()

    def _request_clear(self) -> None:
        self.clear()
        self.clear_requested.emit()

    def submit_text(self) -> bool:
        if self._workflow_active:
            self.validation_message.setText("An active workflow owns the session.")
            return False
        command = self.command_input.text()
        if not command:
            return False
        terminator = self.selected_terminator
        try:
            payload = command.encode("ascii")
        except UnicodeEncodeError:
            self.validation_message.setText(
                "Command must be ASCII; use exact hex for other bytes."
            )
            return False
        sensitive = self._secret or contains_secret_input(payload)
        self.append_transmitted(payload + terminator, sensitive=sensitive)
        if not sensitive:
            if not self._history or self._history[-1] != command:
                self._history.append(command)
        self._reset_history_index()
        self.text_submitted.emit(command, terminator, sensitive)
        self.command_input.clear()
        self.validation_message.clear()
        return True

    def submit_hex(self) -> bool:
        if self._workflow_active:
            self.validation_message.setText("An active workflow owns the session.")
            return False
        try:
            payload = self._parse_hex(self.hex_input.text())
        except ValueError as error:
            self.validation_message.setText(str(error))
            return False
        self.append_transmitted(payload, sensitive=contains_secret_input(payload))
        self.bytes_submitted.emit(payload)
        self.hex_input.clear()
        self.validation_message.clear()
        return True

    def copy_all(self) -> None:
        QApplication.clipboard().setText(self.transcript.toPlainText())

    def paste_into_input(self) -> None:
        self.command_input.insert(QApplication.clipboard().text())
        self.command_input.setFocus()

    def resend_selected_line(self) -> bool:
        """Resend raw bytes from the selected transcript line as text or exact bytes."""

        entry = self._selected_entry()
        if (
            entry is None
            or entry.sensitive
            or entry.direction is TerminalDirection.INFORMATION
            or self._workflow_active
            or self._secret
        ):
            return False
        command, terminator = self._as_text_command(entry.data)
        self.append_transmitted(entry.data)
        if command is None:
            self.bytes_submitted.emit(entry.data)
        else:
            self.text_submitted.emit(command, terminator, False)
        return True

    @staticmethod
    def _parse_hex(value: str) -> bytes:
        compact = "".join(value.split())
        if not compact:
            raise ValueError("Hex input is required.")
        if len(compact) % 2 or re.fullmatch(r"[0-9A-Fa-f]+", compact) is None:
            raise ValueError("Hex input is invalid.")
        return bytes.fromhex(compact)

    def _append(
        self,
        direction: TerminalDirection,
        data: bytes,
        *,
        sensitive: bool = False,
        force_hex: bool = False,
    ) -> None:
        self._entries.append(
            TerminalEntry(
                direction=direction,
                data=b"" if sensitive else bytes(data),
                sensitive=sensitive,
                force_hex=force_hex,
            )
        )
        self._render()

    def _render(self) -> None:
        lines = []
        self._block_entries = []
        for entry in self._entries:
            line = self._format_entry(entry)
            lines.append(line)
            self._block_entries.extend([entry] * (line.count("\n") + 1))
        paused = not self._auto_scroll
        position = self.transcript.verticalScrollBar().value()
        self.transcript.verticalScrollBar().blockSignals(True)
        self.transcript.setPlainText("\n".join(lines))
        if not paused:
            self.transcript.moveCursor(QTextCursor.End)
        scroll_bar = self.transcript.verticalScrollBar()
        scroll_bar.setValue(position if paused else scroll_bar.maximum())
        scroll_bar.blockSignals(False)
        self.counts.setText(
            f"Retained: {len(self._entries)} entries, "
            f"{sum(len(e.data) for e in self._entries)} bytes (raw capture is separate)"
        )

    def _format_entry(self, entry: TerminalEntry) -> str:
        if entry.sensitive and entry.direction is TerminalDirection.TRANSMITTED:
            return "TX  <sensitive command suppressed>"
        mode = DisplayMode(self.display_mode.currentText())
        encoding = (
            "utf-8"
            if entry.direction is TerminalDirection.INFORMATION
            else self.encoding.currentText()
        )
        text = entry.data.decode(encoding, errors="backslashreplace")
        if self.show_controls.isChecked():
            labels = {13: "<CR>", 10: "<LF>", 27: "<ESC>", 26: "<CTRL+Z>"}
            text = "".join(
                labels.get(ord(c), f"<0x{ord(c):02X}>")
                if ord(c) < 32 or ord(c) == 127
                else c
                for c in text
            )
        else:
            text = text.replace("\r\n", "\n").replace("\r", "\n").rstrip("\n")
            if self.compact_blanks.isChecked():
                text = re.sub(r"\n{3,}", "\n\n", text)
        hexadecimal = entry.data.hex(" ").upper()
        if entry.force_hex or mode is DisplayMode.HEX:
            payload = f"HEX {hexadecimal}" if entry.force_hex else hexadecimal
        elif mode is DisplayMode.TEXT:
            payload = text
        else:
            payload = f"{text}  [{hexadecimal}]"
        prefix = (
            f"{entry.timestamp.isoformat(timespec='milliseconds')} {len(entry.data)} B "
            if self.timestamps.isChecked()
            else ""
        )
        return f"{prefix}{entry.direction.value}  {payload}"

    def _track_scroll(self, value: int) -> None:
        scroll_bar = self.transcript.verticalScrollBar()
        self._auto_scroll = value >= scroll_bar.maximum()

    def _show_transcript_menu(self, position) -> None:
        menu: QMenu = self.transcript.createStandardContextMenu()
        menu.addSeparator()
        copy_all = menu.addAction("Copy all")
        paste = menu.addAction("Paste into input")
        resend = menu.addAction("Send line again")
        resend.setEnabled(
            self._selected_entry() is not None
            and self._selected_entry().direction is not TerminalDirection.INFORMATION
            and not self._workflow_active
            and not self._secret
        )
        action = menu.exec(self.transcript.mapToGlobal(position))
        if action is copy_all:
            self.copy_all()
        elif action is paste:
            self.paste_into_input()
        elif action is resend:
            self.resend_selected_line()

    def _selected_entry(self) -> TerminalEntry | None:
        cursor = self.transcript.textCursor()
        block_number = (
            self.transcript.document().findBlock(cursor.position()).blockNumber()
        )
        if 0 <= block_number < len(self._block_entries):
            return self._block_entries[block_number]
        return None

    @staticmethod
    def _as_text_command(data: bytes) -> tuple[str | None, bytes]:
        terminator = b""
        for candidate in (b"\r\n", b"\r", b"\n"):
            if data.endswith(candidate):
                terminator = candidate
                data = data[: -len(candidate)]
                break
        try:
            command = data.decode("ascii")
        except UnicodeDecodeError:
            return None, b""
        if not command or not command.isprintable():
            return None, b""
        return command, terminator

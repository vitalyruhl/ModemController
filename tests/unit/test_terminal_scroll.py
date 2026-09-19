"""Rendered transcript scrolling regressions."""

from __future__ import annotations

import pytest
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication

from modem_controller.ui.main_window import MainWindow
from modem_controller.ui.terminal_view import TerminalWorkspace


def _flush_layout() -> None:
    QApplication.processEvents()
    QApplication.processEvents()


def _append_block(terminal: TerminalWorkspace, label: str) -> None:
    terminal.append_info("\n".join(f"{label}-{line}" for line in range(24)))
    _flush_layout()


def _rendered_terminal(qtbot, *, max_entries: int = 8) -> TerminalWorkspace:
    terminal = TerminalWorkspace(max_entries=max_entries)
    qtbot.addWidget(terminal)
    terminal.resize(640, 300)
    terminal.show()
    _flush_layout()
    return terminal


def _use_segoe_ui(terminal: TerminalWorkspace) -> None:
    font_path = "C:/Windows/Fonts/segoeui.ttf"
    font_id = QFontDatabase.addApplicationFont(font_path)
    if font_id < 0:
        pytest.skip("Segoe UI is unavailable on this Windows test host")
    family = QFontDatabase.applicationFontFamilies(font_id)[0]
    terminal.transcript.setFont(QFont(family, 10))


def test_bottom_stays_at_newest_after_append_and_entry_eviction(qtbot) -> None:
    terminal = _rendered_terminal(qtbot, max_entries=3)
    for label in ("one", "two", "three", "four", "five"):
        _append_block(terminal, label)

    scroll_bar = terminal.transcript.verticalScrollBar()

    assert len(terminal.entries) == 3
    assert scroll_bar.maximum() > 0
    assert scroll_bar.value() == scroll_bar.maximum()
    assert not terminal.is_auto_scroll_paused
    assert "five-23" in terminal.transcript.toPlainText()


def test_append_while_reading_history_keeps_the_scrollbar_position(qtbot) -> None:
    terminal = _rendered_terminal(qtbot)
    for label in ("one", "two", "three", "four"):
        _append_block(terminal, label)
    scroll_bar = terminal.transcript.verticalScrollBar()
    scroll_bar.setValue(scroll_bar.maximum() // 2)
    _flush_layout()
    position = scroll_bar.value()

    _append_block(terminal, "five")

    assert position < scroll_bar.maximum()
    assert scroll_bar.value() == position
    assert terminal.is_auto_scroll_paused


def test_scrolling_to_bottom_resumes_following_new_terminal_entries(qtbot) -> None:
    terminal = _rendered_terminal(qtbot)
    for label in ("one", "two", "three", "four"):
        _append_block(terminal, label)
    scroll_bar = terminal.transcript.verticalScrollBar()
    scroll_bar.setValue(0)
    _flush_layout()
    assert terminal.is_auto_scroll_paused

    scroll_bar.setValue(scroll_bar.maximum())
    _flush_layout()
    _append_block(terminal, "five")

    assert not terminal.is_auto_scroll_paused
    assert scroll_bar.value() == scroll_bar.maximum()
    assert "five-23" in terminal.transcript.toPlainText()


def test_wrapped_segoe_replies_stay_at_bottom_through_resize_and_focus(qtbot) -> None:
    terminal = _rendered_terminal(qtbot, max_entries=4)
    _use_segoe_ui(terminal)
    terminal.resize(360, 260)
    wrapped_reply = ("+LONGREPLY: " + "cellular diagnostic evidence " * 16 + "\n") * 4
    for index in range(6):
        terminal.append_received(f"{index}: ".encode() + wrapped_reply.encode())
        _flush_layout()
    scroll_bar = terminal.transcript.verticalScrollBar()
    assert scroll_bar.maximum() > 0
    assert scroll_bar.value() == scroll_bar.maximum()

    terminal.resize(640, 360)
    terminal.transcript.setFocus()
    _flush_layout()
    terminal.append_received(b"+FINAL: latest evidence\r\n")
    _flush_layout()

    assert scroll_bar.value() == scroll_bar.maximum()
    assert not terminal.is_auto_scroll_paused


def test_main_window_tx_rx_info_burst_keeps_rendered_transcript_at_bottom(
    qtbot,
) -> None:
    window = MainWindow()
    qtbot.addWidget(window)
    window.resize(800, 600)
    window.show()
    _flush_layout()
    terminal = window.terminal
    for index in range(48):
        terminal.append_transmitted(f"AT+TEST={index}\r".encode())
        terminal.append_received(f"+TEST: {index}\r\nOK\r\n".encode())
        terminal.append_info(f"Diagnostic {index} complete")
    _flush_layout()
    scroll_bar = terminal.transcript.verticalScrollBar()

    assert scroll_bar.maximum() > 0
    assert scroll_bar.value() == scroll_bar.maximum()
    assert not terminal.is_auto_scroll_paused

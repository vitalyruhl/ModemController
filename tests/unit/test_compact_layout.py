"""Rendered compact-layout contracts for the main terminal window."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from modem_controller.ui.main_window import MainWindow


def _flush() -> None:
    QApplication.processEvents()
    QApplication.processEvents()


def test_category_buttons_replace_hidden_dropdown_and_switch_commands(qtbot) -> None:
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    _flush()

    buttons = [
        window.category_layout.itemAt(index).widget()
        for index in range(window.category_layout.count())
    ]
    maintenance = next(button for button in buttons if button.text() == "Maintenance")
    maintenance.click()
    _flush()

    assert window.category_selector.isHidden()
    assert all(button.isCheckable() for button in buttons)
    assert window.category_selector.currentText() == "Maintenance"
    assert maintenance.isChecked()
    assert any(
        "Unlock SIM" in window.command_layout.itemAt(index).widget().text()
        for index in range(window.command_layout.count())
    )


def test_command_area_stays_top_aligned_with_fixed_spacing_through_resize(
    qtbot,
) -> None:
    window = MainWindow()
    qtbot.addWidget(window)
    window.resize(900, 620)
    window.show()
    _flush()
    window.resize(1_300, 860)
    _flush()

    assert window.command_layout.alignment() & Qt.AlignTop
    assert window.command_layout.horizontalSpacing() == 6
    assert window.command_layout.verticalSpacing() == 6
    assert all(
        window.command_layout.itemAt(index).widget().height() == 32
        for index in range(window.command_layout.count())
    )


def test_terminal_control_rows_keep_clear_by_display_and_ending_below_command(
    qtbot,
) -> None:
    window = MainWindow()
    qtbot.addWidget(window)
    window.resize(1_100, 720)
    window.show()
    _flush()
    terminal = window.terminal

    assert abs(terminal.clear_button.y() - terminal.display_mode.y()) <= 1
    assert terminal.clear_button.x() > terminal.display_mode.x()
    assert terminal.terminator.y() > terminal.command_input.y()
    assert terminal.command_input.width() > terminal.terminator.width()

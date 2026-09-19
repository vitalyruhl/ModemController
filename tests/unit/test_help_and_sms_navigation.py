"""One SMS entry point and right-aligned program information."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from modem_controller.ui.main_window import MainWindow


def test_help_replaces_evidence_at_right_and_opens_about_without_io(qtbot):
    window = MainWindow(port_provider=lambda: [])
    qtbot.addWidget(window)
    window.show()
    QApplication.processEvents()
    assert window.menuBar().cornerWidget(Qt.TopRightCorner) is window.help_button
    assert window.help_button.text() == "?"
    assert "Evidence" not in [a.text() for a in window.menuBar().actions()]
    assert "Messaging" not in [a.text() for a in window.menuBar().actions()]
    assert any("report" in a.text() for a in window.help_menu.actions())
    window.help_menu.actions()[0].trigger()
    assert window._about_dialog.isVisible()
    assert window._about_dialog.author_label.text() == "Vitaly Ruhl"
    assert window._connection_controller is None


def test_sms_draft_explains_profile_gate_without_claiming_support(qtbot):
    window = MainWindow(port_provider=lambda: [])
    qtbot.addWidget(window)
    window.profile_selector.setCurrentIndex(
        window.profile_selector.findData("tc35-tc35i")
    )
    window._connected("COM10")
    window.prepare_sms_button.click()
    assert window.sms_dialog.isVisible()
    assert not window.sms_dialog.send_button.isEnabled()
    assert "Generic AT" in window.sms_dialog.availability_message.text()
    window.profile_selector.setCurrentIndex(
        window.profile_selector.findData("generic-at")
    )
    assert window.sms_dialog.send_button.isEnabled()
    window._disconnected()
    assert not window.sms_dialog.send_button.isEnabled()
    assert "Connect" in window.sms_dialog.availability_message.text()

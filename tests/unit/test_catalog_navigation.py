from PySide6.QtCore import Qt

from modem_controller.catalog.models import load_starter_catalog
from modem_controller.ui.catalog_editor import CatalogEditor
from modem_controller.ui.main_window import MainWindow


def test_command_navigation_stays_visible_outside_scrolling_fields(qtbot):
    editor = CatalogEditor(load_starter_catalog())
    qtbot.addWidget(editor)
    editor.select_profile("generic-at")
    editor.resize(900, 600)
    editor.show()
    assert editor.command_selector.count() > 2
    editor.field_scroll.verticalScrollBar().setValue(
        editor.field_scroll.verticalScrollBar().maximum()
    )
    assert editor.profile_selector.isVisible()
    assert editor.command_selector.isVisible()
    assert not editor.field_scroll.isAncestorOf(editor.command_selector)
    editor.select_command("signal-quality")
    assert editor.payload.text() == "AT+CSQ"
    editor.select_command("identity")
    assert editor.payload.text() == "ATI"


def test_advanced_fields_are_collapsed_and_all_commands_remain_selectable(qtbot):
    editor = CatalogEditor(load_starter_catalog())
    qtbot.addWidget(editor)
    editor.select_profile("generic-at")
    editor.show()
    assert not editor.advanced.isChecked()
    assert not editor.risk.isVisible()
    assert not editor.parameters.isVisible()
    assert not editor.steps.isVisible()
    assert editor.payload.isVisible()
    editor.advanced.setChecked(True)
    assert editor.risk.isVisible()
    assert editor.parameters.isVisible()
    assert not editor.steps.isVisible()  # An ordinary AT command has no sequence.
    editor.select_command("ras-collector")
    assert editor.command_selector.currentItem().data(Qt.UserRole) == "ras-collector"


def test_no_search_results_cannot_edit_previous_command_fields(qtbot):
    editor = CatalogEditor(load_starter_catalog())
    qtbot.addWidget(editor)
    editor.search.setText("no-such-command")
    assert editor.command_selector.count() == 0
    assert not editor.payload.isEnabled()
    assert editor.payload.text() == ""


def test_editor_opens_on_the_profile_selected_in_the_main_window(qtbot):
    window = MainWindow(port_provider=lambda: [])
    qtbot.addWidget(window)
    window.profile_selector.setCurrentIndex(
        window.profile_selector.findData("generic-at")
    )
    window._show_catalog_editor()
    editor = window._catalog_editor
    assert editor.profile_selector.currentData() == "generic-at"
    assert editor.command_selector.count() == len(window._selected_profile().commands)
    editor.close()

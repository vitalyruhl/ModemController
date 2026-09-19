"""Extra window space is allocated to usable content, not labels."""

from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtWidgets import QApplication

from modem_controller.catalog.models import load_starter_catalog
from modem_controller.ui.catalog_editor import CatalogEditor
from modem_controller.ui.main_window import MainWindow


def settle():
    QApplication.processEvents()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    QApplication.processEvents()


def test_editor_gives_added_height_to_command_list_and_fields(qtbot):
    editor = CatalogEditor(load_starter_catalog())
    qtbot.addWidget(editor)
    editor.show()
    editor.resize(950, 650)
    settle()
    list_height = editor.command_selector.height()
    form_height = editor.field_scroll.height()
    hint_height = editor.selection_hint.height()
    editor.resize(1250, 1000)
    settle()
    assert editor.command_selector.height() - list_height >= 300
    assert editor.field_scroll.height() - form_height >= 300
    assert editor.selection_hint.height() <= hint_height + 3
    assert editor.command_selector.y() < 150


def test_category_and_command_areas_share_added_height_one_to_two(qtbot):
    window = MainWindow(port_provider=lambda: [])
    qtbot.addWidget(window)
    window.show()
    window.resize(1100, 850)
    settle()
    categories = window.category_scroll.height()
    commands = window.command_scroll.height()
    window.resize(1100, 1150)
    settle()
    category_growth = window.category_scroll.height() - categories
    command_growth = window.command_scroll.height() - commands
    assert category_growth > 50
    assert abs(command_growth - 2 * category_growth) <= 6

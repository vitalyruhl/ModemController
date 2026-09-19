from dataclasses import replace
from unittest.mock import patch

from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QMessageBox

from modem_controller.catalog.models import load_starter_catalog
from modem_controller.catalog.storage import SettingsStore, StorageError
from modem_controller.ui.catalog_editor import CatalogEditor
from modem_controller.ui.main_window import MainWindow


def test_editor_changes_command_notes_and_order_without_io(qtbot):
    catalog = load_starter_catalog()
    editor = CatalogEditor(catalog)
    qtbot.addWidget(editor)
    editor.select_profile("generic-at")
    editor.select_command("attention")
    editor.label.setText("Attention edited")
    editor.notes.setPlainText("Observed locally")
    editor.save_button.click()
    assert (
        editor.catalog.profile("generic-at").command("attention").label
        == "Attention edited"
    )
    assert editor.catalog.profile("generic-at").user_notes == "Observed locally"
    editor.duplicate_selected()
    assert (
        len(editor.catalog.profile("generic-at").commands)
        == len(catalog.profile("generic-at").commands) + 1
    )
    editor.move_selected(-1)
    assert "copy" in editor.catalog.profile("generic-at").commands[-2].id


def test_catalog_edit_and_notes_survive_restart(qtbot, tmp_path):
    store = SettingsStore(tmp_path)
    window = MainWindow(settings_store=store, port_provider=lambda: [])
    qtbot.addWidget(window)
    catalog = window._catalog
    profile = catalog.profile("generic-at")
    commands = tuple(
        replace(c, label="My query") if c.id == "attention" else c
        for c in profile.commands
    )
    profile = replace(profile, commands=commands, user_notes="My note")
    changed = replace(
        catalog,
        profiles=tuple(profile if p.id == profile.id else p for p in catalog.profiles),
    )
    window.apply_catalog(changed)
    assert window._save_preferences()
    window.close()
    restored = MainWindow(settings_store=store, port_provider=lambda: [])
    qtbot.addWidget(restored)
    assert (
        restored._catalog.profile("generic-at").command("attention").label == "My query"
    )
    assert restored._catalog.profile("generic-at").user_notes == "My note"


def test_failed_save_does_not_close_or_discard_without_confirmation(qtbot, tmp_path):
    store = SettingsStore(tmp_path)
    window = MainWindow(settings_store=store, port_provider=lambda: [])
    qtbot.addWidget(window)
    event = QCloseEvent()
    with (
        patch.object(store, "save", side_effect=StorageError("disk full")),
        patch.object(QMessageBox, "warning", return_value=QMessageBox.Cancel),
    ):
        window.closeEvent(event)
    assert not event.isAccepted()
    assert window._save_preferences(), window.connection_panel.status.text()


def test_corrupt_settings_are_not_overwritten_on_close(qtbot, tmp_path, monkeypatch):
    store = SettingsStore(tmp_path)
    store.path.write_text("broken")
    window = MainWindow(settings_store=store, port_provider=lambda: [])
    qtbot.addWidget(window)
    monkeypatch.setattr(QMessageBox, "warning", lambda *a: QMessageBox.Discard)
    window.close()
    assert store.path.read_text() == "broken"


def test_editor_draft_requires_apply_or_deliberate_discard(qtbot, monkeypatch):
    editor = CatalogEditor(load_starter_catalog())
    qtbot.addWidget(editor)
    editor.label.setText("Unsaved")
    assert not editor.command_selector.isEnabled()
    event = QCloseEvent()
    monkeypatch.setattr(QMessageBox, "question", lambda *a: QMessageBox.Cancel)
    editor.closeEvent(event)
    assert not event.isAccepted()
    assert editor.label.text() == "Unsaved"
    monkeypatch.setattr(QMessageBox, "question", lambda *a: QMessageBox.Discard)
    editor.close()
    assert editor.label.text() != "Unsaved"


def test_notes_can_be_saved_for_profile_without_commands(qtbot):
    catalog = load_starter_catalog()
    profile = replace(catalog.profiles[0], commands=())
    editor = CatalogEditor(replace(catalog, profiles=(profile,)))
    qtbot.addWidget(editor)
    editor.notes.setPlainText("Observed unsupported device")
    assert editor._save()
    assert editor.catalog.profiles[0].user_notes == "Observed unsupported device"


def test_payload_edits_require_separate_review_before_enabling(qtbot, monkeypatch):
    editor = CatalogEditor(load_starter_catalog())
    qtbot.addWidget(editor)
    editor.select_command("attention")
    editor.payload.setText("AT+CFUN=1,1")
    assert editor._save()
    assert not editor.catalog.profiles[0].command("attention").is_visible
    editor.verification.setCurrentText("supported")
    monkeypatch.setattr(QMessageBox, "question", lambda *a: QMessageBox.No)
    assert not editor._save()
    assert not editor.catalog.profiles[0].command("attention").is_visible
    monkeypatch.setattr(QMessageBox, "question", lambda *a: QMessageBox.Yes)
    assert editor._save()
    assert editor.catalog.profiles[0].command("attention").is_visible

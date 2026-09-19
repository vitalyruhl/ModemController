import pytest

from modem_controller.catalog.legacy_import import (
    LegacyEntry,
    import_reviewed_selection,
    load_legacy,
    preview_legacy,
)
from modem_controller.catalog.models import VerificationStatus, load_starter_catalog
from modem_controller.catalog.storage import export_catalog_json, import_catalog_json


def test_selected_import_is_disabled_persistent_and_source_unchanged(tmp_path):
    source = tmp_path / "old.VCE"
    original = b"AT\r\nAT#CMGF=1\r\n"
    source.write_bytes(original)
    entries = load_legacy(source)
    catalog = import_reviewed_selection(load_starter_catalog(), entries[1:])
    command = catalog.profiles[-1].commands[0]
    assert command.payload == "AT#CMGF=1"
    assert command.verification == VerificationStatus.UNVERIFIED
    assert not command.is_visible
    exported = tmp_path / "export.json"
    export_catalog_json(catalog, exported)
    assert import_catalog_json(exported) == catalog
    assert source.read_bytes() == original


def test_empty_selection_and_credentials_cannot_enter_catalog():
    catalog = load_starter_catalog()
    for entries in ((), preview_legacy('AT+CPIN="1234"', "vce")):
        with pytest.raises(ValueError):
            import_reviewed_selection(catalog, entries)


def test_preview_requires_selection_and_masks_credentials(qtbot):
    from PySide6.QtCore import Qt

    from modem_controller.ui.legacy_import_dialog import LegacyImportDialog

    dialog = LegacyImportDialog(preview_legacy('AT\nAT+CPIN="1234"', "vce"))
    qtbot.addWidget(dialog)
    assert dialog.selected_entries() == ()
    assert "1234" not in dialog.table.item(1, 1).text()
    assert not dialog.table.item(1, 0).flags() & Qt.ItemIsEnabled
    dialog.table.item(0, 0).setCheckState(Qt.Checked)
    assert [e.payload for e in dialog.selected_entries()] == ["AT"]


def test_editor_cancelled_legacy_preview_preserves_catalog(
    qtbot, monkeypatch, tmp_path
):
    from modem_controller.ui import catalog_editor as module
    from modem_controller.ui.catalog_editor import CatalogEditor

    source = tmp_path / "old.vce"
    source.write_text("AT")
    editor = CatalogEditor(load_starter_catalog())
    qtbot.addWidget(editor)
    original = editor.catalog
    monkeypatch.setattr(
        module.QFileDialog, "getOpenFileName", lambda *a: (str(source), "")
    )
    monkeypatch.setattr(module.LegacyImportDialog, "exec", lambda self: 0)
    editor._import_legacy()
    assert editor.catalog is original


def test_xml_preview_decodes_legacy_names_and_description_payloads() -> None:
    source = """<?xml version="1.0" encoding="utf-8"?>
<rootNode>
  <Network_x0020_Status Description="AT_x002B_CREG_x003F_" />
  <Status>
    <Signal_x0020_Quality Description="AT_x002B_CSQ" />
  </Status>
</rootNode>
"""

    entries = preview_legacy(source, "xml")

    assert entries == (
        LegacyEntry("Network Status", "AT+CREG?", ()),
        LegacyEntry("Signal Quality", "AT+CSQ", ()),
    )


def test_xml_preview_preserves_duplicates_and_marks_later_entry_for_review() -> None:
    source = """<rootNode>
  <First Description="AT_x002B_CSQ" />
  <Again Description="AT_x002B_CSQ" />
</rootNode>"""

    entries = preview_legacy(source, "xml")

    assert [entry.payload for entry in entries] == ["AT+CSQ", "AT+CSQ"]
    assert entries[0].warnings == ()
    assert any("duplicate" in warning.lower() for warning in entries[1].warnings)


def test_xml_preview_preserves_unknown_elements_and_payload_without_correction() -> (
    None
):
    source = """<rootNode>
  <Vendor_x0020_Action Description="AT_x0023_CUSTOM_x003D_1" />
  <Unsupported Description="HELLO" />
</rootNode>"""

    entries = preview_legacy(source, "xml")

    assert [entry.label for entry in entries] == ["Vendor Action", "Unsupported"]
    assert [entry.payload for entry in entries] == ["AT#CUSTOM=1", "HELLO"]
    assert all(entry.warnings for entry in entries)


def test_vce_preview_preserves_each_nonempty_line_and_flags_sensitive_syntax() -> None:
    source = "AT\r\n\r\nAT#CMGF=1\r\nATZ|AT+CREG=1\r\n"

    entries = preview_legacy(source, "vce")

    assert [entry.payload for entry in entries] == [
        "AT",
        "AT#CMGF=1",
        "ATZ|AT+CREG=1",
    ]
    assert all(entry.label for entry in entries)
    assert entries[0].warnings == ()
    assert any("state" in warning.lower() for warning in entries[1].warnings)
    assert any("compound" in warning.lower() for warning in entries[2].warnings)


@pytest.mark.parametrize(
    ("source", "format"),
    [
        ("<rootNode><Missing></rootNode>", "xml"),
        (
            "<!DOCTYPE rootNode [<!ENTITY value SYSTEM "
            "'file:///not-used'>]>\n<rootNode />",
            "xml",
        ),
        ("AT", "unknown"),
    ],
)
def test_preview_rejects_malformed_unsafe_or_unknown_formats(
    source: str, format: str
) -> None:
    with pytest.raises(ValueError):
        preview_legacy(source, format)


def test_preview_rejects_oversized_source_before_parsing() -> None:
    with pytest.raises(ValueError):
        preview_legacy("AT+CSQ", "vce", max_bytes=3)


def test_editor_imports_only_selected_entries(qtbot, monkeypatch, tmp_path):
    from modem_controller.ui import catalog_editor as module

    source = tmp_path / "old.vce"
    source.write_text("AT\nATZ")
    editor = module.CatalogEditor(load_starter_catalog())
    qtbot.addWidget(editor)
    monkeypatch.setattr(
        module.QFileDialog, "getOpenFileName", lambda *a: (str(source), "")
    )
    monkeypatch.setattr(module.LegacyImportDialog, "exec", lambda self: 1)
    monkeypatch.setattr(
        module.LegacyImportDialog, "selected_entries", lambda self: self.entries[:1]
    )
    with qtbot.waitSignal(editor.catalog_changed):
        editor._import_legacy()
    assert editor._profile().id == "legacy-import-1"
    assert [c.payload for c in editor._profile().commands] == ["AT"]
    assert not editor._profile().commands[0].is_visible

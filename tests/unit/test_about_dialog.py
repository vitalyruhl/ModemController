from modem_controller.ui.about_dialog import AboutDialog
from modem_controller.versioning import product_version


def test_about_dialog_shows_packaged_identity_without_a_hash(qtbot):
    dialog = AboutDialog(build_metadata={"built_at_utc": "2026-09-19T18:00:00+00:00"})
    qtbot.addWidget(dialog)

    assert not dialog.isModal()
    assert dialog.windowTitle() == "About Modem Controller"
    assert dialog.version_label.text() == product_version()
    assert dialog.build_label.text() == "2026-09-19T18:00:00+00:00"
    assert dialog.author_label.text() == "Vitaly Ruhl"
    assert dialog.license_label.text() == "GPL-3.0-only"


def test_about_dialog_labels_a_source_checkout_without_inventing_build_time(qtbot):
    dialog = AboutDialog(build_metadata={})
    qtbot.addWidget(dialog)

    assert dialog.build_label.text() == "Development checkout (not packaged)"

import importlib.util
from pathlib import Path

import pytest

SCRIPT_PATH = Path(__file__).parents[2] / "tools" / "build_portable.py"
SPEC = importlib.util.spec_from_file_location("build_portable", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
build_portable = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(build_portable)


def test_portable_help_contains_manuals_and_working_readme_links(tmp_path):
    import re

    root = build_portable.PROJECT_ROOT
    (tmp_path / "LICENSE.txt").write_bytes((root / "LICENSE").read_bytes())
    build_portable.copy_help(tmp_path)
    sources = root / "docs" / "reference" / "modems"
    manuals = list(sources.rglob("*.pdf"))
    assert manuals
    for source in manuals:
        target = (
            tmp_path / "help" / "reference" / "modems" / source.relative_to(sources)
        )
        assert target.read_bytes() == source.read_bytes()
    assert not list((tmp_path / "help").rglob("*.exe"))
    for document in (tmp_path / "README.md", tmp_path / "help" / "README.md"):
        text = document.read_text(encoding="utf-8")
        links = re.findall(r"\]\(([^)]+)\)", text)
        assert links
        for link in links:
            if "://" not in link:
                assert (document.parent / link.split("#")[0]).exists(), link
    assert "](help/console.md)" in (tmp_path / "README.md").read_text(encoding="utf-8")


def test_portable_build_uses_onedir_and_collects_application_data() -> None:
    command = build_portable.build_command()

    assert command[:3] == [command[0], "-m", "PyInstaller"]
    assert "--onedir" in command
    assert "--windowed" in command
    assert "--collect-data" not in command
    assert "--add-data" in command
    assert command[command.index("--add-data") + 1].endswith(
        ":modem_controller/catalog/data"
    )
    assert command[command.index("--name") + 1] == build_portable.BUNDLE_NAME
    assert (
        Path(command[-1])
        == build_portable.PROJECT_ROOT / "src" / "modem_controller" / "app.py"
    )


def test_console_recipe_is_headless_and_bundles_metadata():
    command = build_portable.build_command(console=True)
    assert "--console" in command and "--windowed" not in command
    assert "--copy-metadata" in command
    assert command[-1].endswith("cli.py")


def test_candidate_build_rejects_dirty_source_before_any_output(monkeypatch, tmp_path):
    destination = tmp_path / "must-not-exist"
    monkeypatch.setattr(build_portable, "BUILD_DIRECTORY", destination)
    monkeypatch.setattr(
        build_portable,
        "build_info",
        lambda **_: {"dirty": True, "source_revision": "a" * 40},
    )
    with pytest.raises(ValueError, match="clean committed"):
        build_portable.build(candidate=True)
    assert not destination.exists()


def test_provenance_comparison_ignores_only_build_timestamp():
    before = {"source_revision": "abc", "lock_sha256": "lock", "built_at_utc": "a"}
    after = {"source_revision": "abc", "lock_sha256": "lock", "built_at_utc": "b"}
    assert build_portable.same_provenance(before, after)
    assert not build_portable.same_provenance(
        before, {**after, "lock_sha256": "changed"}
    )


def test_flat_catalog_sidecar_preserves_edits_and_new_defaults(tmp_path):
    import json
    from dataclasses import replace

    from modem_controller.catalog.models import VerificationStatus, load_starter_catalog
    from modem_controller.catalog.portable import (
        load_portable_catalog,
        seed_catalog_files,
    )

    defaults = load_starter_catalog()
    seed_catalog_files(tmp_path)
    source = tmp_path / "generic-at.json"
    data = json.loads(source.read_text())
    data["profiles"][0]["commands"][0]["payload"] = "AT+CHANGED"
    source.write_text(json.dumps(data))
    changed = source.read_bytes()
    seed_catalog_files(tmp_path)
    assert source.read_bytes() == changed
    profile = defaults.profiles[0]
    updated = replace(
        defaults,
        profiles=(
            replace(profile, shipped_notes="New release notes"),
            *defaults.profiles[1:],
        ),
    )
    catalog = load_portable_catalog(tmp_path, defaults=updated)
    assert catalog.profiles[0].shipped_notes == "New release notes"
    command = catalog.profile(data["profiles"][0]["id"]).commands[0]
    assert command.payload == "AT+CHANGED"
    assert command.verification == VerificationStatus.UNVERIFIED


def test_portable_paths_follow_executable_not_cwd(monkeypatch, tmp_path):
    import sys

    from modem_controller.paths import application_directory

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "ModemController.exe"))
    assert application_directory() == tmp_path


def test_default_settings_are_flat(tmp_path):
    from modem_controller.catalog.storage import choose_settings_location

    app = tmp_path / "app"
    assert (
        choose_settings_location(app, user_directory=tmp_path / "user").directory == app
    )


def test_artifact_audit_rejects_source_settings(tmp_path):
    from modem_controller.catalog.storage import Settings, SettingsStore

    SettingsStore(tmp_path).save(Settings())
    build_portable.audit_bundle(tmp_path)
    SettingsStore(tmp_path / "_internal" / "modem_controller" / "data").save(Settings())
    with pytest.raises(ValueError, match="Personal source settings"):
        build_portable.audit_bundle(tmp_path)


def test_corrupt_sidecar_is_preserved(tmp_path):
    from modem_controller.catalog.portable import load_portable_catalog
    from modem_controller.catalog.storage import StorageError

    path = tmp_path / "generic-at.json"
    path.write_text("invalid")
    with pytest.raises(StorageError, match="generic-at.json"):
        load_portable_catalog(tmp_path)
    assert path.read_text() == "invalid"


@pytest.mark.parametrize("value", [None, [], "catalog", 42, True])
@pytest.mark.parametrize("in_baseline", [False, True])
def test_non_object_catalog_or_baseline_is_recoverable(tmp_path, value, in_baseline):
    import json

    from modem_controller.catalog.portable import (
        load_portable_catalog,
        seed_catalog_files,
    )
    from modem_controller.catalog.storage import StorageError

    seed_catalog_files(tmp_path)
    path = tmp_path / "generic-at.json"
    data = json.loads(path.read_text())
    if in_baseline:
        data["_shipped_baseline"] = value
    else:
        data = value
    path.write_text(json.dumps(data))
    before = path.read_bytes()
    with pytest.raises(StorageError, match="generic-at.json"):
        load_portable_catalog(tmp_path)
    assert path.read_bytes() == before


def test_moving_settings_preserves_external_catalog_notes(qtbot, monkeypatch, tmp_path):
    from dataclasses import replace

    from modem_controller.catalog.models import load_starter_catalog
    from modem_controller.catalog.storage import SettingsStore, merge_catalog_overlay
    from modem_controller.ui import main_window as module

    defaults = load_starter_catalog()
    changed = replace(
        defaults,
        profiles=(
            replace(defaults.profiles[0], shipped_notes="Sidecar note"),
            *defaults.profiles[1:],
        ),
    )
    window = module.MainWindow(
        catalog=changed,
        port_provider=lambda: [],
        settings_store=SettingsStore(tmp_path / "old"),
    )
    qtbot.addWidget(window)
    destination = tmp_path / "new"
    monkeypatch.setattr(
        module.QFileDialog, "getExistingDirectory", lambda *a: str(destination)
    )
    window._choose_settings_directory()
    restored = merge_catalog_overlay(
        defaults, SettingsStore(destination).load().settings.catalog_changes
    )
    assert restored.profiles[0].shipped_notes == "Sidecar note"

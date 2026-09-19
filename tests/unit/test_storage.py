import json
from pathlib import Path

import pytest

from modem_controller.catalog.storage import (
    NewerSchemaError,
    Settings,
    SettingsStore,
    StorageError,
    choose_settings_location,
)


def test_settings_round_trip_preserves_preferences_without_device_actions(
    tmp_path: Path,
) -> None:
    store = SettingsStore(tmp_path)
    settings = Settings(
        selected_profile="generic-at",
        selected_category="Network",
        connection={"port": "COM7", "baud_rate": "115200"},
        last_directories={"export": "C:/Reports"},
        favorites=("signal-quality",),
        profile_notes={"generic-at": "Adapter observed."},
        log_file="C:/Reports/modem.log",
        logging_enabled=True,
        logging_mode="verbose",
    )

    store.save(settings)

    assert store.load() == type(store.load())(settings)


def test_missing_and_malformed_settings_recover_without_overwriting(
    tmp_path: Path,
) -> None:
    store = SettingsStore(tmp_path)

    assert not store.load().recovered
    store.path.write_text("not json", encoding="utf-8")

    result = store.load()

    assert result.recovered
    assert result.settings == Settings()
    assert store.path.read_text(encoding="utf-8") == "not json"


def test_newer_settings_schema_is_explicitly_rejected(tmp_path: Path) -> None:
    store = SettingsStore(tmp_path)
    store.path.write_text(json.dumps({"schema_version": 2}), encoding="utf-8")

    with pytest.raises(NewerSchemaError):
        store.load()


def test_sensitive_connection_values_are_not_persisted(tmp_path: Path) -> None:
    store = SettingsStore(tmp_path)

    with pytest.raises(StorageError, match="must not be persisted"):
        store.save(Settings(connection={"pin": "1234"}))


def test_explicit_portable_directory_or_user_fallback_is_selected(
    tmp_path: Path,
) -> None:
    portable = tmp_path / "portable"
    fallback = tmp_path / "user"

    location = choose_settings_location(
        tmp_path / "app", portable_directory=portable, user_directory=fallback
    )

    assert location.directory == portable
    assert location.portable


def test_settings_store_wraps_directory_creation_failure(tmp_path):
    blocker = tmp_path / "not-a-directory"
    blocker.write_text("keep")
    with pytest.raises(StorageError):
        SettingsStore(blocker).save(Settings())
    assert blocker.read_text() == "keep"


def test_overlay_preserves_new_defaults_and_only_changes_edited_fields():
    from dataclasses import replace

    from modem_controller.catalog.models import load_starter_catalog
    from modem_controller.catalog.storage import catalog_overlay, merge_catalog_overlay

    defaults = load_starter_catalog()
    profile = defaults.profiles[0]
    command = profile.commands[0]
    changed_profile = replace(
        profile, commands=(replace(command, label="Mine"), *profile.commands[1:])
    )
    edited = replace(defaults, profiles=(changed_profile, *defaults.profiles[1:]))
    overlay = catalog_overlay(defaults, edited)
    upgraded_command = replace(command, help_text="New vendor guidance")
    upgraded = replace(
        defaults,
        profiles=(
            replace(profile, commands=(upgraded_command, *profile.commands[1:])),
            *defaults.profiles[1:],
        ),
    )
    merged = merge_catalog_overlay(upgraded, overlay)
    assert merged.profiles[0].commands[0].label == "Mine"
    assert merged.profiles[0].commands[0].help_text == "New vendor guidance"
    subset = replace(
        defaults,
        profiles=(
            replace(profile, commands=profile.commands[1:]),
            *defaults.profiles[1:],
        ),
    )
    restored = merge_catalog_overlay(defaults, catalog_overlay(defaults, subset))
    assert restored.profiles[0].commands == profile.commands[1:]


def test_selected_location_survives_restart_and_missing_folder_is_visible(tmp_path):
    from modem_controller.catalog.storage import (
        remember_settings_location,
        resolve_settings_location,
    )

    selected = tmp_path / "chosen"
    selected.mkdir()
    user = tmp_path / "user"
    remember_settings_location(user, selected)
    assert resolve_settings_location(tmp_path / "app", user).directory == selected
    selected.rmdir()
    fallback = resolve_settings_location(tmp_path / "app", user)
    assert "unavailable" in fallback.fallback_message
    assert not selected.exists()


def test_write_probe_does_not_overwrite_an_existing_file(tmp_path):
    (tmp_path / ".write-probe").write_text("user data")
    choose_settings_location(
        tmp_path, portable_directory=tmp_path, user_directory=tmp_path
    )
    assert (tmp_path / ".write-probe").read_text() == "user data"


@pytest.mark.parametrize(
    "payload,kind", [('AT+CPIN="1234"', "at"), ("41542B4350494E3D31323334", "bytes")]
)
def test_catalog_import_rejects_literal_credentials(tmp_path, payload, kind):
    from modem_controller.catalog.models import load_starter_catalog
    from modem_controller.catalog.storage import import_catalog_json

    data = load_starter_catalog().to_dict()
    data["profiles"][0]["commands"][0].update(payload=payload, kind=kind)
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps(data))
    with pytest.raises(StorageError, match="transient secret"):
        import_catalog_json(path)

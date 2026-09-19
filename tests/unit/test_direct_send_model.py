import json
from dataclasses import replace

import pytest

from modem_controller.catalog.models import (
    CatalogCommand,
    CatalogValidationError,
    load_starter_catalog,
)
from modem_controller.catalog.portable import load_portable_catalog, seed_catalog_files
from modem_controller.catalog.storage import (
    Settings,
    SettingsStore,
    catalog_overlay,
    merge_catalog_overlay,
)


def _generic_command(command_id: str):
    return load_starter_catalog().profile("generic-at").command(command_id)


def test_legacy_defaults_enable_only_reviewed_simple_presets() -> None:
    attention = _generic_command("attention")
    send_cr = _generic_command("send-cr")
    unlock_sim = _generic_command("unlock-sim")
    restart_modem = _generic_command("restart-modem")

    assert attention.direct_send is None
    assert attention.supports_direct_send_option
    assert attention.uses_direct_send
    assert send_cr.uses_direct_send
    assert not unlock_sim.uses_direct_send
    assert not restart_modem.uses_direct_send


def test_explicit_strategy_overrides_ordinary_presets() -> None:
    attention = _generic_command("attention")
    restart_modem = _generic_command("restart-modem")

    assert not replace(attention, direct_send=False).uses_direct_send
    assert replace(attention, direct_send=True).uses_direct_send
    assert restart_modem.supports_direct_send_option
    assert replace(restart_modem, direct_send=True).uses_direct_send
    assert not _generic_command("unlock-sim").supports_direct_send_option


def test_direct_send_is_strict_and_round_trips_native_json() -> None:
    attention = _generic_command("attention")
    legacy_data = attention.to_dict()
    legacy_data.pop("direct_send", None)

    legacy_command = CatalogCommand.from_dict(legacy_data)
    assert legacy_command.direct_send is None
    assert legacy_command.to_dict()["direct_send"] is None

    for invalid_value in ("true", 0, [], {}):
        with pytest.raises(CatalogValidationError, match="direct_send"):
            CatalogCommand.from_dict({**legacy_data, "direct_send": invalid_value})

    catalog = load_starter_catalog()
    profile = catalog.profile("generic-at")
    edited_profile = replace(
        profile,
        commands=tuple(
            replace(command, direct_send=False)
            if command.id == "attention"
            else command
            for command in profile.commands
        ),
    )
    edited_catalog = replace(
        catalog,
        profiles=tuple(
            edited_profile if item.id == edited_profile.id else item
            for item in catalog.profiles
        ),
    )

    restored = type(catalog).from_json(edited_catalog.to_json())
    assert restored.profile("generic-at").command("attention").direct_send is False


def test_direct_send_false_survives_settings_overlay_merge(tmp_path) -> None:
    defaults = load_starter_catalog()
    profile = defaults.profile("generic-at")
    edited_profile = replace(
        profile,
        commands=tuple(
            replace(command, direct_send=False)
            if command.id == "attention"
            else command
            for command in profile.commands
        ),
    )
    edited = replace(
        defaults,
        profiles=tuple(
            edited_profile if item.id == edited_profile.id else item
            for item in defaults.profiles
        ),
    )

    overlay = catalog_overlay(defaults, edited)
    store = SettingsStore(tmp_path)
    store.save(Settings(catalog_changes=overlay))
    persisted_overlay = store.load().settings.catalog_changes
    merged = merge_catalog_overlay(defaults, persisted_overlay)

    assert (
        overlay["profiles"]["generic-at"]["commands"]["attention"]["direct_send"]
        is False
    )
    assert merged.profile("generic-at").command("attention").direct_send is False


def test_portable_strategy_edit_stays_reviewed_but_payload_edit_is_unverified(
    tmp_path,
) -> None:
    seed_catalog_files(tmp_path)
    path = tmp_path / "generic-at.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    attention = data["profiles"][0]["commands"][0]
    attention["direct_send"] = False
    path.write_text(json.dumps(data), encoding="utf-8")

    strategy_only = load_portable_catalog(tmp_path)
    command = strategy_only.profile("generic-at").command("attention")
    assert command.direct_send is False
    assert command.is_visible

    attention["payload"] = "ATI"
    path.write_text(json.dumps(data), encoding="utf-8")

    assert (
        not load_portable_catalog(tmp_path)
        .profile("generic-at")
        .command("attention")
        .is_visible
    )

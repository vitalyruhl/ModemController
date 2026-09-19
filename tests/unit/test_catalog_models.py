from dataclasses import replace

import pytest

from modem_controller.catalog.models import (
    CatalogValidationError,
    CommandKind,
    CommandUnavailableError,
    RiskLevel,
    VerificationStatus,
    load_starter_catalog,
)


def test_starter_catalog_round_trips_and_preserves_control_bytes() -> None:
    catalog = load_starter_catalog()
    profile = catalog.profile("generic-at")

    payloads = {
        command.id: command.render()
        for command in profile.commands
        if command.kind is CommandKind.BYTES
    }

    assert payloads == {
        "send-cr": b"\x0d",
        "send-lf": b"\x0a",
        "send-crlf": b"\x0d\x0a",
        "send-escape": b"\x1b",
        "send-control-z": b"\x1a",
        "send-at-cr": b"AT\r",
    }
    assert type(catalog).from_json(catalog.to_json()) == catalog


def test_device_profile_packs_expose_only_reviewed_commands() -> None:
    catalog = load_starter_catalog()

    assert {profile.id for profile in catalog.profiles} == {
        "generic-at",
        "mc55i-qw",
        "tc35-tc35i",
        "mc93",
        "tc55i",
        "mc88-mc88i",
        "bg95-m3-observed",
        "analog-56k-legacy",
        "stollmann-isdn-legacy",
    }
    assert {command.id for command in catalog.profile("mc55i-qw").visible_commands} == {
        "attention",
        "identity",
    }
    assert {
        command.id for command in catalog.profile("tc35-tc35i").diagnostic_commands
    } == {"sim-status", "registration-status", "signal-quality"}
    for profile_id in ("mc93", "tc55i", "mc88-mc88i"):
        assert catalog.profile(profile_id).visible_commands == ()


def test_parameter_validation_keeps_sensitive_maintenance_actions_explicit() -> None:
    command = load_starter_catalog().profile("generic-at").command("unlock-sim")

    assert command.risk is RiskLevel.STATE_CHANGING
    assert command.render({"pin": "1234"}) == b"AT+CPIN=1234"
    with pytest.raises(CatalogValidationError, match="required"):
        command.render()
    with pytest.raises(CatalogValidationError, match="invalid value"):
        command.render({"pin": "not-a-pin"})
    with pytest.raises(CatalogValidationError, match="unexpected"):
        command.render({"pin": "1234", "extra": "value"})


def test_visible_and_diagnostic_commands_exclude_unverified_and_unsafe_entries() -> (
    None
):
    profile = load_starter_catalog().profile("generic-at")

    visible_ids = {command.id for command in profile.visible_commands}
    diagnostic_ids = {command.id for command in profile.diagnostic_commands}

    assert "unlock-sim" in visible_ids
    assert "ras-collector" not in visible_ids
    assert "send-control-z" in visible_ids
    assert "send-control-z" not in diagnostic_ids
    assert "unlock-sim" not in diagnostic_ids
    assert diagnostic_ids == {
        "attention",
        "identity",
        "sim-status",
        "registration-status",
        "signal-quality",
        "operator",
        "serial-baud-rate",
        "sms-storage",
    }


def test_unsupported_commands_are_excluded_from_visible_commands() -> None:
    profile = load_starter_catalog().profile("generic-at")
    unsupported = replace(
        profile.command("attention"), verification=VerificationStatus.UNSUPPORTED
    )
    updated = replace(profile, commands=(unsupported, *profile.commands[1:]))

    assert "attention" not in {command.id for command in updated.visible_commands}


def test_missing_reference_is_rejected() -> None:
    catalog = load_starter_catalog()
    profile = catalog.profile("generic-at")
    command = replace(profile.commands[0], references=("missing-reference",))
    invalid_profile = replace(profile, commands=(command, *profile.commands[1:]))

    with pytest.raises(CatalogValidationError, match="unknown sources"):
        replace(catalog, profiles=(invalid_profile,))


def test_shipped_and_user_notes_are_distinct() -> None:
    profile = load_starter_catalog().profile("generic-at")
    updated = replace(profile, user_notes="Observed with test adapter.")

    assert updated.shipped_notes == profile.shipped_notes
    assert updated.user_notes == "Observed with test adapter."


def test_external_tool_reference_cannot_render_or_enter_diagnostics() -> None:
    profile = load_starter_catalog().profile("generic-at")
    command = profile.command("ras-collector")

    with pytest.raises(CommandUnavailableError):
        command.render()
    assert command not in profile.diagnostic_commands


def test_bg95_scope_is_read_only_and_distinct_from_terminal_family():
    catalog = load_starter_catalog()
    profile = catalog.profile("bg95-m3-observed")
    assert "BG95M3LAR02A03" in profile.shipped_notes
    assert profile.connection_defaults["baud_rate"] == "115200"
    assert not profile.sms_text
    assert all(command.is_read_only_diagnostic for command in profile.commands)
    assert profile.command("eps-registration").render() == b"AT+CEREG?"
    assert profile.command("network-info").render() == b"AT+QNWINFO"
    assert {
        command.payload for command in catalog.profile("mc55i-qw").visible_commands
    } == {
        "AT",
        "ATI",
    }

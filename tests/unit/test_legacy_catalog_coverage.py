"""Historical templates remain outside automatically executable catalogs."""

import pytest

from modem_controller.catalog.models import (
    CommandKind,
    CommandUnavailableError,
    VerificationStatus,
    load_starter_catalog,
)
from modem_controller.workflows.maintenance import MaintenanceRunner, SequenceRunner


def test_generic_legacy_templates_are_disabled_and_not_diagnostic() -> None:
    """Prevents historical actions from entering visible or automatic diagnostics."""

    profile = load_starter_catalog().profile("generic-at")
    expected_ids = {
        "manufacturer",
        "model",
        "firmware",
        "serial-number",
        "capabilities",
        "disable-sim-pin",
        "unblock-sim",
        "sms-delete-read",
        "sms-delete-all",
        "sms-ira-charset",
        "dial-voice",
    }

    commands = {command.id: command for command in profile.commands}

    assert expected_ids <= commands.keys()
    assert all(
        commands[command_id].verification is VerificationStatus.UNVERIFIED
        for command_id in expected_ids
    )
    assert not (expected_ids & {command.id for command in profile.visible_commands})
    assert not (expected_ids & {command.id for command in profile.diagnostic_commands})
    assert profile.command("unlock-sim").verification is VerificationStatus.SUPPORTED


def test_legacy_sim_templates_require_only_transient_secret_parameters() -> None:
    """Prevents a legacy PIN/PUK template from becoming an executable default."""

    profile = load_starter_catalog().profile("generic-at")

    for command_id in ("disable-sim-pin", "unblock-sim"):
        command = profile.command(command_id)
        assert command.parameters
        assert all(parameter.secret for parameter in command.parameters)
        with pytest.raises(CommandUnavailableError):
            MaintenanceRunner.preview(command)


def test_legacy_init_profiles_are_present_but_not_visible() -> None:
    """Historical init templates must not become executable presets."""

    catalog = load_starter_catalog()

    for profile_id in ("analog-56k-legacy", "stollmann-isdn-legacy"):
        profile = catalog.profile(profile_id)
        assert profile.commands
        assert all(
            command.verification is VerificationStatus.UNVERIFIED
            for command in profile.commands
        )
        assert profile.visible_commands == ()
        assert profile.diagnostic_commands == ()


def test_tc35_legacy_init_sequence_references_disabled_individual_steps() -> None:
    """Historical TC35i steps remain inspectable, without executing a macro."""

    profile = load_starter_catalog().profile("tc35-tc35i")
    sequence = profile.command("init-legacy")
    commands = {command.id: command for command in profile.commands}

    assert sequence.kind is CommandKind.SEQUENCE
    assert sequence.verification is VerificationStatus.UNVERIFIED
    assert sequence.sequence_steps
    assert all(step.command_id in commands for step in sequence.sequence_steps)
    assert all(
        commands[step.command_id].verification is VerificationStatus.UNVERIFIED
        for step in sequence.sequence_steps
    )
    with pytest.raises(CommandUnavailableError):
        SequenceRunner.validate(sequence, profile)

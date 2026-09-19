"""Atomic persistence for user settings and catalog overlays."""

from __future__ import annotations

import json
import os
import re
import tempfile
from contextlib import suppress
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from modem_controller.catalog.models import (
    CatalogValidationError,
    CommandCatalog,
    CommandKind,
)
from modem_controller.transport.privacy import contains_secret_input

SETTINGS_SCHEMA_VERSION = 1
_SENSITIVE_KEYS = {"pin", "puk", "password", "secret"}


class StorageError(RuntimeError):
    """Base class for persistence failures that the UI can present to a user."""


class NewerSchemaError(StorageError):
    """Raised when data comes from an application version newer than this one."""


@dataclass(frozen=True, slots=True)
class Settings:
    selected_profile: str = "generic-at"
    selected_category: str = "Status"
    connection: dict[str, str] = field(default_factory=dict)
    last_directories: dict[str, str] = field(default_factory=dict)
    favorites: tuple[str, ...] = ()
    profile_notes: dict[str, str] = field(default_factory=dict)
    catalog_changes: dict[str, Any] = field(default_factory=dict)
    log_file: str = ""
    logging_enabled: bool = False
    logging_mode: str = "normal"

    def to_dict(self) -> dict[str, Any]:
        return {"schema_version": SETTINGS_SCHEMA_VERSION, **asdict(self)}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Settings:
        version = data.get("schema_version")
        if not isinstance(version, int):
            raise StorageError("settings schema_version is missing")
        if version > SETTINGS_SCHEMA_VERSION:
            raise NewerSchemaError("settings were created by a newer application")
        if version != SETTINGS_SCHEMA_VERSION:
            raise StorageError(f"unsupported settings schema version {version}")
        connection = _string_mapping(data, "connection")
        _reject_sensitive_values(connection)
        return cls(
            selected_profile=_string(data, "selected_profile", "generic-at"),
            selected_category=_string(data, "selected_category", "Status"),
            connection=connection,
            last_directories=_string_mapping(data, "last_directories"),
            favorites=tuple(_string_list(data, "favorites")),
            profile_notes=_string_mapping(data, "profile_notes"),
            catalog_changes=_catalog_changes(data),
            log_file=_string(data, "log_file", ""),
            logging_enabled=_bool(data, "logging_enabled", False),
            logging_mode=_logging_mode(data),
        )


@dataclass(frozen=True, slots=True)
class LoadResult:
    settings: Settings
    recovered: bool = False
    message: str = ""


@dataclass(frozen=True, slots=True)
class SettingsLocation:
    directory: Path
    portable: bool
    fallback_message: str = ""


class SettingsStore:
    """Reads and atomically writes settings without causing device-side effects."""

    def __init__(self, directory: Path, filename: str = "settings.json") -> None:
        self.directory = directory
        self.path = directory / filename

    def load(self) -> LoadResult:
        if not self.path.exists():
            return LoadResult(Settings())
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise StorageError("settings root must be an object")
            return LoadResult(Settings.from_dict(data))
        except NewerSchemaError:
            raise
        except (OSError, json.JSONDecodeError, StorageError) as error:
            return LoadResult(Settings(), recovered=True, message=str(error))

    def save(self, settings: Settings) -> None:
        _reject_sensitive_values(settings.connection)
        self.save_raw(json.dumps(settings.to_dict(), indent=2, sort_keys=True) + "\n")

    def save_raw(self, payload: str) -> None:
        temporary_path = None
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            descriptor, name = tempfile.mkstemp(
                prefix=f".{self.path.name}.", suffix=".tmp", dir=self.directory
            )
            temporary_path = Path(name)
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, self.path)
        except OSError as error:
            raise StorageError(f"could not save data: {error}") from error
        finally:
            if temporary_path is not None:
                with suppress(OSError):
                    temporary_path.unlink(missing_ok=True)


def choose_settings_location(
    application_directory: Path,
    *,
    portable_directory: Path | None = None,
    user_directory: Path,
) -> SettingsLocation:
    """Prefer an explicit writable portable path, otherwise use a visible fallback."""

    candidate = portable_directory or application_directory / "data"
    try:
        candidate.mkdir(parents=True, exist_ok=True)
        _probe_directory(candidate)
        return SettingsLocation(candidate, portable=True)
    except OSError:
        try:
            user_directory.mkdir(parents=True, exist_ok=True)
            _probe_directory(user_directory)
        except OSError as error:
            raise StorageError(f"No writable settings location: {error}") from error
        return SettingsLocation(
            user_directory,
            portable=False,
            fallback_message=(
                "Portable settings are unavailable; using the selected user directory."
            ),
        )


def _probe_directory(directory: Path) -> None:
    with tempfile.TemporaryFile(dir=directory) as probe:
        probe.write(b"probe")
        probe.flush()


def resolve_settings_location(
    application_directory: Path, user_directory: Path
) -> SettingsLocation:
    """Honor an explicit saved location without creating a locator at startup."""
    locator = user_directory / "location.json"
    message = ""
    if locator.exists():
        try:
            data = json.loads(locator.read_text(encoding="utf-8"))
            selected = Path(data["directory"])
            if not selected.is_absolute() or not selected.is_dir():
                raise ValueError("Selected settings directory is missing")
            _probe_directory(selected)
            return SettingsLocation(selected, portable=False)
        except (OSError, ValueError, KeyError, TypeError) as error:
            message = f"Selected settings location unavailable ({error}). "
    location = choose_settings_location(
        application_directory, user_directory=user_directory
    )
    return SettingsLocation(
        location.directory, location.portable, message + location.fallback_message
    )


def remember_settings_location(user_directory: Path, selected: Path) -> None:
    SettingsStore(user_directory, "location.json").save_raw(
        json.dumps({"directory": str(selected.resolve())}) + "\n"
    )


def export_catalog_json(catalog: CommandCatalog, destination: Path) -> None:
    """Export a validated native catalog object with atomic replacement."""

    validate_persisted_catalog(catalog)
    SettingsStore(destination.parent, destination.name).save_raw(catalog.to_json())


def _string(data: dict[str, Any], key: str, default: str) -> str:
    value = data.get(key, default)
    if not isinstance(value, str):
        raise StorageError(f"{key} must be text")
    return value


def _string_mapping(data: dict[str, Any], key: str) -> dict[str, str]:
    value = data.get(key, {})
    if not isinstance(value, dict) or not all(
        isinstance(name, str) and isinstance(item, str) for name, item in value.items()
    ):
        raise StorageError(f"{key} must be a string mapping")
    return dict(value)


def _string_list(data: dict[str, Any], key: str) -> list[str]:
    value = data.get(key, [])
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise StorageError(f"{key} must be a string list")
    return value


def _bool(data: dict[str, Any], key: str, default: bool) -> bool:
    value = data.get(key, default)
    if not isinstance(value, bool):
        raise StorageError(f"{key} must be true or false")
    return value


def _logging_mode(data: dict[str, Any]) -> str:
    value = _string(data, "logging_mode", "normal")
    if value not in {"normal", "verbose"}:
        raise StorageError("logging_mode must be normal or verbose")
    return value


def _reject_sensitive_values(values: dict[str, str]) -> None:
    if _SENSITIVE_KEYS & {key.casefold() for key in values}:
        raise StorageError("PIN, PUK, and passwords must not be persisted")


def _catalog_changes(data: dict[str, Any]) -> dict[str, Any]:
    changes = data.get("catalog_changes", {})
    if not isinstance(changes, dict):
        raise StorageError("catalog_changes must be an object")
    return deepcopy(changes)


def catalog_overlay(defaults: CommandCatalog, edited: CommandCatalog) -> dict[str, Any]:
    """Persist field-level differences; new bundled defaults remain upgradeable."""
    baseline = {p.id: p.to_dict() for p in defaults.profiles}
    profiles = {}
    for profile in edited.profiles:
        current = profile.to_dict()
        old = baseline.get(profile.id, {})
        patch = {
            k: v for k, v in current.items() if k != "commands" and old.get(k) != v
        }
        old_commands = {c["id"]: c for c in old.get("commands", [])}
        commands = {}
        for command in current["commands"]:
            previous = old_commands.get(command["id"], {})
            difference = {k: v for k, v in command.items() if previous.get(k) != v}
            if difference:
                commands[command["id"]] = difference
        if commands:
            patch["commands"] = commands
        order = [c["id"] for c in current["commands"]]
        if order != list(old_commands):
            patch["order"] = order
        removed = [key for key in old_commands if key not in order]
        if removed:
            patch["removed_commands"] = removed
        if patch:
            profiles[profile.id] = patch
    return {
        "profiles": profiles,
        "references": {
            k: v
            for k, v in edited.references.items()
            if defaults.references.get(k) != v
        },
    }


def merge_catalog_overlay(
    defaults: CommandCatalog, changes: dict[str, Any]
) -> CommandCatalog:
    try:
        root = defaults.to_dict()
        root["references"].update(changes.get("references", {}))
        profiles = {p["id"]: p for p in root["profiles"]}
        for profile_id, patch in changes.get("profiles", {}).items():
            profile = profiles.setdefault(
                profile_id, {"id": profile_id, "commands": []}
            )
            commands = {c["id"]: c for c in profile["commands"]}
            for key in patch.get("removed_commands", []):
                commands.pop(key, None)
            for command_id, command_patch in patch.get("commands", {}).items():
                commands.setdefault(command_id, {"id": command_id}).update(
                    command_patch
                )
            order = list(dict.fromkeys([*patch.get("order", []), *commands]))
            profile.update(
                {
                    k: v
                    for k, v in patch.items()
                    if k not in {"commands", "order", "removed_commands"}
                }
            )
            profile["commands"] = [commands[key] for key in order if key in commands]
        root["profiles"] = list(profiles.values())
        result = CommandCatalog.from_dict(root)
        validate_persisted_catalog(result)
        return result
    except (TypeError, KeyError, AttributeError, ValueError) as error:
        raise StorageError(f"Invalid catalog changes: {error}") from error


def validate_persisted_catalog(catalog: CommandCatalog) -> None:
    if not catalog.profiles:
        raise CatalogValidationError("At least one profile is required")
    for profile in catalog.profiles:
        for command in profile.commands:
            text = command.payload or ""
            payload = (
                bytes.fromhex(text)
                if command.kind is CommandKind.BYTES
                else text.encode("utf-8")
            )
            if not contains_secret_input(payload):
                continue
            match = re.fullmatch(r"AT\+(CPIN|CPWD|CLCK)\s*=(.+)", text, re.I)
            valid = False
            if match:
                arguments = [value.strip().strip('"') for value in match[2].split(",")]
                secret_names = {
                    "{" + p.name + "}" for p in command.parameters if p.secret
                }
                start = {"CPIN": 0, "CPWD": 1, "CLCK": 2}[match[1].upper()]
                expected = {"CPIN": (1, 2), "CPWD": (3,), "CLCK": (3,)}[
                    match[1].upper()
                ]
                valid = len(arguments) in expected and all(
                    value in secret_names for value in arguments[start:]
                )
            if not valid:
                raise CatalogValidationError(
                    "Credential commands need transient secret parameters, "
                    "not saved values"
                )


def import_catalog_json(source: Path, *, max_bytes: int = 1048576) -> CommandCatalog:
    try:
        with source.open("rb") as stream:
            data = stream.read(max_bytes + 1)
        if len(data) > max_bytes:
            raise StorageError("Catalog exceeds the import size limit")
        catalog = CommandCatalog.from_json(data.decode("utf-8-sig"))
        validate_persisted_catalog(catalog)
        return catalog
    except (OSError, UnicodeError, ValueError) as error:
        raise StorageError(f"Could not import catalog: {error}") from error


def last_directory(settings: Settings, purpose: str, fallback: Path) -> Path:
    saved = Path(settings.last_directories.get(purpose, str(fallback)))
    return saved if saved.is_dir() else fallback

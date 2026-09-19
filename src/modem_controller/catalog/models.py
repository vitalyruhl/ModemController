"""Validated, GUI-independent models for versioned modem command catalogs."""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from enum import Enum
from importlib.resources import files
from typing import Any

CATALOG_SCHEMA_VERSION = 1
_PARAMETER_PATTERN = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")


class CatalogValidationError(ValueError):
    """Raised when catalog data cannot meet the documented schema contract."""


class CommandUnavailableError(RuntimeError):
    """Raised when a catalog entry has no executable transport payload."""


class CommandKind(str, Enum):
    AT = "at"
    BYTES = "bytes"
    SEQUENCE = "sequence"
    EXTERNAL_TOOL = "external_tool"


class RiskLevel(str, Enum):
    READ_ONLY = "read_only"
    STATE_CHANGING = "state_changing"
    DESTRUCTIVE = "destructive"


class VerificationStatus(str, Enum):
    SUPPORTED = "supported"
    UNSUPPORTED = "unsupported"
    UNVERIFIED = "unverified"


@dataclass(frozen=True, slots=True)
class ParameterDefinition:
    name: str
    label: str
    required: bool = True
    secret: bool = False
    pattern: str | None = None

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", self.name):
            raise CatalogValidationError("parameter name must be an identifier")
        if not self.label.strip():
            raise CatalogValidationError("parameter label must not be empty")
        if self.pattern is not None:
            try:
                re.compile(self.pattern)
            except re.error as error:
                raise CatalogValidationError(
                    f"invalid pattern for parameter {self.name}"
                ) from error

    def validate(self, value: str) -> None:
        if not isinstance(value, str):
            raise CatalogValidationError(f"parameter {self.name} must be text")
        if self.required and not value:
            raise CatalogValidationError(f"parameter {self.name} is required")
        if (
            self.pattern is not None
            and value
            and re.fullmatch(self.pattern, value) is None
        ):
            raise CatalogValidationError(f"parameter {self.name} has an invalid value")

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "label": self.label,
            "required": self.required,
            "secret": self.secret,
            "pattern": self.pattern,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ParameterDefinition:
        return cls(
            name=_required_string(data, "name"),
            label=_required_string(data, "label"),
            required=_optional_bool(data, "required", True),
            secret=_optional_bool(data, "secret", False),
            pattern=_optional_string(data, "pattern"),
        )


@dataclass(frozen=True, slots=True)
class SequenceStep:
    """A reference to one reviewed command, never executable code or a macro."""

    command_id: str
    expected_contains: str = ""
    timeout_seconds: float = 2.0
    delay_seconds: float = 0.0

    def __post_init__(self) -> None:
        _validate_identifier(self.command_id, "sequence command id")
        if not isinstance(self.expected_contains, str):
            raise CatalogValidationError("sequence condition must be text")
        if not self.expected_contains.isascii():
            raise CatalogValidationError("sequence conditions must be ASCII")
        if not all(
            isinstance(value, int | float) and not isinstance(value, bool)
            for value in (self.timeout_seconds, self.delay_seconds)
        ):
            raise CatalogValidationError("sequence timing must be numeric")
        if not 0 < self.timeout_seconds <= 60 or not 0 <= self.delay_seconds <= 10:
            raise CatalogValidationError("sequence timing exceeds bounded limits")

    def to_dict(self) -> dict[str, Any]:
        return {
            "command_id": self.command_id,
            "expected_contains": self.expected_contains,
            "timeout_seconds": self.timeout_seconds,
            "delay_seconds": self.delay_seconds,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SequenceStep:
        if set(data) - {
            "command_id",
            "expected_contains",
            "timeout_seconds",
            "delay_seconds",
        }:
            raise CatalogValidationError("unknown sequence step fields")
        return cls(
            _required_string(data, "command_id"),
            _optional_string(data, "expected_contains") or "",
            _positive_number(data, "timeout_seconds"),
            data.get("delay_seconds", 0),
        )


@dataclass(frozen=True, slots=True)
class CatalogCommand:
    id: str
    label: str
    category: str
    kind: CommandKind
    payload: str | None
    help_text: str
    risk: RiskLevel
    applicability: tuple[str, ...]
    references: tuple[str, ...]
    verification: VerificationStatus
    expected_response: str
    timeout_seconds: float
    parameters: tuple[ParameterDefinition, ...] = ()
    external_tool_id: str | None = None
    sequence_steps: tuple[SequenceStep, ...] = ()

    def __post_init__(self) -> None:
        _validate_identifier(self.id, "command id")
        if (
            not self.label.strip()
            or not self.category.strip()
            or not self.help_text.strip()
        ):
            raise CatalogValidationError(
                "command label, category, and help text are required"
            )
        if not self.applicability:
            raise CatalogValidationError("command applicability must not be empty")
        if not self.references:
            raise CatalogValidationError("command references must not be empty")
        if not math.isfinite(self.timeout_seconds) or self.timeout_seconds <= 0:
            raise CatalogValidationError("command timeout_seconds must be positive")
        if len({parameter.name for parameter in self.parameters}) != len(
            self.parameters
        ):
            raise CatalogValidationError("command parameter names must be unique")
        if self.kind is CommandKind.EXTERNAL_TOOL:
            if self.external_tool_id is None or self.payload is not None:
                raise CatalogValidationError(
                    "external tool commands need an ID and no transport payload"
                )
        elif self.kind is CommandKind.SEQUENCE:
            if self.payload is not None or not 1 <= len(self.sequence_steps) <= 32:
                raise CatalogValidationError(
                    "sequences require 1-32 steps and no payload"
                )
        elif self.payload is None:
            raise CatalogValidationError("transport commands require a payload")
        if self.kind is not CommandKind.SEQUENCE and self.sequence_steps:
            raise CatalogValidationError("only sequence commands can define steps")
        if self.kind is CommandKind.BYTES and self.payload is not None:
            try:
                bytes.fromhex(self.payload)
            except ValueError as error:
                raise CatalogValidationError(
                    "byte payload must be valid hexadecimal"
                ) from error
        placeholders = set(_PARAMETER_PATTERN.findall(self.payload or ""))
        declared = {parameter.name for parameter in self.parameters}
        if self.kind is not CommandKind.SEQUENCE and placeholders != declared:
            raise CatalogValidationError(
                "payload placeholders must match declared command parameters"
            )

    @property
    def is_visible(self) -> bool:
        return self.verification is VerificationStatus.SUPPORTED

    @property
    def is_read_only_diagnostic(self) -> bool:
        return (
            self.is_visible
            and self.kind is CommandKind.AT
            and self.risk is RiskLevel.READ_ONLY
        )

    def render(self, values: dict[str, str] | None = None) -> bytes:
        """Render an exact byte payload; this method never executes an action."""

        if self.kind is CommandKind.EXTERNAL_TOOL:
            raise CommandUnavailableError(
                "external tools are not executable from a catalog"
            )
        if self.kind is CommandKind.SEQUENCE:
            raise CommandUnavailableError("sequences need a workflow runner")

        values = values or {}
        expected = {parameter.name for parameter in self.parameters}
        unexpected = set(values) - expected
        if unexpected:
            raise CatalogValidationError(
                f"unexpected command parameters: {', '.join(sorted(unexpected))}"
            )
        for parameter in self.parameters:
            if parameter.name not in values:
                if parameter.required:
                    raise CatalogValidationError(
                        f"parameter {parameter.name} is required"
                    )
                continue
            parameter.validate(values[parameter.name])

        payload = (self.payload or "").format(**values)
        if self.kind is CommandKind.BYTES:
            return bytes.fromhex(payload)
        try:
            return payload.encode("ascii")
        except UnicodeEncodeError as error:
            raise CatalogValidationError("AT commands must be ASCII") from error

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "category": self.category,
            "kind": self.kind.value,
            "payload": self.payload,
            "help_text": self.help_text,
            "risk": self.risk.value,
            "applicability": list(self.applicability),
            "references": list(self.references),
            "verification": self.verification.value,
            "expected_response": self.expected_response,
            "timeout_seconds": self.timeout_seconds,
            "parameters": [parameter.to_dict() for parameter in self.parameters],
            "external_tool_id": self.external_tool_id,
            "sequence_steps": [step.to_dict() for step in self.sequence_steps],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CatalogCommand:
        return cls(
            id=_required_string(data, "id"),
            label=_required_string(data, "label"),
            category=_required_string(data, "category"),
            kind=_parse_enum(CommandKind, data, "kind"),
            payload=_optional_string(data, "payload"),
            help_text=_required_string(data, "help_text"),
            risk=_parse_enum(RiskLevel, data, "risk"),
            applicability=_string_tuple(data, "applicability"),
            references=_string_tuple(data, "references"),
            verification=_parse_enum(VerificationStatus, data, "verification"),
            expected_response=_required_string(data, "expected_response"),
            timeout_seconds=_positive_number(data, "timeout_seconds"),
            parameters=tuple(
                ParameterDefinition.from_dict(item)
                for item in _object_list(data, "parameters")
            ),
            external_tool_id=_optional_string(data, "external_tool_id"),
            sequence_steps=tuple(
                SequenceStep.from_dict(step)
                for step in _object_list(data, "sequence_steps")
            ),
        )


@dataclass(frozen=True, slots=True)
class DeviceProfile:
    id: str
    name: str
    shipped_notes: str
    user_notes: str
    commands: tuple[CatalogCommand, ...]
    connection_defaults: dict[str, str] = field(default_factory=dict)
    sms_text: bool = False

    def __post_init__(self) -> None:
        _validate_identifier(self.id, "profile id")
        if not isinstance(self.connection_defaults, dict) or not all(
            isinstance(key, str) and isinstance(value, str)
            for key, value in self.connection_defaults.items()
        ):
            raise CatalogValidationError(
                "profile connection defaults must be text fields"
            )
        if not self.name.strip() or not self.shipped_notes.strip():
            raise CatalogValidationError("profile name and shipped notes are required")
        command_ids = [command.id for command in self.commands]
        if len(set(command_ids)) != len(command_ids):
            raise CatalogValidationError("command IDs must be unique within a profile")
        for command in self.commands:
            if command.kind is not CommandKind.SEQUENCE:
                continue
            for index, step in enumerate(command.sequence_steps):
                try:
                    target = self.command(step.command_id)
                except KeyError as error:
                    raise CatalogValidationError(
                        "sequence references an unknown command"
                    ) from error
                if target.kind not in {CommandKind.AT, CommandKind.BYTES}:
                    raise CatalogValidationError(
                        "sequence steps must be individual AT/byte commands"
                    )
                if any(p.secret for p in target.parameters) and (
                    index != len(command.sequence_steps) - 1 or step.expected_contains
                ):
                    raise CatalogValidationError(
                        "a secret step must be last, without a text condition"
                    )

    @property
    def visible_commands(self) -> tuple[CatalogCommand, ...]:
        return tuple(command for command in self.commands if command.is_visible)

    @property
    def diagnostic_commands(self) -> tuple[CatalogCommand, ...]:
        return tuple(
            command
            for command in self.visible_commands
            if command.is_read_only_diagnostic
        )

    def command(self, command_id: str) -> CatalogCommand:
        for command in self.commands:
            if command.id == command_id:
                return command
        raise KeyError(command_id)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "shipped_notes": self.shipped_notes,
            "user_notes": self.user_notes,
            "commands": [command.to_dict() for command in self.commands],
            "connection_defaults": self.connection_defaults,
            "sms_text": self.sms_text,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DeviceProfile:
        return cls(
            id=_required_string(data, "id"),
            name=_required_string(data, "name"),
            shipped_notes=_required_string(data, "shipped_notes"),
            user_notes=_optional_string(data, "user_notes") or "",
            commands=tuple(
                CatalogCommand.from_dict(item)
                for item in _object_list(data, "commands")
            ),
            connection_defaults=data.get("connection_defaults", {}),
            sms_text=_optional_bool(data, "sms_text", False),
        )


@dataclass(frozen=True, slots=True)
class CommandCatalog:
    schema_version: int
    references: dict[str, str]
    profiles: tuple[DeviceProfile, ...]

    def __post_init__(self) -> None:
        if self.schema_version != CATALOG_SCHEMA_VERSION:
            raise CatalogValidationError(
                f"unsupported catalog schema version {self.schema_version}"
            )
        if not self.references or any(
            not value.strip() for value in self.references.values()
        ):
            raise CatalogValidationError("catalog references must not be empty")
        profile_ids = [profile.id for profile in self.profiles]
        if len(set(profile_ids)) != len(profile_ids):
            raise CatalogValidationError("profile IDs must be unique")
        for profile in self.profiles:
            for command in profile.commands:
                missing = set(command.references) - set(self.references)
                if missing:
                    raise CatalogValidationError(
                        f"command {command.id} references unknown sources: "
                        f"{', '.join(sorted(missing))}"
                    )

    def profile(self, profile_id: str) -> DeviceProfile:
        for profile in self.profiles:
            if profile.id == profile_id:
                return profile
        raise KeyError(profile_id)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "references": dict(self.references),
            "profiles": [profile.to_dict() for profile in self.profiles],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CommandCatalog:
        references = data.get("references")
        if not isinstance(references, dict) or not all(
            isinstance(key, str) and isinstance(value, str)
            for key, value in references.items()
        ):
            raise CatalogValidationError("references must be a string mapping")
        schema_version = data.get("schema_version")
        if not isinstance(schema_version, int):
            raise CatalogValidationError("schema_version must be an integer")
        return cls(
            schema_version=schema_version,
            references=dict(references),
            profiles=tuple(
                DeviceProfile.from_dict(item) for item in _object_list(data, "profiles")
            ),
        )

    @classmethod
    def from_json(cls, text: str) -> CommandCatalog:
        try:
            data = json.loads(text)
        except json.JSONDecodeError as error:
            raise CatalogValidationError("catalog is not valid JSON") from error
        if not isinstance(data, dict):
            raise CatalogValidationError("catalog root must be an object")
        return cls.from_dict(data)


def load_starter_catalog() -> CommandCatalog:
    """Load all reviewed, bundled profile packs into one validated catalog."""

    data_directory = files("modem_controller.catalog").joinpath("data")
    catalogs = [
        CommandCatalog.from_json(path.read_text(encoding="utf-8"))
        for path in sorted(data_directory.iterdir(), key=lambda path: path.name)
        if path.name.endswith(".json")
    ]
    references: dict[str, str] = {}
    profiles: list[DeviceProfile] = []
    for catalog in catalogs:
        for reference_id, source in catalog.references.items():
            existing = references.setdefault(reference_id, source)
            if existing != source:
                raise CatalogValidationError(
                    f"reference {reference_id} has conflicting bundled sources"
                )
        profiles.extend(catalog.profiles)
    return CommandCatalog(CATALOG_SCHEMA_VERSION, references, tuple(profiles))


def _required_string(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise CatalogValidationError(f"{key} must be a non-empty string")
    return value


def _optional_string(data: dict[str, Any], key: str) -> str | None:
    value = data.get(key)
    if value is not None and not isinstance(value, str):
        raise CatalogValidationError(f"{key} must be a string when present")
    return value


def _optional_bool(data: dict[str, Any], key: str, default: bool) -> bool:
    value = data.get(key, default)
    if not isinstance(value, bool):
        raise CatalogValidationError(f"{key} must be a boolean")
    return value


def _string_tuple(data: dict[str, Any], key: str) -> tuple[str, ...]:
    value = data.get(key)
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item for item in value
    ):
        raise CatalogValidationError(f"{key} must be a non-empty list of strings")
    return tuple(value)


def _object_list(data: dict[str, Any], key: str) -> list[dict[str, Any]]:
    value = data.get(key, [])
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise CatalogValidationError(f"{key} must be a list of objects")
    return value


def _positive_number(data: dict[str, Any], key: str) -> float:
    value = data.get(key)
    if not isinstance(value, int | float) or isinstance(value, bool) or value <= 0:
        raise CatalogValidationError(f"{key} must be a positive number")
    return float(value)


def _parse_enum(enum_type: type[Enum], data: dict[str, Any], key: str) -> Any:
    value = _required_string(data, key)
    try:
        return enum_type(value)
    except ValueError as error:
        raise CatalogValidationError(f"invalid {key}: {value}") from error


def _validate_identifier(value: str, label: str) -> None:
    if not re.fullmatch(r"[a-z][a-z0-9-]*", value):
        raise CatalogValidationError(f"{label} must use lowercase kebab-case")

"""Bounded legacy XML/VCE preview; source data is never executed or rewritten."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from pathlib import Path
from xml.etree import ElementTree

from modem_controller.catalog.models import (
    CatalogCommand,
    CommandCatalog,
    CommandKind,
    DeviceProfile,
    RiskLevel,
    VerificationStatus,
    load_starter_catalog,
)
from modem_controller.catalog.storage import validate_persisted_catalog
from modem_controller.transport.privacy import contains_secret_input


@dataclass(frozen=True, slots=True)
class LegacyEntry:
    label: str
    payload: str
    warnings: tuple[str, ...]


def _decode_name(text: str) -> str:
    return re.sub(r"_x([0-9a-fA-F]{4})_", lambda match: chr(int(match[1], 16)), text)


def preview_legacy(
    text: str, format: str, max_bytes: int = 1048576
) -> tuple[LegacyEntry, ...]:
    if max_bytes <= 0 or len(text.encode("utf-8")) > max_bytes:
        raise ValueError("Legacy source exceeds the size limit")
    entries = []
    if format.casefold() == "xml":
        if re.search(r"<!\s*(DOCTYPE|ENTITY)", text, re.I):
            raise ValueError("DTD and entity declarations are not supported")
        try:
            root = ElementTree.fromstring(text)
        except ElementTree.ParseError as error:
            raise ValueError("Malformed legacy XML") from error
        for element in root.iter():
            if "Description" in element.attrib:
                entries.append(
                    (
                        _decode_name(element.tag),
                        _decode_name(element.attrib["Description"]),
                    )
                )
    elif format.casefold() == "vce":
        entries = [
            (f"Legacy line {index}", line)
            for index, line in enumerate(text.splitlines(), 1)
            if line.strip()
        ]
    else:
        raise ValueError("Only legacy XML and VCE are supported")
    if len(entries) > 1000:
        raise ValueError("Legacy import is limited to 1000 entries")
    known = {
        command.payload.upper()
        for profile in load_starter_catalog().profiles
        for command in profile.commands
        if command.is_read_only_diagnostic and command.payload
    }
    result, seen = [], set()
    for label, payload in entries:
        warnings = []
        normalized = payload.strip().upper()
        if normalized in seen:
            warnings.append("Duplicate payload; choose deliberately.")
        seen.add(normalized)
        if any(char in payload for char in ("|", ";", "\r", "\n")):
            warnings.append(
                "Compound syntax: split into reviewed sequence steps manually."
            )
        if normalized not in known:
            warnings.append("Unknown applicability; state-changing behavior may occur.")
        if normalized == "AT#CMGF=1":
            warnings.append(
                "Unverified historical spelling; preserved without correction."
            )
        if contains_secret_input(payload.encode("utf-8")):
            warnings.append(
                "Credential literal cannot be imported; use transient parameters."
            )
        result.append(LegacyEntry(label, payload, tuple(warnings)))
    return tuple(result)


def load_legacy(source: Path, max_bytes: int = 1048576) -> tuple[LegacyEntry, ...]:
    if max_bytes <= 0:
        raise ValueError("Legacy size limit must be positive")
    with source.open("rb") as handle:
        data = handle.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise ValueError("Legacy source exceeds the size limit")
    encoding = "utf-16" if data.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig"
    return preview_legacy(
        data.decode(encoding), source.suffix.lstrip("."), max_bytes=max_bytes
    )


def import_reviewed_selection(
    catalog: CommandCatalog, entries: tuple[LegacyEntry, ...]
) -> CommandCatalog:
    if not entries:
        raise ValueError("Select at least one entry")
    number = 1
    while any(profile.id == f"legacy-import-{number}" for profile in catalog.profiles):
        number += 1
    profile_id = f"legacy-import-{number}"
    reference = profile_id
    while reference in catalog.references:
        reference += "-source"
    commands = tuple(
        CatalogCommand(
            id=f"legacy-{index}",
            label=entry.label,
            category="Imported",
            kind=CommandKind.AT,
            payload=entry.payload,
            help_text="Imported source text; review command, applicability and risk. "
            + " ".join(entry.warnings),
            risk=RiskLevel.STATE_CHANGING,
            applicability=(profile_id,),
            references=(reference,),
            verification=VerificationStatus.UNVERIFIED,
            expected_response="Review required",
            timeout_seconds=2,
        )
        for index, entry in enumerate(entries, 1)
    )
    profile = DeviceProfile(
        profile_id,
        f"Legacy import {number}",
        "Selected legacy text, disabled pending per-command review. "
        "Original source is unchanged.",
        "",
        commands,
    )
    result = replace(
        catalog,
        references={
            **catalog.references,
            reference: "User-selected legacy source; review required.",
        },
        profiles=(*catalog.profiles, profile),
    )
    validate_persisted_catalog(result)
    return result

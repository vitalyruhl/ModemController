"""Editable flat sidecars merged against their original shipped baseline."""

import json
from dataclasses import replace
from importlib.resources import files
from pathlib import Path

from modem_controller.catalog.models import (
    CommandCatalog,
    VerificationStatus,
    load_starter_catalog,
)
from modem_controller.catalog.storage import (
    StorageError,
    catalog_overlay,
    merge_catalog_overlay,
    validate_persisted_catalog,
)

CATALOG_FILES = ("device-profiles.json", "generic-at.json")


def seed_catalog_files(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for name in CATALOG_FILES:
        path = directory / name
        if path.exists():
            continue
        original = json.loads(
            files("modem_controller.catalog")
            .joinpath("data", name)
            .read_text(encoding="utf-8")
        )
        payload = {**original, "_shipped_baseline": original}
        try:
            with path.open("x", encoding="utf-8") as stream:
                json.dump(payload, stream, indent=2)
                stream.write("\n")
        except FileExistsError:
            pass


def load_portable_catalog(directory: Path, *, defaults=None) -> CommandCatalog:
    defaults = defaults or load_starter_catalog()
    current = defaults
    for name in CATALOG_FILES:
        path = directory / name
        if not path.exists():
            continue
        try:
            with path.open("rb") as stream:
                raw = stream.read(2 * 1024 * 1024 + 1)
            if len(raw) > 2 * 1024 * 1024:
                raise ValueError("Catalog exceeds 2 MiB")
            data = json.loads(raw.decode("utf-8-sig"))
            if not isinstance(data, dict):
                raise ValueError("Catalog root must be an object")
            edited = CommandCatalog.from_dict(data)
            validate_persisted_catalog(edited)
            baseline_data = data.get("_shipped_baseline", data)
            if not isinstance(baseline_data, dict):
                raise ValueError("Shipped baseline must be an object")
            baseline = CommandCatalog.from_dict(baseline_data)
            validate_persisted_catalog(baseline)
            if "_shipped_baseline" not in data:
                # Legacy sidecars are explicit complete profile overrides.
                ids = {p.id for p in edited.profiles}
                baseline = replace(
                    defaults,
                    profiles=tuple(p for p in defaults.profiles if p.id in ids),
                )
            current = merge_catalog_overlay(current, catalog_overlay(baseline, edited))
        except (OSError, ValueError, TypeError, KeyError) as error:
            raise StorageError(f"Invalid portable catalog {name}: {error}") from error
    shipped = {(p.id, c.id): c for p in defaults.profiles for c in p.commands}
    current = replace(
        current,
        profiles=tuple(
            replace(
                p,
                commands=tuple(
                    c
                    if c == shipped.get((p.id, c.id))
                    else replace(c, verification=VerificationStatus.UNVERIFIED)
                    for c in p.commands
                ),
            )
            for p in current.profiles
        ),
    )
    validate_persisted_catalog(current)
    return current

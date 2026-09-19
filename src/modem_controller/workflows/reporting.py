"""Explicit redacted report export, separate from sensitive byte capture."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from modem_controller.catalog.storage import SettingsStore
from modem_controller.transport.capture import CaptureRecord, CaptureSnapshot
from modem_controller.workflows.diagnostics import DiagnosticResult

_SENSITIVE = re.compile(
    r"(\+?\d{6,}|[A-Za-z]:[\\/][^\r\n,;]+|\\\\[^\s]+|https?://[^\s]+|[\w.+-]+@[\w.-]+|\b(?:\d{1,3}\.){3}\d{1,3}\b)",
    re.I,
)
_CREDENTIAL = re.compile(r"(?:AT)?\+(?:CPIN|CLCK|CPWD)\s*=[^\r\n]*", re.I)
_PRIVATE_FIELD = re.compile(
    r"(?:password|username|user|message|body|text|endpoint)\s*[:=]\s*[^\r\n]+", re.I
)
_PRIVATE_KEYS = {
    "pin",
    "puk",
    "password",
    "secret",
    "user",
    "username",
    "body",
    "message",
    "notes",
    "profile_notes",
}


def redact(value: str) -> str:
    value = _CREDENTIAL.sub("<sensitive input redacted>", value)
    value = _PRIVATE_FIELD.sub("<private field redacted>", value)
    return _SENSITIVE.sub("<redacted>", value)


def _clean(value):
    if isinstance(value, str):
        return redact(value)
    if isinstance(value, dict):
        return {
            redact(str(key)): "<redacted>"
            if str(key).casefold() in _PRIVATE_KEYS
            else _clean(item)
            for key, item in value.items()
        }
    if isinstance(value, list | tuple):
        return [_clean(item) for item in value]
    return value


def product_version() -> str:
    try:
        return version("modem-controller-rs232")
    except PackageNotFoundError:
        return "unversioned development source"


def render_report(
    results: tuple[DiagnosticResult, ...],
    settings: dict[str, str],
    *,
    profile_id: str = "unknown",
    profile_version: str = "catalog schema 1",
    capture: CaptureSnapshot | None = None,
    metadata: dict | None = None,
) -> dict[str, object]:
    evidence = capture or CaptureSnapshot()
    report = {
        "report_schema": 1,
        "generated_utc": datetime.now(UTC).isoformat(timespec="milliseconds"),
        "app_version": product_version(),
        "profile": profile_id,
        "profile_version": profile_version,
        "settings": settings,
        "capture": evidence.summary(),
        "notice": (
            "Redacted diagnostic report. Raw bytes require a separate "
            "explicit export. Review before sharing."
        ),
        "metadata": metadata or {},
        "results": [
            {
                "command": result.command_id,
                "state": result.state.value,
                "reason": result.reason,
                "observed_monotonic_seconds": result.observed_at,
                "evidence": [
                    line.decode("utf-8", errors="backslashreplace")
                    for line in result.evidence
                ]
                if not re.search(rb"\+(?:CMGR|CMGL|CMT):", b"\n".join(result.evidence))
                and not any(
                    word in result.command_id.lower()
                    for word in ("sms", "cmgr", "cmgl", "message")
                )
                else ["<message evidence excluded>"],
                "next_check": result.next_check,
            }
            for result in results
        ],
    }
    return _clean(report)


def report_text(report: dict[str, object]) -> str:
    lines = [
        f"Modem Controller {report['app_version']}",
        f"Generated UTC: {report['generated_utc']}",
        f"Profile: {report['profile']} ({report['profile_version']})",
        str(report["notice"]),
        "Settings: " + json.dumps(report["settings"], ensure_ascii=False),
        "Capture: " + json.dumps(report["capture"], ensure_ascii=False),
        "Metadata: " + json.dumps(report["metadata"], ensure_ascii=False),
    ]
    for result in report["results"]:
        lines.extend(
            [
                "",
                f"{result['command']}: {result['state']} ({result['reason']})",
                f"Observed monotonic seconds: {result['observed_monotonic_seconds']}",
                *result["evidence"],
                result["next_check"],
            ]
        )
    return "\n".join(lines) + "\n"


def save_report(
    destination: Path, report: dict[str, object], *, text: bool = False
) -> None:
    safe = _clean(report)
    payload = report_text(safe) if text else json.dumps(safe, indent=2) + "\n"
    SettingsStore(destination.parent, destination.name).save_raw(payload)


def export_report(
    destination: Path,
    results: tuple[DiagnosticResult, ...],
    settings: dict[str, str],
    **options,
) -> None:
    save_report(destination, render_report(results, settings, **options))


def export_raw_capture(
    destination: Path, records: tuple[CaptureRecord, ...], *, confirmed: bool
) -> None:
    if not confirmed:
        raise PermissionError("raw capture export requires explicit confirmation")
    SettingsStore(destination.parent, destination.name).save_bytes(
        b"".join(record.data for record in records)
    )

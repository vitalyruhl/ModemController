"""Focused P17 Red-test contract; move to tests/unit/test_ras_collector.py with P17."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

SCRIPT = (
    Path(__file__).parents[2]
    / "src"
    / "modem_controller"
    / "tool_data"
    / "plugins"
    / "ras-collector"
    / "ras-collect.ps1"
)
POWERSHELL = (
    Path(os.environ.get("SystemRoot", "C:\\Windows"))
    / "System32"
    / "WindowsPowerShell"
    / "v1.0"
    / "powershell.exe"
)


def _write_fixture(
    directory: Path,
    collector: str,
    *,
    status: str = "ok",
    data: object = None,
    reason: str = "",
) -> None:
    directory.mkdir(exist_ok=True)
    (directory / f"{collector}.json").write_text(
        json.dumps({"status": status, "data": data, "reason": reason}),
        encoding="utf-8",
    )


def _run_collector(
    output: Path,
    fixtures: Path,
    *,
    collectors: str = "modems",
    hours: int = 24,
    consent: bool = True,
) -> subprocess.CompletedProcess[str]:
    if not POWERSHELL.is_file():
        pytest.skip("Windows PowerShell 5.1 is required for the P17 collector tests")
    command = [
        str(POWERSHELL),
        "-NoProfile",
        "-NonInteractive",
        "-File",
        str(SCRIPT),
        "-OutputDirectory",
        str(output),
        "-Collectors",
        collectors,
        "-Hours",
        str(hours),
        "-FixtureDirectory",
        str(fixtures),
    ]
    if consent:
        command.append("-Consent")
    assert all("ExecutionPolicy" not in argument for argument in command)
    return subprocess.run(
        command, capture_output=True, text=True, check=False, timeout=15
    )


def _report(output: Path) -> dict[str, object]:
    return json.loads((output / "ras-report.json").read_text(encoding="utf-8"))


def test_missing_consent_rejects_before_creating_output(tmp_path) -> None:
    fixtures = tmp_path / "fixtures"
    _write_fixture(fixtures, "modems", data=[])
    output = (tmp_path / "new-output").resolve()

    result = _run_collector(output, fixtures, consent=False)

    assert result.returncode != 0
    assert not output.exists()


def test_fixture_mode_uses_synthetic_data_and_writes_versioned_report(tmp_path) -> None:
    fixtures = tmp_path / "fixtures"
    _write_fixture(fixtures, "modems", data=[{"name": "Synthetic modem"}])
    output = (tmp_path / "new-output").resolve()

    result = _run_collector(output, fixtures)

    assert result.returncode == 0, result.stderr
    report = _report(output)
    assert report["schema_version"] == 1
    assert report["partial"] is False
    assert report["results"] == [
        {
            "collector": "modems",
            "status": "ok",
            "data": [{"name": "Synthetic modem"}],
            "reason": "",
        }
    ]


def test_missing_or_error_fixture_is_partial_without_host_fallback(tmp_path) -> None:
    fixtures = tmp_path / "fixtures"
    _write_fixture(fixtures, "ports", data=[{"port": "COM99"}])
    _write_fixture(
        fixtures,
        "network",
        status="error",
        data=None,
        reason="synthetic unavailable collector",
    )
    output = (tmp_path / "new-output").resolve()

    result = _run_collector(output, fixtures, collectors="ports,network,ras")

    assert result.returncode == 0, result.stderr
    report = _report(output)
    assert report["partial"] is True
    results = {item["collector"]: item for item in report["results"]}
    assert results["ports"]["status"] == "ok"
    assert results["network"] == {
        "collector": "network",
        "status": "error",
        "data": None,
        "reason": "synthetic unavailable collector",
    }
    assert results["ras"]["status"] == "unsupported"
    assert results["ras"]["data"] is None
    assert results["ras"]["reason"]


def test_report_redacts_fixture_secrets_phone_numbers_and_ip_addresses(
    tmp_path,
) -> None:
    fixtures = tmp_path / "fixtures"
    secret = "TopSecret-42"
    phone = "+49 151 12345678"
    address = "192.0.2.44"
    _write_fixture(
        fixtures,
        "phonebook",
        data={"password": secret, "number": phone, "gateway": address},
    )
    output = (tmp_path / "new-output").resolve()

    result = _run_collector(output, fixtures, collectors="phonebook")

    assert result.returncode == 0, result.stderr
    rendered = (output / "ras-report.json").read_text(encoding="utf-8")
    assert secret not in rendered
    assert phone not in rendered
    assert address not in rendered
    assert secret in (fixtures / "phonebook.json").read_text(encoding="utf-8")


def test_collector_row_and_total_output_bounds_mark_report_partial(tmp_path) -> None:
    fixtures = tmp_path / "fixtures"
    _write_fixture(fixtures, "events", data=[{"row": index} for index in range(101)])
    _write_fixture(fixtures, "network", data="x" * (1024 * 1024 + 1024))
    output = (tmp_path / "new-output").resolve()

    result = _run_collector(output, fixtures, collectors="events,network")

    assert result.returncode == 0, result.stderr
    report = _report(output)
    assert report["partial"] is True
    results = {item["collector"]: item for item in report["results"]}
    assert len(results["events"]["data"]) <= 100
    rendered_results = json.dumps(report["results"], ensure_ascii=False).encode("utf-8")
    assert len(rendered_results) <= 1024 * 1024


def test_existing_output_directory_is_rejected_without_clobbering_its_contents(
    tmp_path,
) -> None:
    fixtures = tmp_path / "fixtures"
    _write_fixture(fixtures, "modems", data=[])
    output = (tmp_path / "existing-output").resolve()
    output.mkdir()
    sentinel = output / "keep.txt"
    sentinel.write_text("do not replace", encoding="utf-8")

    result = _run_collector(output, fixtures)

    assert result.returncode != 0
    assert sentinel.read_text(encoding="utf-8") == "do not replace"
    assert not (output / "ras-report.json").exists()


def test_collection_options_require_explicit_scope_and_consent(qtbot, tmp_path):
    from modem_controller.ui.ras_options import RasOptionsDialog

    dialog = RasOptionsDialog(tmp_path)
    qtbot.addWidget(dialog)
    with pytest.raises(ValueError):
        dialog.arguments()
    dialog.collectors["ports"].setChecked(True)
    with pytest.raises(ValueError):
        dialog.arguments()
    dialog.consent.setChecked(True)
    args = dialog.arguments()
    assert args[args.index("-Collectors") + 1] == "ports"
    assert "-Consent" in args
    assert not Path(args[args.index("-OutputDirectory") + 1]).exists()


def test_truncated_rows_alone_are_partial_and_event_time_is_preserved(tmp_path):
    fixtures = tmp_path / "fixtures"
    _write_fixture(fixtures, "events", data=[{"time": "2026-09-19T12:00:00Z"}] * 101)
    output = (tmp_path / "new-output").resolve()
    result = _run_collector(output, fixtures, collectors="events")
    assert result.returncode == 0, result.stderr
    report = _report(output)
    assert report["partial"]
    assert len(report["results"][0]["data"]) == 100
    assert report["results"][0]["data"][0]["time"] == "2026-09-19T12:00:00Z"

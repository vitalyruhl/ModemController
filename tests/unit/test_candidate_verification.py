"""Offline verification contracts for generated portable candidate ZIPs."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import zipfile
from collections.abc import Callable
from pathlib import Path

import pytest

SCRIPT_PATH = Path(__file__).parents[2] / "tools" / "verify_candidate.py"
SPEC = importlib.util.spec_from_file_location("verify_candidate", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
verify_candidate_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verify_candidate_module)
verify_archive = verify_candidate_module.verify_archive


def _build_info(**changes: object) -> dict[str, object]:
    info: dict[str, object] = {
        "version": "2.0.0",
        "source_revision": "a" * 40,
        "dirty": False,
        "lock_sha256": "b" * 64,
    }
    info.update(changes)
    return info


def _write_sidecar(archive: Path) -> Path:
    sidecar = archive.with_name(archive.name + ".sha256")
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    sidecar.write_text(f"{digest}  {archive.name}\n", encoding="ascii")
    return sidecar


def _write_candidate(
    directory: Path,
    *,
    info: dict[str, object] | None = None,
    gui_version: str = "2.0.0",
    console_version: str = "2.0.0",
    gui_build: dict[str, object] | None = None,
    console_build: dict[str, object] | None = None,
    contents: dict[str, bytes] | None = None,
    manifest: dict[str, str] | None = None,
    manifest_transform: Callable[[dict[str, str]], dict[str, str]] | None = None,
) -> Path:
    root = "ModemController-2.0.0-candidate"
    info = _build_info() if info is None else info
    files = {
        f"{root}/build-info.json": json.dumps(info).encode(),
        f"{root}/_internal/modem_controller/_version.json": json.dumps(
            {"version": gui_version}
        ).encode(),
        f"{root}/_internal/modem_controller/_build.json": json.dumps(
            info if gui_build is None else gui_build
        ).encode(),
        f"{root}/_console/modem_controller/_version.json": json.dumps(
            {"version": console_version}
        ).encode(),
        f"{root}/_console/modem_controller/_build.json": json.dumps(
            info if console_build is None else console_build
        ).encode(),
        f"{root}/ModemController.exe": b"synthetic GUI bytes",
        f"{root}/ModemConsole.exe": b"synthetic console bytes",
    }
    files.update(contents or {})
    calculated = {
        name.removeprefix(root + "/"): hashlib.sha256(data).hexdigest()
        for name, data in files.items()
    }
    recorded_manifest = calculated if manifest is None else manifest
    if manifest_transform is not None:
        recorded_manifest = manifest_transform(dict(calculated))
    files[f"{root}/contents-sha256.json"] = json.dumps(
        recorded_manifest, sort_keys=True
    ).encode()
    archive = directory / "candidate.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
        for name, data in files.items():
            bundle.writestr(name, data)
    _write_sidecar(archive)
    return archive


def test_verify_archive_returns_clean_root_build_info_for_valid_candidate(
    tmp_path,
) -> None:
    info = _build_info()
    archive = _write_candidate(tmp_path, info=info)

    assert verify_archive(archive) == info


def test_sidecar_requires_sha256_two_spaces_and_matching_archive_name(tmp_path) -> None:
    archive = _write_candidate(tmp_path)
    sidecar = archive.with_name(archive.name + ".sha256")

    for invalid in (
        "not-a-hash  candidate.zip\n",
        f"{'a' * 64} {archive.name}\n",
        f"{'a' * 64}  another.zip\n",
    ):
        sidecar.write_text(invalid, encoding="ascii")
        with pytest.raises(ValueError):
            verify_archive(archive)


@pytest.mark.parametrize(
    "unsafe", ["/absolute.txt", "../traversal.txt", "OtherRoot/file.txt"]
)
def test_verify_archive_rejects_non_root_and_traversal_members(
    tmp_path, unsafe
) -> None:
    archive = _write_candidate(tmp_path)
    with zipfile.ZipFile(archive, "a", zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr(unsafe, b"synthetic")
    _write_sidecar(archive)

    with pytest.raises(ValueError):
        verify_archive(archive)


def test_verify_archive_rejects_duplicate_zip_member(tmp_path) -> None:
    archive = _write_candidate(tmp_path)
    root = "ModemController-2.0.0-candidate"
    with (
        pytest.warns(UserWarning),
        zipfile.ZipFile(archive, "a", zipfile.ZIP_DEFLATED) as bundle,
    ):
        bundle.writestr(f"{root}/ModemConsole.exe", b"replacement")
    _write_sidecar(archive)

    with pytest.raises(ValueError):
        verify_archive(archive)


@pytest.mark.parametrize(
    "mode",
    ["missing", "extra", "tampered"],
    ids=["missing", "extra", "tampered"],
)
def test_verify_archive_rejects_missing_extra_or_tampered_manifest_entries(
    tmp_path, mode
) -> None:
    def transform(manifest: dict[str, str]) -> dict[str, str]:
        if mode == "missing":
            del manifest["ModemConsole.exe"]
        elif mode == "extra":
            manifest["unexpected.txt"] = hashlib.sha256(b"unused").hexdigest()
        else:
            manifest["ModemConsole.exe"] = "0" * 64
        return manifest

    archive = _write_candidate(tmp_path, manifest_transform=transform)

    with pytest.raises(ValueError):
        verify_archive(archive)


@pytest.mark.parametrize(
    ("info", "gui_version", "console_version", "gui_build", "console_build"),
    [
        (_build_info(dirty=True), "2.0.0", "2.0.0", None, None),
        (_build_info(), "2.0.1", "2.0.0", None, None),
        (_build_info(), "2.0.0", "2.0.1", None, None),
        (_build_info(), "2.0.0", "2.0.0", _build_info(source_revision="c" * 40), None),
        (_build_info(), "2.0.0", "2.0.0", None, _build_info(lock_sha256="d" * 64)),
    ],
    ids=["dirty", "gui-version", "console-version", "gui-build", "console-build"],
)
def test_verify_archive_rejects_dirty_or_inconsistent_build_metadata(
    tmp_path, info, gui_version, console_version, gui_build, console_build
) -> None:
    archive = _write_candidate(
        tmp_path,
        info=info,
        gui_version=gui_version,
        console_version=console_version,
        gui_build=gui_build,
        console_build=console_build,
    )

    with pytest.raises(ValueError):
        verify_archive(archive)

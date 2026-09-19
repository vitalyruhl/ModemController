"""Verify a locally built candidate, optionally launching its trusted executables."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import subprocess
import tempfile
import zipfile
from pathlib import Path, PurePosixPath


def _digest(stream) -> str:
    return hashlib.file_digest(stream, "sha256").hexdigest()


def verify_archive(archive: Path) -> dict:
    """Check integrity and provenance without extracting or running payload code."""
    try:
        expected = archive.with_name(archive.name + ".sha256").read_text().strip()
        with archive.open("rb") as stream:
            actual = _digest(stream)
        if expected != f"{actual}  {archive.name}":
            raise ValueError("Archive checksum mismatch")
        with zipfile.ZipFile(archive) as package:
            entries = package.infolist()
            if len(entries) > 10_000 or sum(e.file_size for e in entries) > 2**30:
                raise ValueError("Candidate exceeds verification limits")
            seen = set()
            roots = set()
            for entry in entries:
                name = entry.filename.rstrip("/")
                parts = PurePosixPath(name).parts
                if (
                    not parts
                    or parts[0] == "/"
                    or ".." in parts
                    or "\\" in name
                    or ":" in name
                    or name.casefold() in seen
                    or ((entry.external_attr >> 16) & 0o170000) == 0o120000
                ):
                    raise ValueError("Unsafe or duplicate archive path")
                seen.add(name.casefold())
                roots.add(parts[0])
            if len(roots) != 1:
                raise ValueError("Expected one candidate root")
            root = roots.pop() + "/"
            manifest = json.loads(package.read(root + "contents-sha256.json"))
            names = {
                entry.filename[len(root) :] for entry in entries if not entry.is_dir()
            }
            if not isinstance(manifest, dict) or set(manifest) != names - {
                "contents-sha256.json"
            }:
                raise ValueError("Manifest file set mismatch")
            for name, digest in manifest.items():
                with package.open(root + name) as stream:
                    if _digest(stream) != digest:
                        raise ValueError(f"Payload checksum mismatch: {name}")
            info = json.loads(package.read(root + "build-info.json"))
            if (
                not isinstance(info, dict)
                or info.get("dirty") is not False
                or not re.fullmatch(r"[0-9a-f]{40}", info.get("source_revision", ""))
                or not re.fullmatch(r"[0-9a-f]{64}", info.get("lock_sha256", ""))
                or not re.fullmatch(r"\d+\.\d+\.\d+", info.get("version", ""))
            ):
                raise ValueError("Candidate must identify a clean committed source")
            for runtime in ("_internal", "_console"):
                prefix = root + runtime + "/modem_controller/"
                version = json.loads(package.read(prefix + "_version.json"))
                if version.get("version") != info["version"]:
                    raise ValueError("Frozen version mismatch")
                if json.loads(package.read(prefix + "_build.json")) != info:
                    raise ValueError("Frozen provenance mismatch")
            return info
    except (OSError, KeyError, TypeError, AttributeError, zipfile.BadZipFile) as error:
        raise ValueError(f"Invalid candidate: {error}") from error


def smoke_archive(archive: Path) -> dict:
    """Run a trusted local build; hashes prove integrity, not publisher identity."""
    info = verify_archive(archive)
    scratch = Path(__file__).resolve().parents[1] / "build" / "verification"
    scratch.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="candidate-", dir=scratch) as temporary:
        directory = Path(temporary).resolve()
        if not directory.is_relative_to(scratch.resolve()):
            raise ValueError("Unexpected verification directory")
        with zipfile.ZipFile(archive) as package:
            package.extractall(directory)
        bundle = next(path for path in directory.iterdir() if path.is_dir())
        relocated = directory / "relocated candidate with spaces"
        bundle.rename(relocated)
        required = (
            "ModemController.exe",
            "ModemConsole.exe",
            "settings.json",
            "generic-at.json",
            "device-profiles.json",
            "plugins/ras-collector/plugin.json",
            "plugins/ras-collector/launch.ps1",
            "plugins/ras-collector/ras-collect.ps1",
            "LICENSE.txt",
            "help/acceptance.md",
            "help/release-notes.md",
            "help/third-party-notices.md",
            "licenses/QT_PYSIDE_SHA256SUMS.txt",
        )
        if any(not (relocated / name).is_file() for name in required):
            raise ValueError("Missing executable, sidecar, help or license resource")
        env = dict(os.environ)
        for key in ("PYTHONHOME", "PYTHONPATH", "VIRTUAL_ENV"):
            env.pop(key, None)
        env.update(
            QT_QPA_PLATFORM="offscreen",
            LOCALAPPDATA=str(directory / "user-data"),
            PATH=str(Path(os.environ.get("SystemRoot", "C:/Windows")) / "System32"),
        )
        commands = (
            ("ModemConsole.exe", "--version"),
            ("ModemConsole.exe", "--help"),
            ("ModemConsole.exe",),
            ("ModemController.exe", "--smoke-test"),
        )
        for command in commands:
            result = subprocess.run(
                [str(relocated / command[0]), *command[1:]],
                cwd=directory,
                env=env,
                input="",
                text=True,
                capture_output=True,
                timeout=30,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            if result.returncode:
                raise ValueError(f"Candidate startup failed: {command[0]}")
            if "--version" in command and (
                info["version"] not in result.stdout
                or info["source_revision"][:12] not in result.stdout
            ):
                raise ValueError("Console displayed version/source mismatch")
    return {
        **info,
        "archive": archive.name,
        "local_platform": platform.platform(),
        "relocated_startup": "passed",
        "gui_backend": "offscreen",
        "serial_opened": False,
        "clean_target": False,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="Launch executables from this trusted local build",
    )
    args = parser.parse_args()
    result = smoke_archive(args.archive) if args.smoke else verify_archive(args.archive)
    print(json.dumps(result, indent=2))

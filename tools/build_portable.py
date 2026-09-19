"""Build a portable Windows bundle without embedding local reference material."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

from modem_controller.catalog.portable import seed_catalog_files
from modem_controller.catalog.storage import Settings, SettingsStore
from modem_controller.versioning import build_info, product_version

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DIST_DIRECTORY = PROJECT_ROOT / "dist"
BUILD_DIRECTORY = PROJECT_ROOT / "build" / "pyinstaller"
BUNDLE_NAME = "ModemController"


def build_command(
    *, console: bool = False, destination: Path = DIST_DIRECTORY
) -> list[str]:
    return [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onedir",
        "--console" if console else "--windowed",
        "--name",
        "ModemConsole" if console else BUNDLE_NAME,
        "--contents-directory",
        "_console" if console else "_internal",
        "--additional-hooks-dir",
        str(PROJECT_ROOT / "tools" / "pyinstaller-hooks"),
        "--add-data",
        str(PROJECT_ROOT / "src" / "modem_controller" / "catalog" / "data")
        + ":modem_controller/catalog/data",
        "--copy-metadata",
        "modem-controller-rs232",
        "--add-data",
        str(BUILD_DIRECTORY / "_version.json") + ":modem_controller",
        "--add-data",
        str(BUILD_DIRECTORY / "_build.json") + ":modem_controller",
        "--version-file",
        str(BUILD_DIRECTORY / "windows-version.txt"),
        "--distpath",
        str(destination),
        "--workpath",
        str(BUILD_DIRECTORY),
        "--specpath",
        str(BUILD_DIRECTORY),
        str(
            PROJECT_ROOT
            / "src"
            / "modem_controller"
            / ("cli.py" if console else "app.py")
        ),
    ]


def audit_bundle(bundle: Path) -> None:
    """Fail closed if a collector accidentally includes personal/local material."""
    for path in bundle.rglob("*"):
        relative = path.relative_to(bundle)
        if any(
            part in {".Plan", ".agents", ".Temp", ".Old_Version", ".git"}
            for part in relative.parts
        ):
            raise ValueError("Local-only material in portable payload")
        if path.name == "settings.json" and path.parent != bundle:
            raise ValueError("Personal source settings in portable payload")
        if path.suffix.lower() in {".log", ".yacps", ".inf"}:
            raise ValueError("Unexpected log/reference/driver in portable payload")
    if (
        Settings.from_dict(json.loads((bundle / "settings.json").read_text()))
        != Settings()
    ):
        raise ValueError("Portable initial settings must be blank defaults")


def build() -> Path:
    info = build_info()
    BUILD_DIRECTORY.mkdir(parents=True, exist_ok=True)
    (BUILD_DIRECTORY / "_version.json").write_bytes(
        (PROJECT_ROOT / "version.json").read_bytes()
    )
    (BUILD_DIRECTORY / "_build.json").write_text(
        json.dumps(info, indent=2), encoding="utf-8"
    )
    numeric = (*map(int, product_version().split(".")), 0)
    (BUILD_DIRECTORY / "windows-version.txt").write_text(
        f"VSVersionInfo(ffi=FixedFileInfo(filevers={numeric!r}, prodvers={numeric!r}, "
        "mask=0x3f, flags=0, OS=0x40004, fileType=1, subtype=0, date=(0,0)), "
        "kids=[StringFileInfo([StringTable('040904B0', ["
        f"StringStruct('FileVersion', '{product_version()}'), "
        f"StringStruct('ProductVersion', '{product_version()}'), "
        "StringStruct('ProductName', 'Modem Controller')])]), "
        "VarFileInfo([VarStruct('Translation', [1033,1200])])])",
        encoding="utf-8",
    )
    stage = BUILD_DIRECTORY / ("stage-" + uuid.uuid4().hex)
    for console in (False, True):
        subprocess.run(
            build_command(console=console, destination=stage),
            check=True,
            cwd=PROJECT_ROOT,
        )
    bundle = stage / BUNDLE_NAME
    shutil.copy2(stage / "ModemConsole" / "ModemConsole.exe", bundle)
    shutil.copytree(stage / "ModemConsole" / "_console", bundle / "_console")
    seed_catalog_files(bundle)
    shutil.copy2(
        PROJECT_ROOT / "src" / "modem_controller" / "tool_data" / "tools.json",
        bundle / "tools.json",
    )
    (bundle / "build-info.json").write_text(
        json.dumps(info, indent=2) + "\n", encoding="utf-8"
    )
    SettingsStore(bundle).save(Settings())
    shutil.copy2(PROJECT_ROOT / "LICENSE", bundle / "LICENSE.txt")
    help_directory = bundle / "help"
    help_directory.mkdir()
    for name in (
        "console.md",
        "catalog-editing.md",
        "privacy.md",
        "device-support.md",
        "portable-build.md",
        "third-party-notices.md",
        "versioning.md",
        "release-notes.md",
        "local-tools.md",
    ):
        shutil.copy2(PROJECT_ROOT / "docs" / name, help_directory / name)
    shutil.copytree(PROJECT_ROOT / "docs" / "licenses", bundle / "licenses")
    for metadata in bundle.rglob("modem_controller_rs232-*.dist-info"):
        for item in metadata.iterdir():
            if item.is_file() and item.name != "METADATA":
                if not item.resolve().is_relative_to(bundle.resolve()):
                    raise RuntimeError("Unexpected metadata path")
                item.unlink()
    audit_bundle(bundle)
    contents = {
        str(path.relative_to(bundle)).replace("\\", "/"): hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
        for path in sorted(bundle.rglob("*"))
        if path.is_file()
    }
    (bundle / "contents-sha256.json").write_text(
        json.dumps(contents, indent=2) + "\n", encoding="utf-8"
    )
    source = info["source_revision"][:12] + ("-dirty" if info["dirty"] else "")
    name = f"{BUNDLE_NAME}-{product_version()}-{source}-" + datetime.now(UTC).strftime(
        "%Y%m%d-%H%M%S"
    )
    target = DIST_DIRECTORY / name
    DIST_DIRECTORY.mkdir(exist_ok=True)
    if target.exists():
        raise FileExistsError(target)
    shutil.copytree(bundle, target)
    archive = shutil.make_archive(
        str(DIST_DIRECTORY / name), "zip", DIST_DIRECTORY, name
    )
    resolved = stage.resolve()
    if not resolved.is_relative_to(
        BUILD_DIRECTORY.resolve()
    ) or not resolved.name.startswith("stage-"):
        raise RuntimeError("Unexpected build staging path")
    shutil.rmtree(resolved)
    return Path(archive)


if __name__ == "__main__":
    print(build())

"""One product version, with derived source/build provenance for acceptance."""

from __future__ import annotations

import hashlib
import json
import platform
import re
import subprocess
import sys
from pathlib import Path


def read_version(path: Path) -> str:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))["version"]
        if not isinstance(value, str) or not re.fullmatch(
            r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)", value
        ):
            raise ValueError("Expected a canonical major.minor.patch version")
        return value
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise ValueError("Missing or invalid product version source") from error


def _source_root() -> Path | None:
    if getattr(sys, "frozen", False):
        return None
    root = Path(__file__).resolve().parents[2]
    return root if (root / "pyproject.toml").exists() else None


def product_version() -> str:
    root = _source_root()
    return read_version(
        root / "version.json" if root else Path(__file__).with_name("_version.json")
    )


def build_info() -> dict:
    root = _source_root()
    if root is None:
        path = Path(__file__).with_name("_build.json")
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("version") != product_version():
            raise ValueError("Build metadata version does not match product version")
        return data
    recorded = root / "source-build.json"
    if recorded.exists() and not (root / ".git").exists():
        data = json.loads(recorded.read_text(encoding="utf-8"))
        if data.get("version") != product_version():
            raise ValueError("Source build version mismatch")
        return data
    revision, dirty = "unavailable", True
    try:
        flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        revision = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            text=True,
            timeout=5,
            stderr=subprocess.DEVNULL,
            creationflags=flags,
        ).strip()
        dirty = bool(
            subprocess.check_output(
                ["git", "status", "--porcelain"],
                cwd=root,
                text=True,
                timeout=5,
                stderr=subprocess.DEVNULL,
                creationflags=flags,
            ).strip()
        )
    except (OSError, subprocess.SubprocessError):
        pass
    return {
        "version": product_version(),
        "source_revision": revision,
        "dirty": dirty,
        "lock_sha256": hashlib.sha256((root / "uv.lock").read_bytes()).hexdigest(),
        "python": platform.python_version(),
    }


def version_label() -> str:
    info = build_info()
    suffix = " dirty" if info["dirty"] else ""
    return f"{product_version()} ({info['source_revision'][:12]}{suffix})"

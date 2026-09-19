"""Discover local plugin folders and start their own independent interfaces."""

import json
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Plugin:
    name: str
    program: Path
    arguments: tuple[str, ...]
    directory: Path


def load_plugin(directory: Path) -> Plugin:
    directory = directory.resolve()
    with (directory / "plugin.json").open("rb") as stream:
        raw = stream.read(65537)
    if len(raw) > 65536:
        raise ValueError("Plugin configuration exceeds 64 KiB")
    data = json.loads(raw.decode("utf-8-sig"))
    if not isinstance(data, dict) or set(data) - {"name", "program", "arguments"}:
        raise ValueError(
            "Plugin configuration needs name, program and optional arguments"
        )
    for field in ("name", "program"):
        value = data.get(field)
        if not isinstance(value, str) or not value.strip() or "\0" in value:
            raise ValueError(f"Plugin {field} must be nonempty text")
    arguments = data.get("arguments", [])
    if not isinstance(arguments, list) or not all(
        isinstance(value, str) and "\0" not in value for value in arguments
    ):
        raise ValueError("Plugin arguments must be a list of text values")
    program = Path(data["program"])
    if not program.is_absolute():
        program = directory / program
    return Plugin(data["name"], program.resolve(), tuple(arguments), directory)


def discover_plugins(directory: Path) -> tuple[Plugin, ...]:
    try:
        children = sorted(directory.iterdir(), key=lambda path: path.name.casefold())
    except OSError:
        return ()
    result = []
    for child in children:
        if not child.is_dir():
            continue
        try:
            result.append(load_plugin(child))
        except (OSError, ValueError):
            continue
    return tuple(result)


def plugin_arguments(plugin: Plugin) -> tuple[str, list[str]]:
    if not plugin.program.is_file():
        raise ValueError("The plugin program is unavailable")
    if plugin.program.suffix.lower() == ".ps1":
        interpreter = (
            Path(os.environ.get("SystemRoot", "C:/Windows"))
            / "System32/WindowsPowerShell/v1.0/powershell.exe"
        )
        return str(interpreter), [
            "-NoProfile",
            "-STA",
            "-File",
            str(plugin.program),
            *plugin.arguments,
        ]
    return str(plugin.program), list(plugin.arguments)


def launch_plugin(plugin: Plugin, *, detached=None) -> int:
    """Start once without shell composition, elevation or owning the plugin lifetime."""
    if detached is None:
        from PySide6.QtCore import QProcess

        detached = QProcess.startDetached
    program, arguments = plugin_arguments(plugin)
    started, process_id = detached(program, arguments, str(plugin.directory))
    if not started:
        raise RuntimeError("The plugin could not start; check its program and runtime")
    return process_id

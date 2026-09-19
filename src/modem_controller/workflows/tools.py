"""Reviewed local process definitions, independent of GUI and serial sessions."""

from __future__ import annotations

import hashlib
import json
import os
import re
import signal
import subprocess
import time
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from threading import Event, Lock, Thread

from modem_controller.transport.privacy import contains_secret_input


@dataclass(frozen=True)
class ToolDefinition:
    id: str
    label: str
    script: Path
    kind: str = "python"
    interpreter: Path | None = None
    arguments: tuple[str, ...] = ()
    working_directory: Path | None = None
    timeout_seconds: float = 30
    output_limit: int = 65536
    serial_requirement: str = "disconnected"
    effects: str = "Unknown effects"
    reviewed_fingerprint: str = ""

    def __post_init__(self):
        for path in (self.script, self.interpreter, self.working_directory):
            if path is not None and str(path).startswith(("\\\\", "//")):
                raise ValueError("Network paths are not local tool inputs")
        if not re.fullmatch(r"[a-z][a-z0-9-]*", self.id) or not self.label:
            raise ValueError("Tool needs an ID and label")
        if self.kind not in {"python", "ps1", "cmd"}:
            raise ValueError("Unsupported script type")
        if not 0 < self.timeout_seconds <= 300 or not 1 <= self.output_limit <= 1048576:
            raise ValueError("Tool timeout/output limit outside bounds")
        if self.serial_requirement not in {"disconnected", "none", "unknown"}:
            raise ValueError("Unknown serial requirement")
        if not isinstance(self.arguments, tuple) or not all(
            isinstance(a, str) for a in self.arguments
        ):
            raise ValueError("Arguments must be a list of strings")


@dataclass(frozen=True)
class ToolResult:
    exit_code: int | None
    stdout: str
    stderr: str
    status: str
    truncated: bool = False


def _local_file(path: Path) -> Path:
    if str(path).startswith(("\\\\", "//")) or not path.is_absolute():
        raise ValueError("Select an absolute local path")
    if not path.is_file():
        raise ValueError("Local script or interpreter is unavailable")
    return path


def _interpreter(tool):
    path = tool.interpreter
    if path is None and tool.kind in {"ps1", "cmd"}:
        system = Path(os.environ.get("SystemRoot", "C:/Windows")) / "System32"
        path = system / (
            "WindowsPowerShell/v1.0/powershell.exe" if tool.kind == "ps1" else "cmd.exe"
        )
    if path is None:
        raise ValueError(
            "Select an installed local Python interpreter; "
            "none is installed automatically"
        )
    path = _local_file(path)
    if os.name == "nt" and path.suffix.lower() != ".exe":
        raise ValueError("Interpreter must be a local executable")
    return path


def launch_arguments(tool: ToolDefinition) -> list[str]:
    script = _local_file(tool.script)
    expected = {"python": ".py", "ps1": ".ps1", "cmd": ".cmd"}[tool.kind]
    if script.suffix.lower() != expected:
        raise ValueError("Script extension does not match its type")
    interpreter = _interpreter(tool)
    if any(
        contains_secret_input(a.encode("utf-8"))
        or re.search(r"(?i)(password|passwd|secret|token|pin)\s*[=:]", a)
        for a in tool.arguments
    ):
        raise ValueError("Secrets are not allowed in process arguments")
    if any(any(c in a for c in "\r\n\0") for a in tool.arguments):
        raise ValueError("Control characters are not allowed in arguments")
    if tool.kind == "python":
        return [str(interpreter), str(script), *tool.arguments]
    if tool.kind == "ps1":
        return [
            str(interpreter),
            "-NoProfile",
            "-NonInteractive",
            "-File",
            str(script),
            *tool.arguments,
        ]
    parts = [str(script), *tool.arguments]
    if any(re.search(r'[&|<>^%!"()\r\n]', part) for part in parts):
        raise ValueError("CMD shell metacharacters are not permitted")
    command = '"' + " ".join('"' + p + '"' for p in parts) + '"'
    return [str(interpreter), "/d", "/s", "/c", command]


def fingerprint(tool: ToolDefinition) -> str:
    launch_arguments(tool)
    data = asdict(replace(tool, reviewed_fingerprint=""))
    payload = json.dumps(data, default=str, sort_keys=True).encode()
    with tool.script.open("rb") as stream:
        source = stream.read(1048577)
    if len(source) > 1048576:
        raise ValueError("Tool script exceeds 1 MiB")
    with _interpreter(tool).open("rb") as executable:
        runtime = hashlib.file_digest(executable, "sha256").digest()
    return hashlib.sha256(payload + source + runtime).hexdigest()


def review_tool(tool: ToolDefinition) -> ToolDefinition:
    return replace(tool, reviewed_fingerprint=fingerprint(tool))


def load_tool_registry(path: Path) -> tuple[ToolDefinition, ...]:
    with path.open("rb") as stream:
        content = stream.read(1048577)
    if len(content) > 1048576:
        raise ValueError("Registry exceeds 1 MiB")
    data = json.loads(content)
    definitions = data["tools"]
    if not isinstance(definitions, list) or len(definitions) > 100:
        raise ValueError("Registry must contain at most 100 tools")
    result = []
    for definition in definitions:
        fields = dict(definition)
        for key in ("script", "interpreter", "working_directory"):
            if fields.get(key):
                value = Path(fields[key])
                fields[key] = value if value.is_absolute() else path.parent / value
        fields["arguments"] = tuple(fields.get("arguments", ()))
        fields["reviewed_fingerprint"] = ""
        result.append(ToolDefinition(**fields))
    if len({t.id for t in result}) != len(result):
        raise ValueError("Duplicate tool IDs")
    return tuple(result)


def run_tool(
    tool: ToolDefinition, *, cancelled=None, serial_connected=False
) -> ToolResult:
    cancelled = cancelled or Event()
    if serial_connected and tool.serial_requirement != "none":
        return ToolResult(
            None, "", "Release the serial connection before running", "serial_connected"
        )
    if cancelled.is_set():
        return ToolResult(None, "", "", "cancelled")
    process = job = None
    readers = []
    stdout, stderr = bytearray(), bytearray()
    lock = Lock()
    truncated = False
    status, exit_code = "failed", None
    try:
        if not tool.reviewed_fingerprint or tool.reviewed_fingerprint != fingerprint(
            tool
        ):
            return ToolResult(
                None,
                "",
                "Review this definition and script before running",
                "unreviewed",
            )
        arguments = launch_arguments(tool)
        if tool.kind == "cmd":
            # CMD does not implement C-runtime backslash escaping of nested quotes.
            # The script path and values were restricted before this composition.
            arguments = (
                subprocess.list2cmdline(arguments[:1]) + " /d /s /c " + arguments[-1]
            )
        cwd = tool.working_directory or tool.script.parent
        if not cwd.is_dir() or str(cwd).startswith(("\\\\", "//")):
            raise ValueError("Working directory must exist locally")
        if os.name == "nt":
            from modem_controller.transport.process_job import WindowsJob

            job = WindowsJob()
        process = subprocess.Popen(
            arguments,
            cwd=cwd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
            creationflags=(subprocess.CREATE_NO_WINDOW | 4) if os.name == "nt" else 0,
            start_new_session=os.name != "nt",
        )
        if job:
            job.assign_and_resume(process)

        def read(stream, buffer):
            nonlocal truncated
            while chunk := stream.read(4096):
                with lock:
                    remaining = max(0, tool.output_limit - len(stdout) - len(stderr))
                    buffer.extend(chunk[:remaining])
                    truncated |= len(chunk) > remaining

        for stream, buffer in ((process.stdout, stdout), (process.stderr, stderr)):
            thread = Thread(target=read, args=(stream, buffer), daemon=True)
            readers.append(thread)
            thread.start()
        deadline = time.monotonic() + tool.timeout_seconds
        while process.poll() is None:
            if cancelled.wait(0.01):
                status = "cancelled"
                break
            if time.monotonic() >= deadline:
                status = "timed_out"
                break
        else:
            status, exit_code = "completed", process.returncode
    except (OSError, ValueError, RuntimeError) as error:
        stderr.extend(str(error).encode()[: tool.output_limit])
    finally:
        if job:
            job.close()
        if process:
            if os.name != "nt":
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            if process.poll() is None:
                process.kill()
            process.wait(timeout=3)
            for thread in readers:
                thread.join(timeout=3)
            for stream in (process.stdout, process.stderr):
                if stream:
                    stream.close()
    return ToolResult(
        exit_code,
        stdout.decode("utf-8", "replace").replace("\r\n", "\n"),
        stderr.decode("utf-8", "replace").replace("\r\n", "\n"),
        status,
        truncated,
    )

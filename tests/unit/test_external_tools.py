"""Focused P16 Red-test contract; move to tests/unit/test_external_tools.py with P16."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from threading import Event, Thread
from time import sleep

import pytest

from modem_controller.workflows.tools import (
    ToolDefinition,
    fingerprint,
    launch_arguments,
    load_tool_registry,
    review_tool,
    run_tool,
)


def _python_tool(script: Path, **changes: object) -> ToolDefinition:
    values: dict[str, object] = {
        "id": "synthetic-tool",
        "label": "Synthetic tool",
        "script": script,
        "kind": "python",
        "interpreter": Path(sys.executable),
    }
    values.update(changes)
    return ToolDefinition(**values)


def _write_python_script(path: Path, source: str) -> Path:
    path.write_text(source, encoding="utf-8")
    return path


def test_unreviewed_and_changed_scripts_are_rejected_before_launch(tmp_path) -> None:
    marker = tmp_path / "launched.txt"
    script = _write_python_script(
        tmp_path / "harmless.py",
        f"from pathlib import Path\nPath({str(marker)!r}).write_text('launched')\n",
    )
    tool = _python_tool(script)

    unreviewed = run_tool(tool)
    assert unreviewed.status == "unreviewed"
    assert unreviewed.exit_code is None
    assert not marker.exists()

    reviewed = review_tool(tool)
    assert reviewed.reviewed_fingerprint == fingerprint(reviewed)
    script.write_text("print('changed after review')\n", encoding="utf-8")

    changed = run_tool(reviewed)
    assert changed.status == "unreviewed"
    assert changed.exit_code is None
    assert not marker.exists()


def test_imported_registry_definition_discards_persisted_review(tmp_path) -> None:
    script = _write_python_script(tmp_path / "harmless.py", "print('safe')\n")
    registry = tmp_path / "tools.json"
    registry.write_text(
        json.dumps(
            {
                "tools": [
                    {
                        "id": "imported",
                        "label": "Imported",
                        "script": str(script),
                        "kind": "python",
                        "interpreter": sys.executable,
                        "reviewed_fingerprint": "pretend-trusted",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    (imported,) = load_tool_registry(registry)

    assert imported.reviewed_fingerprint == ""
    assert run_tool(imported).status == "unreviewed"


def test_launch_arguments_require_existing_explicit_python_interpreter(
    tmp_path,
) -> None:
    script = _write_python_script(tmp_path / "say.py", "print('safe')\n")
    tool = _python_tool(script, arguments=("two words", "ü"))

    assert launch_arguments(tool) == [
        str(Path(sys.executable)),
        str(script),
        "two words",
        "ü",
    ]
    with pytest.raises(ValueError):
        launch_arguments(_python_tool(script, interpreter=None))
    with pytest.raises(ValueError):
        launch_arguments(_python_tool(script, interpreter=tmp_path / "missing.exe"))


def test_reviewed_python_tool_returns_stdout_and_preserves_nonzero_exit(
    tmp_path,
) -> None:
    script = _write_python_script(
        tmp_path / "result.py",
        "import sys\nprint('synthetic stdout')\n"
        "print('synthetic stderr', file=sys.stderr)\nsys.exit(7)\n",
    )

    result = run_tool(review_tool(_python_tool(script)))

    assert result.status == "completed"
    assert result.exit_code == 7
    assert result.stdout == "synthetic stdout\n"
    assert result.stderr == "synthetic stderr\n"
    assert not result.truncated


def test_timeout_cancellation_and_output_limit_bound_harmless_python_child(
    tmp_path,
) -> None:
    sleeper = _write_python_script(
        tmp_path / "sleep.py", "from time import sleep\nsleep(10)\n"
    )
    timed_out = run_tool(review_tool(_python_tool(sleeper, timeout_seconds=0.01)))
    assert timed_out.status == "timed_out"
    assert timed_out.exit_code is None

    cancelled = Event()
    trigger = Thread(target=lambda: (sleep(0.02), cancelled.set()), daemon=True)
    trigger.start()
    cancelled_result = run_tool(
        review_tool(_python_tool(sleeper, timeout_seconds=2)), cancelled=cancelled
    )
    trigger.join()
    assert cancelled_result.status == "cancelled"
    assert cancelled_result.exit_code is None

    noisy = _write_python_script(tmp_path / "noisy.py", "print('x' * 4096)\n")
    limited = run_tool(review_tool(_python_tool(noisy, output_limit=32)))
    assert limited.status == "completed"
    assert limited.truncated
    assert len(limited.stdout.encode()) <= 32


def test_default_disconnected_requirement_blocks_a_reviewed_tool_while_serial_is_owned(
    tmp_path,
) -> None:
    marker = tmp_path / "launched.txt"
    script = _write_python_script(
        tmp_path / "harmless.py",
        f"from pathlib import Path\nPath({str(marker)!r}).write_text('launched')\n",
    )

    result = run_tool(review_tool(_python_tool(script)), serial_connected=True)

    assert result.status == "serial_connected"
    assert result.exit_code is None
    assert not marker.exists()


def test_cmd_shell_metacharacters_are_rejected_before_any_command_composition(
    tmp_path,
) -> None:
    command = tmp_path / "harmless.cmd"
    command.write_text("@echo safe\r\n", encoding="ascii")
    cmd = Path(os.environ.get("ComSpec", ""))
    if not cmd.is_file():
        pytest.skip("CMD interpreter is only available on Windows")
    tool = ToolDefinition(
        id="cmd-tool",
        label="CMD tool",
        script=command,
        kind="cmd",
        interpreter=cmd,
        arguments=("safe", "& whoami"),
    )

    with pytest.raises(ValueError, match="metachar"):
        launch_arguments(tool)


@pytest.mark.skipif(os.name != "nt", reason="Windows launcher fixtures")
@pytest.mark.parametrize("kind", ["cmd", "ps1"])
def test_windows_launchers_preserve_safe_spaced_arguments(tmp_path, kind):
    script = tmp_path / f"with spaces.{kind}"
    script.write_text(
        "@echo off\necho %~1\n"
        if kind == "cmd"
        else "param([string]$Value)\nWrite-Output $Value\n"
    )
    tool = ToolDefinition(
        "sample", "Sample", script, kind=kind, arguments=("two words",)
    )
    result = run_tool(review_tool(tool))
    assert result.status == "completed"
    assert result.exit_code == 0, result.stderr
    assert "two words" in result.stdout


@pytest.mark.skipif(os.name != "nt", reason="Windows Job Object ownership")
def test_owned_child_is_killed_even_when_parent_exits(tmp_path):
    marker = tmp_path / "escaped.txt"
    child = tmp_path / "child.py"
    child.write_text(
        "import time\nfrom pathlib import Path\ntime.sleep(0.5)\n"
        f"Path({str(marker)!r}).write_text('escaped')\n"
    )
    parent = tmp_path / "parent.py"
    parent.write_text(
        "import subprocess, sys\n"
        f"p=subprocess.Popen([sys.executable, {str(child)!r}])\n"
        "print(p.pid, flush=True)\n"
    )
    result = run_tool(review_tool(_python_tool(parent)))
    assert result.status == "completed" and result.exit_code == 0
    sleep(0.6)
    assert not marker.exists()


def test_tool_dialog_import_review_and_change_never_auto_execute(qtbot, tmp_path):
    from modem_controller.ui.tools_dialog import ToolsDialog

    script = tmp_path / "sample.py"
    script.write_text("print('GUI fixture')\n")
    registry = tmp_path / "tools.json"
    registry.write_text(
        json.dumps(
            {
                "tools": [
                    {
                        "id": "sample",
                        "label": "Sample",
                        "script": str(script),
                        "kind": "python",
                        "interpreter": sys.executable,
                    }
                ]
            }
        )
    )
    dialog = ToolsDialog(tmp_path)
    qtbot.addWidget(dialog)
    assert dialog.thread is None and not dialog.run_button.isEnabled()
    dialog._review()
    assert dialog.run_button.isEnabled()
    dialog.arguments.setPlainText('["changed"]')
    assert not dialog.run_button.isEnabled() and dialog.thread is None
    dialog._review()
    dialog._run()
    qtbot.waitUntil(lambda: dialog.thread.isFinished(), timeout=5000)
    qtbot.waitUntil(lambda: "GUI fixture" in dialog.output.toPlainText(), timeout=5000)


def test_escape_waits_for_tool_cleanup_before_dismissing(qtbot, tmp_path):
    from modem_controller.ui.tools_dialog import ToolsDialog, _ToolThread

    script = _write_python_script(
        tmp_path / "sleeper.py", "import time; time.sleep(10)"
    )
    dialog = ToolsDialog(tmp_path)
    qtbot.addWidget(dialog)
    dialog.show()
    dialog.thread = _ToolThread(review_tool(_python_tool(script)), dialog)
    dialog.thread.finished.connect(dialog._finished)
    dialog.thread.start()
    dialog.reject()
    assert dialog.close_pending and dialog.isVisible()
    qtbot.waitUntil(lambda: not dialog.isVisible(), timeout=5000)
    assert dialog.thread.isFinished()


def test_network_script_is_rejected_without_opening_it():
    with pytest.raises(ValueError, match="Network"):
        _python_tool(Path(r"\\server\share\tool.py"))

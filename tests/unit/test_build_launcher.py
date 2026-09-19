"""Exercise the Windows build entry point with a harmless local uv substitute."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows CMD entry point")
SOURCE = Path(__file__).parents[2] / "build-portable.cmd"


def run_launcher(tmp_path, *arguments, sync_code=0, build_code=0, available=True):
    project = tmp_path / "project with spaces"
    project.mkdir()
    shutil.copy2(SOURCE, project / SOURCE.name)
    fake_bin = tmp_path / "fake bin"
    fake_bin.mkdir()
    trace = tmp_path / "calls.txt"
    if available:
        (fake_bin / "uv.cmd").write_text(
            "@echo off\n"
            'cd>>"%UV_TRACE%"\n'
            'echo %*>>"%UV_TRACE%"\n'
            'if "%~1"=="sync" exit /b %UV_SYNC_CODE%\n'
            "exit /b %UV_BUILD_CODE%\n",
            encoding="ascii",
        )
    env = {
        **os.environ,
        "PATH": str(fake_bin)
        + os.pathsep
        + str(Path(os.environ["SystemRoot"]) / "System32"),
        "UV_TRACE": str(trace),
        "UV_SYNC_CODE": str(sync_code),
        "UV_BUILD_CODE": str(build_code),
    }
    result = subprocess.run(
        [
            os.environ["COMSPEC"],
            "/d",
            "/c",
            str(project / SOURCE.name),
            "--no-pause",
            *arguments,
        ],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
        timeout=10,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    recorded = trace.read_text().splitlines() if trace.exists() else []
    lines = [
        f"{cwd} | {args}"
        for cwd, args in zip(recorded[::2], recorded[1::2], strict=True)
    ]
    return result, project, lines


def test_build_launcher_uses_project_root_and_frozen_environment(tmp_path):
    result, project, lines = run_launcher(tmp_path)
    assert result.returncode == 0, result.stderr
    assert len(lines) == 2
    assert all(Path(line.split(" | ", 1)[0]) == project for line in lines), lines
    assert lines[0].endswith("sync --frozen")
    assert (
        lines[1]
        .rstrip()
        .endswith("run --frozen --no-sync python tools/build_portable.py")
    )
    assert "dist" in result.stdout and "ModemController.exe" in result.stdout
    assert "intermediate" in result.stdout


def test_candidate_option_reaches_build_tool(tmp_path):
    result, _, lines = run_launcher(tmp_path, "--candidate")
    assert result.returncode == 0
    assert lines[-1].endswith("tools/build_portable.py --candidate")


@pytest.mark.parametrize(("sync_code", "build_code", "calls"), [(7, 0, 1), (0, 9, 2)])
def test_failure_stops_and_preserves_exit_code(tmp_path, sync_code, build_code, calls):
    result, _, lines = run_launcher(
        tmp_path, sync_code=sync_code, build_code=build_code
    )
    assert result.returncode == (sync_code or build_code)
    assert len(lines) == calls
    assert "Build complete" not in result.stdout
    assert "Build failed" in result.stdout


def test_missing_uv_is_actionable_and_does_not_build(tmp_path):
    result, _, lines = run_launcher(tmp_path, available=False)
    assert result.returncode == 1
    assert not lines
    assert "uv was not found" in result.stdout


@pytest.mark.parametrize(("argument", "code"), [("--help", 0), ("--unknown", 2)])
def test_help_and_invalid_arguments_never_start_build(tmp_path, argument, code):
    result, _, lines = run_launcher(tmp_path, argument)
    assert result.returncode == code
    assert not lines

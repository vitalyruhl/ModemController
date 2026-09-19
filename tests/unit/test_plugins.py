"""Plugin discovery and explicit launch without running host tools."""

import json
import sys
from pathlib import Path

import pytest

from modem_controller.workflows.plugins import (
    discover_plugins,
    launch_plugin,
    load_plugin,
    plugin_arguments,
)


def make_plugin(root, name="sample", **changes):
    directory = root / name
    directory.mkdir(parents=True)
    data = {"name": "Sample tool", "program": "tool.exe", **changes}
    (directory / "plugin.json").write_text(json.dumps(data), encoding="utf-8")
    return directory


def test_discovery_only_lists_valid_child_plugin_directories(tmp_path):
    valid = make_plugin(tmp_path)
    make_plugin(tmp_path, "bad", arguments="not a list")
    (tmp_path / "missing").mkdir()
    (tmp_path / "other.json").write_text("{}")
    assert [p.directory for p in discover_plugins(tmp_path)] == [valid.resolve()]
    assert discover_plugins(tmp_path / "absent") == ()


@pytest.mark.parametrize(
    "data",
    [
        [],
        None,
        {},
        {"name": "X", "program": "x", "unknown": True},
        {"name": "X", "program": "x", "arguments": [1]},
        {"name": "X", "program": "x\u0000"},
    ],
)
def test_invalid_configuration_is_rejected(tmp_path, data):
    (tmp_path / "plugin.json").write_text(json.dumps(data))
    with pytest.raises(ValueError):
        load_plugin(tmp_path)


def test_relative_program_and_argument_paths_use_plugin_directory(tmp_path):
    directory = make_plugin(tmp_path, arguments=["config/my data.json", "& literal"])
    (directory / "tool.exe").write_bytes(b"fake")
    plugin = load_plugin(directory)
    program, arguments = plugin_arguments(plugin)
    assert program == str((directory / "tool.exe").resolve())
    assert arguments == ["config/my data.json", "& literal"]
    calls = []
    assert (
        launch_plugin(plugin, detached=lambda *a: calls.append(a) or (True, 321)) == 321
    )
    assert calls == [(program, arguments, str(directory.resolve()))]


def test_powershell_plugin_uses_system_runtime_without_policy_or_elevation(
    tmp_path, monkeypatch
):
    directory = make_plugin(tmp_path, program="launch.ps1")
    (directory / "launch.ps1").write_text("# fake")
    monkeypatch.setenv("SystemRoot", str(tmp_path / "Windows"))
    program, arguments = plugin_arguments(load_plugin(directory))
    assert program == str(
        tmp_path / "Windows/System32/WindowsPowerShell/v1.0/powershell.exe"
    )
    assert arguments == ["-NoProfile", "-STA", "-File", str(directory / "launch.ps1")]


def test_missing_program_and_failed_launch_are_visible_errors(tmp_path):
    directory = make_plugin(tmp_path)
    plugin = load_plugin(directory)
    with pytest.raises(ValueError, match="unavailable"):
        launch_plugin(plugin, detached=lambda *a: pytest.fail("Must not launch"))
    (directory / "tool.exe").write_bytes(b"fake")
    with pytest.raises(RuntimeError, match="could not start"):
        launch_plugin(plugin, detached=lambda *a: (False, 0))


def test_real_detached_fixture_preserves_arguments_and_plugin_working_directory(
    qtbot, tmp_path
):
    directory = make_plugin(
        tmp_path,
        program=sys.executable,
        arguments=[
            "-c",
            "from pathlib import Path; import sys; "
            "Path('result.txt').write_text(sys.argv[1])",
            "two words & literal",
        ],
    )
    assert launch_plugin(load_plugin(directory)) > 0
    marker = directory / "result.txt"
    qtbot.waitUntil(marker.exists, timeout=5000)
    qtbot.waitUntil(lambda: marker.read_text() == "two words & literal", timeout=5000)


def test_dialog_does_not_start_on_open_or_selection_only_explicit_click(
    qtbot, tmp_path, monkeypatch
):
    from modem_controller.ui import tools_dialog

    make_plugin(tmp_path / "plugins")
    make_plugin(tmp_path / "plugins", "second")
    calls = []
    monkeypatch.setattr(
        tools_dialog, "launch_plugin", lambda plugin: calls.append(plugin) or 99
    )
    dialog = tools_dialog.ToolsDialog(tmp_path)
    qtbot.addWidget(dialog)
    assert not calls
    assert dialog.selector.count() == 2
    dialog.selector.setCurrentIndex(1)
    assert not calls
    assert not hasattr(dialog, "preview")
    assert not hasattr(dialog, "review_button")
    dialog.run_button.click()
    assert len(calls) == 1
    dialog.reject()
    assert len(calls) == 1


def test_dialog_empty_folder_has_no_launch_action(qtbot, tmp_path):
    (tmp_path / "plugins").mkdir()
    from modem_controller.ui.tools_dialog import ToolsDialog

    dialog = ToolsDialog(tmp_path)
    qtbot.addWidget(dialog)
    assert not dialog.run_button.isEnabled()


def test_bundled_ras_plugin_has_no_personal_settings_and_owns_its_launcher():
    directory = (
        Path(__file__).parents[2]
        / "src/modem_controller/tool_data/plugins/ras-collector"
    )
    plugin = load_plugin(directory)
    assert plugin.arguments == ()
    assert plugin.program == directory.resolve() / "launch.ps1"
    assert (directory / "ras-collect.ps1").is_file()


def test_missing_portable_plugins_do_not_fall_back_to_internal_resources(
    qtbot, tmp_path, monkeypatch
):
    from modem_controller.ui import tools_dialog

    monkeypatch.setattr(tools_dialog.sys, "frozen", True, raising=False)
    dialog = tools_dialog.ToolsDialog(tmp_path)
    qtbot.addWidget(dialog)
    assert dialog.plugins == ()


def test_source_checkout_can_show_bundled_plugins_without_copying_them(qtbot, tmp_path):
    from modem_controller.ui.tools_dialog import ToolsDialog

    dialog = ToolsDialog(tmp_path)
    qtbot.addWidget(dialog)
    assert any(p.name == "Windows RAS diagnostics" for p in dialog.plugins)
    assert not (tmp_path / "plugins").exists()

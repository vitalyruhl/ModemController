import json
from pathlib import Path

import pytest

from modem_controller.versioning import build_time_label, product_version, read_version


@pytest.mark.parametrize(
    "value", ["2.0", "v2.0.0", "02.0.0", "", None, "2.0.0+unknown"]
)
def test_invalid_version_rejected(tmp_path, value):
    path = tmp_path / "version.json"
    path.write_text(json.dumps({"version": value}))
    with pytest.raises(ValueError):
        read_version(path)


def test_missing_and_malformed_version_rejected(tmp_path):
    path = tmp_path / "version.json"
    with pytest.raises(ValueError):
        read_version(path)
    path.write_text("broken")
    with pytest.raises(ValueError):
        read_version(path)


def test_source_package_and_gui_version_agree(qtbot):
    from importlib.metadata import version

    from modem_controller.ui.main_window import MainWindow

    root = Path(__file__).parents[2]
    expected = read_version(root / "version.json")
    assert expected == product_version() == version("modem-controller-rs232")
    window = MainWindow(port_provider=lambda: [])
    qtbot.addWidget(window)
    assert window.windowTitle() == f"Modem Controller {expected}"


def test_packaged_resource_used_without_source(monkeypatch, tmp_path):
    import modem_controller.versioning as module

    (tmp_path / "_version.json").write_text(json.dumps({"version": "2.3.4"}))
    monkeypatch.setattr(module, "_source_root", lambda: None)
    monkeypatch.setattr(module, "__file__", str(tmp_path / "versioning.py"))
    assert module.product_version() == "2.3.4"


def test_stale_packaged_build_identity_is_rejected(monkeypatch, tmp_path):
    import modem_controller.versioning as module

    (tmp_path / "_version.json").write_text('{"version":"2.0.0"}')
    (tmp_path / "_build.json").write_text('{"version":"1.0.0"}')
    monkeypatch.setattr(module, "_source_root", lambda: None)
    monkeypatch.setattr(module, "__file__", str(tmp_path / "versioning.py"))
    with pytest.raises(ValueError, match="does not match"):
        module.build_info()


def test_build_time_label_uses_only_recorded_build_time():
    assert build_time_label({"built_at_utc": "2026-09-19T18:00:00+00:00"}) == (
        "2026-09-19T18:00:00+00:00"
    )
    assert build_time_label({}) == "Development checkout (not packaged)"

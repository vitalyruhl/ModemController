from modem_controller.catalog.storage import Settings, SettingsStore
from modem_controller.ui.main_window import MainWindow


def test_window_restores_preferences_without_opening_a_connection(
    qtbot, tmp_path
) -> None:
    store = SettingsStore(tmp_path)
    store.save(
        Settings(
            selected_profile="mc55i-qw",
            selected_category="Status",
            connection={"port": "COM10", "baud_rate": "19200"},
        )
    )
    window = MainWindow(port_provider=lambda: ["COM10"], settings_store=store)
    qtbot.addWidget(window)

    assert window.profile_selector.currentData() == "mc55i-qw"
    assert window.category_selector.currentText() == "Status"
    assert window.connection_panel.port_selector.currentText() == "COM10"
    assert window.connection_panel.baud_rate.currentText() == "19200"
    assert window.connection_panel.status.text() == "Disconnected"


def test_window_saves_explicit_ui_preferences_on_close(qtbot, tmp_path) -> None:
    store = SettingsStore(tmp_path)
    window = MainWindow(port_provider=lambda: ["COM10"], settings_store=store)
    qtbot.addWidget(window)
    window.profile_selector.setCurrentIndex(
        window.profile_selector.findData("mc55i-qw")
    )
    window.category_selector.setCurrentText("Status")
    window.connection_panel.baud_rate.setCurrentText("19200")

    window.close()

    saved = store.load().settings
    assert saved.selected_profile == "mc55i-qw"
    assert saved.selected_category == "Status"
    assert saved.connection["port"] == "COM10"
    assert saved.connection["baud_rate"] == "19200"


def test_window_restores_explicit_file_logging_preferences(qtbot, tmp_path) -> None:
    store = SettingsStore(tmp_path)
    log_path = tmp_path / "evidence.log"
    store.save(
        Settings(
            log_file=str(log_path),
            logging_enabled=True,
            logging_mode="verbose",
        )
    )

    window = MainWindow(port_provider=lambda: ["COM10"], settings_store=store)
    qtbot.addWidget(window)

    assert window.enable_logging_action.isChecked()
    assert window.verbose_logging_action.isChecked()
    assert window._session_log.path == log_path
    assert "LOGGING enabled mode=verbose" in log_path.read_text(encoding="utf-8")


def test_transient_search_connection_is_not_persisted_as_selected_settings(
    qtbot, tmp_path
):
    store = SettingsStore(tmp_path)
    window = MainWindow(port_provider=lambda: ["COM10"], settings_store=store)
    qtbot.addWidget(window)
    window.connection_panel.baud_rate.setCurrentText("19200")
    window._transient_connection = window.connection_panel.preferences()
    window.connection_panel.baud_rate.setCurrentText("9600")
    assert window._save_preferences()
    assert window.connection_panel.selected_settings().baud_rate == 9600
    assert store.load().settings.connection["baud_rate"] == "19200"

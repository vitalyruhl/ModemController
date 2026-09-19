from pathlib import Path

from modem_controller.ui.session_log import LogMode, SessionLog


def test_pin_and_fragmented_echo_are_replaced_by_a_gap(tmp_path: Path) -> None:
    log = SessionLog()
    path = tmp_path / "privacy.log"
    log.configure(path, enabled=True, mode=LogMode.VERBOSE)
    log.record_sent(b"AT+CPIN=1234\r")
    log.record_received(b"AT+CP")
    log.record_received(b"IN=1234\r\nOK\r\n")
    log.close()
    saved = path.read_text()
    assert "1234" not in saved
    assert "31 32 33 34" not in saved
    assert "CAPTURE GAP" in saved


def test_normal_log_records_text_payloads(tmp_path: Path) -> None:
    path = tmp_path / "session.log"
    log = SessionLog()
    log.configure(path, enabled=True, mode=LogMode.NORMAL)
    log.record_sent(b"AT\r")
    log.record_sent(b'AT+CMGS="491234567"\r')
    log.record_received(b"\r\nOK\r\n")
    log.record_connected("COM10 | 19200 Bd")

    content = path.read_text(encoding="utf-8")

    assert "TX 'AT\\r'" in content
    assert "TX 'AT+CMGS=\"491234567\"\\r'" in content
    assert "RX '\\r\\nOK\\r\\n'" in content
    assert "HEX" not in content
    assert "CONNECTED" not in content


def test_verbose_log_adds_connection_events_and_hex_payloads(tmp_path: Path) -> None:
    path = tmp_path / "session.log"
    log = SessionLog()
    log.configure(path, enabled=True, mode=LogMode.VERBOSE)
    log.record_connected("COM10 | 19200 Bd")
    log.record_sent(b"AT\r")
    log.record_received(b"\r\nOK\r\n")
    log.record_disconnected()
    log.record_connect_requested("COM10 | 115200 Bd | 8N1 | none")
    log.record_preset_requested("AT plus CR", b"AT\r")
    log.record_terminal_cleared()

    content = path.read_text(encoding="utf-8")

    assert "CONNECTED COM10 | 19200 Bd" in content
    assert "TX HEX 41 54 0D" in content
    assert "RX HEX 0D 0A 4F 4B 0D 0A" in content
    assert "DISCONNECTED" in content
    assert "CONNECT REQUESTED COM10 | 115200 Bd | 8N1 | none" in content
    assert "PRESET REQUESTED AT plus CR: 41 54 0D" in content
    assert "TERMINAL CLEARED" in content

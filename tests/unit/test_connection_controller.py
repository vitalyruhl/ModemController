from collections import deque

from modem_controller.catalog.models import load_starter_catalog
from modem_controller.transport.serial_port import SerialPortError, SerialSettings
from modem_controller.ui.connection_controller import (
    ConnectionController,
    SerialConnectionWorker,
)
from modem_controller.workflows.connection_search import SearchOutcome


class FakePort:
    def __init__(self) -> None:
        self.is_open = False
        self.settings: SerialSettings | None = None
        self.received: deque[bytes] = deque()
        self.writes: list[tuple[bytes, bool]] = []

    def open(self, settings: SerialSettings) -> None:
        self.is_open = True
        self.settings = settings

    def close(self) -> None:
        self.is_open = False

    def read_available(self) -> bytes:
        return self.received.popleft() if self.received else b""

    def write(self, payload: bytes) -> int:
        if not self.is_open:
            raise SerialPortError("port is closed")
        self.writes.append((payload, False))
        return len(payload)

    def write_sensitive(self, payload: bytes) -> int:
        if not self.is_open:
            raise SerialPortError("port is closed")
        self.writes.append((payload, True))
        return len(payload)


def test_worker_opens_sends_receives_and_closes_without_ui_thread_io(qtbot) -> None:
    port = FakePort()
    worker = SerialConnectionWorker(lambda: port)
    connected: list[str] = []
    received: list[bytes] = []
    transmitted: list[bytes] = []
    worker.connected.connect(connected.append)
    worker.received.connect(received.append)
    worker.transmitted.connect(transmitted.append)

    worker.open(SerialSettings(port="COM10", baud_rate=19200))
    worker.send(b"AT\r", False)
    port.received.append(b"AT\r\r\nOK\r\n")
    worker.poll()
    worker.send(b"AT+CPIN=1234\r", True)
    worker.close()

    assert connected == ["COM10 | 19200 Bd | 8N1 | None"]
    assert port.writes == [(b"AT\r", False), (b"AT+CPIN=1234\r", True)]
    assert received == [b"AT\r\r\nOK\r\n"]
    assert transmitted == [b"AT\r"]
    assert not port.is_open


def test_worker_confirms_control_bytes_only_after_the_write_succeeds(qtbot) -> None:
    port = FakePort()
    port.open(SerialSettings(port="COM10"))
    worker = SerialConnectionWorker(lambda: port)
    worker._port = port
    confirmed: list[bytes] = []
    worker.control_bytes_sent.connect(confirmed.append)

    worker.send_control_bytes(b"\r")

    assert port.writes == [(b"\r", False)]
    assert confirmed == [b"\r"]

    port.close()
    worker.send_control_bytes(b"\x1b")

    assert confirmed == [b"\r"]


def test_controller_shutdown_closes_the_worker_owned_port(qtbot) -> None:
    port = FakePort()
    controller = ConnectionController(port_factory=lambda: port)

    with qtbot.waitSignal(controller.connected, timeout=1_000):
        controller.open(SerialSettings(port="COM10"))
    controller.shutdown()

    assert not port.is_open


def test_controller_relays_control_byte_write_confirmation(qtbot) -> None:
    port = FakePort()
    controller = ConnectionController(port_factory=lambda: port)

    with qtbot.waitSignal(controller.connected, timeout=1_000):
        controller.open(SerialSettings(port="COM10"))
    with qtbot.waitSignal(controller.control_bytes_sent, timeout=1_000):
        controller.send_control_bytes(b"\r")

    assert port.writes == [(b"\r", False)]
    controller.shutdown()


def test_worker_runs_read_only_diagnostics_through_the_at_session(qtbot) -> None:
    port = FakePort()
    port.open(SerialSettings(port="COM10"))
    port.received.extend(
        b"\r\nOK\r\n" for _ in load_starter_catalog().profile("mc55i-qw").commands
    )
    worker = SerialConnectionWorker(lambda: port)
    worker._port = port
    completed: list[object] = []
    worker.diagnostics_completed.connect(completed.append)

    worker.run_diagnostics(load_starter_catalog().profile("mc55i-qw"))

    assert len(completed) == 1
    assert [payload for payload, _ in port.writes] == [b"AT\r", b"ATI\r"]


def test_worker_connection_search_requires_repeated_at_responses(qtbot) -> None:
    ports = [FakePort(), FakePort()]
    for port in ports:
        port.received.append(b"\r\nOK\r\n")
    worker = SerialConnectionWorker(lambda: ports.pop(0))
    completed: list[object] = []
    worker.search_completed.connect(completed.append)

    worker.search_settings("COM10")

    assert completed[0].selected is not None
    assert completed[0].selected.settings.baud_rate == 9600
    assert len(completed[0].attempts) == 1
    assert completed[0].attempts[0].outcome is SearchOutcome.CONFIRMED


def test_worker_runs_confirmed_maintenance_once_then_closes(qtbot) -> None:
    port = FakePort()
    port.open(SerialSettings(port="COM10"))
    port.received.append(b"\r\nOK\r\n")
    worker = SerialConnectionWorker(lambda: port)
    worker._port = port
    completed: list[object] = []
    worker.maintenance_completed.connect(completed.append)
    command = load_starter_catalog().profile("generic-at").command("restart-modem")

    worker.run_maintenance(command, {})

    assert completed[0] is not None
    assert [payload for payload, _ in port.writes] == [b"AT+CFUN=1,1\r"]
    assert not port.is_open


def test_worker_queries_sms_status_with_at_session(qtbot) -> None:
    port = FakePort()
    port.open(SerialSettings(port="COM10"))
    port.received.extend((b"\r\nOK\r\n",) * 3)
    worker = SerialConnectionWorker(lambda: port)
    worker._port = port
    completed: list[object] = []
    worker.sms_status_completed.connect(completed.append)

    worker.query_sms_status()

    assert len(completed) == 1
    assert [payload for payload, _ in port.writes] == [
        b"AT+CMGF?\r",
        b"AT+CSCS?\r",
        b"AT+CPMS?\r",
    ]


def test_worker_records_full_sms_wire_payloads_and_responses(qtbot) -> None:
    port = FakePort()
    port.open(SerialSettings(port="COM10"))
    port.received.extend((b"\r\n> ", b"\r\n+CMGS: 7\r\nOK\r\n"))
    worker = SerialConnectionWorker(lambda: port)
    worker._port = port
    transmitted: list[bytes] = []
    received: list[bytes] = []
    worker.transmitted.connect(transmitted.append)
    worker.session_received.connect(received.append)

    worker.send_sms("491234567", "evidence text")

    assert transmitted == [b'AT+CMGS="491234567"\r', b"evidence text\x1a"]
    assert received == [b"\r\n> ", b"\r\n+CMGS: 7\r\nOK\r\n"]


def test_guided_pin_never_reaches_log_signals_or_result(qtbot) -> None:
    port = FakePort()
    port.open(SerialSettings(port="FAKE"))
    port.received.extend((b"AT+CP", b"IN=1234\r\nOK\r\n"))
    worker = SerialConnectionWorker(lambda: port)
    worker._port = port
    sent, received, results = [], [], []
    worker.transmitted.connect(sent.append)
    worker.session_received.connect(received.append)
    worker.maintenance_completed.connect(results.append)
    command = load_starter_catalog().profile("generic-at").command("unlock-sim")
    worker.run_maintenance(command, {"pin": "1234"})
    assert port.writes == [(b"AT+CPIN=1234\r", True)]
    assert sent == received == []
    assert b"1234" not in repr(results).encode()
    assert not port.is_open


def test_manual_hex_pin_suppresses_late_received_echo(qtbot) -> None:
    port = FakePort()
    port.open(SerialSettings(port="FAKE"))
    worker = SerialConnectionWorker(lambda: port)
    worker._port = port
    sent, received = [], []
    worker.transmitted.connect(sent.append)
    worker.received.connect(received.append)
    worker.send(bytes.fromhex("41 54 2b 43 50 49 4e 3d 31 32 33 34 0d"), False)
    port.received.extend((b"AT+CP", b"IN=1234\r\n", b"OK\r\n"))
    for _ in range(3):
        worker.poll()
    assert sent == received == []
    assert port.writes[0][1] is True

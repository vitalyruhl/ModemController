"""Focused P19 test contract; move to tests/unit/test_cli.py with P19."""

from __future__ import annotations

import os
import subprocess
import sys
from io import StringIO
from pathlib import Path

import pytest

from modem_controller.cli import encode_input, main
from modem_controller.transport.serial_port import SerialIOError


class FakePort:
    def __init__(self, *, write_error: Exception | None = None) -> None:
        self.is_open = False
        self.settings = None
        self.writes: list[bytes] = []
        self.closed = False
        self.write_error = write_error
        self.received = b""

    def open(self, settings) -> None:
        self.settings = settings
        self.is_open = True

    def close(self) -> None:
        self.is_open = False
        self.closed = True

    def write(self, payload: bytes) -> int:
        if self.write_error is not None:
            raise self.write_error
        self.writes.append(payload)
        self.received += b"\r\nOK\r\n"
        return len(payload)

    def read_available(self, max_bytes: int = 4096) -> bytes:
        data, self.received = self.received, b""
        return data


def test_one_shot_send_requires_explicit_open_and_creates_no_port() -> None:
    factories: list[FakePort] = []

    def factory() -> FakePort:
        port = FakePort()
        factories.append(port)
        return port

    output = StringIO()
    assert (
        main(["-c", "COM10", "send", "AT&V"], port_factory=factory, stdout=output) != 0
    )
    assert all(not port.is_open and not port.writes for port in factories)
    assert "open" in output.getvalue().casefold()


def test_case_insensitive_open_and_connect_preserve_send_payload_exactly() -> None:
    port = FakePort()
    output = StringIO()

    exit_code = main(
        ["--OPEN", "-C", "COM10", "send", "At&V"],
        port_factory=lambda: port,
        stdout=output,
    )

    assert exit_code == 0
    assert port.settings.port == "COM10"
    assert port.writes == [b"At&V\r"]
    assert port.closed


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("<CR>", b"\r"),
        ("<LF>", b"\n"),
        ("<CRLF>", b"\r\n"),
        ("<ESC>", b"\x1b"),
        ("<CTRL+Z>", b"\x1a"),
        ("AT", b"AT\n"),
    ],
)
def test_encode_input_uses_exact_control_tokens_without_a_terminator(
    text: str, expected: bytes
) -> None:
    assert encode_input(text, terminator=b"\n") == expected


def test_encode_input_rejects_unknown_tokens_and_non_ascii_text() -> None:
    with pytest.raises(ValueError):
        encode_input("<BREAK>")
    with pytest.raises(ValueError):
        encode_input("Grüße")


@pytest.mark.parametrize("quit", ["--quit", "--quitt", "-Q"])
def test_interactive_quit_aliases_close_without_transmitting(quit: str) -> None:
    port = FakePort()

    exit_code = main(
        ["--open", "-c", "COM10"],
        port_factory=lambda: port,
        stdin=StringIO(quit + "\n"),
        stdout=StringIO(),
    )

    assert exit_code == 0
    assert port.writes == []
    assert port.closed


class InterruptingInput:
    def readline(self) -> str:
        raise KeyboardInterrupt


@pytest.mark.parametrize("stream", [StringIO(""), InterruptingInput()])
def test_eof_or_interrupt_closes_the_open_port(stream) -> None:
    port = FakePort()

    exit_code = main(
        ["--open", "-c", "COM10"],
        port_factory=lambda: port,
        stdin=stream,
        stdout=StringIO(),
    )

    assert exit_code in {0, 130}
    assert port.closed


def test_write_error_is_reported_and_closes_port() -> None:
    port = FakePort(write_error=SerialIOError("synthetic write failure"))
    output = StringIO()

    exit_code = main(
        ["--open", "-c", "COM10", "send", "AT"],
        port_factory=lambda: port,
        stdout=output,
    )

    assert exit_code != 0
    assert "write failure" in output.getvalue()
    assert port.closed


def test_cli_imports_without_qt() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; sys.modules['PySide6'] = None; import modem_controller.cli",
        ],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "PYTHONPATH": str(Path(__file__).parents[2] / "src")},
    )

    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("alias", ["--Log", "-L", "-LV"])
def test_log_alias_preserves_path_case(alias, tmp_path):
    path = tmp_path / "MixedCase.log"
    assert (
        main(
            ["--open", "-c", "COM10", alias, str(path), "SEND", "At"],
            port_factory=FakePort,
            stdout=StringIO(),
        )
        == 0
    )
    content = path.read_text()
    assert "At" in content and "OK" in content
    assert ("TX HEX" in content) == (alias == "-LV")


def test_timeout_is_not_success_and_closes():
    port = FakePort()
    port.read_available = lambda max_bytes=4096: b""
    output = StringIO()
    assert (
        main(
            ["--open", "-c", "COM10", "--timeout", "0.01", "send", "AT"],
            port_factory=lambda: port,
            stdout=output,
        )
        == 3
    )
    assert "timed_out" in output.getvalue() and port.closed


def test_read_error_closes_and_no_default_open():
    port = FakePort()

    def fail(max_bytes=4096):
        raise SerialIOError("synthetic read failure")

    port.read_available = fail
    assert (
        main(
            [],
            port_factory=lambda: pytest.fail("must not instantiate"),
            stdout=StringIO(),
        )
        == 0
    )
    output = StringIO()
    assert (
        main(
            ["--open", "-c", "COM10", "send", "AT"],
            port_factory=lambda: port,
            stdout=output,
        )
        == 2
    )
    assert port.closed and "read failure" in output.getvalue()


def test_credential_arguments_never_open_or_enter_log(tmp_path):
    path = tmp_path / "secret.log"
    output = StringIO()
    assert (
        main(
            ["--open", "-c", "COM10", "--log", str(path), "send", 'AT+CPIN="1234"'],
            port_factory=lambda: pytest.fail("must not instantiate"),
            stdout=output,
        )
        == 2
    )
    assert "1234" not in output.getvalue() and not path.exists()


def test_gui_owner_prevents_console_backend_open(qtbot):
    from test_serial_port import FakeSerialBackend

    from modem_controller.transport.serial_port import SerialPort, SerialSettings
    from modem_controller.ui.connection_controller import SerialConnectionWorker

    owners = set()

    class ExclusiveBackend(FakeSerialBackend):
        def open(self):
            if owners:
                raise OSError("port already owned")
            owners.add(self)
            super().open()

        def close(self):
            owners.discard(self)
            super().close()

    def factory():
        return SerialPort(backend_factory=lambda settings: ExclusiveBackend())

    worker = SerialConnectionWorker(factory)
    worker.open(SerialSettings("COM10"))
    try:
        assert len(owners) == 1
        output = StringIO()
        assert (
            main(
                ["--open", "-c", "COM10"],
                port_factory=factory,
                stdin=StringIO(""),
                stdout=output,
            )
            == 2
        )
        assert "owned" in output.getvalue() and len(owners) == 1
    finally:
        worker.close()
    assert not owners


def test_idle_timeout_closes_without_sending():
    from threading import Event

    release = Event()

    class Input:
        def readline(self):
            release.wait(1)
            return ""

    port = FakePort()
    try:
        assert (
            main(
                ["--open", "-c", "COM10", "--idle-timeout", "0.01"],
                port_factory=lambda: port,
                stdin=Input(),
                stdout=StringIO(),
            )
            == 0
        )
        assert port.closed and not port.writes
    finally:
        release.set()

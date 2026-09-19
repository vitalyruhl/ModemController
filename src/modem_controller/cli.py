"""Explicit, headless serial console using the shared transport and AT scheduler."""

from __future__ import annotations

import argparse
import sys
import time
from datetime import timedelta
from pathlib import Path
from queue import Empty, Full, Queue
from threading import Event, Thread

from modem_controller.protocol.at_session import AtSession, ExchangeOutcome
from modem_controller.transport.privacy import contains_secret_input
from modem_controller.transport.serial_port import (
    FlowControl,
    Parity,
    SerialPort,
    SerialSettings,
)
from modem_controller.ui.session_log import LogMode, SessionLog
from modem_controller.versioning import version_label

TOKENS = {
    "<CR>": b"\r",
    "<LF>": b"\n",
    "<CRLF>": b"\r\n",
    "<ESC>": b"\x1b",
    "<CTRL+Z>": b"\x1a",
}
QUIT = {"-q", "--quit", "--quitt"}


def encode_input(text: str, terminator: bytes = b"\r") -> bytes:
    if len(text) > 65536:
        raise ValueError("Console input is limited to 65536 characters")
    if text.upper() in TOKENS:
        return TOKENS[text.upper()]
    if text.startswith("<") and text.endswith(">"):
        raise ValueError("Unknown control token")
    if any(ord(char) < 32 or ord(char) > 126 for char in text):
        raise ValueError("Use printable ASCII or a standalone control token")
    return text.encode("ascii") + terminator


def _normalize(argv):
    # Only option names and the subcommand are folded; values remain byte-for-byte.
    values = {
        "-c",
        "--connect",
        "--baud",
        "--bits",
        "--parity",
        "--stop-bits",
        "--flow",
        "--terminator",
        "--timeout",
        "--idle-timeout",
        "--log",
        "-l",
        "-lv",
    }
    result, value_next, payload_next = [], False, False
    for item in argv:
        if value_next or payload_next:
            result.append(item)
            value_next = payload_next = False
            continue
        name, separator, value = item.partition("=")
        folded = name.casefold()
        if name.startswith("-"):
            result.append(folded + separator + value)
            value_next = folded in values and not separator
        else:
            result.append(item.casefold())
            payload_next = item.casefold() == "send"
    return result


def _parser():
    parser = argparse.ArgumentParser(description=__doc__, exit_on_error=False)
    parser.add_argument("--version", action="version", version=version_label())
    parser.add_argument("-c", "--connect")
    parser.add_argument("--open", action="store_true")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--bits", type=int, default=8)
    parser.add_argument(
        "--parity", type=str.upper, choices=[p.value for p in Parity], default="N"
    )
    parser.add_argument("--stop-bits", type=float, default=1)
    parser.add_argument(
        "--flow", type=str.lower, choices=[f.value for f in FlowControl], default="none"
    )
    parser.add_argument(
        "--terminator",
        type=str.upper,
        choices=["CR", "LF", "CRLF", "NONE"],
        default="CR",
    )
    parser.add_argument("--timeout", type=float, default=2)
    parser.add_argument(
        "--idle-timeout",
        type=float,
        default=0,
        help="Close after idle seconds; 0 waits for quit",
    )
    logging = parser.add_mutually_exclusive_group()
    logging.add_argument("--log", "-l")
    logging.add_argument("-lv", dest="verbose_log")
    parser.add_argument("command", nargs="?", choices=["send"])
    parser.add_argument("payload", nargs="?")
    return parser


class _ObservedPort:
    def __init__(self, port, log, output):
        self.port, self.log, self.output = port, log, output
        self.secret = False

    @property
    def is_open(self):
        return self.port.is_open

    def _show(self, direction, data):
        if data and not self.secret:
            print(f"{direction} {data!r}", file=self.output, flush=True)

    def write(self, data):
        if contains_secret_input(data):
            raise ValueError(
                "Credential input is excluded from the console; use guided maintenance"
            )
        written = self.port.write(data)
        self.log.record_sent(data[:written])
        self._show("TX", data[:written])
        return written

    def read_available(self, max_bytes=4096):
        data = self.port.read_available(max_bytes)
        if contains_secret_input(data):
            self.secret = True
        self.log.record_received(data)
        self._show("RX", data)
        return data


def _interactive(observed, stdin, stdout, terminator, idle_timeout):
    queue = Queue(maxsize=1)
    stop = Event()

    def read_lines():
        while not stop.is_set():
            try:
                item = stdin.readline()
            except BaseException as error:
                item = error
            while not stop.is_set():
                try:
                    queue.put(item, timeout=0.05)
                    break
                except Full:
                    pass
            if not item or isinstance(item, BaseException):
                break

    Thread(target=read_lines, daemon=True, name="console-input").start()
    last_activity = time.monotonic()
    try:
        while True:
            if observed.read_available():
                last_activity = time.monotonic()
            try:
                line = queue.get(timeout=0.02)
            except Empty:
                if idle_timeout and time.monotonic() - last_activity >= idle_timeout:
                    print("Idle deadline reached; disconnected.", file=stdout)
                    return 0
                continue
            if isinstance(line, BaseException):
                raise line
            if not line or line.rstrip("\r\n").casefold() in QUIT:
                return 0
            text = line.rstrip("\r\n")
            if not text:
                continue
            try:
                payload = encode_input(text, terminator)
                observed.write(payload)
                last_activity = time.monotonic()
            except ValueError as error:
                print(f"Input rejected: {error}", file=stdout)
    finally:
        stop.set()


def main(argv=None, *, port_factory=SerialPort, stdin=None, stdout=None) -> int:
    stdin = sys.stdin if stdin is None else stdin
    stdout = sys.stdout if stdout is None else stdout
    port, log = None, SessionLog()
    result = 0
    try:
        arguments = sys.argv[1:] if argv is None else argv
        if any(contains_secret_input(arg.encode("utf-8")) for arg in arguments):
            raise ValueError("Credential input is excluded from the console")
        args = _parser().parse_args(_normalize(arguments))
        if args.command and (args.payload is None or not args.open):
            raise ValueError("send requires a payload and explicit --open")
        if args.payload is not None and args.command is None:
            raise ValueError("Payload requires send")
        if not args.open:
            print(
                "Disconnected. Use --open -c PORT to connect explicitly.", file=stdout
            )
            return 0
        if not args.connect:
            raise ValueError("--open requires --connect PORT")
        if not 0 <= args.idle_timeout <= 86400:
            raise ValueError("Idle timeout must be between 0 and 86400 seconds")
        terminator = (
            b"" if args.terminator == "NONE" else TOKENS[f"<{args.terminator}>"]
        )
        payload = encode_input(args.payload, terminator) if args.command else None
        if payload is not None and contains_secret_input(payload):
            raise ValueError("Credential input is excluded from the console")
        settings = SerialSettings(
            args.connect,
            args.baud,
            args.bits,
            Parity(args.parity),
            args.stop_bits,
            FlowControl(args.flow),
            response_timeout=args.timeout,
        )
        path = args.verbose_log or args.log
        log.configure(
            Path(path) if path else None,
            enabled=bool(path),
            mode=LogMode.VERBOSE if args.verbose_log else LogMode.NORMAL,
        )
        port = port_factory()
        log.record_connect_requested(str(settings))
        port.open(settings)
        log.record_connected(str(settings))
        observed = _ObservedPort(port, log, stdout)
        if payload is None:
            print(
                "Connected. Enter ASCII/control tokens; -Q, --quit or --quitt closes.",
                file=stdout,
            )
            result = _interactive(
                observed, stdin, stdout, terminator, args.idle_timeout
            )
        elif args.payload.upper() in TOKENS:
            observed.write(payload)
            print(
                "Control bytes transmitted; no command success inferred.", file=stdout
            )
        else:
            session = AtSession(observed, clock=time.monotonic)
            session.start(payload, timeout=timedelta(seconds=args.timeout))
            while True:
                exchange = session.poll()
                if exchange is not None:
                    if exchange.outcome != ExchangeOutcome.COMPLETED:
                        print(
                            f"Response {exchange.outcome.value}; no automatic retry.",
                            file=stdout,
                        )
                        result = 3
                    elif exchange.final_result != b"OK":
                        result = 4
                    break
                time.sleep(0.01)
    except SystemExit as error:
        result = int(error.code or 0)
    except KeyboardInterrupt:
        print("Cancelled; disconnected.", file=stdout)
        result = 130
    except (OSError, ValueError, RuntimeError, argparse.ArgumentError) as error:
        # Do not repeat parser input or device exception text containing credentials.
        message = str(error)
        if contains_secret_input(message.encode("utf-8")):
            message = "Sensitive operation rejected."
        print(f"Error: {message}", file=stdout)
        result = 2
    finally:
        try:
            if port is not None:
                port.close()
                log.record_disconnected()
            log.close()
        except (OSError, RuntimeError):
            print("Error while closing connection or log.", file=stdout)
            result = 2
    return result


if __name__ == "__main__":
    raise SystemExit(main())

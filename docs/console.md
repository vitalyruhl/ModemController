# Headless serial console

Run `modem-console --help`, or `python -m modem_controller.cli --help` from the
development environment. No Qt application is loaded. Without `--open`, the
console stays disconnected. Close the desktop connection before opening the
same COM port in the console; Windows grants only one owner.

```powershell
modem-console --open -c COM10 --baud 115200 send "AT"
modem-console --open -c COM10 --terminator CR --Log "session.log"
modem-console --open -c COM10 -LV "verbose.log"
```

Options and command names ignore case; payloads and file paths preserve case.
`--bits`, `--parity`, `--stop-bits`, `--flow`, `--timeout` and `--terminator`
configure the connection explicitly. Flow values are none, rts_cts and dsr_dtr.
No autobaud search or modem configuration is implicit.

Interactive input sends printable ASCII with the selected terminator. Standalone
`<CR>`, `<LF>`, `<CRLF>`, `<ESC>` and `<CTRL+Z>` send exactly those bytes, without
another terminator. Unknown tokens and non-ASCII input are rejected. Exact local
`-Q`, `--quit` or `--quitt`, EOF or Ctrl+C closes the port. RX is displayed while
waiting for input. An optional `--idle-timeout` closes an inactive session;
the default waits for explicit quit. Interactive sends are raw terminal input,
not a promise of command success.

One-shot `send` waits up to `--timeout` seconds for an AT final result. Exit codes:
0 = OK (or exact control bytes transmitted), 2 = argument/I/O/log error,
3 = response timeout/disconnection, 4 = modem error, 130 = cancellation.
No automatic resend occurs. Control tokens do not imply modem success.

Logging is opt-in, append-only and stops at 10 MiB. `--log`/`-l` use the desktop's
normal format; `-lv` adds hex and lifecycle events. Logs can contain SMS data and
device identifiers. Credential commands are rejected before opening a port or
creating a log; use guided maintenance for transient credentials. Do not put
secrets in shell arguments, which your shell may retain independently.

# Modem Controller

> **AT commands. Clear replies. Desktop or command line.**

**Windows · Portable · GUI + CLI · Analog / GSM / AT-compatible ISDN**

[Download the latest release](https://github.com/vitalyruhl/ModemController/releases/latest)

Connect your device, send an AT command, inspect the reply and save useful evidence.
Use the compact graphical window for quick checks and command templates, or work
directly in a terminal with the standalone console. The GUI keeps advanced
controls tucked away until you need them.

| Diagnose | Inspect | Preserve |
| --- | --- | --- |
| SIM, identity, registration and signal checks | Shared text/hex terminal with exact control bytes | Redacted reports and explicitly selected raw evidence |

### Built for practical AT work

- **Analog and Hayes-compatible modems** where their command set is compatible.
- **GSM and cellular terminals** for focused registration, SIM, signal and SMS diagnosis.
- **Legacy ISDN equipment** where it provides a compatible text-based AT interface.

Device names are never a support promise. Command availability depends on the
actual module, firmware, adapter and driver. See [device support](docs/device-support.md)
before sending a profile command.

Connect through a native serial port, a USB-to-serial adapter or a USB modem
that exposes a Windows COM port. A serial AT interface is required; a USB
connection alone does not establish compatibility.

## Run the portable app

1. Extract the complete ZIP into a folder.
2. Keep every extracted file and subfolder together.
3. Choose how to work:

| Desktop | Command line |
| --- | --- |
| Start `ModemController.exe` | Run `ModemConsole.exe` in PowerShell or CMD |
| Command buttons, profiles and shared terminal | Interactive AT terminal or one-shot commands, without the GUI |

For example, from PowerShell inside the extracted folder:

```powershell
.\ModemConsole.exe --help
.\ModemConsole.exe --open -c COM10 --baud 115200 send "AT"
```

Use your device's port and baud rate. Omit `send "AT"` for an interactive session;
enter `--quit` to close it. Disconnect the GUI before using the same port in the
CLI. See the [console guide](docs/console.md) for options, logging and exit codes.

The portable bundle includes its Python runtime. The app opens no serial port and
sends no modem command until you request it. See [portable operation and upgrades](docs/portable-build.md)
for settings, logs, verification and upgrade guidance.

## From source

Run `build-portable.cmd` to create the portable bundle. For setup, checks and the
development GUI, see the [development guide](docs/development.md).

## Documentation

[Documentation index](docs/README.md) · [Console / CLI](docs/console.md) · [AT command reference](docs/reference/at-commands.md) · [Device support](docs/device-support.md) · [Portable builds](docs/portable-build.md) · [Privacy and evidence](docs/privacy.md)

## License

GNU General Public License v3.0: [LICENSE](LICENSE). See the
[third-party notices](docs/third-party-notices.md) for bundled-component information.

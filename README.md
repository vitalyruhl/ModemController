# Modem Controller

> **AT commands. Clear replies. A compact desktop.**

**Windows · Portable · Analog / GSM / AT-compatible ISDN**

Connect your device, send an AT command, inspect the reply and save useful evidence.
Modem Controller brings the essentials into one clear graphical window, with
advanced controls tucked away until you need them.

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

## Run the portable app

1. Extract the complete ZIP into a folder.
2. Keep every extracted file and subfolder together.
3. Start `ModemController.exe` inside the extracted folder.

The portable bundle includes its Python runtime. The app opens no serial port and
sends no modem command until you request it. See [portable operation and upgrades](docs/portable-build.md)
for settings, logs, verification and upgrade guidance.

## From source

Run `build-portable.cmd` to create the portable bundle. For setup, checks and the
development GUI, see the [development guide](docs/development.md).

## Documentation

[Documentation index](docs/README.md) · [AT command reference](docs/reference/at-commands.md) · [Device support](docs/device-support.md) · [Portable builds](docs/portable-build.md) · [Privacy and evidence](docs/privacy.md)

## License

GNU General Public License v3.0: [LICENSE](LICENSE). See the
[third-party notices](docs/third-party-notices.md) for bundled-component information.

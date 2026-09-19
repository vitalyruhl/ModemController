# ModemControllerRS232

A compact Windows modem terminal and diagnostic application built with Python,
PySide6 and pySerial. The initial Python release candidate is **2.0.0**; its displayed
source/build identifier distinguishes builds during acceptance.

Use the shared ASCII/hex terminal, data-driven command profiles, read-only
diagnostics, bounded serial-settings search and redacted reports. Catalog editing,
legacy XML/VCE preview, reviewed maintenance sequences, guarded text SMS, a headless
console and optional reviewed local Tools/RAS collection are implemented.

Start `ModemController.exe` from the extracted portable folder, or use
`ModemConsole.exe --help` in PowerShell. No port opens automatically. Modem commands
require an explicit connection/action; reviewed state-changing actions require
confirmation. SMS submission acknowledgment does not establish delivery.

The editable `settings.json`, `generic-at.json`, `device-profiles.json` and
`tools.json` are beside the executables. Logging is opt-in and defaults to this
folder. See [portable operation and upgrades](docs/portable-build.md),
[console usage](docs/console.md) and the [documentation index](docs/README.md).

## Development

Python 3.12 or 3.13 is required. Runtime dependencies are PySide6 6.8.3 and pySerial
3.5; the lock includes PyInstaller 6.12.0, pytest 8.3.5, pytest-qt 4.4.0 and Ruff
0.11.2 for development.

```powershell
uv sync --frozen
uv run python -m modem_controller.app
uv run modem-console --help
uv run ruff check src tests tools setup.py
uv run ruff format --check src tests tools setup.py
uv run pytest
uv build
uv run python tools/build_portable.py
```

`start-gui.cmd` also starts the local development GUI. Use focused tests during
scoped changes; the full suite belongs to integrated candidate validation.

The source separates `ui/`, `transport/`, `protocol/`, `catalog/` and `workflows/`.
The CLI shares transport/session/log behavior. Tools execute through a separate
bounded process adapter; they cannot access an internal AT-session scripting API.
`version.json` is authoritative; build outputs derive their metadata from it.

## Evidence and limits

See [acceptance evidence](docs/acceptance.md) and [device support](docs/device-support.md).
Offline tests and local executable startup are distinct from clean-target Windows
and user hardware acceptance. The target is Windows 10 20H2 x64 and newer, but
untested Windows builds are not certified. Windows Server observations remain
additional evidence, not a blanket support claim.

A read-only COM10 session identified the reported 55iQ as Quectel BG95-M3 with a
ready SIM and LTE-M registration at 115200 8N1. That does not establish SMS/data
success or explain an earlier transient network failure. The SIM-info button,
full settings popup and Phoenix Contact evaluation remain deferred.

Historical VB.NET sources, releases and removed reference files are available in
Git history. Remaining manuals are evidence sources, not runtime dependencies or
automatic driver-installation instructions.

## License

GNU General Public License v3.0: [LICENSE](LICENSE).
[Third-party notices](docs/third-party-notices.md) record bundled components and
remaining provenance checks before public redistribution. No public release,
signing claim or deployment is implied by a local candidate build.

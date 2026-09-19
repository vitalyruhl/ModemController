# Portable Windows build

Build on Windows x64 with the locked environment:

```powershell
uv sync --frozen
uv run python tools/build_portable.py
```

The recipe creates a dated folder and ZIP in `dist/`. Unpack the entire folder;
start `ModemController.exe` for the desktop or `ModemConsole.exe` in PowerShell.
Python is bundled. `_internal` and `_console` contain runtime files and must stay
beside the executables.

`settings.json`, `generic-at.json` and `device-profiles.json` are directly beside
the executables. The default log destination is also this folder, but logging
requires explicit enablement. Source runs use the repository root. If the folder
is unwritable, the desktop shows its selected per-user fallback. A user-selected
settings location is remembered; its location is shown on startup.

Edit catalog sidecars while the application is closed. Each sidecar carries its
original `_shipped_baseline`; retain it unchanged so upgrades can distinguish
customizations from old defaults. Updated bundled defaults fill unchanged fields,
while edits survive. Changed commands become unverified until reviewed in the
catalog editor. Editor changes and notes are field overlays in `settings.json`.
Malformed sidecars are preserved and reported; the desktop shows bundled defaults
for that launch. No file is silently corrected or overwritten at startup.

To upgrade, extract the new bundle into a separate folder and copy your three JSON
files into it, replacing only the fresh sidecars. Keep backups. This preserves
customizations and allows new unmodified defaults to merge. Do not copy old runtime
folders. An optional remembered external settings directory remains authoritative.

The build uses an explicit package-resource whitelist. Personal source settings,
logs, modem archives, drivers, local plans and governance are excluded. Help,
project license, third-party notices and a SHA-256 contents manifest are included.
The notice pack records upstream provenance; public distribution and clean-target
acceptance are separate from a successful local build.

Clean Windows 10 20H2/Windows 11 launch without installed Python, physical-device
acceptance and additional Server observations remain in the acceptance matrix.
A local `--smoke-test` desktop launch closes itself without opening any COM port.

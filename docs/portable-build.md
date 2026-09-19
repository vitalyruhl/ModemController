# Portable Windows build

On Windows x64, double-click **`build-portable.cmd`** in the repository root.
It prepares the locked environment and builds the portable folder, ZIP and checksum.
For a terminal run that returns without pausing:

```powershell
.\build-portable.cmd --no-pause
```

The recipe creates a dated folder and ZIP in `dist/`. Unpack the entire folder;
start `ModemController.exe` for the desktop or `ModemConsole.exe` in PowerShell.
Python is bundled. `_internal` and `_console` contain runtime files and must stay
beside the executables.

### Startup error: Python DLL cannot be loaded

An EXE under `build\pyinstaller\ModemController\` is an intermediate build output.
It does not have the adjacent `_internal\python313.dll` runtime from the finished
bundle and must not be used to start the application.

Use `dist\ModemController-<version>-<source>-<timestamp>\ModemController.exe`, or
fully extract the matching ZIP and launch the EXE inside that extracted folder.
Do not move only the EXE, run it inside the ZIP preview, or download individual
DLLs. Keep the entire portable folder together. If a fully extracted package still
fails, verify its original ZIP checksum and check whether security software
quarantined a runtime file.

Build prerequisites and source-run commands are in [development.md](development.md).

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
files into it, replacing only the fresh sidecars. Also preserve `tools.json` if
you customized optional tool definitions; review their scripts again. Keep backups. This preserves
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

## Local candidate delivery

After committing the tested source, build from a clean tree:

```powershell
uv run python tools/build_portable.py --candidate
uv run python tools/verify_candidate.py dist/<candidate-name>.zip
uv run python tools/verify_candidate.py dist/<candidate-name>.zip --smoke
```

Replace `<candidate-name>` with the exact filename printed by the build. Candidate
mode rejects an uncommitted tree and detects source/provenance changes during the
build. Development builds can still be created without `--candidate`; their dirty
state is explicit and they do not pass candidate verification.

The ZIP filename contains product version, producing commit and UTC build time.
`build-info.json` records the full source revision, `uv.lock` SHA-256, Python version
and clean/dirty state. Both frozen programs carry matching copies. The adjacent
`.zip.sha256` checks the archive, while `contents-sha256.json` covers each payload
file. Checksums provide integrity, not a signing or publisher-identity claim.

Verification checks the archive and all payload hashes without execution by
default. `--smoke` is only for a trusted local build: it extracts into a temporary
project build folder, relocates to a path with spaces, checks required resources,
and starts CLI help/version/disconnected mode and the GUI offscreen smoke. It
isolates remembered settings and removes development Python paths; it opens no
COM port and removes its temporary extraction afterwards. This is local startup
evidence, not a clean-machine or native-DPI acceptance result. See
[acceptance.md](acceptance.md) for remaining user and platform gates.

Keep the ZIP and checksum together, then extract the complete folder for use.
Once the application saves settings, its mutable sidecars can differ from the
pristine manifest; verify the original ZIP when checking delivery integrity.

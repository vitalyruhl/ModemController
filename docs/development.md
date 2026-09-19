# Development

Build on Windows x64 with Python 3.12 or 3.13 and `uv` available on PATH.
The frozen lock selects PySide6 6.8.3, pySerial 3.5, PyInstaller 6.12.0,
pytest 8.3.5, pytest-qt 4.4.0 and Ruff 0.11.2. No dependency update is needed
for a normal build.

```powershell
uv sync --frozen
uv run python -m modem_controller.app
uv run ruff check src tests tools setup.py
uv run ruff format --check src tests tools setup.py
uv run pytest
uv build
```

`start-gui.cmd` starts the source application. Use focused tests for a scoped
change; the full suite belongs to integrated candidate validation. No modem is
required for the offline tests. Hardware tests need an explicit device/action
scope, especially for PIN entry, configuration changes or SMS submission.

## Build a portable ZIP

Double-click **`build-portable.cmd`** in the repository root, or run:

```powershell
.\build-portable.cmd --no-pause
```

The script changes to its own project directory, synchronizes the locked
environment, builds the GUI and optional console, and prints the ZIP location.
It stops on errors and keeps the window open by default. `uv sync` may download
the locked dependencies when they are not already cached; nothing is installed
into the system Python environment.

After committing the tested source, prepare a candidate with:

```powershell
.\build-portable.cmd --candidate --no-pause
```

Normal builds allow local edits and display a dirty source identifier. Candidate
builds require a clean committed tree. The script does not commit, tag, publish
or start the application. The later release download is the generated ZIP and
checksum; users of that ZIP do not need the build script, Python or `uv`.

See [portable builds](portable-build.md) for output layout, verification,
upgrade handling and troubleshooting.

## Project structure

The source separates `ui/`, `transport/`, `protocol/`, `catalog/` and `workflows/`.
The optional [headless console](console.md) shares transport/session/log behavior.
External Tools use a separate bounded process adapter. Root `version.json` is
authoritative; package and executable metadata derive from it. See
[versioning](versioning.md) and [acceptance evidence](acceptance.md).

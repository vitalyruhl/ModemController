# Third-party notices

This document and the assets in [`licenses/`](licenses/) record the notice
inputs for the Windows onedir payload inspected on 2026-09-19. They do not
establish that an artifact is compliant or complete. The build/release workflow
must inspect each generated payload and add every component it includes.

## Recorded inputs

| Component | Version observed | License asset or source |
| --- | --- | --- |
| CPython | 3.13.15 local interpreter | [`licenses/Python-3.13.15-LICENSE.txt`](licenses/Python-3.13.15-LICENSE.txt) |
| pyserial | 3.5 | [`licenses/pyserial-3.5-LICENSE.txt`](licenses/pyserial-3.5-LICENSE.txt) |
| PySide6, PySide6-Essentials, PySide6-Addons, Shiboken6 | 6.8.3 | [`licenses/pyside-setup-6.8.3-LGPL-3.0-only.txt`](licenses/pyside-setup-6.8.3-LGPL-3.0-only.txt) |
| Qt base runtime | 6.8.3 | [`licenses/qtbase-6.8.3/`](licenses/qtbase-6.8.3/) and [`licenses/QT_PYSIDE_SHA256SUMS.txt`](licenses/QT_PYSIDE_SHA256SUMS.txt) |
| PyInstaller | 6.12.0 | [`licenses/pyinstaller-6.12.0-COPYING.txt`](licenses/pyinstaller-6.12.0-COPYING.txt) |

The PyInstaller asset includes its bootloader exception. It is recorded because
the generated Windows executable contains a bootloader; it does not by itself
enumerate all build-time or run-time-hook material.

PySide6 wheel metadata records `LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only`
as well as a commercial license file. This repository records the LGPL text for
the intended open-source notice path and makes no selection or legal conclusion
for an eventual distribution.

The local interpreter reports Python 3.13.15. That differs from the previously
noted 3.13.7 and must be reconciled against the interpreter actually frozen into
each artifact.

## Inspected Qt payload

The inspected payload contains `Qt6Core.dll`, `Qt6Gui.dll`, `Qt6Network.dll`,
`Qt6Widgets.dll`, `pyside6.abi3.dll`, and `opengl32sw.dll`. Its Qt plugins are
`qnetworklistmanager`, `qminimal`, `qoffscreen`, `qwindows`,
`qmodernwindowsstyle`, `qcertonlybackend`, `qopensslbackend`, and
`qschannelbackend`. It contains no Qt Qml, Pdf, Quick, or Svg payload.

For conservative source coverage, [`licenses/qtbase-6.8.3/`](licenses/qtbase-6.8.3/)
contains every text license in the Qtbase 6.8.3 `LICENSES` directory and the
16 attribution records relevant to Qt Core, Gui, Network, Widgets, and their
common third-party sources. The official Qt for Python 6.8 third-party-license
page is preserved as
[`licenses/pyside6-6.8-third-party-licenses.html`](licenses/pyside6-6.8-third-party-licenses.html).
[`licenses/QT_PYSIDE_SHA256SUMS.txt`](licenses/QT_PYSIDE_SHA256SUMS.txt)
records portable, `licenses/`-relative hashes for these source records.

The payload also contains Microsoft CRT files `MSVCP140.dll`,
`MSVCP140_1.dll`, `MSVCP140_2.dll`, `VCRUNTIME140.dll`, and
`VCRUNTIME140_1.dll`, obtained through the frozen wheel set. No matching
Microsoft redistribution license text was present in the inspected wheel
metadata or the locally available Visual C++ redist material. Preserve and
review the Microsoft Visual C++ Redistributable terms that apply to the exact
redist source before public redistribution.

## Remaining artifact-specific checks

The included Qtbase source records are a conservative notice set; they are not
a component-to-attribution determination. Before a public release, verify the
shipping binary provenance for `opengl32sw.dll`, the OpenSSL backend, and the
Microsoft CRT files against the final archive. This is required because the
exact source/build configuration and applicable redistribution terms cannot be
determined from the inspected wheel metadata alone.

Use these primary Qt source entry points during that verification:

- [qtbase 6.8.3 license directory](https://code.qt.io/cgit/qt/qtbase.git/tree/LICENSES?h=v6.8.3)
- [qtbase attribution metadata](https://code.qt.io/cgit/qt/qtbase.git/tree/src/gui/qt_attribution.json?h=v6.8.3)
- [Qt source modules at 6.8.3](https://code.qt.io/cgit/qt/qt.git/tree/?h=v6.8.3)

Do not treat this document as a substitute for the component-to-attribution
mapping, the applicable Qt licensing route, or final archive inspection.

Asset URLs and SHA-256 values are recorded in
[`licenses/PROVENANCE.md`](licenses/PROVENANCE.md).

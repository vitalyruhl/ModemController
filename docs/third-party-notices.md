# Third-party notices

ModemController uses the following components in its Windows portable package.
License texts are included in [`licenses/`](licenses/). The package's
`build-info.json` identifies its source revision, Python version and dependency
lock; `contents-sha256.json` identifies the packaged files.

## Runtime components

| Component | Version | License and provenance |
| --- | --- | --- |
| CPython | 3.13.15 | [`Python-3.13.15-LICENSE.txt`](licenses/Python-3.13.15-LICENSE.txt), copied from the installed Windows interpreter |
| OpenSSL used by CPython | 3.0.21 | [`openssl-3.0.21-LICENSE.txt`](licenses/openssl-3.0.21-LICENSE.txt), Apache 2.0; the same text is also included in the Python Windows license |
| pyserial | 3.5 | [`pyserial-3.5-LICENSE.txt`](licenses/pyserial-3.5-LICENSE.txt) |
| PySide6 and Shiboken6 | 6.8.3 | [`pyside-setup-6.8.3-LGPL-3.0-only.txt`](licenses/pyside-setup-6.8.3-LGPL-3.0-only.txt) |
| Qt Core, Gui, Network and Widgets | 6.8.3 | [`qtbase-6.8.3/`](licenses/qtbase-6.8.3/) includes LGPL 3.0 and third-party notices |
| PyInstaller bootloader | 6.12.0 | [`pyinstaller-6.12.0-COPYING.txt`](licenses/pyinstaller-6.12.0-COPYING.txt), including the bootloader exception |

PySide6 wheel metadata offers `LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only`
and a commercial route. This package records the LGPL 3.0 open-source route
for the Qt/PySide libraries. The separate DLLs remain in the portable directory.
Their license terms, including modification and replacement rights, are not
replaced by the application's license.

Qt's upstream source and attribution records are available in the
[Qtbase 6.8.3 source tree](https://code.qt.io/cgit/qt/qtbase.git/tree/?h=v6.8.3)
and the [PySide 6.8.3 source tree](https://github.com/pyside/pyside-setup/tree/v6.8.3).
The recorded Qtbase license catalog is deliberately broader than the included
Qt modules. Its 16 attribution records cover common third-party sources used
by Core, Gui, Network and Widgets. The official Qt for Python license page is
also preserved in
[`pyside6-6.8-third-party-licenses.html`](licenses/pyside6-6.8-third-party-licenses.html).

## Microsoft runtime files

These files accompany the upstream Windows interpreter and binding wheels;
their versions are separate from the Python and Qt version numbers.

| Upstream binary source | Files | Observed file version |
| --- | --- | --- |
| CPython 3.13.15 Windows installation | `VCRUNTIME140.dll`, `VCRUNTIME140_1.dll` | 14.51.36247.0 |
| PySide6 6.8.3 Windows wheel | `MSVCP140.dll`, `MSVCP140_1.dll`, `MSVCP140_2.dll`, `VCRUNTIME140.dll`, `VCRUNTIME140_1.dll` | 14.39.33520.0 |
| Shiboken6 6.8.3 Windows wheel | `MSVCP140.dll`, `VCRUNTIME140.dll`, `VCRUNTIME140_1.dll` | 14.39.33520.0 |

The included Python license preserves its **Additional Conditions for this
Windows binary build**, including the Microsoft Distributable Code conditions.
Microsoft's own
[redistribution documentation](https://learn.microsoft.com/en-us/cpp/windows/redistributing-visual-cpp-files?view=msvc-170)
and [Visual Studio 2022 distributable-code list](https://learn.microsoft.com/en-us/visualstudio/releases/2022/redistribution)
describe the applicable restrictions. The PySide wheel metadata does not supply
a separate Microsoft runtime license. Recording the wheel source and DLL
version does not grant rights beyond the upstream terms.

## Package boundaries

Public release packaging excludes the optional Mesa software OpenGL renderer
(`opengl32sw.dll`) and Qt's optional OpenSSL backend (`qopensslbackend.dll`).
CPython's own `libcrypto-3.dll` and `libssl-3.dll` remain included; they are the
OpenSSL 3.0.21 components listed above. Build collection must not acquire
additional OpenSSL or Universal CRT DLLs from unrelated tools on `PATH`.

Manufacturer modem PDFs are not part of the public package. Consult
[modem manual sources](reference/modem-manuals.md) for official download and
support entry points. A document's former presence in this repository does
not change its manufacturer's terms.

Asset URLs, hashes and binary-source verification details are recorded in
[`licenses/PROVENANCE.md`](licenses/PROVENANCE.md). Recheck that mapping when
changing the interpreter, wheel versions or portable build inputs.

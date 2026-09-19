# License asset provenance

Retrieved on 2026-09-19. SHA-256 values are calculated over the checked-in
asset bytes, after retrieval.

| Asset | Upstream source or local installed source | SHA-256 |
| --- | --- | --- |
| `pyserial-3.5-LICENSE.txt` | <https://raw.githubusercontent.com/pyserial/pyserial/v3.5/LICENSE.txt> | `F91CB9813DE6A5B142B8F7F2DEDE630B5134160AEDAEAF55F4D6A7E2593CA3F3` |
| `pyside-setup-6.8.3-LGPL-3.0-only.txt` | <https://raw.githubusercontent.com/pyside/pyside-setup/v6.8.3/LICENSES/LGPL-3.0-only.txt> | `DA7EABB7BAFDF7D3AE5E9F223AA5BDC1EECE45AC569DC21B3B037520B4464768` |
| `qtbase-6.8.3-LGPL-3.0-only.txt` | <https://code.qt.io/cgit/qt/qtbase.git/plain/LICENSES/LGPL-3.0-only.txt?h=v6.8.3> | `DA7EABB7BAFDF7D3AE5E9F223AA5BDC1EECE45AC569DC21B3B037520B4464768` |
| `pyinstaller-6.12.0-COPYING.txt` | Installed `pyinstaller-6.12.0.dist-info/COPYING.txt`; upstream <https://raw.githubusercontent.com/pyinstaller/pyinstaller/v6.12.0/COPYING.txt> | `DCF75FDB959DB1E3B41C0F8505069D2ECE781B5EC6B3D0A4D30975CFC6580245` |
| `Python-3.13.15-LICENSE.txt` | Installed interpreter `LICENSE.txt`; upstream release source <https://github.com/python/cpython/blob/v3.13.15/LICENSE> | `62BEC384DF47B0328307DB41455FF6EA2559E5546B394AC69148561B21703120` |
| `qtbase-6.8.3/` | Every `LICENSES/*.txt` file and selected relevant `qt_attribution.json` records from the Qtbase `v6.8.3` source tree; tree <https://api.github.com/repos/qt/qtbase/git/trees/v6.8.3?recursive=1> and raw files under <https://raw.githubusercontent.com/qt/qtbase/v6.8.3/> | Per-file values in `QT_PYSIDE_SHA256SUMS.txt` |
| `pyside6-6.8-third-party-licenses.html` | <https://doc.qt.io/qtforpython-6.8/licenses.html> | `1EBD223C6C3389D10C845029584CF1AE8515ECC68D7E4791645222EE4F09A39B` |
| `QT_PYSIDE_SHA256SUMS.txt` | Locally generated portable checksum manifest for the preceding Qtbase and PySide records | `DEEB48221681E1D63677BE5E834669AE59479B9A6D73BD3E58D203DE74B8A07E` |

The two LGPL assets have identical hashes because they are the same GNU LGPL
3.0-only text from their respective upstream source trees.

The Qtbase collection is intentionally broader than the inspected runtime
payload. It preserves the full upstream Qtbase 6.8.3 license catalog while the
release workflow establishes the final binary-to-attribution mapping.


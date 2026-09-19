# Candidate acceptance evidence

Date: 2026-09-19. Current feedback candidate: **2.0.1**.
This records automated and observed evidence. User HIL acceptance, clean target
systems and public redistribution remain pending. No item is frozen or declared
ready on the strength of an agent simulation.

## 2.0.1 desktop feedback

The title omits build hashes. Autoscroll follows delayed Qt layout changes while
real scrollbar/keyboard navigation can pause it. Catalog navigation, compact
category buttons, wider command entry, preparation-only presets and historical
XML/YAT coverage passed **98 focused tests** with lint and formatting checks.
The legacy comparison includes all 19 original XML AT entries; remote-access
labels and personal test values are excluded. New templates remain unverified
and do not expand automatic diagnostics. No modem command, SMS or call was sent
for these corrections. Native user/DPI acceptance remains pending.

The plugin launcher and portable integration passed **69 focused tests**. A real
detached harmless process verified argument and working-directory handling; the
standalone RAS form used a synthetic collector to verify that scope and consent
are required. No real host collection or elevation occurred. Wheel resources
include the complete plugin folder. The collector matches the user's previous
2.0.0 portable script byte-for-byte. Candidate archive and relocated executable
startup are verified separately by the build procedure.

## Source and automated coverage

The following evidence records the original **2.0.0** implementation interval.

The continuation starts at `5249e1d` and retains the established serial/protocol
foundations. Each implementation point has its own local commit and focused tests.
No dependency versions changed during this continuation.

| Point / scope | Commit | Focused tests passed |
| --- | --- | ---: |
| Capture, credential and log privacy | `ed46ea7` | 67 |
| Diagnostic interpretation and budgets | `2b42c4e` | 34 |
| Catalog editor and persistence | `7fdd757` | 44 |
| Terminal and connection controls | `949fd11` | 82 |
| Reviewed maintenance sequences | `94ffac3` | 72 |
| Reports and capture export | `ca664c9` | 57 |
| Bounded connection search | `3540fa8` | 71 |
| SMS preflight and submission boundary | `73777a7` | 58 |
| Exact BG95-M3 profile | `5d7f0d5` | 42 |
| Legacy XML/VCE preview and selection | `c855a0c` | 40 |
| Headless console | `bd18e24` | 73 |
| Portable sidecars and dual executable recipe | `7b3eb9d` | 41 |
| Canonical version and build identity | `ee31bc6` | 65 |
| Reviewed local tool process lifecycle | `b2c1de2` | 56 |
| Opt-in RAS collector and options | `bf340f9` | 29 |

Counts overlap; they are not a sum of distinct tests. RAS tests use synthetic
fixture data only. Tool process tests use harmless Python/PowerShell/CMD scripts,
including child cleanup, cancellation and output bounds. No real RAS collection,
SMS submission or PIN entry was performed.

The first whole-suite integration at `bf340f9` passed 242 tests. Independent
review then reproduced five gaps: split PIN history retention, delayed PIN echoes
in diagnostics, stale replies after diagnostic timeout, control bytes after
reconnection and malformed sidecar roots. The integration correction adds
regressions and closes those gaps. The corrected integration snapshot passed
**256 tests**, Ruff lint/format, `git diff --check` and `uv build` (wheel/sdist).
A Qt test warning about disconnecting a
`waitSignal` callback is test-harness output, not hardware evidence.

Final checks and candidate provenance are recorded by the candidate build and
verification procedure in [portable-build.md](portable-build.md). A generated
artifact identifies its producing revision separately from this evidence commit.

## Observed environment and hardware

Local development host: **Microsoft Windows 11 Pro, 10.0.26200, x64**,
Python **3.13.15**. OS identity was checked with `Win32_OperatingSystem` and the
runtime; the old Windows 10 registry product label was not treated as OS proof.
The host has development runtimes installed and is not a clean target machine.

Read-only COM10 investigation was explicitly authorized. An AT-only baud search
found **115200, 8N1, no flow control, CR**. Identity queries returned
**Quectel BG95-M3 / BG95M3LAR02A03**, despite the reported 55iQ enclosure/model.
The user reported an O2 SIM with PIN disabled.

| Query | Observed result |
| --- | --- |
| `AT+CPIN?` | `READY`: SIM accessible without a pending PIN request |
| `AT+CREG?` / `AT+CEREG?` | `0,1`: registered |
| `AT+CGREG?` | `0,4`: unknown in this registration domain |
| `AT+COPS?` | Operator text `winSIM`, access technology `8` |
| `AT+QNWINFO` | `eMTC`, `26202`, `LTE BAND 20`, `6300` |
| `AT+CSQ` | `16,99`: approximately -81 dBm; BER unknown |
| `AT+CEER` | `ERROR`: no usable failure explanation |
| `AT+CMGF?` / `AT+CSCS?` | `0` / `GSM`, unchanged |

The SIM was detected and LTE-M registration was present during observation.
The earlier failure to register was not reproduced. Serial baud mismatch explains
PC communication failure, not a proven network-registration cause. No configuration,
reset, PIN, call, SMS, packet-data or network-scan command was sent. The port was
closed after observation. Interpretation follows the manufacturer reference linked
in [device-support.md](device-support.md).

## Remaining acceptance

| Gate | Current evidence / required action |
| --- | --- |
| Whole offline integration | 256 tests passed after review corrections; lint, formatting and wheel/sdist build passed |
| Desktop layout | Offscreen render inspected with an explicitly loaded local Segoe UI font; native DPI, resizing and sustained traffic require user observation |
| Local portable launch | GUI smoke and headless CLI checked on the development host; final ZIP verification is separate |
| Clean Windows 10 20H2 x64 / Windows 11 | Pending launch, relocation, non-writable folder fallback and operation without installed Python |
| Windows Server 2019 and later | User has systems available; no runs performed and no general support claim |
| User HIL | Pending terminal, search, disconnect/unplug, diagnostics, catalog persistence and export acceptance |
| State-changing modem / SMS checks | Require explicit device and operation scope; not implied by read-only access |
| RAS host collection | Pending explicit selected collection scope; normal AT use does not require it |
| Public redistribution | Additional OpenGL/OpenSSL/Microsoft CRT provenance review remains open; see third-party notices |

Future scope is recorded separately: the **Show Sim-Info** button is deferred;
the full settings popup and **Phoenix Contact 23 13 106, firmware 1.60** evaluation
belong to a later substantial minor version. Their absence is intentional.

After implementation, user HIL corrections increment patch/minor as appropriate.
Keep the executable version, source identifier and `build-info.json` with every
test report so different candidates cannot be confused.

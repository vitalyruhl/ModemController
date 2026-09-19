# Device support and evidence limits

Catalog entries describe reviewed command scope; they do not certify every unit,
firmware, cable, driver or mobile network. Unsupported entries remain hidden.
Unverified historical AT templates can be prepared for manual review; they are
not included in automatic diagnostics. Common templates can be shown alongside a
device profile without certifying that device's support.

| Profile | Current visible scope | Evidence limit |
| --- | --- | --- |
| Generic AT | Standard status queries and explicitly confirmed maintenance; guarded text SMS | Each connected modem must support the queried form. SMS requires fresh SIM READY, text mode and GSM or IRA observations. |
| MC55i-Q / MC55i-W | AT and ATI | Historical initialization notes are not a reviewed automatic setup sequence. Module and firmware must be identified first. |
| Quectel BG95-M3, observed 55iQ | Reviewed identity, SIM, registration, operator and signal queries | Observed firmware BG95M3LAR02A03 only; no broader terminal-family or SMS-send acceptance. |
| TC35 / TC35i | SIM status, registration and signal | Based on the bundled TC35-family AT manual, version 04.00; not proof for other families or all firmware. |
| MC93 | No device-specific buttons | No reviewed command specification establishes support. |
| TC55i | No device-specific buttons | Exact identity and command specification remain unresolved. |
| MC88 / MC88i | No device-specific buttons | Product material is not an AT command specification. |
| Analog 56K / Stollmann ISDN, legacy | Individual historical init templates | Unverified; complete sequences require review. |

The [historical inventory](reference/legacy-command-inventory.md) maps the original
XML buttons and additional local collections to the current commands. TC35i and
MC55i historical setup entries remain unverified.

The catalog source references are in `catalog/data/generic-at.json` and
`catalog/data/device-profiles.json`. The consolidated
[AT reference](reference/at-commands.md) explains query and state-change boundaries.
Use the [catalog editor](catalog-editing.md) for user notes; notes do not promote
unverified commands to supported status. No wake-up-call capability is inferred.

## Read-only observation, 2026-09-19

The user reported a currently attached **55iQ with an O2 SIM and PIN disabled**.
COM10 opened at 19200 baud, 8N1, no flow control, driver-default DTR/RTS. A single
`AT` with CR received no bytes before the three-second deadline. The connection
was closed. Identity, firmware, SIM detection and network registration were not
established by this observation. Other rates were not inferred from the timeout.
No PIN, reset, setting change, operator scan, call or SMS was sent.

The user then confirmed the connection and authorized an AT-only rate search.
The five quick rates were tried at 8N1 with CR. 115200 baud returned two separate
OK replies; the other rates remained inconclusive. Subsequent read-only queries
identified Quectel BG95-M3, firmware BG95M3LAR02A03. Observed results:

| Query | Observation |
| --- | --- |
| CPIN? | READY: SIM recognized and ready |
| CREG? | 0,1: registered on the home network |
| CGREG? | 0,4: unknown in that registration domain |
| CEREG? | 0,1: EPS registration on the home network |
| COPS? | 0,0,"winSIM",8 |
| QNWINFO | "eMTC","26202","LTE BAND 20",6300 |
| CSQ | 16,99: approximately -81 dBm RSSI, unknown BER |
| CEER | ERROR; no explanatory rejection cause obtained |
| CMGF? / CSCS? | 0 / "GSM": PDU mode and GSM charset; unchanged |

Command forms and interpretation were checked against the manufacturer's
[BG95/BG77/BG600L AT manual, version 2.0](https://quectel.com/content/uploads/2021/03/Quectel_BG95BG77BG600L_Series_AT_Commands_Manual_V2.0-2.pdf),
sections 6.2, 6.3, 6.15 and 9.8. The current lack of registration was not reproduced.
The serial rate explains the initial PC communication failure, not a historical
network failure. The source of an earlier transient network problem remains unknown.

A separate exact-module profile avoids treating the reported 55iQ terminal label
as proof for other MC55i variants. These observations do not establish SMS delivery,
packet data transfer, wake-up calling, other firmware, or user HIL acceptance.

The user's Phoenix Contact unit marked `23 13 106`, firmware `1.60`, is reserved
for evaluation in a later minor release. No supported profile is claimed here.

## User SMS and dialing feedback, 2026-09-19

The supplied 2.1.0 log contains text mode (`CMGF: 1`) and `CSCS: "GSM"`, but no
CMGS submission. Offline reproduction found that native Qt confirmation results
were compared by object identity, silently discarding Yes. Guided exchanges also
reached the log without appearing in the shared terminal. Both are corrected in
2.1.2. Basic text uses the same restricted byte-compatible subset with GSM or IRA;
no character-set switch or automatic resend is introduced. Recipient delivery is
still not established by these tests.

The logged dial attempts omitted the voice-call semicolon; one also quoted the
number. The documented form is `ATD<number>;` without spaces or quotes. The
existing Generic AT voice template already prepares that form. A bare ERROR from
the observed attempts does not establish the exact cause or a lack of voice support.

Quectel's [voice application note, sections 1.1, 2.2 and 4.2](https://quectel.com/content/uploads/2024/02/Quectel_BG95BG77BG600L_Series_Voice_Application_Note_V1.0.pdf)
lists BG95-M3 voice capabilities, with firmware and network prerequisites for
VoLTE. That family capability is not proof for the observed BG95M3LAR02A03 firmware,
SIM subscription or current IMS registration. The terminal's Q/W enclosure label
alone cannot resolve this. No call, firmware update or configuration change was
performed during this diagnosis.

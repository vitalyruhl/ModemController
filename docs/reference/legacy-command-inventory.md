# Historical command coverage

The 2.0.1 catalog was compared with the user's local `.Temp/XMLSettings.xml`,
`MC-TC-Commands.yacps`, `AT-Befehle.txt`, `Init-Strings.md` and
`tc35i-incoming-calls-original.md`. These are historical sources, not hardware
acceptance. Personal sample recipients, message bodies and credentials are not
copied into the distributed catalog.

## Original program

The XML contains 29 description nodes: 19 AT entries, seven empty metadata nodes
and three remote-access labels (`Show`, `save`, `quit`). The latter are not AT
commands and are not sent to a modem.

| Original function | Current location |
| --- | --- |
| SIM status / PIN entry | Generic AT: SIM status / Unlock SIM |
| PIN protection off | Generic AT: Disable SIM PIN protection, secret parameter |
| Legacy “PIN change” | Generic AT: Unblock SIM with PUK, secret PUK and new PIN |
| Manufacturer, model, firmware | Generic AT: Manufacturer / Model / Firmware |
| Serial number / capabilities | Generic AT: Serial number / IMEI / Reported capabilities |
| Operator, signal, serial speed | Generic AT: Operator / Signal quality / Serial baud rate |
| Delete read / all SMS | Generic AT, SMS category; prepare only |
| Test SMS | Prepare SMS button, with recipient and message fields; explicit send |
| Text mode | Generic AT: Use SMS text mode; prepare only |
| Analog initialization | Analog 56K (legacy templates), individual steps and review-only sequence |
| Stollmann ISDN initialization | Stollmann ISDN (legacy templates), individual steps and review-only sequence |
| TC35i initialization | TC35 / TC35i, Legacy initialization category |

The original PIN-change label was misleading: `AT+CPIN` with a PUK and new PIN is
SIM recovery. Wrong PUK attempts can permanently block a SIM. It is preserved as
an unverified secret workflow template, not an ordinary editable command draft.

The original delete templates omit the index (`AT+CMGD=,1` and `AT+CMGD=,4`).
They remain unverified because acceptance of that spelling is device-dependent.
An explicit-index delete template is also provided. No SMS was deleted or sent
during catalog validation.

The TC35i source uses `AT#CMGF=1`, whereas the other collections use `AT+CMGF=1`.
The historical sequence retains the `#` spelling and remains disabled pending
review; the separate text-mode template uses the `+` spelling. Compound init
strings were split into visible individual commands, with AT prefixes made
explicit. Reset, auto-answer, flow-control and persistent-save operations must
be reviewed for the exact device before enabling a complete sequence.

## Other local collections

The YAT collection contributes registration reporting, caller identification,
extended ring indications, SMS text mode, notification routing and combined
message storage. Its six exact-byte actions already exist under Control bytes.
Its status queries overlap the standard catalog.

The AT notes additionally supply voice/data dialing, hang-up, redial, SMS reading,
listing, deletion by index, service-center configuration, phonebook reading,
battery/clock/subscriber queries and character-set queries. The prose also names
vendor-dependent functions without complete arguments; those names are reference
material rather than fabricated executable presets. Network mailbox shortcodes,
Windows driver files and incident-collection scripts are not modem presets.

The Q/W initialization notes are available as individual common setup templates.
Their module-specific URC-port command is an unverified MC55i-Q/W template; the
terminal enclosure label does not establish compatibility with its embedded module.

## Availability and verification

Historical entries remain `unverified` except the explicitly reviewed steps of
the [user-defined GSM SMS initialization](gsm-sms-initialization.md), added in
2.1.0. That source/workflow review is not device-specific HIL acceptance.
Non-secret AT templates can be prepared
for manual editing, but do not auto-send or enter diagnostics. PIN/PUK actions
and complete sequences require separate review in the catalog editor before
execution. Existing reviewed queries keep their previous scope.

**Include common AT templates** adds generic entries to the selected modem's
button view without modifying its profile or certifying those commands for that
modem. Duplicates are suppressed. Disable it to inspect only the device's entries.
Common AT queries borrowed from another profile are also prepared rather than
sent immediately. The catalog editor edits the selected profile; select Generic
AT there to edit a common template.

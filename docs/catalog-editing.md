# Catalog editing

The bundled JSON catalogs define button labels, categories, payloads, applicability,
references, parameters and deadlines. Use **Catalog → Edit / import / export**
to edit local copies. Field changes must be applied or discarded before switching
commands. User overlays preserve unchanged fields from future bundled defaults.
Native imports and executable-field edits remain unverified until separately
reviewed and explicitly enabled. No editor action opens a port or sends bytes.

The editor opens on the profile selected in the main window. The profile selector,
search and command list stay visible while the form scrolls. Select another button
in the list on the left. Common fields appear first; expand **Advanced** for protocol
details, verification, sequence steps and parameter definitions.

PIN/password values belong only in transient secret prompts. Literal credential
commands are rejected from native import/export and persisted catalog changes.
If saving fails, closing requires retry, cancellation or deliberate discard.
Corrupt/newer settings remain untouched; select another directory to recover.

## Reviewed sequences

A sequence has `kind: "sequence"`, `payload: null` and 1–32 `sequence_steps`.
Each step references a command ID in the same profile. Example shape:

```json
{"command_id": "attention", "expected_contains": "", "timeout_seconds": 2, "delay_seconds": 0}
```

All referenced commands must be reviewed AT or exact-byte commands. Each step
requires a final `OK`; a nonempty `expected_contains` additionally matches text
in response lines. Timeouts are at most 60 seconds per step, optional delays at
most 10 seconds, and the desktop run has a 30-second total budget. The configured
connection response deadline can further shorten an exchange.

Sequences never evaluate code, macros, nested sequences or external tools.
The complete step list and risks require confirmation. Failure or cancellation
stops without retry or automatic resume. Secret steps are allowed only last,
without a text condition. Reconnect after completion before continuing work.
No device-specific initialization sequence is supplied without reviewed evidence.
# Legacy XML and VCE

Choose **Import legacy** in the catalog editor to preview an XML or VCE file.
Select individual rows deliberately. Import preserves the source and command
spelling, including historical `AT#CMGF=1`; compound syntax, unknown commands and
duplicates carry warnings. Credential literals cannot be imported. XML DTDs and
entities are rejected; sources are limited to 1 MiB and 1,000 entries.

Selected rows form a new profile. Every imported command remains unverified and
disabled until its applicability, syntax and risk are checked in the editor.
Import never sends bytes or launches processes. UTF-8 and BOM-marked UTF-16 are
supported; other encodings require an explicit conversion of a copy.

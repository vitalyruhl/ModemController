# Catalog editing

The bundled JSON catalogs define button labels, categories, payloads, applicability,
references, parameters and deadlines. Use **Catalog → Edit / import / export**
to edit local copies. Field changes must be applied or discarded before switching
commands. User overlays preserve unchanged fields from future bundled defaults.
Native imports and executable-field edits remain unverified until separately
reviewed and explicitly enabled. No editor action opens a port or sends bytes.

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

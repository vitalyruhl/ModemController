# Release notes

## 2.0.1 - desktop feedback corrections

The window title shows only the product version. Terminal output continues
following new replies after wrapped text, resizing and focus changes; deliberately
scrolling into history still pauses following. Build metadata refreshes when the
canonical version file changes, avoiding stale installed package versions.

The catalog editor follows the selected modem profile and keeps its command list
and search visible. Protocol and verification fields are grouped under Advanced.
Legacy XML/YAT command coverage now includes historical analog, ISDN and cellular
templates. Unverified templates stay outside automatic diagnostics. Parameterized
and state-changing AT buttons prepare editable commands without sending; SMS has
a separate preparation button. Categories use buttons, command spacing is fixed,
and the terminal input has more horizontal space.

## 2.0.0 - local candidate preparation

Python rewrite with an English desktop, shared serial terminal, reviewed modem
catalogs, bounded diagnostic workflows, editable portable data, legacy import,
reports, connection search, guarded SMS and a separate headless console.
Optional local Tools require script/argument review and explicit execution; the
RAS collector requires selected scope, consent and a new output directory.

Final integration fixes protect split credential input/history and delayed echoes,
close timed-out diagnostic connections, restore control-byte sends after reconnect
and preserve malformed catalog sidecars with a visible fallback. Candidate builds
include exact source/lock provenance, an archive checksum and payload verification.

The source/build identifier distinguishes candidates within this initial
implementation interval. Offline checks and read-only hardware observations do
not replace user HIL acceptance. Clean-target platform checks and redistribution
provenance remain separate gates; this is not a published release.

# Release notes

## 2.1.3 - public Python release and isolated portable build

This is the first public Python GUI/CLI release, replacing the VB application
on `main`. The repository is now named **ModemController**. Native serial ports,
USB-to-serial adapters and USB modems with a serial AT interface use the same
COM-port workflow. The historical `V1.5.0.10` tag/release remains available.

The public portable ZIP includes download references for manufacturer manuals
instead of redistributing their PDFs. The source `.tar.gz` includes build scripts,
locked dependencies and documentation. Windows CI checks Python 3.12 and 3.13.
Portable builds isolate dependency discovery from unrelated programs on PATH.

The user confirmed SMS sending and receiving on the tested BG95-M3 setup.
Clean Windows 10/11 and Server 2019+ field checks remain pending. Voice dialing
on this firmware is unconfirmed; the Phoenix Contact test is deferred. SIM Info,
the settings popup and cross-profile JSON-value search remain planned.

Version 2.1.3 changes packaging and documentation; the SMS implementation
accepted by the user in 2.1.2 is unchanged.

## 2.1.2 - SMS confirmation and visible workflow traffic

Native Qt Yes results are compared by value so confirmed SMS sends/reads and
maintenance/control-byte actions start correctly. Guided TX/RX now appears in the
shared terminal as well as the selected session log, preserving secret suppression.
SMS results and preflight failures appear in the SMS dialog, terminal and log.
Basic text SMS accepts the common supported character subset with either GSM or
IRA; other encodings remain blocked and no modem configuration changes implicitly.
Successful modem submission is still distinguished from recipient delivery.

## 2.1.1 - portable documentation completeness

The portable root includes the main README with working links into `help/`.
The documentation index and PDF modem manuals are bundled under
`help/reference/modems/`, preserving their source subfolders. Driver installers
remain excluded. Application and modem behavior are unchanged.

## 2.1.0 - explicit command execution choices

The catalog editor exposes Direct execution/send beside Favorite and persists
the independent choice in JSON. Commands can be prepared in the AT/hex input or
executed through their existing reviewed, confirmed path. Older configurations
keep their defaults; unverified commands and sensitive workflows retain their gates.
Declared secret parameters always use masked, confirmed input and suppressed
capture, including custom commands labeled read-only. Transient values are cleared
after the worker finishes.

Resizing the editor now expands its command list and editable content. In the main
window, categories and commands share additional vertical space at a 1:2 ratio;
buttons keep consistent spacing and remain aligned at the top.

The rightmost **?** menu contains About and report export. About shows the author,
product version, license and fixed UTC build timestamp. The duplicate Messaging
menu is removed; **Prepare SMS** is the single entry point and explains when
connection or profile capabilities prevent SMS actions.

Generic AT → Setup now includes the user-defined full GSM SMS initialization,
including `AT+CLIP=1`, as ten separately acknowledged steps. Its confirmation
shows the commands and reset/data/persistence effects. Failure identifies the
stopped step and prevents later commands. Compatibility remains device-dependent;
the user's BG95 returned ERROR for CLIP. No full initialization was run on hardware.

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

The desktop Tools editor is replaced by a small plugin launcher. Each plugin has
its own folder under `plugins` and a `plugin.json` containing its name, program
and optional arguments. The RAS collector uses its own selection window. Plugins
own their lifetime and any UAC request; the modem application does not elevate.

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

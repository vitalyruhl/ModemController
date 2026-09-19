# Reviewed local tools

Choose **Local tools...** to release the application's serial connection and open
the optional tools dialog. No script runs on startup, import, profile selection or
reconnect. Import a JSON registry, inspect the script preview, interpreter,
arguments, working directory, effects and limits, then confirm review and click
**Run selected tool**. Every import/restart requires review. Script, interpreter
or definition changes invalidate the review fingerprint. There is no script editor.

Definitions in `tools.json` have `schema_version: 1` and a `tools` list. Each tool
has `id`, `label`, `script`, `kind` (python/ps1/cmd), `interpreter`, `arguments`,
`working_directory`, `effects`, `serial_requirement`, `timeout_seconds` and
`output_limit`. Relative paths resolve beside the registry. Unknown/serial tools
require release of the application port; the desktop releases it for all tools.
Arguments are a JSON list of individual strings, without secret values.

Windows PowerShell 5.1 is the PS1 default. No execution-policy bypass, elevation,
download or interpreter installation occurs. Python requires an explicitly
selected installed executable; the portable app's private runtime is not an
arbitrary script interpreter. CMD metacharacters are rejected before invocation.
CMD is inherently a shell; only the reviewed script path and restricted literal
arguments are passed to it. Python and PS1 receive separate argument values.

Local scripts are trusted executable code, not a sandbox. A read-only label does
not enforce read-only behavior. Cancellation cannot undo effects. Execution runs
outside the GUI thread, captures bounded stdout/stderr, reports exit status and
cleans up owned children on timeout/cancel and normal parent exit. On Windows the
process is created suspended, assigned to a kill-on-close Job Object, then resumed;
failure to establish ownership prevents execution. See Microsoft's
[job assignment](https://learn.microsoft.com/en-us/windows/win32/api/jobapi2/nf-jobapi2-assignprocesstojobobject)
and [thread enumeration](https://learn.microsoft.com/en-us/windows/win32/toolhelp/traversing-the-thread-list).

Only the registered script and interpreter files are fingerprinted; scripts that
load other files or invoke other programs remain responsible for those dependencies.
Review their behavior and environment before use. Tools do not receive an internal
AT-session API. Harmless process-fixture tests are separate from permission to run
host diagnostics or a RAS collection.

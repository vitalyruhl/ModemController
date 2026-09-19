# Optional Windows RAS evidence

Open **Local tools...**, select the RAS collector, then **Collection options...**.
Select sources, a 1-168 hour event window and a new output directory, and explicitly
consent. Review the script/arguments, confirm review, then Run. No collection starts
when opening the dialog. Normal AT use requires neither this tool nor administrator
rights. Missing PowerShell, commands, permissions or data produce explicit errors
or partial results; the app does not install, elevate or change execution policy.

The collector reads only the selected modem, port, adapter, RAS status, current-user
phonebook or RasClient event summaries. It never searches other users' profiles,
dials/disconnects, enables logging, changes registry/services or installs drivers.
Phonebooks include only Type/Device/DeviceType fields; event messages, connection
names and network addresses are intentionally omitted. The RAS status collector
records command availability and output line count, not an active-connection count.

Rows are limited to 100 per collector, serialized results to 100,000 bytes each,
and the report to 1 MiB. The registered process deadline is 60 seconds. Results are
saved atomically after each source; cancellation may leave a clearly partial report
and/or a partial write file in the newly created directory. Existing output
directories are refused. Unknown/access-denied sources remain partial, with no
repair or fallback collection. Redaction removes common credential, phone/IP/email
patterns; review device descriptions before sharing. Redaction is not an anonymity
guarantee.

`-FixtureDirectory` is the offline test adapter: it reads only synthetic selected
JSON fixtures and bypasses all host collectors, including when a fixture is missing.
Those tests demonstrate bounds/error handling, not an actual Windows RAS collection
or diagnosis. An actual host smoke test requires a separately agreed collection
scope and user acceptance. The old `.Temp/dfue-check.ps1` remains unexecuted source
material; its broad traversal and fixed-drive assumptions are not part of this tool.

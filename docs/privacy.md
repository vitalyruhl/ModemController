# Local session privacy

PIN/password assignments and incomplete credential-command prefixes pause capture
and file-log payload recording until the connection is reopened. The terminal
shows a capture-gap notice. This conservative boundary also suppresses fragmented
or delayed echoes; it must not be described as a complete raw transcript.

Secret command input is cleared after submission and is not retained in terminal
entries or AT exchange snapshots. Guided maintenance uses the same boundary and
closes the invalidated connection after the single confirmed action.

Explicitly enabled SMS wire logging remains sensitive local evidence and can
contain recipients and message bodies. It is separate from a redacted shareable
report. Logs are never uploaded automatically.

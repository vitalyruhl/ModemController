# Local session privacy

PIN/password assignments and incomplete credential-command prefixes pause capture
and file-log payload recording until the connection is reopened. The terminal
shows a capture-gap notice. This conservative boundary also suppresses fragmented
or delayed echoes; it must not be described as a complete raw transcript.

Secret command input is cleared after submission and is not retained in terminal
entries or AT exchange snapshots. Guided maintenance uses the same boundary and
closes the invalidated connection after the single confirmed action.

The pause also covers split text/hex submissions, history drafts and resend.
Clearing the terminal or disconnecting does not reset it; a successful new
connection clears transient input and starts a new capture context. Automated
diagnostic, maintenance and SMS workflows require reconnecting after manual
credential input, so delayed echoes cannot enter their result evidence.

An incomplete diagnostic run closes its connection on timeout or cancellation.
Reconnect deliberately before retrying; a late reply must not confirm a later run.

Explicitly enabled SMS wire logging remains sensitive local evidence and can
contain recipients and message bodies. It is separate from a redacted shareable
report. Logs are never uploaded automatically.
# SMS submission boundary

The reviewed generic SMS path queries SIM readiness, text mode and a GSM or IRA
character set before issuing CMGS. It currently accepts letters, digits, spaces
and basic ASCII punctuation only. It never changes modes automatically. Other
character sets and PDU mode stop before submission. Device-specific profiles
default to no SMS capability until reviewed. A CMGS reference plus final OK
confirms modem submission, not recipient delivery. Cancellation after Ctrl+Z has
an unknown outcome and must not cause an automatic resend.

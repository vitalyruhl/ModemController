# User-defined GSM SMS initialization

In **Generic AT → Setup**, **Full GSM SMS initialization** provides the sequence
requested by the user on 2026-09-19. The user confirmed `AT&F` as the first command
and then added `AT+CLIP=1`. Each line is sent separately, in this order:

```text
AT&F
AT+CREG=1
AT+CRC=1
AT+CLIP=1
AT+CMGF=1
AT+CNMI=1,1
AT+CPMS="MT"
AT+CGATT=0
AT+CGDCONT=1,"IP",""
AT&W
```

The complete preview requires confirmation. This resets settings, changes incoming
call/SMS indications and storage, detaches packet service, overwrites PDP context 1
and saves the active profile. It does not send an SMS. Ordinary individual buttons
prepare their command by default; the complete sequence uses the guarded runner.

Every step requires a final `OK`. The first error, timeout or cancellation stops
the sequence without retry or resume. Later steps, including `AT&W`, are not sent.
The result identifies the stopped step. A failure does not undo earlier changes.
The desktop total budget is 30 seconds; per-step and configured connection
response deadlines may stop a command earlier. Reconnect after the operation.

`supported` records source/workflow review for this explicit user-defined generic
sequence, not hardware acceptance for every modem. Device-specific profiles and
their diagnostic allowlists remain unchanged. The full sequence is available in
Generic AT; borrowing common single AT templates does not import sequences.

`AT+CLIP=1` enables incoming caller identification at the terminal. It does not
control transmission of the caller's own number; `AT+CLIR` controls outgoing
identification restriction. See the manufacturer's
[AT manual, sections 10.4 and 10.5](https://quectel.com/content/uploads/2021/03/Quectel_BG95BG77BG600L_Series_AT_Commands_Manual_V2.0-2.pdf).
The user's BG95-M3 / BG95M3LAR02A03 log returned `ERROR` for `AT+CLIP=1`.
The cause is unconfirmed; this sequence deliberately stops if that result recurs.
No full initialization or SMS delivery has been validated on hardware in this run.

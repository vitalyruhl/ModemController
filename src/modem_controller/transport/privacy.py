"""Conservative classification of credential-bearing AT input, including raw bytes."""

import re

_ASSIGNMENT = re.compile(rb"(?:^|[\r\n;])\s*(?:AT)?\+(?:CPIN|CPWD|CLCK)\s*=", re.I)
_PREFIXES = (b"AT+CPIN=", b"AT+CPWD=", b"AT+CLCK=")


def contains_secret_input(payload: bytes) -> bool:
    """Recognize assignments and incomplete credential-command prefixes."""
    normalized = payload.strip().upper()
    return bool(_ASSIGNMENT.search(payload)) or (
        normalized.startswith(b"AT+")
        and any(prefix.startswith(normalized) for prefix in _PREFIXES)
    )

"""Timestamped byte capture independent of terminal display formatting."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class CaptureDirection(str, Enum):
    """The direction in which bytes crossed the serial connection."""

    RECEIVED = "received"
    TRANSMITTED = "transmitted"


@dataclass(frozen=True, slots=True)
class CaptureRecord:
    """One accepted, unmodified serial byte sequence."""

    timestamp: datetime
    direction: CaptureDirection
    data: bytes

    @property
    def byte_count(self) -> int:
        return len(self.data)


@dataclass(frozen=True, slots=True)
class CaptureAppendResult:
    """The result of attempting to retain a capture record."""

    accepted: bool
    dropped_records: int = 0
    dropped_bytes: int = 0


@dataclass(frozen=True, slots=True)
class CaptureSnapshot:
    records: tuple[CaptureRecord, ...] = ()
    dropped_records: int = 0
    dropped_bytes: int = 0
    sensitive_gaps: int = 0
    sensitive_bytes: int = 0

    def summary(self) -> dict[str, object]:
        return {
            "available": bool(
                self.records or self.dropped_records or self.sensitive_gaps
            ),
            "records": len(self.records),
            "stored_bytes": sum(r.byte_count for r in self.records),
            "dropped_records": self.dropped_records,
            "dropped_bytes": self.dropped_bytes,
            "sensitive_gaps": self.sensitive_gaps,
            "sensitive_bytes": self.sensitive_bytes,
            "incomplete": bool(self.dropped_records or self.sensitive_gaps),
            "first_record_utc": self.records[0].timestamp.isoformat(
                timespec="milliseconds"
            )
            if self.records
            else None,
            "last_record_utc": self.records[-1].timestamp.isoformat(
                timespec="milliseconds"
            )
            if self.records
            else None,
        }


class CaptureBuffer:
    """A bounded append-only buffer that never silently evicts accepted bytes."""

    def __init__(self, *, max_records: int, max_bytes: int) -> None:
        if max_records <= 0:
            raise ValueError("max_records must be positive")
        if max_bytes <= 0:
            raise ValueError("max_bytes must be positive")

        self._max_records = max_records
        self._max_bytes = max_bytes
        self._records: deque[CaptureRecord] = deque()
        self._stored_bytes = 0
        self._dropped_records = 0
        self._dropped_bytes = 0
        self._sensitive_gaps = 0
        self._sensitive_bytes = 0

    @property
    def dropped_records(self) -> int:
        return self._dropped_records

    @property
    def dropped_bytes(self) -> int:
        return self._dropped_bytes

    @property
    def stored_bytes(self) -> int:
        return self._stored_bytes

    @property
    def sensitive_gaps(self) -> int:
        return self._sensitive_gaps

    @property
    def sensitive_bytes(self) -> int:
        return self._sensitive_bytes

    def append(self, record: CaptureRecord) -> CaptureAppendResult:
        """Retain *record* only when doing so fits the declared limits."""

        record_size = record.byte_count
        if (
            len(self._records) >= self._max_records
            or self._stored_bytes + record_size > self._max_bytes
        ):
            self._dropped_records += 1
            self._dropped_bytes += record_size
            return CaptureAppendResult(
                accepted=False,
                dropped_records=1,
                dropped_bytes=record_size,
            )

        self._records.append(record)
        self._stored_bytes += record_size
        return CaptureAppendResult(accepted=True)

    def record_sensitive_gap(self, byte_count: int) -> None:
        """Record intentionally excluded sensitive bytes without retaining them."""

        if byte_count <= 0:
            raise ValueError("byte_count must be positive")
        self._sensitive_gaps += 1
        self._sensitive_bytes += byte_count

    def snapshot(self) -> tuple[CaptureRecord, ...]:
        return tuple(self._records)

    def evidence_snapshot(self) -> CaptureSnapshot:
        return CaptureSnapshot(
            self.snapshot(),
            self._dropped_records,
            self._dropped_bytes,
            self._sensitive_gaps,
            self._sensitive_bytes,
        )

    def clear(self) -> None:
        self._records.clear()
        self._stored_bytes = 0

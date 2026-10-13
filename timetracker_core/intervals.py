"""Validation for explicitly entered, completed intervals (not legacy loading)."""
from datetime import datetime, timezone
import re

# The loader remains permissive. New writes require whole seconds and an explicit,
# well-formed offset; fromisoformat alone accepts/normalizes more than this contract.
_TIMESTAMP = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:Z|[+-](?:[01][0-9]|2[0-3]):[0-5][0-9])"
)


class IntervalError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def parse_interval_timestamp(value):
    try:
        if not isinstance(value, str) or not _TIMESTAMP.fullmatch(value):
            raise ValueError("Expected an explicit timestamp")
        return datetime.fromisoformat(value).astimezone(timezone.utc)
    except (ValueError, OverflowError):
        raise IntervalError(
            "invalid_timestamp",
            "Use a valid date and time with seconds and UTC offset, such as "
            "2026-10-12T09:00:00-05:00 (or Z for UTC).",
        ) from None


def same_recorded_instant(stored, supplied):
    # The public view and JSON use seconds. An untouched editor must not unlog an
    # entry merely because the in-memory tracking clock originally had microseconds.
    return stored is not None and stored.replace(microsecond=0) == supplied


def validate_interval(session, start, end, now, exclude_id=None):
    if end <= start:
        raise IntervalError("invalid_interval", "End time must be later than start time.")
    if end > now:
        raise IntervalError("future_interval", "Recorded time cannot end in the future.")
    for other in session.visible_entries():
        if other.id == exclude_id:
            continue
        other_start = other.start_time
        other_end = other.end_time
        if other_start is None or (other.is_complete and (other_end is None or other_end < other_start)):
            raise IntervalError(
                "invalid_existing_interval",
                f"Entry #{other.id} has missing or invalid times. Correct or delete that "
                "entry before adding or correcting other intervals; nothing was changed.",
            )
        # Half-open intervals: adjacency and empty legacy intervals are not overlaps.
        if other.is_complete and other_end == other_start:
            continue
        if (not other.is_complete or start < other_end) and other_start < end:
            raise IntervalError(
                "interval_overlap",
                f"This interval overlaps entry #{other.id}. Choose non-overlapping times "
                "or correct that entry first.",
            )

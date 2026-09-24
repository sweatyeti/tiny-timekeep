"""Stdlib-only core of the time-tracking application."""

CONTRACT_VERSION = "v1.4"

from .model import (
    UNNAMED_TASK, SCHEMA_VERSION, Entry, Session, format_timestamp, is_unnamed,
    normalize_description, normalize_task, now_utc, parse_timestamp, round_up_minutes,
    tasks_match,
)
from .storage import LoadedDocument, SessionStore
from .core import TimeTrackerCore

__all__ = ["CONTRACT_VERSION", "UNNAMED_TASK", "SCHEMA_VERSION", "Entry", "Session",
           "format_timestamp", "is_unnamed", "normalize_description", "normalize_task",
           "now_utc", "parse_timestamp", "round_up_minutes", "tasks_match",
           "LoadedDocument", "SessionStore", "TimeTrackerCore"]
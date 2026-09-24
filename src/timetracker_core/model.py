"""Core data model for the time-tracking application."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone

UNNAMED_TASK = "unnamed"
SCHEMA_VERSION = 2
TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%S%z"


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def format_timestamp(moment: datetime | None) -> str | None:
    if moment is None:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    moment = moment.replace(microsecond=0)
    return moment.isoformat()


def parse_timestamp(text: object) -> datetime | None:
    if not isinstance(text, str):
        return None
    try:
        dt = datetime.fromisoformat(text)
    except (ValueError, TypeError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def round_up_minutes(seconds: float) -> int:
    if seconds < 0:
        return 0
    return math.ceil(seconds / 60)


def normalize_task(value: object) -> str:
    if value is None:
        return UNNAMED_TASK
    s = str(value).strip()
    if not s:
        return UNNAMED_TASK
    return s


def normalize_description(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def tasks_match(a: str, b: str) -> bool:
    return a.lower() == b.lower()


def is_unnamed(task: str) -> bool:
    return task.lower() == UNNAMED_TASK


@dataclass
class Entry:
    id: int
    start_time: datetime | None
    end_time: datetime | None
    task: str = UNNAMED_TASK
    description: str = ""
    logged: bool = False
    is_complete: bool = False
    is_deleted: bool = False

    def is_running(self) -> bool:
        return not self.is_complete and not self.is_deleted

    def duration_seconds(self) -> float | None:
        if self.start_time is None or self.end_time is None:
            return None
        return max(0.0, (self.end_time - self.start_time).total_seconds())

    def to_document(self) -> dict:
        return {
            "id": self.id,
            "startTime": format_timestamp(self.start_time),
            "endTime": format_timestamp(self.end_time),
            "task": self.task,
            "description": self.description,
            "logged": self.logged,
            "isComplete": self.is_complete,
            "isDeleted": self.is_deleted,
        }

    @classmethod
    def from_document(cls, doc: object) -> Entry | None:
        if not isinstance(doc, dict):
            return None
        raw_id = doc.get("id")
        if isinstance(raw_id, bool):
            return None
        if isinstance(raw_id, int):
            entry_id = raw_id
        elif isinstance(raw_id, float):
            if raw_id != int(raw_id):
                return None
            entry_id = int(raw_id)
        elif isinstance(raw_id, str):
            try:
                entry_id = int(raw_id)
            except ValueError:
                return None
        else:
            return None

        start_time = parse_timestamp(doc.get("startTime"))
        end_time = parse_timestamp(doc.get("endTime"))
        task = normalize_task(doc.get("task"))
        description = normalize_description(doc.get("description"))
        logged = bool(doc.get("logged", False))
        is_deleted = bool(doc.get("isDeleted", False))

        if "isComplete" in doc:
            is_complete = bool(doc["isComplete"])
        else:
            is_complete = end_time is not None
        if end_time is not None:
            is_complete = True

        return cls(
            id=entry_id,
            start_time=start_time,
            end_time=end_time,
            task=task,
            description=description,
            logged=logged,
            is_complete=is_complete,
            is_deleted=is_deleted,
        )


@dataclass
class Session:
    session_id: str
    name: str
    started_at: datetime | None
    ended_at: datetime | None
    entries: list[Entry] = field(default_factory=list)
    file_name: str | None = None

    def next_entry_id(self) -> int:
        if not self.entries:
            return 1
        return max(e.id for e in self.entries) + 1

    def ordered_entries(self) -> list[Entry]:
        return sorted(self.entries, key=lambda e: e.id)

    def visible_entries(self) -> list[Entry]:
        return [e for e in self.ordered_entries() if not e.is_deleted]

    def deleted_entries(self) -> list[Entry]:
        return [e for e in self.ordered_entries() if e.is_deleted]

    def running_entries(self) -> list[Entry]:
        return [e for e in self.visible_entries() if e.is_running()]

    def current_entry(self) -> Entry | None:
        running = self.running_entries()
        if not running:
            return None
        return max(running, key=lambda e: e.id)

    def is_active(self) -> bool:
        """True while this session is open (contract v1.1 §2).

        Open means no end time has been stored yet; it is independent of
        whether any entry is currently being tracked.
        """
        return self.ended_at is None

    def find_entry(self, entry_id: int) -> Entry | None:
        for e in self.entries:
            if e.id == entry_id and not e.is_deleted:
                return e
        return None

    def to_document(self) -> dict:
        return {
            "schemaVersion": SCHEMA_VERSION,
            "sessionId": self.session_id,
            "name": self.name,
            "startedAt": format_timestamp(self.started_at),
            "endedAt": format_timestamp(self.ended_at),
            "entries": [e.to_document() for e in self.ordered_entries()],
        }

    @classmethod
    def from_document(
        cls, doc: object, file_name: str | None = None
    ) -> tuple[Session | None, str | None]:
        if not isinstance(doc, dict):
            return None, "document is not a JSON object"

        raw_version = doc.get("schemaVersion")
        if not isinstance(raw_version, int) or isinstance(raw_version, bool):
            return None, "document has no readable schema version"
        if raw_version > SCHEMA_VERSION:
            return None, (
                f"document schema version {raw_version} is newer than supported version {SCHEMA_VERSION}"
            )

        session_id = str(doc["sessionId"]) if "sessionId" in doc else ""

        name = doc.get("name")
        if name is None or not str(name).strip():
            name = "Untitled session"
        else:
            name = str(name).strip()

        started_at = parse_timestamp(doc.get("startedAt"))
        ended_at = parse_timestamp(doc.get("endedAt"))

        raw_entries = doc.get("entries")
        if not isinstance(raw_entries, list):
            raw_entries = []

        parsed: list[Entry] = []
        for n, item in enumerate(raw_entries, 1):
            if not isinstance(item, dict):
                return None, f"entry {n} is not a JSON object"
            entry = Entry.from_document(item)
            if entry is None:
                return None, f"entry {n} has a corrupt or invalid id"
            parsed.append(entry)

        # Collapse duplicate ids: last occurrence's values win,
        # entry keeps the position of its first occurrence.
        first_pos: dict[int, int] = {}
        last_entry: dict[int, Entry] = {}
        for i, entry in enumerate(parsed):
            if entry.id not in first_pos:
                first_pos[entry.id] = i
            last_entry[entry.id] = entry

        entries: list[Entry] = []
        for eid in sorted(first_pos.keys(), key=lambda x: first_pos[x]):
            entries.append(last_entry[eid])

        return cls(
            session_id=session_id,
            name=name,
            started_at=started_at,
            ended_at=ended_at,
            entries=entries,
            file_name=file_name,
        ), None
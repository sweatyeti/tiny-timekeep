"""Time-tracking core module."""

import threading
import uuid
from pathlib import Path

from .model import (
    Entry,
    Session,
    format_timestamp,
    is_unnamed,
    normalize_description,
    normalize_task,
    now_utc,
    round_up_minutes,
    tasks_match,
)
from .storage import SessionStore


class TimeTrackerCore:
    def __init__(self, storage_path, clock=None) -> None:
        self._clock = clock if clock is not None else now_utc
        self._store = SessionStore(storage_path)
        self._session = None
        self._lock = threading.RLock()

    def _is_session_open(self) -> bool:
        return self._session is not None and self._session.is_active()

    def _no_active_session(self) -> dict:
        return {
            "ok": False,
            "error": "no_active_session",
            "message": "No session is open. Start or resume a session first.",
        }

    # ------------------------------------------------------------------
    # View-model construction (private helpers)
    # ------------------------------------------------------------------

    def _build_view_model(self) -> dict:
        if self._session is None:
            return {
                "session": None,
                "currentEntry": None,
                "entries": [],
                "summary": [],
                "totals": {"unloggedMinutes": 0, "totalMinutes": 0},
            }

        session = self._session
        visible = session.visible_entries()

        session_view = {
            "id": session.session_id,
            "name": session.name,
            "startedAt": format_timestamp(session.started_at),
        }

        current = session.current_entry()
        current_view = None
        if current is not None:
            current_view = {
                "id": current.id,
                "task": current.task,
                "startTime": format_timestamp(current.start_time),
            }

        entries_view = []
        for entry in sorted(visible, key=lambda e: e.id, reverse=True):
            if entry.is_running() or is_unnamed(entry.task):
                logged_status = "N/A"
            elif entry.logged:
                logged_status = "Logged"
            else:
                logged_status = "Unlogged"
            entries_view.append({
                "id": entry.id,
                "task": entry.task,
                "description": entry.description,
                "startTime": format_timestamp(entry.start_time),
                "endTime": format_timestamp(entry.end_time),
                "isComplete": entry.is_complete,
                "loggedStatus": logged_status,
            })

        summary, totals = self._build_summary(visible)

        return {
            "session": session_view,
            "currentEntry": current_view,
            "entries": entries_view,
            "summary": summary,
            "totals": totals,
        }

    def _build_summary(self, visible_entries) -> tuple:
        completed = [e for e in visible_entries if e.is_complete]

        groups: dict[str, dict] = {}
        order: list[str] = []

        for entry in sorted(completed, key=lambda e: e.id):
            dur = entry.duration_seconds()
            if dur is None:
                continue
            key = entry.task.lower()
            if key not in groups:
                groups[key] = {"task": entry.task, "entries": []}
                order.append(key)
            groups[key]["entries"].append(entry)

        summary: list[dict] = []
        total_unlogged = 0
        total_minutes = 0

        for key in order:
            group = groups[key]
            count = len(group["entries"])
            total_min = 0
            unlogged_min = 0
            for entry in group["entries"]:
                mins = round_up_minutes(entry.duration_seconds())
                total_min += mins
                if not entry.logged:
                    unlogged_min += mins
            callout = (not is_unnamed(group["task"])) and unlogged_min > 0
            summary.append({
                "task": group["task"],
                "count": count,
                "unloggedMinutes": unlogged_min,
                "totalMinutes": total_min,
                "callout": callout,
            })
            if not is_unnamed(group["task"]):
                total_unlogged += unlogged_min
                total_minutes += total_min

        totals = {"unloggedMinutes": total_unlogged, "totalMinutes": total_minutes}
        return summary, totals

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_state(self) -> dict:
        with self._lock:
            return self._build_view_model()

    def list_sessions(self) -> list[dict]:
        with self._lock:
            try:
                docs = self._store.load_all()
            except Exception:
                return []

            rows: list[dict] = []
            for doc in docs:
                if doc.session is not None:
                    s = doc.session
                    started_at = format_timestamp(s.started_at)
                    ended_at = format_timestamp(s.ended_at)
                    if s.started_at is not None:
                        sort_key = (0, -s.started_at.timestamp(), doc.file_name)
                    else:
                        sort_key = (1, 0, doc.file_name)
                    rows.append({
                        "_sort": sort_key,
                        "id": s.session_id,
                        "name": s.name,
                        "startedAt": started_at,
                        "endedAt": ended_at,
                        "isUnfinished": ended_at is None,
                        "isUnreadable": False,
                    })
                else:
                    stem = Path(doc.file_name).stem
                    rows.append({
                        "_sort": (1, 0, doc.file_name),
                        "id": doc.session_id,
                        "name": stem,
                        "startedAt": None,
                        "endedAt": None,
                        "isUnfinished": False,
                        "isUnreadable": True,
                        "reason": doc.error,
                    })

            rows.sort(key=lambda r: r["_sort"])
            for r in rows:
                del r["_sort"]
            return rows

    def list_loggable_task_groups(self) -> list[dict]:
        with self._lock:
            if self._session is None:
                return []
            try:
                visible = self._session.visible_entries()
                qualifying = [
                    e for e in visible
                    if e.is_complete and not e.logged and not is_unnamed(e.task)
                ]
                groups: dict[str, dict] = {}
                order: list[str] = []
                for entry in sorted(qualifying, key=lambda e: e.id):
                    key = entry.task.lower()
                    if key not in groups:
                        groups[key] = {"task": entry.task, "count": 0}
                        order.append(key)
                    groups[key]["count"] += 1
                return [
                    {"task": groups[k]["task"], "unloggedCount": groups[k]["count"]}
                    for k in order
                ]
            except Exception:
                return []

    def list_deleted_entries(self) -> list[dict]:
        with self._lock:
            if self._session is None:
                return []
            try:
                deleted = self._session.deleted_entries()
                return [
                    {
                        "id": e.id,
                        "task": e.task,
                        "startTime": format_timestamp(e.start_time),
                        "endTime": format_timestamp(e.end_time),
                        # v1.4 (§3.10): the UI shows what a deleted entry was before restoring it.
                        "description": e.description,
                    }
                    for e in deleted
                ]
            except Exception:
                return []

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    def start_session(self, name, first_task) -> dict:
        with self._lock:
            try:
                clock_now = self._clock()

                if name is None or not name.strip():
                    name = "Session " + clock_now.strftime("%Y-%m-%d %H:%M")

                session_id = str(uuid.uuid4())
                task = normalize_task(first_task)

                entry = Entry(
                    id=1,
                    start_time=clock_now,
                    end_time=None,
                    task=task,
                    description="",
                    logged=False,
                    is_complete=False,
                    is_deleted=False,
                )

                session = Session(
                    session_id=session_id,
                    name=name,
                    started_at=clock_now,
                    ended_at=None,
                    entries=[entry],
                    file_name=None,
                )

                self._store.save(session)
                self._session = session

                return {"ok": True, "state": self._build_view_model()}
            except Exception as exc:
                return {"ok": False, "error": "internal_error", "message": str(exc)}

    def resume_session(self, session_id) -> dict:
        with self._lock:
            try:
                session, code, message = self._store.find(session_id)

                if code == "session_not_found":
                    return {
                        "ok": False,
                        "error": "session_not_found",
                        "message": message or "Session not found.",
                    }
                if code == "session_unreadable":
                    return {
                        "ok": False,
                        "error": "session_unreadable",
                        "message": message or "Session is unreadable.",
                    }
                if session is None:
                    return {
                        "ok": False,
                        "error": "session_not_found",
                        "message": "Session not found.",
                    }

                session.ended_at = None
                self._store.save(session)
                self._session = session

                return {"ok": True, "state": self._build_view_model()}
            except Exception as exc:
                return {"ok": False, "error": "internal_error", "message": str(exc)}

    def stop_and_start_entry(self, next_task) -> dict:
        with self._lock:
            try:
                if not self._is_session_open():
                    return self._no_active_session()

                clock_now = self._clock()
                session = self._session

                current = session.current_entry()
                if current is not None:
                    current.end_time = clock_now
                    current.is_complete = True

                new_id = session.next_entry_id()
                entry = Entry(
                    id=new_id,
                    start_time=clock_now,
                    end_time=None,
                    task=normalize_task(next_task),
                    description="",
                    logged=False,
                    is_complete=False,
                    is_deleted=False,
                )
                session.entries.append(entry)

                self._store.save(session)

                return {"ok": True, "state": self._build_view_model()}
            except Exception as exc:
                return {"ok": False, "error": "internal_error", "message": str(exc)}

    def edit_entry(self, entry_id, task, description, logged) -> dict:
        with self._lock:
            try:
                if not self._is_session_open():
                    return self._no_active_session()

                entry = self._session.find_entry(entry_id)
                if entry is None:
                    return {
                        "ok": False,
                        "error": "entry_not_found",
                        "message": "Entry not found.",
                    }

                effective_task = normalize_task(task) if task is not None else entry.task

                if logged is not None:
                    if not entry.is_complete or is_unnamed(effective_task):
                        return {
                            "ok": False,
                            "error": "logged_not_applicable",
                            "message": "Cannot set logged on a running or unnamed entry.",
                        }

                if task is not None:
                    entry.task = normalize_task(task)
                if description is not None:
                    entry.description = normalize_description(description)
                if logged is not None:
                    entry.logged = bool(logged)

                self._store.save(self._session)

                return {"ok": True, "state": self._build_view_model()}
            except Exception as exc:
                return {"ok": False, "error": "internal_error", "message": str(exc)}

    def delete_entry(self, entry_id) -> dict:
        with self._lock:
            try:
                if not self._is_session_open():
                    return self._no_active_session()

                entry = self._session.find_entry(entry_id)
                if entry is None:
                    return {
                        "ok": False,
                        "error": "entry_not_found",
                        "message": "Entry not found.",
                    }

                if entry.is_running():
                    return {
                        "ok": False,
                        "error": "entry_not_completed",
                        "message": "Entry is still running; stop it first.",
                    }

                entry.is_deleted = True
                self._store.save(self._session)

                return {"ok": True, "state": self._build_view_model()}
            except Exception as exc:
                return {"ok": False, "error": "internal_error", "message": str(exc)}

    def restore_entry(self, entry_id) -> dict:
        with self._lock:
            try:
                if not self._is_session_open():
                    return self._no_active_session()

                entry = None
                for e in self._session.entries:
                    if e.id == entry_id and e.is_deleted:
                        entry = e
                        break

                if entry is None:
                    return {
                        "ok": False,
                        "error": "entry_not_found",
                        "message": "Deleted entry not found.",
                    }

                entry.is_deleted = False
                self._store.save(self._session)

                return {"ok": True, "state": self._build_view_model()}
            except Exception as exc:
                return {"ok": False, "error": "internal_error", "message": str(exc)}

    def log_task_group(self, task) -> dict:
        with self._lock:
            try:
                if not self._is_session_open():
                    return self._no_active_session()

                effective = normalize_task(task)
                if is_unnamed(effective):
                    return {
                        "ok": False,
                        "error": "nothing_to_log",
                        "message": "Task is unnamed or empty.",
                    }

                visible = self._session.visible_entries()
                qualifying = [
                    e for e in visible
                    if e.is_complete and not e.logged and tasks_match(e.task, effective)
                ]

                if not qualifying:
                    return {
                        "ok": False,
                        "error": "nothing_to_log",
                        "message": "No unlogged completed entries for this task.",
                    }

                for e in qualifying:
                    e.logged = True

                self._store.save(self._session)

                return {"ok": True, "state": self._build_view_model()}
            except Exception as exc:
                return {"ok": False, "error": "internal_error", "message": str(exc)}

    def stop_tracking(self) -> dict:
        with self._lock:
            try:
                if self._session is None:
                    return {"ok": True, "state": self._build_view_model()}

                clock_now = self._clock()
                current = self._session.current_entry()
                if current is not None:
                    current.end_time = clock_now
                    current.is_complete = True

                self._store.save(self._session)

                return {"ok": True, "state": self._build_view_model()}
            except Exception as exc:
                return {"ok": False, "error": "internal_error", "message": str(exc)}

    def stop_and_exit(self) -> dict:
        with self._lock:
            try:
                if self._session is None:
                    return {"ok": True, "state": self._build_view_model()}

                clock_now = self._clock()
                current = self._session.current_entry()
                if current is not None:
                    current.end_time = clock_now
                    current.is_complete = True

                self._session.ended_at = clock_now
                self._store.save(self._session)
                self._session = None

                return {"ok": True, "state": self._build_view_model()}
            except Exception as exc:
                return {"ok": False, "error": "internal_error", "message": str(exc)}

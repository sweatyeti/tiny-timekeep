import os
import sys
import json
import shutil
import tempfile
import threading
import unittest
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from timetracker_core import CONTRACT_VERSION, UNNAMED_TASK, TimeTrackerCore  # noqa: E402


class FrozenClock:
    def __init__(self, start: datetime) -> None:
        self._now = start

    def __call__(self) -> datetime:
        return self._now

    def set(self, moment: datetime) -> None:
        self._now = moment

    def advance(self, **kwargs) -> None:
        self._now = self._now + timedelta(**kwargs)


def at(hour, minute, second=0):
    return datetime(2026, 9, 23, hour, minute, second, tzinfo=timezone.utc)


def _read_storage_json(storage_dir):
    """Return the single .json file content in storage_dir as a string."""
    files = [f for f in os.listdir(storage_dir) if f.endswith(".json")]
    assert len(files) == 1, f"Expected exactly one .json file, got {files}"
    with open(os.path.join(storage_dir, files[0]), "r", encoding="utf-8") as fh:
        return fh.read()


def _read_storage_json_obj(storage_dir):
    return json.loads(_read_storage_json(storage_dir))


def _assert_no_tmp_files(storage_dir):
    tmps = [f for f in os.listdir(storage_dir) if f.startswith(".tmp-")]
    assert not tmps, f"Found leftover .tmp- files: {tmps}"


class TestChecklistA(unittest.TestCase):
    """Task name, description, logged status and deletion can all be changed,
    with logged and deletion offered only where they apply."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.clock = FrozenClock(at(10, 0, 0))
        self.core = TimeTrackerCore(self.tmpdir, clock=self.clock)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _start_and_create_entries(self):
        """Start a session with 'alpha', stop it and start 'beta' (running)."""
        env = self.core.start_session("Test Session", "alpha")
        assert env["ok"]
        self.clock.advance(minutes=5)
        env = self.core.stop_and_start_entry("beta")
        assert env["ok"]
        return env["state"]

    def test_partial_update_none_fields_unchanged(self):
        state = self._start_and_create_entries()
        # entries newest-first: [beta(running), alpha(completed)]
        alpha_entry = state["entries"][1]
        alpha_id = alpha_entry["id"]

        # Change only the task, leave description and logged as None
        env = self.core.edit_entry(alpha_id, task="gamma", description=None, logged=None)
        assert env["ok"]
        new_state = env["state"]
        new_alpha = [e for e in new_state["entries"] if e["id"] == alpha_id][0]
        assert new_alpha["task"] == "gamma"
        # description was originally None/"" and stays the same
        assert new_alpha["description"] == alpha_entry["description"]
        # logged status unchanged (was "Unlogged" for completed named task)
        assert new_alpha["loggedStatus"] == alpha_entry["loggedStatus"]

    def test_empty_task_string_clears_to_unnamed(self):
        state = self._start_and_create_entries()
        alpha_entry = state["entries"][1]
        alpha_id = alpha_entry["id"]

        env = self.core.edit_entry(alpha_id, task="", description=None, logged=None)
        assert env["ok"]
        new_alpha = [e for e in env["state"]["entries"] if e["id"] == alpha_id][0]
        assert new_alpha["task"] == "unnamed"

    def test_empty_description_clears_to_empty_string(self):
        state = self._start_and_create_entries()
        alpha_entry = state["entries"][1]
        alpha_id = alpha_entry["id"]

        # First set a description
        env = self.core.edit_entry(alpha_id, task=None, description="hello", logged=None)
        assert env["ok"]

        # Now clear it
        env = self.core.edit_entry(alpha_id, task=None, description="", logged=None)
        assert env["ok"]
        new_alpha = [e for e in env["state"]["entries"] if e["id"] == alpha_id][0]
        assert new_alpha["description"] == ""

    def test_whitespace_trimmed(self):
        state = self._start_and_create_entries()
        alpha_id = state["entries"][1]["id"]

        env = self.core.edit_entry(alpha_id, task="  padded task  ", description="  padded desc  ", logged=None)
        assert env["ok"]
        new_alpha = [e for e in env["state"]["entries"] if e["id"] == alpha_id][0]
        assert new_alpha["task"] == "padded task"
        assert new_alpha["description"] == "padded desc"

    def test_logged_true_on_running_entry_rejected(self):
        state = self._start_and_create_entries()
        beta_entry = state["entries"][0]  # running
        beta_id = beta_entry["id"]
        original_task = beta_entry["task"]
        original_desc = beta_entry["description"]

        env = self.core.edit_entry(beta_id, task="changed", description="changed", logged=True)
        assert env["ok"] is False
        assert env["error"] == "logged_not_applicable"
        assert env["message"]

        # Nothing was changed
        new_state = self.core.get_state()
        new_beta = [e for e in new_state["entries"] if e["id"] == beta_id][0]
        assert new_beta["task"] == original_task
        assert new_beta["description"] == original_desc

    def test_logged_true_on_completed_unnamed_rejected(self):
        # Create an unnamed completed entry
        env = self.core.start_session("S", "")
        assert env["ok"]
        self.clock.advance(minutes=3)
        env = self.core.stop_tracking()
        assert env["ok"]
        state = env["state"]
        entry_id = state["entries"][0]["id"]
        assert state["entries"][0]["task"] == "unnamed"

        env = self.core.edit_entry(entry_id, task=None, description=None, logged=True)
        assert env["ok"] is False
        assert env["error"] == "logged_not_applicable"

    def test_delete_running_entry_rejected(self):
        state = self._start_and_create_entries()
        beta_id = state["entries"][0]["id"]  # running

        env = self.core.delete_entry(beta_id)
        assert env["ok"] is False
        assert env["error"] == "entry_not_completed"
        assert env["message"]

    def test_delete_completed_entry_ok(self):
        state = self._start_and_create_entries()
        alpha_id = state["entries"][1]["id"]  # completed

        env = self.core.delete_entry(alpha_id)
        assert env["ok"] is True
        new_state = env["state"]
        assert all(e["id"] != alpha_id for e in new_state["entries"])

    def test_unknown_id_entry_not_found(self):
        self._start_and_create_entries()
        bogus_id = "nonexistent-id-12345"

        env = self.core.edit_entry(bogus_id, task="x", description=None, logged=None)
        assert env["ok"] is False
        assert env["error"] == "entry_not_found"
        assert env["message"]

        env = self.core.delete_entry(bogus_id)
        assert env["ok"] is False
        assert env["error"] == "entry_not_found"
        assert env["message"]

        env = self.core.restore_entry(bogus_id)
        assert env["ok"] is False
        assert env["error"] == "entry_not_found"
        assert env["message"]

    def test_deleted_entry_not_editable(self):
        state = self._start_and_create_entries()
        alpha_id = state["entries"][1]["id"]

        env = self.core.delete_entry(alpha_id)
        assert env["ok"]

        env = self.core.edit_entry(alpha_id, task="x", description=None, logged=None)
        assert env["ok"] is False
        assert env["error"] == "entry_not_found"

    def test_failure_envelope_state_unchanged_on_disk(self):
        state = self._start_and_create_entries()
        beta_id = state["entries"][0]["id"]

        disk_before = _read_storage_json(self.tmpdir)
        env = self.core.edit_entry(beta_id, task="x", description=None, logged=True)
        assert env["ok"] is False
        disk_after = _read_storage_json(self.tmpdir)
        assert disk_before == disk_after


class TestChecklistB(unittest.TestCase):
    """A task group can be logged in one action, skipping running entries."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.clock = FrozenClock(at(9, 0, 0))
        self.core = TimeTrackerCore(self.tmpdir, clock=self.clock)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _build_scenario(self):
        """
        Creates:
          entry1: "weeding" completed (5 min)
          entry2: "Weeding" completed (3 min)
          entry3: "planning" completed (4 min)
          entry4: "planning" running
        """
        env = self.core.start_session("Garden", "weeding")
        assert env["ok"]
        self.clock.advance(minutes=5)
        env = self.core.stop_and_start_entry("Weeding")
        assert env["ok"]
        self.clock.advance(minutes=3)
        env = self.core.stop_and_start_entry("planning")
        assert env["ok"]
        self.clock.advance(minutes=4)
        env = self.core.stop_and_start_entry("planning")
        assert env["ok"]
        return env["state"]

    def test_loggable_groups_order_and_counts(self):
        self._build_scenario()
        groups = self.core.list_loggable_task_groups()
        # first-recorded order: weeding (entries 1,2) then planning (entry 3)
        assert len(groups) == 2
        assert groups[0]["task"] == "weeding"
        assert groups[0]["unloggedCount"] == 2
        assert groups[1]["task"] == "planning"
        assert groups[1]["unloggedCount"] == 1
        # unnamed never offered
        assert all(g["task"] != "unnamed" for g in groups)

    def test_log_task_group_case_insensitive(self):
        state = self._build_scenario()
        weeding_ids = [e["id"] for e in state["entries"] if e["task"].lower() == "weeding"]
        planning_ids = [e["id"] for e in state["entries"] if e["task"].lower() == "planning"]

        env = self.core.log_task_group("WEEDING")
        assert env["ok"] is True
        new_state = env["state"]

        for eid in weeding_ids:
            entry = [e for e in new_state["entries"] if e["id"] == eid][0]
            assert entry["loggedStatus"] == "Logged"

        # planning entries untouched
        for eid in planning_ids:
            entry = [e for e in new_state["entries"] if e["id"] == eid][0]
            if entry["isComplete"]:
                assert entry["loggedStatus"] == "Unlogged"
            else:
                assert entry["loggedStatus"] == "N/A"

        # weeding no longer offered
        groups = self.core.list_loggable_task_groups()
        assert all(g["task"] != "weeding" for g in groups)

    def test_log_task_group_with_running_entry(self):
        state = self._build_scenario()
        # entry4 is the running planning entry
        running_planning = [e for e in state["entries"] if e["task"].lower() == "planning" and not e["isComplete"]][0]
        completed_planning = [e for e in state["entries"] if e["task"].lower() == "planning" and e["isComplete"]][0]

        env = self.core.log_task_group("planning")
        assert env["ok"] is True
        new_state = env["state"]

        new_completed = [e for e in new_state["entries"] if e["id"] == completed_planning["id"]][0]
        assert new_completed["loggedStatus"] == "Logged"

        new_running = [e for e in new_state["entries"] if e["id"] == running_planning["id"]][0]
        assert new_running["loggedStatus"] == "N/A"
        assert new_running["endTime"] is None

    def test_log_task_group_nothing_to_log(self):
        self._build_scenario()

        env = self.core.log_task_group("nothing-here")
        assert env["ok"] is False
        assert env["error"] == "nothing_to_log"
        assert env["message"]

        env = self.core.log_task_group("unnamed")
        assert env["ok"] is False
        assert env["error"] == "nothing_to_log"
        assert env["message"]


class TestChecklistC(unittest.TestCase):
    """Deleting is reversible, restoring brings the entry back everywhere,
    and deleted entries survive a restart."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.clock = FrozenClock(at(8, 0, 0))
        self.core = TimeTrackerCore(self.tmpdir, clock=self.clock)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _build_entries(self):
        """
        entry1: "weeding" completed
        entry2: "weeding" completed
        entry3: "mowing" completed
        """
        env = self.core.start_session("Yard", "weeding")
        assert env["ok"]
        self.clock.advance(minutes=10)
        env = self.core.stop_and_start_entry("weeding")
        assert env["ok"]
        self.clock.advance(minutes=7)
        env = self.core.stop_and_start_entry("mowing")
        assert env["ok"]
        self.clock.advance(minutes=5)
        env = self.core.stop_tracking()
        assert env["ok"]
        return env["state"]

    def test_delete_disappears_everywhere(self):
        state = self._build_entries()
        # entries newest-first: [mowing, weeding2, weeding1]
        target_id = state["entries"][1]["id"]  # second weeding
        target_task = state["entries"][1]["task"]

        env = self.core.delete_entry(target_id)
        assert env["ok"]
        new_state = env["state"]

        # Gone from entries
        assert all(e["id"] != target_id for e in new_state["entries"])

        # Gone from summary count (weeding count should be 1 now)
        weeding_summary = [s for s in new_state["summary"] if s["task"] == "weeding"][0]
        assert weeding_summary["count"] == 1

        # Gone from loggable groups (if it was unlogged)
        groups = self.core.list_loggable_task_groups()
        weeding_group = [g for g in groups if g["task"] == "weeding"]
        if weeding_group:
            assert weeding_group[0]["unloggedCount"] == 1

    def test_list_deleted_entries_oldest_first(self):
        state = self._build_entries()
        # Delete two entries
        id1 = state["entries"][2]["id"]  # oldest weeding
        id2 = state["entries"][1]["id"]  # second weeding

        env = self.core.delete_entry(id1)
        assert env["ok"]
        env = self.core.delete_entry(id2)
        assert env["ok"]

        deleted = self.core.list_deleted_entries()
        assert len(deleted) == 2
        assert deleted[0]["id"] == id1
        assert deleted[1]["id"] == id2
        for d in deleted:
            assert "task" in d
            assert "startTime" in d
            assert "endTime" in d

    def test_restore_entry_reappears(self):
        state = self._build_entries()
        target_id = state["entries"][2]["id"]  # oldest
        target_task = state["entries"][2]["task"]

        env = self.core.delete_entry(target_id)
        assert env["ok"]
        assert all(e["id"] != target_id for e in env["state"]["entries"])

        env = self.core.restore_entry(target_id)
        assert env["ok"]
        new_state = env["state"]
        restored = [e for e in new_state["entries"] if e["id"] == target_id]
        assert len(restored) == 1
        assert restored[0]["task"] == target_task

        # Gone from deleted list
        deleted = self.core.list_deleted_entries()
        assert all(d["id"] != target_id for d in deleted)

    def test_deleted_entry_survives_restart(self):
        state = self._build_entries()
        session_id = state["session"]["id"]
        target_id = state["entries"][2]["id"]

        env = self.core.delete_entry(target_id)
        assert env["ok"]

        # Simulate restart: a new core on the same directory. A fresh core has no session open,
        # so the session must be resumed before its entries are visible again.
        self.clock2 = FrozenClock(at(12, 0, 0))
        core2 = TimeTrackerCore(self.tmpdir, clock=self.clock2)
        env = core2.resume_session(session_id)
        assert env["ok"] is True

        # Entry still hidden
        state2 = core2.get_state()
        assert all(e["id"] != target_id for e in state2["entries"])

        # Still in deleted list
        deleted = core2.list_deleted_entries()
        assert any(d["id"] == target_id for d in deleted)

        # Still restorable
        env = core2.restore_entry(target_id)
        assert env["ok"]
        state3 = env["state"]
        assert any(e["id"] == target_id for e in state3["entries"])


class TestChecklistD(unittest.TestCase):
    """Stop and exit records the session's end time and saves before closing."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.clock = FrozenClock(at(14, 0, 0))
        self.core = TimeTrackerCore(self.tmpdir, clock=self.clock)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_stop_and_exit_with_running_entry(self):
        env = self.core.start_session("Work", "coding")
        assert env["ok"]
        self.clock.advance(minutes=20)

        env = self.core.stop_and_exit()
        assert env["ok"] is True
        state = env["state"]

        # Live state is the null-session shape (contract v1.3 §2)
        assert state["session"] is None
        assert state["currentEntry"] is None
        assert state["entries"] == []
        assert state["summary"] == []
        assert state["totals"] == {"unloggedMinutes": 0, "totalMinutes": 0}

        # Disk: exactly one .json, no .tmp-
        files = os.listdir(self.tmpdir)
        json_files = [f for f in files if f.endswith(".json")]
        tmp_files = [f for f in files if f.startswith(".tmp-")]
        assert len(json_files) == 1
        assert len(tmp_files) == 0

        # Persistence is unchanged: endedAt set, the running entry stored completed
        doc = _read_storage_json_obj(self.tmpdir)
        assert doc["endedAt"] is not None
        entry = doc["entries"][0]
        assert entry["isComplete"] is True
        assert entry["endTime"] is not None

    def test_stop_and_exit_idempotent(self):
        env = self.core.start_session("S", "t")
        assert env["ok"]
        self.clock.advance(minutes=5)

        env1 = self.core.stop_and_exit()
        assert env1["ok"] is True

        # Second call: no exception, envelope comes back
        env2 = self.core.stop_and_exit()
        assert isinstance(env2, dict)
        assert "ok" in env2

    def test_closed_session_in_list_and_resume(self):
        env = self.core.start_session("Evening", "reading")
        assert env["ok"]
        session_id = env["state"]["session"]["id"]
        self.clock.advance(minutes=15)

        env = self.core.stop_and_exit()
        assert env["ok"]

        # Appears in list_sessions with isUnfinished False
        sessions = self.core.list_sessions()
        match = [s for s in sessions if s["id"] == session_id]
        assert len(match) == 1
        assert match[0]["isUnfinished"] is False

        # Resume reopens the session (session is not None) but starts no entry
        env = self.core.resume_session(session_id)
        assert env["ok"] is True
        state = env["state"]
        assert state["session"]["id"] == session_id
        assert state["session"] is not None
        assert state["currentEntry"] is None

        # endedAt cleared on disk
        doc = _read_storage_json_obj(self.tmpdir)
        assert doc["endedAt"] is None

        # tracking can be started again inside the resumed session
        self.clock.advance(minutes=5)
        env = self.core.stop_and_start_entry("more reading")
        assert env["ok"] is True
        assert env["state"]["session"] is not None
        assert env["state"]["currentEntry"]["task"] == "more reading"


class TestChecklistE(unittest.TestCase):
    """Loading repairs missing fields and duplicate ids consistently,
    and refuses unsupported versions with a reason."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write_doc(self, filename, content):
        path = os.path.join(self.tmpdir, filename)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(content)
        return path

    def test_newer_schema_version_refused(self):
        doc = {
            "schemaVersion": 99,
            "sessionId": "future-session",
            "name": "Future",
            "startedAt": "2026-09-23T10:00:00+00:00",
            "endedAt": None,
            "entries": []
        }
        path = self._write_doc("future.json", json.dumps(doc))
        with open(path, "rb") as fh:
            original_bytes = fh.read()

        clock = FrozenClock(at(10, 0, 0))
        core = TimeTrackerCore(self.tmpdir, clock=clock)

        # resume_session refused
        env = core.resume_session("future-session")
        assert env["ok"] is False
        assert env["error"] == "session_unreadable"
        assert "99" in env["message"] or "version" in env["message"].lower()

        # File unchanged
        with open(path, "rb") as fh:
            assert fh.read() == original_bytes

        # list_sessions shows it as unreadable
        sessions = core.list_sessions()
        unreadable = [s for s in sessions if s.get("isUnreadable")]
        assert len(unreadable) == 1
        assert unreadable[0]["reason"]

    def test_invalid_json_unreadable(self):
        path = self._write_doc("broken.json", "{not valid json at all")
        with open(path, "rb") as fh:
            original_bytes = fh.read()

        clock = FrozenClock(at(10, 0, 0))
        core = TimeTrackerCore(self.tmpdir, clock=clock)

        sessions = core.list_sessions()
        unreadable = [s for s in sessions if s.get("isUnreadable")]
        assert len(unreadable) == 1
        assert unreadable[0]["reason"]

        # File untouched
        with open(path, "rb") as fh:
            assert fh.read() == original_bytes

    def test_missing_name_gets_placeholder(self):
        doc = {
            "schemaVersion": 2,
            "sessionId": "no-name",
            "startedAt": "2026-09-23T10:00:00+00:00",
            "endedAt": None,
            "entries": []
        }
        self._write_doc("noname.json", json.dumps(doc))

        clock = FrozenClock(at(10, 0, 0))
        core = TimeTrackerCore(self.tmpdir, clock=clock)

        env = core.resume_session("no-name")
        assert env["ok"] is True
        assert env["state"]["session"]["name"]
        assert env["state"]["session"]["name"] != ""

    def test_missing_or_empty_entries(self):
        # No "entries" key at all
        doc = {
            "schemaVersion": 2,
            "sessionId": "empty-1",
            "name": "Empty",
            "startedAt": "2026-09-23T10:00:00+00:00",
            "endedAt": None
        }
        self._write_doc("empty1.json", json.dumps(doc))

        clock = FrozenClock(at(10, 0, 0))
        core = TimeTrackerCore(self.tmpdir, clock=clock)
        env = core.resume_session("empty-1")
        assert env["ok"] is True
        state = env["state"]
        assert state["entries"] == []
        assert state["summary"] == []
        assert state["totals"]["unloggedMinutes"] == 0
        assert state["totals"]["totalMinutes"] == 0

    def test_entry_missing_task_and_description(self):
        doc = {
            "schemaVersion": 2,
            "sessionId": "sparse",
            "name": "Sparse",
            "startedAt": "2026-09-23T10:00:00+00:00",
            "endedAt": None,
            "entries": [
                {"id": 1, "startTime": "2026-09-23T10:00:00+00:00",
                 "endTime": "2026-09-23T10:05:00+00:00",
                 "isComplete": True, "isDeleted": False, "logged": False}
            ]
        }
        self._write_doc("sparse.json", json.dumps(doc))

        clock = FrozenClock(at(10, 0, 0))
        core = TimeTrackerCore(self.tmpdir, clock=clock)
        env = core.resume_session("sparse")
        assert env["ok"] is True
        entry = env["state"]["entries"][0]
        assert entry["task"] == "unnamed"
        assert entry["description"] == ""

    def test_duplicate_ids_collapse_last_wins(self):
        doc = {
            "schemaVersion": 2,
            "sessionId": "dups",
            "name": "Dups",
            "startedAt": "2026-09-23T10:00:00+00:00",
            "endedAt": None,
            "entries": [
                {"id": 7, "startTime": "2026-09-23T10:00:00+00:00",
                 "endTime": "2026-09-23T10:05:00+00:00",
                 "task": "first", "description": "first desc",
                 "logged": False, "isComplete": True, "isDeleted": False},
                {"id": 7, "startTime": "2026-09-23T10:10:00+00:00",
                 "endTime": "2026-09-23T10:20:00+00:00",
                 "task": "second", "description": "second desc",
                 "logged": True, "isComplete": True, "isDeleted": False}
            ]
        }
        self._write_doc("dups.json", json.dumps(doc))

        clock = FrozenClock(at(10, 0, 0))
        core = TimeTrackerCore(self.tmpdir, clock=clock)
        env = core.resume_session("dups")
        assert env["ok"] is True
        entries = env["state"]["entries"]
        assert len(entries) == 1
        assert entries[0]["task"] == "second"
        assert entries[0]["description"] == "second desc"

    def test_entry_with_unusable_id_refuses_session(self):
        # Contract v1.1: a session document containing an entry whose id cannot be parsed is
        # refused whole — never loaded with that entry silently dropped (which would erase it
        # from disk on the next save), and never rewritten.
        doc = {
            "schemaVersion": 2,
            "sessionId": "mixed",
            "name": "Mixed",
            "startedAt": "2026-09-23T10:00:00+00:00",
            "endedAt": None,
            "entries": [
                {
                    "id": "not-an-id",
                    "startTime": "2026-09-23T10:00:00+00:00",
                    "endTime": "2026-09-23T10:05:00+00:00",
                    "task": "ghost",
                    "description": "",
                    "logged": False,
                    "isComplete": True,
                    "isDeleted": False,
                },
                {
                    "id": 1,
                    "startTime": "2026-09-23T10:00:00+00:00",
                    "endTime": "2026-09-23T10:05:00+00:00",
                    "task": "real",
                    "description": "",
                    "logged": False,
                    "isComplete": True,
                    "isDeleted": False,
                },
            ],
        }
        path = self._write_doc("mixed.json", json.dumps(doc))
        with open(path, "rb") as fh:
            before = fh.read()

        core = TimeTrackerCore(self.tmpdir, clock=FrozenClock(at(10, 0, 0)))
        env = core.resume_session("mixed")
        assert env["ok"] is False
        assert env["error"] == "session_unreadable"
        assert env["message"]
        assert "entry" in env["message"]

        # The document was left exactly as it was
        with open(path, "rb") as fh:
            after = fh.read()
        assert before == after

        # Still listed, never hidden, with a reason
        rows = core.list_sessions()
        assert len(rows) == 1
        assert rows[0]["id"] == "mixed"
        assert rows[0]["isUnreadable"] is True
        assert rows[0]["reason"]

        # Nothing was loaded
        assert core.get_state()["session"] is None

    def test_non_object_entry_refuses_session(self):
        doc = {
            "schemaVersion": 2,
            "sessionId": "badentry",
            "name": "BadEntry",
            "startedAt": "2026-09-23T10:00:00+00:00",
            "endedAt": None,
            "entries": [
                "oops",
                {
                    "id": 1,
                    "startTime": "2026-09-23T10:00:00+00:00",
                    "endTime": "2026-09-23T10:05:00+00:00",
                    "task": "real",
                    "description": "",
                    "logged": False,
                    "isComplete": True,
                    "isDeleted": False,
                },
            ],
        }
        path = self._write_doc("badentry.json", json.dumps(doc))
        with open(path, "rb") as fh:
            before = fh.read()

        core = TimeTrackerCore(self.tmpdir, clock=FrozenClock(at(10, 0, 0)))
        env = core.resume_session("badentry")
        assert env["ok"] is False
        assert env["error"] == "session_unreadable"

        with open(path, "rb") as fh:
            after = fh.read()
        assert before == after

    def test_older_schema_version_accepted(self):
        doc = {
            "schemaVersion": 1,
            "sessionId": "old",
            "name": "Old",
            "startedAt": "2026-09-23T10:00:00+00:00",
            "endedAt": None,
            "entries": [
                {"id": 1, "startTime": "2026-09-23T10:00:00+00:00",
                 "endTime": "2026-09-23T10:10:00+00:00",
                 "task": "legacy", "description": "",
                 "logged": False, "isComplete": True, "isDeleted": False}
            ]
        }
        self._write_doc("old.json", json.dumps(doc))

        clock = FrozenClock(at(10, 0, 0))
        core = TimeTrackerCore(self.tmpdir, clock=clock)
        env = core.resume_session("old")
        assert env["ok"] is True
        assert env["state"]["entries"][0]["task"] == "legacy"


class TestContractGuarantees(unittest.TestCase):
    """Contract note 7 guarantees plus the frozen constant."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.clock = FrozenClock(at(11, 0, 0))
        self.core = TimeTrackerCore(self.tmpdir, clock=self.clock)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_contract_version_and_unnamed_task(self):
        assert CONTRACT_VERSION == "v1.4"
        assert UNNAMED_TASK == "unnamed"

    def test_no_none_in_state_from_null_args(self):
        env = self.core.start_session(None, None)
        assert env["ok"] is True
        state_json = json.dumps(env["state"])
        assert "none" not in state_json.lower().replace("unnamed", "")
        # More precisely: the literal string "none" should not appear as a value
        # (it could appear inside "unnamed" which is fine)
        # Check that no field has the value "none"
        def _check_no_none(obj):
            if isinstance(obj, dict):
                for v in obj.values():
                    _check_no_none(v)
            elif isinstance(obj, list):
                for v in obj:
                    _check_no_none(v)
            elif isinstance(obj, str):
                assert obj != "none", f"Found 'none' in state: {obj}"
        _check_no_none(env["state"])

    def test_no_exception_crosses_boundary(self):
        self.core.start_session("S", "t")
        self.clock.advance(minutes=1)
        self.core.stop_tracking()

        # edit_entry with various bad ids
        for bad_id in ["string-id", 3.14, None]:
            env = self.core.edit_entry(bad_id, task="x", description=None, logged=None)
            assert isinstance(env, dict)
            assert isinstance(env["ok"], bool)
            if not env["ok"]:
                assert "error" in env
                assert "message" in env
                assert env["message"]

        # resume_session with bogus id
        env = self.core.resume_session("does-not-exist")
        assert isinstance(env, dict)
        assert isinstance(env["ok"], bool)
        if not env["ok"]:
            assert "error" in env
            assert "message" in env

        # log_task_group(None)
        env = self.core.log_task_group(None)
        assert isinstance(env, dict)
        assert isinstance(env["ok"], bool)
        if not env["ok"]:
            assert "error" in env
            assert "message" in env

        # restore_entry(999)
        env = self.core.restore_entry(999)
        assert isinstance(env, dict)
        assert isinstance(env["ok"], bool)
        if not env["ok"]:
            assert "error" in env
            assert "message" in env

    def test_unwritable_storage_path_internal_error(self):
        # Create a file, then use a path under it as storage dir
        blocker = os.path.join(self.tmpdir, "blocker")
        with open(blocker, "w") as fh:
            fh.write("x")
        bad_path = os.path.join(blocker, "subdir")

        clock = FrozenClock(at(11, 0, 0))
        try:
            core = TimeTrackerCore(bad_path, clock=clock)
        except Exception:
            # If __init__ raises, that violates the contract
            self.fail("TimeTrackerCore.__init__ raised on unwritable path")

        env = core.start_session("S", "t")
        assert isinstance(env, dict)
        assert env["ok"] is False
        assert env["error"] == "internal_error"
        assert env["message"]

    def test_timestamp_format_on_disk(self):
        env = self.core.start_session("TS", "task")
        assert env["ok"]
        self.clock.advance(minutes=3)
        env = self.core.stop_tracking()
        assert env["ok"]

        doc_str = _read_storage_json(self.tmpdir)
        doc = json.loads(doc_str)

        # Check all timestamp fields
        ts_fields = [doc["startedAt"]]
        if doc.get("endedAt"):
            ts_fields.append(doc["endedAt"])
        for entry in doc["entries"]:
            ts_fields.append(entry["startTime"])
            if entry.get("endTime"):
                ts_fields.append(entry["endTime"])

        for ts in ts_fields:
            assert ts is not None
            assert ts.endswith("+00:00"), f"Timestamp {ts} does not end with +00:00"
            assert "." not in ts, f"Timestamp {ts} has fractional seconds"

    def test_atomicity_continuity_no_tmp(self):
        env = self.core.start_session("Atom", "a")
        assert env["ok"]
        _assert_no_tmp_files(self.tmpdir)
        # Disk reflects the start
        doc = _read_storage_json_obj(self.tmpdir)
        assert doc["name"] == "Atom"

        self.clock.advance(minutes=2)
        env = self.core.stop_and_start_entry("b")
        assert env["ok"]
        _assert_no_tmp_files(self.tmpdir)
        doc = _read_storage_json_obj(self.tmpdir)
        assert len(doc["entries"]) == 2

        self.clock.advance(minutes=3)
        env = self.core.stop_tracking()
        assert env["ok"]
        _assert_no_tmp_files(self.tmpdir)
        doc = _read_storage_json_obj(self.tmpdir)
        assert doc["entries"][0]["isComplete"] is True


class TestConcurrency(unittest.TestCase):
    """The core must not assume a single calling thread."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.clock = FrozenClock(at(16, 0, 0))
        self.core = TimeTrackerCore(self.tmpdir, clock=self.clock)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_eight_threads_no_corruption(self):
        env = self.core.start_session("Conc", "init")
        assert env["ok"]

        errors = []
        barrier = threading.Barrier(8)

        def worker(n):
            try:
                barrier.wait(timeout=5)
                for i in range(3):
                    self.clock.advance(seconds=1)
                    env = self.core.stop_and_start_entry(f"task-{n}-{i}")
                    if not env.get("ok"):
                        errors.append(f"thread {n} iter {i}: {env}")
                    _ = self.core.get_state()
            except Exception as exc:
                errors.append(f"thread {n}: {exc!r}")

        threads = [threading.Thread(target=worker, args=(n,)) for n in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        assert not errors, f"Thread errors: {errors}"

        # Document is valid JSON
        doc_str = _read_storage_json(self.tmpdir)
        doc = json.loads(doc_str)

        # All entry ids unique
        ids = [e["id"] for e in doc["entries"]]
        assert len(ids) == len(set(ids)), f"Duplicate entry ids: {ids}"

        # No .tmp- files
        _assert_no_tmp_files(self.tmpdir)


if __name__ == "__main__":
    unittest.main()

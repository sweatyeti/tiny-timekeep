import os
import sys
import json
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from timetracker_core import CONTRACT_VERSION, UNNAMED_TASK, TimeTrackerCore  # noqa: E402


class FrozenClock:
    def __init__(self, moment):
        self._moment = moment

    def __call__(self):
        return self._moment

    def set(self, moment):
        self._moment = moment

    def advance(self, **kwargs):
        self._moment = self._moment + timedelta(**kwargs)


def at(hour, minute, second=0):
    return datetime(2026, 9, 23, hour, minute, second, tzinfo=timezone.utc)


def _read_storage_json_obj(storage_dir):
    files = [f for f in os.listdir(storage_dir) if f.endswith(".json")]
    assert len(files) == 1, f"Expected exactly one .json file, got {files}"
    with open(os.path.join(storage_dir, files[0]), "r") as fh:
        return json.loads(fh.read())


class TestNoSessionState(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self.clock = FrozenClock(at(9, 0, 0))
        self.core = TimeTrackerCore(self._tmpdir, clock=self.clock)

    def tearDown(self):
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_empty_state_before_any_session(self):
        state = self.core.get_state()
        assert state["session"] is None
        assert state["currentEntry"] is None
        assert state["entries"] == []
        assert state["summary"] == []
        assert state["totals"] == {"unloggedMinutes": 0, "totalMinutes": 0}
        assert self.core.list_sessions() == []
        assert self.core.list_loggable_task_groups() == []
        assert self.core.list_deleted_entries() == []

    def test_reserved_code_no_active_session_without_any_session(self):
        calls = [
            lambda: self.core.stop_and_start_entry("x"),
            lambda: self.core.edit_entry(1, None, None, None),
            lambda: self.core.delete_entry(1),
            lambda: self.core.restore_entry(1),
            lambda: self.core.log_task_group("x"),
        ]
        for fn in calls:
            result = fn()
            assert result["ok"] is False
            assert result["error"] == "no_active_session"
            assert result["message"]

    def test_no_active_session_after_stop_and_exit(self):
        self.core.start_session("S", "task")
        self.clock.advance(minutes=5)
        result = self.core.stop_and_exit()
        assert result["ok"] is True

        calls = [
            lambda: self.core.stop_and_start_entry("x"),
            lambda: self.core.edit_entry(1, None, None, None),
            lambda: self.core.delete_entry(1),
            lambda: self.core.restore_entry(1),
            lambda: self.core.log_task_group("x"),
        ]
        for fn in calls:
            result = fn()
            assert result["ok"] is False
            assert result["error"] == "no_active_session"

        assert self.core.stop_tracking()["ok"] is True
        assert self.core.stop_and_exit()["ok"] is True

        state = self.core.get_state()
        assert state["session"] is None
        assert state["currentEntry"] is None
        assert state["entries"] == []
        assert state["summary"] == []
        assert state["totals"] == {"unloggedMinutes": 0, "totalMinutes": 0}

    def test_stop_tracking_keeps_session_open_and_resumable(self):
        self.core.start_session("S", "task")
        self.clock.advance(minutes=10)
        result = self.core.stop_tracking()
        assert result["ok"] is True

        state = self.core.get_state()
        assert state["currentEntry"] is None
        assert state["session"] is not None
        assert len(state["entries"]) == 1
        assert state["entries"][0]["isComplete"] is True

        session_id = state["session"]["id"]
        core2 = TimeTrackerCore(self._tmpdir, clock=self.clock)
        result2 = core2.resume_session(session_id)
        assert result2["ok"] is True
        sessions = core2.list_sessions()
        assert len(sessions) == 1


class TestCommandsSaveImmediately(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self.clock = FrozenClock(at(9, 0, 0))
        self.core = TimeTrackerCore(self._tmpdir, clock=self.clock)

    def tearDown(self):
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _assert_no_tmp_files(self):
        for f in os.listdir(self._tmpdir):
            assert not f.startswith(".tmp-"), f"Leftover temp file: {f}"

    def test_each_command_is_persisted(self):
        # start_session
        self.core.start_session("Cont", "alpha")
        doc = _read_storage_json_obj(self._tmpdir)
        assert len(doc["entries"]) == 1
        assert doc["name"] == "Cont"
        assert doc["endedAt"] is None
        self._assert_no_tmp_files()

        # stop_and_start_entry
        self.clock.advance(minutes=5)
        self.core.stop_and_start_entry("beta")
        doc = _read_storage_json_obj(self._tmpdir)
        assert len(doc["entries"]) == 2
        entry1 = [e for e in doc["entries"] if e["id"] == 1][0]
        assert entry1["isComplete"] is True
        assert entry1["endTime"] is not None
        self._assert_no_tmp_files()

        # edit_entry
        result = self.core.edit_entry(1, task="renamed", description="note", logged=True)
        assert result["ok"] is True
        doc = _read_storage_json_obj(self._tmpdir)
        entry1 = [e for e in doc["entries"] if e["id"] == 1][0]
        assert entry1["task"] == "renamed"
        assert entry1["description"] == "note"
        assert entry1["logged"] is True
        state = result["state"]
        e1_view = [e for e in state["entries"] if e["id"] == 1][0]
        assert e1_view["loggedStatus"] == "Logged"
        self._assert_no_tmp_files()

        # delete_entry
        result = self.core.delete_entry(1)
        assert result["ok"] is True
        doc = _read_storage_json_obj(self._tmpdir)
        entry1 = [e for e in doc["entries"] if e["id"] == 1][0]
        assert entry1["isDeleted"] is True
        state = result["state"]
        assert 1 not in [e["id"] for e in state["entries"]]
        deleted = self.core.list_deleted_entries()
        assert any(e["id"] == 1 for e in deleted)
        self._assert_no_tmp_files()

        # restore_entry
        result = self.core.restore_entry(1)
        assert result["ok"] is True
        doc = _read_storage_json_obj(self._tmpdir)
        entry1 = [e for e in doc["entries"] if e["id"] == 1][0]
        assert entry1["isDeleted"] is False
        state = result["state"]
        assert 1 in [e["id"] for e in state["entries"]]
        self._assert_no_tmp_files()


class TestEntryViewCompleteness(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self.clock = FrozenClock(at(9, 0, 0))
        self.core = TimeTrackerCore(self._tmpdir, clock=self.clock)

    def tearDown(self):
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_entry_fields_and_running_entry(self):
        self.core.start_session("V", "alpha")
        self.clock.advance(minutes=5)
        self.core.stop_and_start_entry("beta")

        state = self.core.get_state()
        entries = state["entries"]
        assert len(entries) == 2
        assert [e["id"] for e in entries] == [2, 1]

        expected_keys = {"id", "task", "description", "startTime", "endTime", "isComplete", "loggedStatus"}
        for entry in entries:
            assert set(entry.keys()) == expected_keys

        # Running entry (id 2, "beta")
        running = entries[0]
        assert running["id"] == 2
        assert running["endTime"] is None
        assert running["isComplete"] is False
        assert running["loggedStatus"] == "N/A"

        # Completed entry (id 1, "alpha")
        completed = entries[1]
        assert completed["id"] == 1
        assert completed["isComplete"] is True
        assert completed["endTime"] is not None
        assert completed["loggedStatus"] == "Unlogged"

    def test_deleted_entry_leaves_the_entry_view_only(self):
        self.core.start_session("V", "alpha")
        self.clock.advance(minutes=5)
        self.core.stop_and_start_entry("beta")
        self.clock.advance(minutes=3)
        self.core.stop_tracking()

        state = self.core.get_state()
        assert len(state["entries"]) == 2

        self.core.delete_entry(1)
        state = self.core.get_state()
        assert 1 not in [e["id"] for e in state["entries"]]

        deleted = self.core.list_deleted_entries()
        assert len(deleted) == 1
        assert deleted[0]["id"] == 1
        assert set(deleted[0].keys()) == {"id", "task", "startTime", "endTime", "description"}

        # A task only appears in the summary while it has completed, non-deleted entries:
        # alpha's single entry is deleted, so the row is gone and its minutes leave the totals.
        assert [s["task"] for s in state["summary"]] == ["beta"]
        beta_row = state["summary"][0]
        assert beta_row["count"] == 1
        assert beta_row["unloggedMinutes"] == 3
        assert beta_row["totalMinutes"] == 3
        assert beta_row["callout"] is True
        assert state["totals"] == {"unloggedMinutes": 3, "totalMinutes": 3}


class TestContractConstant(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self.clock = FrozenClock(at(9, 0, 0))
        self.core = TimeTrackerCore(self._tmpdir, clock=self.clock)

    def tearDown(self):
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_contract_version_is_v12(self):
        assert CONTRACT_VERSION == "v1.4"

    def test_unnamed_placeholder_is_never_none(self):
        self.core.start_session(None, None)
        state = self.core.get_state()

        def walk_strings(obj):
            if isinstance(obj, str):
                yield obj
            elif isinstance(obj, dict):
                for v in obj.values():
                    yield from walk_strings(v)
            elif isinstance(obj, (list, tuple)):
                for item in obj:
                    yield from walk_strings(item)

        for s in walk_strings(state):
            assert s != "none", f"Found 'none' string in state: {s}"

        entries = state["entries"]
        assert entries[0]["task"] == "unnamed"
        assert entries[0]["task"] == UNNAMED_TASK


if __name__ == "__main__":
    unittest.main()
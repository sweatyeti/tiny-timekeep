"""Pins the v1.2 session-state rules for the time-tracking core."""

import os
import sys
import json
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from timetracker_core import CONTRACT_VERSION, TimeTrackerCore  # noqa: E402


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


class TestSessionKeySet(unittest.TestCase):
    """A: session object has exactly {id, name, startedAt} and no isActive."""

    def setUp(self):
        self._dir = tempfile.mkdtemp()
        self.clock = FrozenClock(at(9, 0, 0))
        self.core = TimeTrackerCore(self._dir, clock=self.clock)

    def tearDown(self):
        shutil.rmtree(self._dir, ignore_errors=True)

    def test_session_object_exact_keys(self):
        result = self.core.start_session("My Session", "first task")
        self.assertTrue(result["ok"])
        session = result["state"]["session"]
        self.assertIsNotNone(session)
        self.assertEqual(set(session.keys()), {"id", "name", "startedAt"})
        self.assertNotIn("isActive", session)


class TestNoIsActiveAnywhere(unittest.TestCase):
    """B: no dict in the entire view model contains an 'isActive' key."""

    def setUp(self):
        self._dir = tempfile.mkdtemp()
        self.clock = FrozenClock(at(9, 0, 0))
        self.core = TimeTrackerCore(self._dir, clock=self.clock)

    def tearDown(self):
        shutil.rmtree(self._dir, ignore_errors=True)

    def test_no_isActive_key_in_view_model(self):
        result = self.core.start_session("S", "task")
        self.assertTrue(result["ok"])
        state = result["state"]

        def walk(obj, path="root"):
            if isinstance(obj, dict):
                self.assertNotIn(
                    "isActive", obj, f"'isActive' found at {path}"
                )
                for k, v in obj.items():
                    walk(v, f"{path}.{k}")
            elif isinstance(obj, list):
                for i, v in enumerate(obj):
                    walk(v, f"{path}[{i}]")

        walk(state)

        serialized = json.dumps(state)
        self.assertNotIn("isActive", serialized)


class TestStopAndExitNullShape(unittest.TestCase):
    """C: stop_and_exit returns null-session shape; get_state agrees."""

    def setUp(self):
        self._dir = tempfile.mkdtemp()
        self.clock = FrozenClock(at(9, 0, 0))
        self.core = TimeTrackerCore(self._dir, clock=self.clock)

    def tearDown(self):
        shutil.rmtree(self._dir, ignore_errors=True)

    def test_stop_and_exit_null_session_shape(self):
        self.core.start_session("S", "task")
        result = self.core.stop_and_exit()
        self.assertTrue(result["ok"])
        state = result["state"]
        self.assertIsNone(state["session"])
        self.assertIsNone(state["currentEntry"])
        self.assertEqual(state["entries"], [])
        self.assertEqual(state["summary"], [])
        self.assertEqual(state["totals"], {"unloggedMinutes": 0, "totalMinutes": 0})

        live = self.core.get_state()
        self.assertIsNone(live["session"])
        self.assertIsNone(live["currentEntry"])
        self.assertEqual(live["entries"], [])
        self.assertEqual(live["summary"], [])
        self.assertEqual(live["totals"], {"unloggedMinutes": 0, "totalMinutes": 0})


class TestStopAndExitPersistenceAndResume(unittest.TestCase):
    """D: full flow - stop_and_exit preserves disk, resume reopens, entry id continues."""

    def setUp(self):
        self._dir = tempfile.mkdtemp()
        self.clock = FrozenClock(at(9, 0, 0))
        self.core = TimeTrackerCore(self._dir, clock=self.clock)

    def tearDown(self):
        shutil.rmtree(self._dir, ignore_errors=True)

    def test_full_flow(self):
        # Start session with first task (creates entry id 1)
        result = self.core.start_session("Work", "first task")
        self.assertTrue(result["ok"])
        session_id = result["state"]["session"]["id"]

        # Advance the clock so the entry has duration
        self.clock.advance(minutes=30)

        # Stop and exit
        result = self.core.stop_and_exit()
        self.assertTrue(result["ok"])

        # --- Live state is null ---
        live = self.core.get_state()
        self.assertIsNone(live["session"])
        self.assertIsNone(live["currentEntry"])
        self.assertEqual(live["entries"], [])
        self.assertEqual(live["summary"], [])
        self.assertEqual(live["totals"], {"unloggedMinutes": 0, "totalMinutes": 0})

        # --- Disk document unchanged: endedAt set, entry complete ---
        disk = _read_storage_json_obj(self._dir)
        self.assertIsNotNone(disk["endedAt"])
        entries_on_disk = disk["entries"]
        self.assertEqual(len(entries_on_disk), 1)
        self.assertIsNotNone(entries_on_disk[0]["endTime"])
        self.assertTrue(entries_on_disk[0]["isComplete"])

        # --- list_sessions: one row, finished ---
        sessions = self.core.list_sessions()
        self.assertEqual(len(sessions), 1)
        row = sessions[0]
        self.assertEqual(row["id"], session_id)
        self.assertFalse(row["isUnfinished"])
        self.assertIsNotNone(row["endedAt"])

        # --- Resume the session ---
        result = self.core.resume_session(session_id)
        self.assertTrue(result["ok"])
        state = result["state"]
        self.assertEqual(state["session"]["id"], session_id)
        self.assertEqual(set(state["session"].keys()), {"id", "name", "startedAt"})
        self.assertIsNone(state["currentEntry"])
        self.assertEqual(len(state["entries"]), 1)
        self.assertIsNotNone(state["entries"][0]["endTime"])

        # Disk endedAt cleared after resume
        disk2 = _read_storage_json_obj(self._dir)
        self.assertIsNone(disk2["endedAt"])

        # --- Start a new entry in the reopened session ---
        result = self.core.stop_and_start_entry("more work")
        self.assertTrue(result["ok"])
        state = result["state"]
        self.assertEqual(state["session"]["id"], session_id)
        self.assertIsNotNone(state["currentEntry"])
        self.assertEqual(state["currentEntry"]["task"], "more work")
        self.assertEqual(state["currentEntry"]["id"], 2)


class TestContractVersion(unittest.TestCase):
    """E: CONTRACT_VERSION is exactly 'v1.4'."""

    def test_contract_version(self):
        self.assertEqual(CONTRACT_VERSION, "v1.4")
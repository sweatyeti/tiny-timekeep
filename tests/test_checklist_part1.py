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


def at(hour, minute, second=0):
    return datetime(2026, 9, 23, hour, minute, second, tzinfo=timezone.utc)


class FrozenClock:
    def __init__(self, start: datetime) -> None:
        self._moment = start

    def __call__(self) -> datetime:
        return self._moment

    def set(self, moment: datetime) -> None:
        self._moment = moment

    def advance(self, **kwargs) -> None:
        self._moment = self._moment + timedelta(**kwargs)


class TestGoldenFixture(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.clock = FrozenClock(at(9, 0, 0))
        self.core = TimeTrackerCore(self.tmpdir, clock=self.clock)

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_golden_scenario(self):
        # 09:00 start session
        env = self.core.start_session("Garden work", "weeding")
        self.assertTrue(env["ok"])

        # 09:45 stop entry 1, start entry 2
        self.clock.set(at(9, 45, 0))
        env = self.core.stop_and_start_entry("weeding")
        self.assertTrue(env["ok"])
        env = self.core.edit_entry(1, None, "front bed", True)
        self.assertTrue(env["ok"])

        # 10:15 stop entry 2, start entry 3 (unnamed)
        self.clock.set(at(10, 15, 0))
        env = self.core.stop_and_start_entry(None)
        self.assertTrue(env["ok"])
        env = self.core.edit_entry(2, None, "back bed", None)
        self.assertTrue(env["ok"])

        # 10:30 stop entry 3, start entry 4 (planning)
        self.clock.set(at(10, 30, 0))
        env = self.core.stop_and_start_entry("planning")
        self.assertTrue(env["ok"])
        env = self.core.edit_entry(4, None, "weekly review", None)
        self.assertTrue(env["ok"])

        state = self.core.get_state()

        # --- entries ---
        entries = state["entries"]
        self.assertEqual([e["id"] for e in entries], [4, 3, 2, 1])

        e4 = entries[0]
        self.assertEqual(e4["task"], "planning")
        self.assertEqual(e4["description"], "weekly review")
        self.assertIsNone(e4["endTime"])
        self.assertFalse(e4["isComplete"])
        self.assertEqual(e4["loggedStatus"], "N/A")
        self.assertEqual(e4["startTime"], "2026-09-23T10:30:00+00:00")

        e3 = entries[1]
        self.assertEqual(e3["task"], "unnamed")
        self.assertEqual(e3["description"], "")
        self.assertEqual(e3["loggedStatus"], "N/A")
        self.assertEqual(e3["startTime"], "2026-09-23T10:15:00+00:00")
        self.assertEqual(e3["endTime"], "2026-09-23T10:30:00+00:00")
        self.assertTrue(e3["isComplete"])

        e2 = entries[2]
        self.assertEqual(e2["task"], "weeding")
        self.assertEqual(e2["description"], "back bed")
        self.assertEqual(e2["loggedStatus"], "Unlogged")
        self.assertEqual(e2["startTime"], "2026-09-23T09:45:00+00:00")
        self.assertEqual(e2["endTime"], "2026-09-23T10:15:00+00:00")
        self.assertTrue(e2["isComplete"])

        e1 = entries[3]
        self.assertEqual(e1["task"], "weeding")
        self.assertEqual(e1["description"], "front bed")
        self.assertEqual(e1["loggedStatus"], "Logged")
        self.assertEqual(e1["startTime"], "2026-09-23T09:00:00+00:00")
        self.assertEqual(e1["endTime"], "2026-09-23T09:45:00+00:00")
        self.assertTrue(e1["isComplete"])

        # --- summary ---
        expected_summary = [
            {"task": "weeding", "count": 2, "unloggedMinutes": 30, "totalMinutes": 75, "callout": True},
            {"task": "unnamed", "count": 1, "unloggedMinutes": 15, "totalMinutes": 15, "callout": False},
        ]
        self.assertEqual(state["summary"], expected_summary)

        # --- totals ---
        self.assertEqual(state["totals"], {"unloggedMinutes": 30, "totalMinutes": 75})

        # --- currentEntry ---
        self.assertEqual(
            state["currentEntry"],
            {"id": 4, "task": "planning", "startTime": "2026-09-23T10:30:00+00:00"},
        )

        # --- session ---
        self.assertIsNotNone(state["session"])

        # --- document on disk ---
        json_files = [f for f in os.listdir(self.tmpdir) if f.endswith(".json")]
        self.assertEqual(len(json_files), 1)
        with open(os.path.join(self.tmpdir, json_files[0]), "r") as fh:
            doc = json.load(fh)
        self.assertEqual(doc["schemaVersion"], 2)
        self.assertEqual(len(doc["entries"]), 4)

        tmp_files = [f for f in os.listdir(self.tmpdir) if f.startswith(".tmp-")]
        self.assertEqual(tmp_files, [])


class TestNewSession(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.clock = FrozenClock(at(9, 0, 0))
        self.core = TimeTrackerCore(self.tmpdir, clock=self.clock)

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_start_with_none_generates_name_and_unnamed_entry(self):
        env = self.core.start_session(None, None)
        self.assertTrue(env["ok"])
        state = env["state"]

        self.assertIsNotNone(state["session"])
        self.assertTrue(len(state["session"]["name"]) > 0)
        self.assertIsNotNone(state["session"])

        self.assertEqual(len(state["entries"]), 1)
        entry = state["entries"][0]
        self.assertEqual(entry["task"], "unnamed")
        self.assertIsNone(entry["endTime"])
        self.assertFalse(entry["isComplete"])

        self.assertEqual(state["currentEntry"]["id"], entry["id"])
        self.assertEqual(state["currentEntry"]["task"], "unnamed")

    def test_start_with_empty_strings_behaves_same(self):
        env = self.core.start_session("", "")
        self.assertTrue(env["ok"])
        state = env["state"]

        self.assertIsNotNone(state["session"])
        self.assertTrue(len(state["session"]["name"]) > 0)
        self.assertIsNotNone(state["session"])

        self.assertEqual(len(state["entries"]), 1)
        entry = state["entries"][0]
        self.assertEqual(entry["task"], "unnamed")
        self.assertIsNone(entry["endTime"])
        self.assertFalse(entry["isComplete"])

    def test_two_sessions_same_second_no_collision(self):
        env1 = self.core.start_session("First", "task_a")
        self.assertTrue(env1["ok"])
        env2 = self.core.start_session("Second", "task_b")
        self.assertTrue(env2["ok"])

        sessions = self.core.list_sessions()
        self.assertEqual(len(sessions), 2)
        ids = {s["id"] for s in sessions}
        self.assertEqual(len(ids), 2)
        for s in sessions:
            self.assertFalse(s["isUnreadable"])


class TestResumeSessions(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.clock = FrozenClock(at(9, 0, 0))
        self.core = TimeTrackerCore(self.tmpdir, clock=self.clock)

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_resume_and_ordering(self):
        # Session A: 09:00 - 09:30
        env = self.core.start_session("Session A", "work")
        self.assertTrue(env["ok"])
        id_a = env["state"]["session"]["id"]
        self.clock.set(at(9, 30, 0))
        env = self.core.stop_and_exit()
        self.assertTrue(env["ok"])

        # Session B: 10:00, left open
        self.clock.set(at(10, 0, 0))
        env = self.core.start_session("Session B", "more work")
        self.assertTrue(env["ok"])
        id_b = env["state"]["session"]["id"]

        sessions = self.core.list_sessions()
        self.assertEqual(len(sessions), 2)
        self.assertEqual(sessions[0]["id"], id_b)
        self.assertEqual(sessions[1]["id"], id_a)

        row_a = sessions[1]
        self.assertEqual(row_a["name"], "Session A")
        self.assertIsNotNone(row_a["endedAt"])
        self.assertFalse(row_a["isUnfinished"])

        row_b = sessions[0]
        self.assertEqual(row_b["name"], "Session B")
        self.assertIsNone(row_b["endedAt"])
        self.assertTrue(row_b["isUnfinished"])

        # Resume B
        env = self.core.resume_session(id_b)
        self.assertTrue(env["ok"])
        state = env["state"]
        self.assertIsNotNone(state["session"])

        # Verify endedAt cleared on disk
        json_files = [f for f in os.listdir(self.tmpdir) if f.endswith(".json")]
        found_b = False
        for jf in json_files:
            with open(os.path.join(self.tmpdir, jf), "r") as fh:
                doc = json.load(fh)
            if doc.get("sessionId") == id_b:
                found_b = True
                self.assertIsNone(doc.get("endedAt"))
        self.assertTrue(found_b)

        # New entry after resume keeps id sequence and same document count
        json_count_before = len(json_files)
        self.clock.set(at(10, 5, 0))
        env = self.core.stop_and_start_entry("continued")
        self.assertTrue(env["ok"])
        new_entry_id = env["state"]["currentEntry"]["id"]
        self.assertGreater(new_entry_id, 1)  # id sequence continues

        json_files_after = [f for f in os.listdir(self.tmpdir) if f.endswith(".json")]
        self.assertEqual(len(json_files_after), json_count_before)


class TestSummaryGrouping(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.clock = FrozenClock(at(9, 0, 0))
        self.core = TimeTrackerCore(self.tmpdir, clock=self.clock)

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_case_insensitive_grouping_and_rounding(self):
        # Entry 1: "Weeding" 30s -> 1 min
        env = self.core.start_session("Test", "Weeding")
        self.assertTrue(env["ok"])
        self.clock.advance(seconds=30)
        env = self.core.stop_and_start_entry("weeding")
        self.assertTrue(env["ok"])

        # Entry 2: "weeding" 30 min
        self.clock.advance(minutes=30)
        env = self.core.stop_and_start_entry("WEEDING")
        self.assertTrue(env["ok"])

        # Entry 3: "WEEDING" 1s -> 1 min
        self.clock.advance(seconds=1)
        env = self.core.stop_and_start_entry(None)
        self.assertTrue(env["ok"])

        # Log entries 1 and 3, leave 2 unlogged
        env = self.core.edit_entry(1, None, None, True)
        self.assertTrue(env["ok"])
        env = self.core.edit_entry(3, None, None, True)
        self.assertTrue(env["ok"])

        state = self.core.get_state()
        summary = state["summary"]

        # Exactly one weeding row, first-recorded spelling
        weeding_rows = [s for s in summary if s["task"].lower() == "weeding"]
        self.assertEqual(len(weeding_rows), 1)
        w = weeding_rows[0]
        self.assertEqual(w["task"], "Weeding")
        self.assertEqual(w["count"], 3)
        self.assertEqual(w["unloggedMinutes"], 30)
        self.assertEqual(w["totalMinutes"], 32)
        self.assertTrue(w["callout"])

        # Running entry (id 4, unnamed) not counted
        self.assertEqual(w["count"], 3)

        # Delete entry 1 -> count drops by 1, minutes leave totals
        env = self.core.delete_entry(1)
        self.assertTrue(env["ok"])
        state = self.core.get_state()
        weeding_rows = [s for s in state["summary"] if s["task"].lower() == "weeding"]
        self.assertEqual(weeding_rows[0]["count"], 2)
        self.assertEqual(weeding_rows[0]["totalMinutes"], 31)

        # Stop the running unnamed entry to make it completed
        self.clock.advance(minutes=5)
        env = self.core.stop_tracking()
        self.assertTrue(env["ok"])
        state = self.core.get_state()

        unnamed_rows = [s for s in state["summary"] if s["task"] == "unnamed"]
        self.assertEqual(len(unnamed_rows), 1)
        self.assertEqual(unnamed_rows[0]["count"], 1)
        self.assertEqual(unnamed_rows[0]["totalMinutes"], 5)

        # Totals exclude unnamed
        self.assertEqual(state["totals"]["totalMinutes"], 31)
        self.assertEqual(state["totals"]["unloggedMinutes"], 30)


class TestCalloutRules(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.clock = FrozenClock(at(9, 0, 0))
        self.core = TimeTrackerCore(self.tmpdir, clock=self.clock)

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_callout_named_all_logged_false(self):
        env = self.core.start_session("T", "coding")
        self.assertTrue(env["ok"])
        self.clock.advance(minutes=1)
        env = self.core.stop_and_start_entry("coding")
        self.assertTrue(env["ok"])
        self.clock.advance(minutes=1)
        env = self.core.stop_tracking()
        self.assertTrue(env["ok"])

        self.core.edit_entry(1, None, None, True)
        self.core.edit_entry(2, None, None, True)

        state = self.core.get_state()
        coding = [s for s in state["summary"] if s["task"] == "coding"][0]
        self.assertFalse(coding["callout"])
        self.assertEqual(coding["unloggedMinutes"], 0)

    def test_callout_named_one_second_unlogged_true(self):
        env = self.core.start_session("T", "coding")
        self.assertTrue(env["ok"])
        self.clock.advance(minutes=1)
        env = self.core.stop_and_start_entry("coding")
        self.assertTrue(env["ok"])
        self.clock.advance(seconds=1)
        env = self.core.stop_tracking()
        self.assertTrue(env["ok"])

        self.core.edit_entry(1, None, None, True)
        # Entry 2 stays unlogged (1s -> 1 min)

        state = self.core.get_state()
        coding = [s for s in state["summary"] if s["task"] == "coding"][0]
        self.assertTrue(coding["callout"])
        self.assertEqual(coding["unloggedMinutes"], 1)

    def test_callout_unnamed_always_false(self):
        env = self.core.start_session("T", "coding")
        self.assertTrue(env["ok"])
        self.clock.advance(minutes=1)
        env = self.core.stop_and_start_entry(None)
        self.assertTrue(env["ok"])
        self.clock.advance(minutes=5)
        env = self.core.stop_tracking()
        self.assertTrue(env["ok"])

        self.core.edit_entry(1, None, None, True)
        # Entry 2 (unnamed, 5 min) is unlogged

        state = self.core.get_state()
        unnamed = [s for s in state["summary"] if s["task"] == "unnamed"][0]
        self.assertFalse(unnamed["callout"])
        self.assertEqual(unnamed["unloggedMinutes"], 5)


class TestActiveInactive(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.clock = FrozenClock(at(9, 0, 0))
        self.core = TimeTrackerCore(self.tmpdir, clock=self.clock)

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_active_follows_tracking(self):
        # After start_session: session is open and an entry is running
        env = self.core.start_session("T", "task")
        self.assertTrue(env["ok"])
        state = env["state"]
        self.assertIsNotNone(state["session"])
        self.assertIsNotNone(state["currentEntry"])

        # stop_tracking: no current entry, but the session stays open (session is not None, v1.3)
        self.clock.advance(minutes=10)
        env = self.core.stop_tracking()
        self.assertTrue(env["ok"])
        state = env["state"]
        self.assertIsNone(state["currentEntry"])
        self.assertIsNotNone(state["session"])
        self.assertIsNotNone(state["session"])
        # Session stays open (resumable) — endedAt is null
        sessions = self.core.list_sessions()
        self.assertEqual(len(sessions), 1)
        self.assertIsNone(sessions[0]["endedAt"])
        self.assertTrue(sessions[0]["isUnfinished"])

        # stop_and_start_entry: an entry is running again
        env = self.core.stop_and_start_entry("x")
        self.assertTrue(env["ok"])
        state = env["state"]
        self.assertIsNotNone(state["session"])
        self.assertIsNotNone(state["currentEntry"])
        self.assertEqual(state["currentEntry"]["task"], "x")

    def test_session_is_null_after_stop_and_exit(self):
        env = self.core.start_session("T", "task")
        self.assertTrue(env["ok"])

        env = self.core.stop_and_exit()
        self.assertTrue(env["ok"])
        state = env["state"]
        self.assertIsNone(state["session"])
        self.assertIsNone(state["currentEntry"])
        self.assertEqual(state["entries"], [])
        self.assertEqual(state["summary"], [])
        self.assertEqual(state["totals"], {"unloggedMinutes": 0, "totalMinutes": 0})

        # stop_tracking after stop_and_exit is a no-op
        env = self.core.stop_tracking()
        self.assertTrue(env["ok"])

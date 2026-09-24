"""Pins the v1.4 rules for the time-tracking core.

v1.4 is a single additive change: `list_deleted_entries` (§3.10) now returns a `description`
field alongside id/task/startTime/endTime, so the UI can show what a deleted entry actually
was before restoring it. No existing field changed meaning.
"""

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

    def advance(self, **kwargs):
        self._moment = self._moment + timedelta(**kwargs)


def at(hour, minute, second=0):
    return datetime(2026, 9, 23, hour, minute, second, tzinfo=timezone.utc)


class DeletedEntriesBase(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self.clock = FrozenClock(at(9, 0, 0))
        self.core = TimeTrackerCore(self._tmpdir, clock=self.clock)

    def tearDown(self):
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _make_entry(self, task, description):
        """Runs one entry to completion, returning its id."""
        self.core.start_session("Garden work", task)
        current = self.core.get_state()["currentEntry"]["id"]
        self.core.edit_entry(current, task, description, None)
        self.clock.advance(minutes=15)
        self.core.stop_tracking()
        return current


class TestVersion(DeletedEntriesBase):
    def test_contract_version_is_v1_4(self):
        assert CONTRACT_VERSION == "v1.4", CONTRACT_VERSION


class TestDeletedEntryShape(DeletedEntriesBase):
    def test_key_set_is_exactly_the_contract_set(self):
        """A: rows carry exactly id, task, startTime, endTime, description."""
        eid = self._make_entry("weeding", "back bed")
        self.core.delete_entry(eid)
        rows = self.core.list_deleted_entries()
        assert len(rows) == 1, rows
        assert set(rows[0].keys()) == {"id", "task", "startTime", "endTime", "description"}, rows[0]

    def test_description_comes_through(self):
        """B: the deleted entry's description is what the user typed."""
        eid = self._make_entry("weeding", "back bed")
        self.core.delete_entry(eid)
        assert self.core.list_deleted_entries()[0]["description"] == "back bed"

    def test_missing_description_is_empty_string_not_null(self):
        """C: an entry with no description reports '', matching the entries list."""
        eid = self._make_entry("weeding", "")
        self.core.delete_entry(eid)
        row = self.core.list_deleted_entries()[0]
        assert row["description"] == "", row
        assert row["description"] is not None

    def test_description_is_not_normalised_into_the_task(self):
        """D: description stays its own field; task is unchanged by the addition."""
        eid = self._make_entry("planning", "weekly review")
        self.core.delete_entry(eid)
        row = self.core.list_deleted_entries()[0]
        assert row["task"] == "planning", row
        assert row["description"] == "weekly review", row


class TestExistingBehaviourUnchanged(DeletedEntriesBase):
    def test_empty_when_no_session_open(self):
        """E: no session open still answers []."""
        assert self.core.list_deleted_entries() == []

    def test_order_stays_oldest_first(self):
        """F: v1.3 ordering is untouched by the new field."""
        first = self._make_entry("weeding", "front bed")
        self.core.delete_entry(first)
        second = self._make_entry("planning", "weekly review")
        self.core.delete_entry(second)
        ids = [row["id"] for row in self.core.list_deleted_entries()]
        assert ids == sorted(ids), ids

    def test_restore_still_works_and_description_survives(self):
        """G: restoring clears the flag and the entry returns to the entries list intact."""
        eid = self._make_entry("weeding", "back bed")
        self.core.delete_entry(eid)
        self.core.restore_entry(eid)
        assert self.core.list_deleted_entries() == []
        entries = {e["id"]: e for e in self.core.get_state()["entries"]}
        assert entries[eid]["description"] == "back bed", entries[eid]

    def test_description_survives_a_restart(self):
        """H: the field is read from the stored document, not held in memory."""
        eid = self._make_entry("weeding", "back bed")
        self.core.delete_entry(eid)
        session_id = self.core.get_state()["session"]["id"]
        self.core.stop_and_exit()

        restarted = TimeTrackerCore(self._tmpdir, clock=self.clock)
        result = restarted.resume_session(session_id)
        assert result["ok"] is True, result
        rows = restarted.list_deleted_entries()
        assert rows[0]["description"] == "back bed", rows

    def test_stored_document_keeps_the_description(self):
        """I: the on-disk entry for the deleted row carries the description."""
        eid = self._make_entry("weeding", "back bed")
        self.core.delete_entry(eid)
        self.core.stop_and_exit()
        files = [f for f in os.listdir(self._tmpdir) if f.endswith(".json")]
        assert len(files) == 1, files
        document = json.loads(open(os.path.join(self._tmpdir, files[0]), encoding="utf-8").read())
        row = [e for e in document["entries"] if e["id"] == eid][0]
        assert row["description"] == "back bed", row
        assert row["isDeleted"] is True, row


if __name__ == "__main__":
    unittest.main()
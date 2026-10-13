"""App/bridge boundary tests; canonical interval rule tests stay in the core repo."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from main import Api, EXPECTED_CONTRACT_VERSION


class TimeCorrectionApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.api = Api(storage_path=str(self.root / "sessions"), preferences_path=str(self.root / "prefs.json"))
        self.now = datetime(2026, 10, 12, 9, tzinfo=timezone.utc)
        self.api.core._clock = lambda: self.now
        self.sid = self.api.start_session("Boundary", "Work")["state"]["session"]["id"]
        self.now = self.now.replace(hour=10)
        self.assertTrue(self.api.stop_tracking()["ok"])
        self.assertTrue(self.api.edit_entry(1, None, "keep this", True)["ok"])
        self.now = self.now.replace(hour=12)

    def saved(self):
        paths = list((self.root / "sessions").glob("*.json"))
        self.assertEqual(len(paths), 1)
        return json.loads(paths[0].read_text(encoding="utf-8"))

    def test_add_wrapper_preserves_argument_order_and_calls_save_location_hook(self):
        with patch.object(self.api, "_after_core_save", wraps=self.api._after_core_save) as hook:
            r = self.api.add_completed_entry(" Past ", " note ", "2026-10-12T07:00:00Z", "2026-10-12T08:00:00Z", self.sid)
            hook.assert_called_once()
        self.assertTrue(r["ok"], r)
        entry = self.saved()["entries"][-1]
        self.assertEqual((entry["task"], entry["description"], entry["startTime"], entry["endTime"]),
                         ("Past", "note", "2026-10-12T07:00:00+00:00", "2026-10-12T08:00:00+00:00"))
        self.assertTrue(entry["isComplete"])
        self.assertFalse(entry["logged"])

    def test_correction_wrapper_preserves_id_times_and_session_argument_order(self):
        with patch.object(self.api, "_after_core_save", wraps=self.api._after_core_save) as hook:
            r = self.api.correct_entry_time(1, "2026-10-12T04:05:00-05:00", "2026-10-12T04:55:00-05:00", self.sid)
            hook.assert_called_once()
        self.assertTrue(r["ok"], r)
        entry = self.saved()["entries"][0]
        self.assertEqual(entry["id"], 1)
        self.assertEqual(entry["startTime"], "2026-10-12T09:05:00+00:00")
        self.assertEqual(entry["endTime"], "2026-10-12T09:55:00+00:00")
        self.assertEqual(entry["description"], "keep this")
        self.assertFalse(entry["logged"])

    def test_errors_do_not_remove_a_pending_source_file(self):
        source = self.root / "previous-location.json"
        source.write_text("untouched", encoding="utf-8")
        self.api._pending_source = source
        before = self.saved()
        r = self.api.add_completed_entry("x", "", "bad", "bad", self.sid)
        self.assertEqual(r["error"], "invalid_timestamp")
        r = self.api.correct_entry_time(1, "2026-10-12T08:00:00Z", "2026-10-12T09:00:00Z", "wrong-session")
        self.assertEqual(r["error"], "session_changed")
        self.assertEqual(source.read_text(encoding="utf-8"), "untouched")
        self.assertEqual(self.saved(), before)

    def test_real_replace_failure_preserves_wrapper_state_and_file(self):
        before = self.saved(), self.api.get_state()
        with patch("timetracker_core.storage.os.replace", side_effect=OSError("injected")) as fault:
            r = self.api.correct_entry_time(1, "2026-10-12T09:01:00Z", "2026-10-12T10:00:00Z", self.sid)
        fault.assert_called_once()
        self.assertEqual(r["error"], "internal_error")
        self.assertEqual((self.saved(), self.api.get_state()), before)

    def test_new_host_instance_reads_persisted_correction(self):
        r = self.api.correct_entry_time(1, "2026-10-12T09:01:00Z", "2026-10-12T10:00:00Z", self.sid)
        self.assertTrue(r["ok"], r)
        other = Api(storage_path=str(self.root / "sessions"), preferences_path=str(self.root / "prefs.json"))
        self.assertTrue(other.resume_session(self.sid)["ok"])
        self.assertEqual(other.get_state(), r["state"])

    def test_new_controls_and_commands_are_wired_in_shipped_assets(self):
        html = (ROOT / "web/index.html").read_text(encoding="utf-8")
        js = (ROOT / "web/app.js").read_text(encoding="utf-8")
        self.assertIn('id="add-missed-time-btn"', html)
        self.assertIn("getElementById('add-missed-time-btn').onclick", js)
        self.assertIn("timeBtn.onclick = () => openIntervalEditor(e)", js)
        self.assertIn("api().add_completed_entry(taskInput.value, descInput.value, startInput.value, endInput.value, sessionId)", js)
        self.assertIn("api().correct_entry_time(entry.id, startInput.value, endInput.value, sessionId)", js)
        self.assertIn("save.disabled = cancel.disabled = close.disabled = true", js)
        self.assertIn("Changing either time marks this entry Unlogged again", js)
        self.assertIn(f"version: {EXPECTED_CONTRACT_VERSION}\n", (ROOT / "specs/core-logic-contract.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()

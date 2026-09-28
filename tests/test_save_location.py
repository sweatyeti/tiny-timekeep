"""Persisted entry save-location preference and safe folder switching."""

import json
import os
import shutil
import tempfile
import unittest
from unittest.mock import patch

import main
from preferences import DEFAULT_PREFERENCES, PreferencesStore


class SaveLocationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="koot-save-location-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.source = os.path.join(self.tmp, "sessions")
        self.target = os.path.join(self.tmp, "chosen")
        self.prefs_path = os.path.join(self.tmp, "preferences.json")
        self.api = main.Api(storage_path=self.source, preferences_path=self.prefs_path,
                            location_locked=False)

    def test_preference_defaults_to_current_location_and_persists(self):
        self.assertIsNone(DEFAULT_PREFERENCES["entrySaveLocation"])
        self.assertEqual(self.api.get_preferences()["entrySaveLocation"], os.path.abspath(self.source))
        result = self.api.set_preference("entrySaveLocation", self.target, False)
        self.assertTrue(result["ok"], result)
        reopened = PreferencesStore(self.prefs_path)
        self.assertEqual(reopened.get_all()["entrySaveLocation"], os.path.abspath(self.target))

    def test_invalid_and_environment_locked_selection_do_not_change_location(self):
        result = self.api.set_preference("entrySaveLocation", "  ", False)
        self.assertFalse(result["ok"])
        self.assertEqual(str(self.api.core._store.directory), os.path.abspath(self.source))
        self.assertEqual(self.api.get_preferences()["entrySaveLocation"], os.path.abspath(self.source))
        locked = main.Api(storage_path=self.source,
                          preferences_path=os.path.join(self.tmp, "locked.json"),
                          location_locked=True)
        result = locked.set_preference("entrySaveLocation", self.target, True)
        self.assertFalse(result["ok"])
        self.assertTrue(locked.get_preferences()["entrySaveLocationLocked"])

    def test_move_preserves_files_and_renames_collisions_without_overwrite(self):
        self.api.start_session("Garden work", "weeding")
        original = self.api.core._store.document_path(self.api.core._session.file_name)
        os.makedirs(self.target)
        collision = os.path.join(self.target, original.name)
        with open(collision, "w", encoding="utf-8") as handle:
            handle.write("unrelated target data")

        result = self.api.set_preference("entrySaveLocation", self.target, True)

        self.assertTrue(result["ok"], result)
        self.assertFalse(original.exists())
        with open(collision, encoding="utf-8") as handle:
            self.assertEqual(handle.read(), "unrelated target data")
        moved = os.path.join(self.target, self.api.core._session.file_name)
        self.assertTrue(os.path.isfile(moved))
        with open(moved, encoding="utf-8") as handle:
            document = json.load(handle)
        self.assertEqual(document["sessionId"], self.api.core._session.session_id)
        self.assertTrue(self.api.stop_tracking()["ok"])
        self.assertEqual(str(self.api.core._store.directory), os.path.abspath(self.target))

    def test_failed_move_keeps_source_and_active_location_unchanged(self):
        self.api.start_session("Garden work", "weeding")
        original = self.api.core._store.document_path(self.api.core._session.file_name)
        with patch.object(main.shutil, "copyfileobj", side_effect=OSError("simulated copy failure")):
            result = self.api.set_preference("entrySaveLocation", self.target, True)
        self.assertFalse(result["ok"])
        self.assertTrue(original.exists())
        self.assertEqual(str(self.api.core._store.directory), os.path.abspath(self.source))
        self.assertEqual(self.api.get_preferences()["entrySaveLocation"], os.path.abspath(self.source))

    def test_declining_move_immediately_relocates_active_session(self):
        self.api.start_session("Garden work", "weeding")
        original = self.api.core._store.document_path(self.api.core._session.file_name)
        session_id = self.api.core._session.session_id
        historical = os.path.join(str(self.api.core._store.directory), "old-session.json")
        with open(historical, "w", encoding="utf-8") as handle:
            json.dump({"sessionId": "old-id", "title": "Old"}, handle)
        result = self.api.set_preference("entrySaveLocation", self.target, False)
        self.assertTrue(result["ok"], result)
        self.assertTrue(self.api.core._session.is_active())
        self.assertFalse(original.exists())
        entries = list(os.scandir(self.target))
        self.assertEqual(len(entries), 1)
        target_name = entries[0].name
        with open(os.path.join(self.target, target_name), "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data["sessionId"], session_id)
        self.assertEqual(self.api.core._session.file_name, target_name)
        self.assertIsNone(self.api._pending_source)
        self.assertTrue(os.path.exists(historical))

    def test_immediate_copy_failure_falls_back_to_pending(self):
        self.api.start_session("Garden work", "weeding")
        original = self.api.core._store.document_path(self.api.core._session.file_name)
        with patch("main.shutil.copyfileobj", side_effect=OSError("simulated")):
            result = self.api.set_preference("entrySaveLocation", self.target, False)
        self.assertTrue(result["ok"], result)
        self.assertEqual(str(self.api.core._store.directory), os.path.abspath(self.target))
        self.assertEqual(self.api.get_preferences()["entrySaveLocation"], os.path.abspath(self.target))
        self.assertTrue(original.exists())
        self.assertEqual(self.api._pending_source, original)
        self.assertIsNone(self.api.core._session.file_name)
        self.assertTrue(self.api.stop_tracking()["ok"])
        self.assertFalse(original.exists())
        self.assertTrue(list(os.scandir(self.target)))

if __name__ == "__main__":
    unittest.main()

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
        self.default = os.path.join(self.tmp, "default")
        self._default_patch = patch.object(main, "_default_storage_path", return_value=self.default)
        self._default_patch.start()
        self.addCleanup(self._default_patch.stop)
        self.api = main.Api(storage_path=self.source, preferences_path=self.prefs_path,
                            location_locked=False)

    def _stored_preference(self):
        return PreferencesStore(self.prefs_path).get_all()["entrySaveLocation"]

    def test_preference_defaults_to_current_location_and_persists(self):
        self.assertIsNone(DEFAULT_PREFERENCES["entrySaveLocation"])
        self.assertEqual(self.api.get_preferences()["entrySaveLocation"], os.path.abspath(self.source))
        result = self.api.set_preference("entrySaveLocation", self.target, False)
        self.assertTrue(result["ok"], result)
        reopened = PreferencesStore(self.prefs_path)
        self.assertEqual(reopened.get_all()["entrySaveLocation"], os.path.abspath(self.target))

        with self.subTest("restore persists an unset preference and survives a restart"):
            result = self.api.restore_default_save_location(False)
            self.assertTrue(result["ok"], result)
            self.assertEqual(str(self.api.core._store.directory), os.path.abspath(self.default))
            self.assertIsNone(self._stored_preference())
            prefs = self.api.get_preferences()
            self.assertEqual(prefs["entrySaveLocation"], os.path.abspath(self.default))
            self.assertEqual(prefs["entrySaveLocationDefault"], os.path.abspath(self.default))
            self.assertTrue(prefs["entrySaveLocationIsDefault"])
            self.assertFalse(prefs["entrySaveLocationLocked"])
            restarted = main.Api(storage_path=None, preferences_path=self.prefs_path,
                                 location_locked=False)
            self.assertEqual(str(restarted.core._store.directory), os.path.abspath(self.default))
            self.assertIsNone(self._stored_preference())
            self.assertTrue(restarted.get_preferences()["entrySaveLocationIsDefault"])

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

        with self.subTest("restoring the default is refused while the location is locked"):
            self.api.set_preference("entrySaveLocation", self.target, False)
            result = locked.restore_default_save_location(True)
            self.assertFalse(result["ok"])
            self.assertEqual(str(locked.core._store.directory), os.path.abspath(self.source))
            self.assertEqual(locked.get_preferences()["entrySaveLocation"],
                             os.path.abspath(self.source))
            self.assertTrue(locked.get_preferences()["entrySaveLocationLocked"])
            self.assertEqual(self._stored_preference(), os.path.abspath(self.target))

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

        with self.subTest("restore with move is collision-safe and clears the preference"):
            active = self.api.core._store.document_path(self.api.core._session.file_name)
            os.makedirs(self.default, exist_ok=True)
            collision = os.path.join(self.default, active.name)
            with open(collision, "w", encoding="utf-8") as handle:
                handle.write("unrelated default data")
            result = self.api.restore_default_save_location(True)
            self.assertTrue(result["ok"], result)
            self.assertEqual(str(self.api.core._store.directory), os.path.abspath(self.default))
            self.assertIsNone(self._stored_preference())
            with open(collision, encoding="utf-8") as handle:
                self.assertEqual(handle.read(), "unrelated default data")
            moved = self.api.core._store.document_path(self.api.core._session.file_name)
            self.assertTrue(os.path.isfile(moved))
            self.assertNotEqual(moved.name, active.name)
            with open(moved, encoding="utf-8") as handle:
                self.assertEqual(json.load(handle)["sessionId"], self.api.core._session.session_id)
            self.assertFalse(active.exists())

    def test_failed_move_keeps_source_and_active_location_unchanged(self):
        self.api.start_session("Garden work", "weeding")
        original = self.api.core._store.document_path(self.api.core._session.file_name)
        with patch.object(main.shutil, "copyfileobj", side_effect=OSError("simulated copy failure")):
            result = self.api.set_preference("entrySaveLocation", self.target, True)
        self.assertFalse(result["ok"])
        self.assertTrue(original.exists())
        self.assertEqual(str(self.api.core._store.directory), os.path.abspath(self.source))
        self.assertEqual(self.api.get_preferences()["entrySaveLocation"], os.path.abspath(self.source))

        with self.subTest("a failed restore keeps the custom location and the custom preference"):
            self.api.set_preference("entrySaveLocation", self.target, False)
            self.assertEqual(self._stored_preference(), os.path.abspath(self.target))
            relocated = self.api.core._store.document_path(self.api.core._session.file_name)
            self.assertTrue(relocated.is_file())
            with patch.object(main.shutil, "copyfileobj",
                              side_effect=OSError("simulated copy failure")):
                result = self.api.restore_default_save_location(True)
            self.assertFalse(result["ok"])
            self.assertEqual(str(self.api.core._store.directory), os.path.abspath(self.target))
            self.assertEqual(self._stored_preference(), os.path.abspath(self.target))
            self.assertTrue(relocated.is_file())

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

        with self.subTest("restore without move relocates the active session and clears the preference"):
            result = self.api.restore_default_save_location(False)
            self.assertTrue(result["ok"], result)
            self.assertEqual(str(self.api.core._store.directory), os.path.abspath(self.default))
            self.assertIsNone(self._stored_preference())
            self.assertTrue(self.api.core._session.is_active())
            entries = list(os.scandir(self.default))
            self.assertEqual(len(entries), 1)
            with open(os.path.join(self.default, entries[0].name), encoding="utf-8") as handle:
                self.assertEqual(json.load(handle)["sessionId"], session_id)
            self.assertFalse(os.path.exists(os.path.join(self.target, target_name)))

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

        with self.subTest("restoring an already-default location is a harmless no-op"):
            result = self.api.restore_default_save_location(False)
            self.assertTrue(result["ok"], result)
            self.assertIsNone(self._stored_preference())
            before = sorted(os.listdir(self.default))
            again = self.api.restore_default_save_location(False)
            self.assertTrue(again["ok"], again)
            self.assertEqual(sorted(os.listdir(self.default)), before)

        with self.subTest("an explicit path equal to the default is cleared without copying"):
            # Switching to the path already in force is a no-op that stores nothing, so move away
            # first and then store the default path explicitly.
            self.api.set_preference("entrySaveLocation", self.target, False)
            self.api.set_preference("entrySaveLocation", self.default, False)
            self.assertEqual(self._stored_preference(), os.path.abspath(self.default))
            before = sorted(os.listdir(self.default))
            result = self.api.restore_default_save_location(True)
            self.assertTrue(result["ok"], result)
            self.assertIsNone(self._stored_preference())
            self.assertEqual(sorted(os.listdir(self.default)), before)


if __name__ == "__main__":
    unittest.main()

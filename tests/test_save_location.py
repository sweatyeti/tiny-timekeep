"""Persisted entry save-location preference and safe folder switching."""

import json
import os
import shutil
import sys
import tempfile
import types
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

    def test_invalid_selection_does_not_change_active_or_persisted_location(self):
        result = self.api.set_preference("entrySaveLocation", "  ", False)
        self.assertFalse(result["ok"])
        self.assertEqual(str(self.api.core._store.directory), os.path.abspath(self.source))
        self.assertEqual(self.api.get_preferences()["entrySaveLocation"], os.path.abspath(self.source))

    def test_environment_locked_location_cannot_be_changed(self):
        locked = main.Api(storage_path=self.source,
                          preferences_path=os.path.join(self.tmp, "locked.json"),
                          location_locked=True)
        result = locked.set_preference("entrySaveLocation", self.target, True)
        self.assertFalse(result["ok"])
        self.assertTrue(locked.get_preferences()["entrySaveLocationLocked"])

    def test_native_chooser_returns_selection_without_switching_before_confirmation(self):
        class Window:
            def __init__(self, path):
                self.path = path

            def create_file_dialog(self, dialog_type):
                self.dialog_type = dialog_type
                return [self.path]

        window = Window(self.target)
        self.api.set_window(window)
        webview_stub = types.SimpleNamespace(FOLDER_DIALOG=7)
        with patch.dict(sys.modules, {"webview": webview_stub}):
            result = self.api.choose_entry_save_location()
        self.assertEqual(result, {"ok": True, "path": os.path.abspath(self.target)})
        self.assertEqual(window.dialog_type, 7)
        self.assertEqual(str(self.api.core._store.directory), os.path.abspath(self.source))

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

    def test_declining_move_keeps_source_until_next_successful_active_save(self):
        self.api.start_session("Garden work", "weeding")
        original = self.api.core._store.document_path(self.api.core._session.file_name)
        result = self.api.set_preference("entrySaveLocation", self.target, False)
        self.assertTrue(result["ok"], result)
        self.assertTrue(original.exists())
        self.assertTrue(self.api.stop_tracking()["ok"])
        self.assertFalse(original.exists())
        self.assertTrue(list(os.scandir(self.target)))

    def test_ui_exposes_accessible_selector_and_two_confirmations(self):
        with open(os.path.join(main.BASE_DIR, "web", "index.html"), encoding="utf-8") as handle:
            html = handle.read()
        with open(os.path.join(main.BASE_DIR, "web", "app.js"), encoding="utf-8") as handle:
            js = handle.read()
        with open(os.path.join(main.BASE_DIR, "web", "style.css"), encoding="utf-8") as handle:
            css = handle.read()
        self.assertIn('id="save-location-btn"', html)
        self.assertIn('aria-label="Entry save location"', html)
        self.assertIn("choose.className = 'btn btn-primary save-location-choose';", js)
        self.assertIn("confirmSaveLocation", js)
        self.assertIn("role', 'dialog'", js)
        self.assertIn("aria-modal", js)
        self.assertIn("Confirm save location", js)
        self.assertIn("Use this folder for new sessions?", js)
        self.assertIn("Move existing session files to this folder? Choose Cancel to leave them where they are.", js)
        self.assertIn("api().choose_entry_save_location()", js)
        self.assertIn("Current entry save location", js)
        self.assertNotIn("window.confirm", js)
        self.assertIn(".save-location-choose {", css)
        self.assertIn(".save-location-confirmation {", css)
        choose_rule = css.split('.save-location-choose {', 1)[1].split('}', 1)[0]
        confirmation_rule = css.split('.save-location-confirmation {', 1)[1].split('}', 1)[0]
        self.assertIn("var(--accent-pink)", choose_rule)
        self.assertIn("var(--bg-top)", confirmation_rule)
        self.assertIn("var(--panel)", css)
        self.assertIn("var(--accent-mint)", css)


if __name__ == "__main__":
    unittest.main()

"""Persisted entry save-location preference and safe folder switching."""

import json
import os
import shutil
import tempfile
from types import SimpleNamespace
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

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
        self._original_default_storage_path = main._default_storage_path
        self._default_patch = patch.object(main, "_default_storage_path", return_value=self.default)
        self._default_patch.start()
        self.addCleanup(self._default_patch.stop)
        self.api = main.Api(storage_path=self.source, preferences_path=self.prefs_path,
                            location_locked=False)

    def _stored_preference(self):
        return PreferencesStore(self.prefs_path).get_all()["entrySaveLocation"]

    def _default_path_in(self, localappdata, override=""):
        with patch.dict(os.environ, {
            "LOCALAPPDATA": localappdata,
            main.DATA_DIR_ENV: override,
        }):
            return self._original_default_storage_path()

    def test_fresh_install_uses_tinytimekeep_sessions_folder(self):
        localappdata = os.path.join(self.tmp, "Local")

        selected = self._default_path_in(localappdata)

        expected = os.path.join(localappdata, "tinyTimekeep", "sessions")
        self.assertEqual(selected, expected)
        self.assertTrue(os.path.isdir(expected))
        self.assertFalse(os.path.exists(os.path.join(localappdata, "KeeperOfTime", "sessions")))

    def test_existing_legacy_sessions_folder_stays_in_use_without_copying_files(self):
        localappdata = os.path.join(self.tmp, "Local")
        legacy = Path(localappdata) / "KeeperOfTime" / "sessions"
        original = legacy / "existing-session.json"
        original.parent.mkdir(parents=True)
        original_bytes = b'{"sessionId":"legacy","title":"Keep in place"}\n'
        original.write_bytes(original_bytes)

        selected = self._default_path_in(localappdata)

        self.assertEqual(selected, str(legacy))
        self.assertEqual(original.read_bytes(), original_bytes)
        self.assertFalse((Path(localappdata) / "tinyTimekeep" / "sessions").exists())

    def test_legacy_sessions_folder_wins_when_both_defaults_exist(self):
        localappdata = Path(self.tmp) / "Local"
        legacy = localappdata / "KeeperOfTime" / "sessions"
        new_default = localappdata / "tinyTimekeep" / "sessions"
        legacy_file = legacy / "legacy.json"
        new_file = new_default / "new.json"
        legacy_file.parent.mkdir(parents=True)
        new_file.parent.mkdir(parents=True)
        legacy_bytes = b"legacy bytes stay here"
        new_bytes = b"new-default bytes stay here"
        legacy_file.write_bytes(legacy_bytes)
        new_file.write_bytes(new_bytes)

        selected = self._default_path_in(str(localappdata))

        self.assertEqual(selected, str(legacy))
        self.assertEqual(legacy_file.read_bytes(), legacy_bytes)
        self.assertEqual(new_file.read_bytes(), new_bytes)
        self.assertEqual([path.name for path in legacy.iterdir()], ["legacy.json"])
        self.assertEqual([path.name for path in new_default.iterdir()], ["new.json"])

    def test_environment_override_takes_precedence_over_both_default_folders(self):
        localappdata = Path(self.tmp) / "Local"
        legacy = localappdata / "KeeperOfTime" / "sessions"
        new_default = localappdata / "tinyTimekeep" / "sessions"
        legacy.mkdir(parents=True)
        new_default.mkdir(parents=True)
        override = Path(self.tmp) / "custom sessions"

        selected = self._default_path_in(str(localappdata), str(override))

        self.assertEqual(selected, str(override))
        self.assertFalse(override.exists())

    def test_preferences_file_keeps_keeper_of_time_location(self):
        localappdata = os.path.join(self.tmp, "Local")
        with patch.dict(os.environ, {"LOCALAPPDATA": localappdata}):
            selected = main._default_preferences_path()

        self.assertEqual(
            selected,
            os.path.join(localappdata, "KeeperOfTime", "preferences.json"),
        )
        self.assertEqual(main.APP_NAME, "KeeperOfTime")

    def test_explicit_custom_location_remains_selected_on_startup(self):
        localappdata = Path(self.tmp) / "Local"
        custom = Path(self.tmp) / "custom sessions"
        preferences_path = localappdata / "KeeperOfTime" / "preferences.json"
        PreferencesStore(str(preferences_path)).set("entrySaveLocation", str(custom))
        fake_webview = SimpleNamespace(
            create_window=Mock(return_value=object()),
            start=Mock(),
        )

        with patch.dict(os.environ, {
            "LOCALAPPDATA": str(localappdata),
            main.DATA_DIR_ENV: "",
        }), patch.dict("sys.modules", {"webview": fake_webview}):
            result = main.main([])

        self.assertEqual(result, 0)
        api = fake_webview.create_window.call_args.kwargs["js_api"]
        self.assertEqual(api.core._store.directory, custom)
        self.assertEqual(api.get_preferences()["entrySaveLocation"], str(custom))
        self.assertEqual(
            PreferencesStore(str(preferences_path)).get_all()["entrySaveLocation"],
            str(custom),
        )

    # ------------------------------------------------------------------
    # open_entry_save_location
    # ------------------------------------------------------------------

    def test_open_folder_windows(self):
        with patch.object(main.sys, "platform", "win32"), \
             patch.object(main.os, "startfile", create=True) as mock_startfile:
            result = self.api.open_entry_save_location()
        self.assertTrue(result["ok"])
        self.assertEqual(result["path"], os.path.abspath(self.source))
        mock_startfile.assert_called_once_with(os.path.abspath(self.source))

    def test_open_folder_darwin(self):
        with patch.object(main.sys, "platform", "darwin"), \
             patch.object(main.subprocess, "Popen") as mock_popen:
            result = self.api.open_entry_save_location()
        self.assertTrue(result["ok"])
        mock_popen.assert_called_once_with(["open", os.path.abspath(self.source)], shell=False)

    def test_open_folder_linux(self):
        with patch.object(main.sys, "platform", "linux"), \
             patch.object(main.subprocess, "Popen") as mock_popen:
            result = self.api.open_entry_save_location()
        self.assertTrue(result["ok"])
        mock_popen.assert_called_once_with(["xdg-open", os.path.abspath(self.source)], shell=False)

    def test_open_folder_posix_argv_is_list_no_shell(self):
        with patch.object(main.sys, "platform", "linux"), \
             patch.object(main.subprocess, "Popen") as mock_popen:
            self.api.open_entry_save_location()
        args, kwargs = mock_popen.call_args
        self.assertIsInstance(args[0], list)
        self.assertEqual(kwargs.get("shell"), False)

    def test_open_folder_shell_metacharacters(self):
        tricky = os.path.join(self.tmp, "dir with spaces & $(rm -rf) `echo`")
        os.makedirs(tricky)
        self.api.core._store._directory = Path(tricky)
        with patch.object(main.sys, "platform", "linux"), \
             patch.object(main.subprocess, "Popen") as mock_popen:
            result = self.api.open_entry_save_location()
        self.assertTrue(result["ok"])
        args, kwargs = mock_popen.call_args
        self.assertEqual(args[0], ["xdg-open", os.path.abspath(tricky)])
        self.assertEqual(kwargs.get("shell"), False)

    def test_open_folder_missing_path(self):
        self.api.core._store._directory = Path("/nonexistent/koot/xyz")
        with patch.object(main.sys, "platform", "linux"), \
             patch.object(main.subprocess, "Popen") as mock_popen:
            result = self.api.open_entry_save_location()
        self.assertFalse(result["ok"])
        mock_popen.assert_not_called()

    def test_open_folder_file_not_directory(self):
        fpath = os.path.join(self.tmp, "afile.txt")
        with open(fpath, "w") as f:
            f.write("x")
        self.api.core._store._directory = Path(fpath)
        with patch.object(main.sys, "platform", "linux"), \
             patch.object(main.subprocess, "Popen") as mock_popen:
            result = self.api.open_entry_save_location()
        self.assertFalse(result["ok"])
        mock_popen.assert_not_called()

    def test_open_folder_opener_error(self):
        with patch.object(main.sys, "platform", "linux"), \
             patch.object(main.subprocess, "Popen", side_effect=OSError("spawn failed")):
            result = self.api.open_entry_save_location()
        self.assertFalse(result["ok"])
        self.assertIn("spawn failed", result["message"])

    def test_open_folder_unsupported_platform(self):
        with patch.object(main.sys, "platform", "freebsd"):
            result = self.api.open_entry_save_location()
        self.assertFalse(result["ok"])
        self.assertIn("Unsupported platform", result["message"])

    def test_open_folder_uses_store_directory_not_pref(self):
        # The backend must use core._store.directory, not a passed path
        self.assertEqual(self.api.core._store.directory, Path(self.source))
        with patch.object(main.sys, "platform", "linux"), \
             patch.object(main.subprocess, "Popen") as mock_popen:
            result = self.api.open_entry_save_location()
        self.assertTrue(result["ok"])
        args, _ = mock_popen.call_args
        self.assertEqual(args[0][1], os.path.abspath(self.source))

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

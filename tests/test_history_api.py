"""REAL Api/core export regressions. Only native dialog/OS failure boundaries are injected."""
import csv
import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import main
import history_export

SAVE = object()
WEBVIEW_BOUNDARY = SimpleNamespace(FileDialog=SimpleNamespace(SAVE=SAVE))


class HistoryApi(unittest.TestCase):
    def setUp(self):
        td = tempfile.TemporaryDirectory(prefix='ttk-api-history-')
        self.addCleanup(td.cleanup)
        self.root = Path(td.name)
        self.sessions, self.exports = self.root / 'sessions', self.root / 'exports'
        self.sessions.mkdir()
        self.exports.mkdir()
        self.prefs = self.root / 'preferences.json'
        self.prefs.write_text('{}', encoding='utf-8')
        self.api = main.Api(str(self.sessions), str(self.prefs), location_locked=True)
        isolated = patch.dict(os.environ, {main.DATA_DIR_ENV: str(self.sessions), 'LOCALAPPDATA': str(self.root)})
        isolated.start()
        self.addCleanup(isolated.stop)
        self.clock = main._FixedClock(datetime(2026, 10, 10, 9, tzinfo=timezone.utc))
        self.api.core._clock = self.clock
        self.assertTrue(self.api.start_session('Fixture', 'café 雪')['ok'])
        self.assertTrue(self.api.edit_entry(1, description='comma, "quote"\nnext')['ok'])
        self.clock.advance(seconds=61)
        self.assertTrue(self.api.stop_and_start_entry('@formula')['ok'])
        self.clock.advance(seconds=1)
        self.assertTrue(self.api.stop_and_start_entry('Still running')['ok'])

    def snapshot(self):
        return (self.api.get_state(), self.api.core._session.to_document(),
                {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in self.api.core._store.directory.iterdir() if p.is_file()},
                hashlib.sha256(self.prefs.read_bytes()).hexdigest())

    def guarded(self, method, *args, **kw):
        before = self.snapshot()
        result = method(*args, **kw)
        self.assertEqual(self.snapshot(), before, 'session document, file hashes, prefs or timer changed')
        self.assertNotIn('state', result)
        return result

    def save(self, selection, **kw):
        window = Mock()
        window.create_file_dialog.return_value = selection
        self.api.set_window(window)
        with patch.dict(sys.modules, {'webview': WEBVIEW_BOUNDARY}):
            result = self.guarded(self.api.save_history_csv, **kw)
        return result, window

    def test_query_real_api_and_fresh_process_readback(self):
        result = self.guarded(self.api.get_history, task_query='CAFÉ')
        self.assertTrue(result['ok'])
        self.assertEqual([r['task'] for r in result['report']['rows']], ['café 雪'])
        # Separate interpreter proves persistence, not an in-memory round trip.
        before = self.snapshot()
        proc = subprocess.run([sys.executable, str(ROOT / 'tools/history_fresh_readback.py'),
                               str(self.sessions), str(self.prefs)], capture_output=True,
                              text=True, encoding='utf-8', timeout=20)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        fresh = json.loads(proc.stdout)
        self.assertIsNone(fresh['state']['session'])
        self.assertEqual(fresh['report'], self.api.get_history())
        self.assertEqual(self.snapshot(), before)

    def test_save_csv_utf8_quoting_formula_and_filtered_snapshot(self):
        dest = self.exports / 'history.csv'
        result, window = self.save((str(dest),))
        self.assertTrue(result['ok'], result)
        self.assertEqual(result['path'], str(dest.resolve()))
        window.create_file_dialog.assert_called_once_with(
            SAVE, save_filename='tinyTimeKeep-history.csv', file_types=('CSV files (*.csv)',))
        self.assertTrue(dest.read_bytes().startswith(b'\xef\xbb\xbf'))
        with dest.open(encoding='utf-8-sig', newline='') as stream:
            reader = csv.DictReader(stream)
            rows = list(reader)
            self.assertIn('roundedMinutes (minutes)', reader.fieldnames)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]['description'], 'comma, "quote"\nnext')
        self.assertEqual(rows[0]['task'], 'café 雪')
        self.assertEqual(rows[0]['roundedMinutes (minutes)'], '2')
        self.assertEqual(rows[1]['task'], "'@formula")
        filtered, _ = self.save(str(dest), task_query='CAFÉ')
        self.assertTrue(filtered['ok'])
        with dest.open(encoding='utf-8-sig', newline='') as stream:
            self.assertEqual(len(list(csv.DictReader(stream))), 1)

    def test_cancel_writes_nothing_and_timer_continues(self):
        for selected in (None, (), []):
            with self.subTest(selected=selected):
                result, _ = self.save(selected)
                self.assertEqual(result, {'ok': True, 'cancelled': True})
        self.assertEqual(list(self.exports.iterdir()), [])
        start = self.api.get_state()['currentEntry']
        self.clock.advance(seconds=61)
        self.assertEqual(self.api.get_state()['currentEntry'], start)
        self.assertTrue(self.api.stop_tracking()['ok'])
        self.assertEqual(self.api.get_history(task_query='Still running')['report']['rows'][0]['roundedMinutes'], 2)

    def test_invalid_paths_no_writes(self):
        directory_target = self.exports / 'directory.csv'
        directory_target.mkdir()
        bad = ['relative.csv', str(self.exports / 'no.json'), str(self.sessions / 'no.csv'),
               str(self.exports / 'absent' / 'no.csv'), str(directory_target),
               str(self.exports / 'nul\0.csv'), 'x' * 4097, (123,), (str(self.exports / 'x.csv'), 'other'), {}, 5]
        for selection in bad:
            with self.subTest(selection=repr(selection)):
                result, _ = self.save(selection)
                self.assertEqual(result['error'], 'invalid_export_path', result)
        self.assertEqual(list(self.exports.iterdir()), [directory_target])

    @unittest.skipIf(os.name == 'nt', 'symlink creation requires Windows privilege; local Unix containment check')
    def test_linked_paths_and_preferences_are_rejected(self):
        target = self.exports / 'original.csv'
        target.write_bytes(b'original')
        linked = self.exports / 'linked.csv'
        linked.symlink_to(target)
        folder = self.root / 'linked-folder'
        folder.symlink_to(self.exports, target_is_directory=True)
        prefs_alias = self.exports / 'preferences.csv'
        os.link(self.prefs, prefs_alias)
        for selection in (linked, folder / 'new.csv', prefs_alias):
            result, _ = self.save((str(selection),))
            self.assertEqual(result['error'], 'invalid_export_path', result)
        self.assertEqual(target.read_bytes(), b'original')

    def test_unavailable_dialog_and_invalid_filters(self):
        with patch.dict(sys.modules, {'webview': WEBVIEW_BOUNDARY}):
            self.api.set_window(None)
            result = self.guarded(self.api.save_history_csv)
        self.assertEqual(result['error'], 'export_unavailable')
        window = Mock()
        window.create_file_dialog.side_effect = OSError('dialog unavailable fixture')
        self.api.set_window(window)
        with patch.dict(sys.modules, {'webview': WEBVIEW_BOUNDARY}):
            result = self.guarded(self.api.save_history_csv)
        self.assertEqual(result['error'], 'export_unavailable')
        result, window = self.save(str(self.exports / 'unused.csv'), logged_filter='bad')
        self.assertEqual(result['error'], 'invalid_history_filter')
        window.create_file_dialog.assert_not_called()
        self.assertEqual(list(self.exports.iterdir()), [])

    def test_atomic_replace_failure_preserves_existing_target_and_cleans_temp(self):
        dest = self.exports / 'history.csv'
        dest.write_bytes(b'original')
        with patch.object(history_export.os, 'replace', side_effect=OSError('fixture replace failure')):
            result, _ = self.save((str(dest),))
        self.assertEqual(result['error'], 'export_failed')
        self.assertEqual(dest.read_bytes(), b'original')
        self.assertEqual(list(self.exports.iterdir()), [dest])

    def test_fdopen_failure_closes_descriptor_and_cleans_temp(self):
        real_mkstemp = history_export.tempfile.mkstemp
        opened = []
        def tracked(*args, **kwargs):
            fd, path = real_mkstemp(*args, **kwargs)
            opened.append(fd)
            return fd, path
        with patch.object(history_export.tempfile, 'mkstemp', side_effect=tracked), \
             patch.object(history_export.os, 'fdopen', side_effect=OSError('fixture fdopen failure')):
            result, _ = self.save(str(self.exports / 'history.csv'))
        self.assertEqual(result['error'], 'export_failed')
        self.assertEqual(len(opened), 1)
        fd = opened[0]
        try:
            os.fstat(fd)
        except OSError:
            pass
        else:
            os.close(fd)  # clean the defect after observing it, never hide the failing assertion.
            self.fail('export leaked its temporary file descriptor after fdopen failure')
        self.assertEqual(list(self.exports.iterdir()), [])

    def test_selected_folder_change_with_and_without_move(self):
        for move in (False, True):
            with self.subTest(move=move):
                target = self.root / ('moved' if move else 'selected')
                self.api._location_locked = False
                self.assertTrue(self.api.set_entry_save_location(str(target), move)['ok'])
                before = self.snapshot()
                result = self.guarded(self.api.get_history)
                self.assertEqual(len(result['report']['rows']), 2)
                self.assertEqual(self.snapshot(), before)
                # Active source moves once; an old-only file is not reported in the new folder.
                old = self.sessions / 'old-only.json'
                old.write_text(json.dumps(dict(schemaVersion=2, sessionId='old-only', name='Old', entries=[
                    dict(id=1, task='Old-only', startTime='2026-10-10T01:00:00Z', endTime='2026-10-10T01:01:00Z')])), encoding='utf-8')
                self.assertNotIn('Old-only', [r['task'] for r in self.guarded(self.api.get_history)['report']['rows']])
                # Keep the ORIGINAL folder pointer to test files left behind, not the selected store.
                # self.sessions = target


class HistoryTestDiscoveryCanary(unittest.TestCase):
    def test_history_api_suite_is_discoverable(self):
        self.assertGreaterEqual(unittest.defaultTestLoader.loadTestsFromTestCase(HistoryApi).countTestCases(), 9)


if __name__ == '__main__':
    unittest.main()

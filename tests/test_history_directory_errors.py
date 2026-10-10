"""HR01 host regression: Api.save_history_csv under sessions os.scandir faults."""
import errno, hashlib, json, os, sys, tempfile, unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import main

_ENTRY = dict(id=1, task='T', description='', startTime='2026-10-10T09:00:00+00:00',
              endTime='2026-10-10T09:01:01+00:00', isComplete=True, isDeleted=False, logged=False)
_DOC = dict(schemaVersion=2, sessionId='saved-sid', name='F', startedAt='2026-10-10T09:00:00+00:00',
            endedAt=None, entries=[_ENTRY])

class _LateIter:
    def __init__(self, real, canary, path):
        self._it, self._canary, self._path, self._done, self._closed = real, canary, path, False, False
    def __iter__(self): return self
    def __next__(self):
        if self._done: raise OSError(errno.EIO, 'HR01 late', str(self._path))
        while True:
            e = next(self._it)
            if e.name.endswith('.json'):
                self._canary['yielded'].append(e.name); self._done = True; return e
    def close(self):
        if not self._closed: self._closed = True; self._it.close()
    def __enter__(self): return self
    def __exit__(self, *a): self.close(); return False

class _Win:
    def __init__(self, path): self._path, self.called = path, False
    def create_file_dialog(self, *a, **kw): self.called = True; return self._path

class TestSaveHistoryCsvErrors(unittest.TestCase):
    def _run(self, fault, active, existing_target):
        tmp = tempfile.TemporaryDirectory(prefix='ttk-hr01-'); self.addCleanup(tmp.cleanup)
        root = Path(tmp.name); sessions = root / 'sessions'; sessions.mkdir()
        (sessions / 'saved.json').write_text(json.dumps(_DOC), encoding='utf-8')
        prefs = root / 'preferences.json'; prefs.write_text('{}', encoding='utf-8')
        exports = root / 'exports'; exports.mkdir()
        target = exports / 'history.csv'
        if existing_target: target.write_bytes(b'prior complete CSV')
        clock = main._FixedClock(datetime(2026, 10, 10, 10, tzinfo=timezone.utc))
        api = main.Api(storage_path=str(sessions), preferences_path=str(prefs), location_locked=True)
        api.core._clock = clock
        if active:
            self.assertTrue(api.start_session('S', 'Task1')['ok'], 'start_session')
            clock.advance(seconds=61)
            self.assertTrue(api.stop_and_start_entry('Task2')['ok'], 'stop_and_start')
        bl = api.get_history(); self.assertTrue(bl['ok'])
        exp_rows = 2 if active else 1
        self.assertEqual(len(bl['report']['rows']), exp_rows)
        def _snap():
            h = {}
            for p in sorted(root.rglob('*')):
                if p.is_file() and not p.is_symlink():
                    h[str(p.relative_to(root))] = hashlib.sha256(p.read_bytes()).hexdigest()
            sd = api.core._session.to_document() if api.core._session is not None else None
            return api.get_state(), sd, h
        before = _snap()
        win = _Win(str(target)); real_scandir = os.scandir
        canary = {'attempted': False, 'yielded': []}; refs = []
        sess_str = os.fspath(sessions)
        def faulty(path, *a, **kw):
            if str(Path(os.fspath(path))) != sess_str: return real_scandir(path, *a, **kw)
            canary['attempted'] = True
            if fault == 'open': raise PermissionError(errno.EACCES, 'HR01 denied', str(path))
            w = _LateIter(real_scandir(path, *a, **kw), canary, path); refs.append(w); return w
        real_mkstemp = tempfile.mkstemp; mkstemp_calls = []
        def _mk(*a, **kw): mkstemp_calls.append(True); return real_mkstemp(*a, **kw)
        fake_wv = SimpleNamespace(FileDialog=SimpleNamespace(SAVE='SAVE'))
        with patch('os.scandir', side_effect=faulty), patch('tempfile.mkstemp', _mk), \
             patch.dict(sys.modules, {'webview': fake_wv}):
            api.set_window(win); r = api.save_history_csv()
        self.assertTrue(canary['attempted'], 'scandir not attempted')
        if fault == 'late':
            self.assertTrue(any(n.endswith('.json') for n in canary['yielded']),
                            f'late: no .json yielded, got {canary["yielded"]}')
        for w in refs: self.assertTrue(w._closed, 'scandir iterator not closed')
        self.assertFalse(win.called, 'save dialog called despite fault')
        self.assertEqual(mkstemp_calls, [], 'mkstemp called despite fault')
        after = _snap()
        self.assertEqual(after, before, 'state/files mutated after fault')
        if existing_target: self.assertEqual(target.read_bytes(), b'prior complete CSV')
        else: self.assertFalse(target.exists(), 'target created on fault')
        self.assertFalse(list(exports.glob('.ttk-csv-*')), 'temp file leaked')
        r2 = api.get_history(); self.assertTrue(r2['ok']); self.assertEqual(r2, bl, 'post-fault report != baseline')
        self.assertFalse(r['ok'],
            f"ok={r['ok']} rows={len(r.get('report',{}).get('rows',[]))} "
            f"warnings={r.get('report',{}).get('warnings')} baseline={exp_rows}")
        self.assertEqual(r.get('error'), 'internal_error')
        self.assertTrue(r.get('message'), 'message must be nonempty')
        for k in ('report', 'csv', 'state', 'path'): self.assertNotIn(k, r, f'unexpected key {k!r}')
    def test_open_eacces_fault(self):
        for a in (False, True):
            for t in (False, True):
                with self.subTest(active=a, existing_target=t): self._run('open', a, t)
    def test_late_eio_fault(self):
        for a in (False, True):
            for t in (False, True):
                with self.subTest(active=a, existing_target=t): self._run('late', a, t)

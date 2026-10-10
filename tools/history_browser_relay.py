"""Task-only localhost bridge to the REAL Api; stdlib, isolated fixture data.

No product code uses this relay. The native window/dialog is the sole substituted
boundary. Browser controls receive real Python payloads and every call records
state, canonical document and pre/post file hashes. Never point it at user data.
"""
import argparse
import csv
import errno
import hashlib
import io
import json
import mimetypes
import os
import subprocess
import sys
import tempfile
import threading
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import unquote, urlsplit
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import main
import history_export

LOCK = threading.RLock()
METHODS = ('get_state', 'get_preferences', 'set_preference', 'list_sessions',
           'list_deleted_entries', 'get_history', 'save_history_csv', 'start_session',
           'resume_session', 'stop_and_start_entry', 'edit_entry', 'delete_entry',
           'restore_entry', 'log_task_group', 'unlog_task_group', 'stop_tracking',
           'stop_and_exit', 'move_window_to', 'resize_window_to', 'minimize_window', 'exit_app')


def seed(folder):
    def e(i, task, start, end, **kw):
        return dict(id=i, task=task, startTime=start, endTime=end, **kw)
    def doc(sid, name, rows):
        return dict(schemaVersion=2, sessionId=sid, name=name, startedAt='2026-10-09T09:00:00+00:00',
                    endedAt=None, entries=rows)
    samples = {
        'a.json': doc('a', 'Earlier café 雪', [
            e(1, 'Case Alpha', '2026-10-10T09:00:00+00:00', '2026-10-10T09:00:01+00:00', description='café 雪, "quoted"\nline'),
            e(2, 'unnamed', '2026-10-10T09:10:00+00:00', '2026-10-10T09:11:00+00:00'),
            e(3, 'Deleted', '2026-10-10T09:20:00+00:00', '2026-10-10T09:22:00+00:00', isDeleted=True),
            e(4, 'Missing time', None, '2026-10-10T09:30:00+00:00', isComplete=True)]),
        'b.json': doc('b', 'Offset / overnight', [
            e(1, 'case alpha', '2026-10-10T05:30:00-04:00', '2026-10-10T05:31:01-04:00', logged=True),
            e(2, 'CASE ALPHA', '2026-10-09T23:59:30-04:00', '2026-10-10T00:00:31-04:00'),
            e(3, 'DST fall', '2026-11-01T01:30:00-04:00', '2026-11-01T01:31:00-05:00'),
            e(4, 'DST spring', '2026-03-08T01:30:00-05:00', '2026-03-08T03:00:00-04:00')]),
        'text.json': doc('=1+1', '+Unicode session', [
            e(1, '@formula', '2026-10-10T09:40:00+00:00', '2026-10-10T09:40:01+00:00', description='=danger'),
            e(2, '<img src=x onerror="window.injected=true">' + 'L' * 100,
              '2026-10-10T09:50:00+00:00', '2026-10-10T09:50:01+00:00',
              description='<script>window.injected=true</script>' + 'D' * 100)]),
        'future.json': dict(schemaVersion=99, sessionId='future'),
    }
    for filename, doc in samples.items():
        (folder / filename).write_text(json.dumps(doc, ensure_ascii=False), encoding='utf-8')
    (folder / 'broken.json').write_bytes(b'{invalid fixture')


class DialogBoundary:
    def __init__(self, root):
        self.root = root
        self.mode = 'cancel'

    def create_file_dialog(self, kind, **kwargs):
        if kind != 'SAVE':
            raise AssertionError('not a Save dialog')
        if self.mode == 'cancel':
            return None
        if self.mode in ('save', 'write_failure'):
            return (str(self.root / 'exports/history.csv'),)
        if self.mode == 'invalid':
            return (str(self.root / 'sessions/invalid.csv'),)
        raise OSError('native dialog unavailable fixture')

    def move(self, *args):
        pass
    resize = minimize = destroy = move


class Relay:
    def __init__(self, evidence):
        self.tmp = tempfile.TemporaryDirectory(prefix='ttk-real-api-relay-')
        self.root = Path(self.tmp.name)
        (self.root / 'sessions').mkdir()
        (self.root / 'exports').mkdir()
        self.evidence = evidence
        evidence.mkdir(parents=True, exist_ok=True)
        self.log = evidence / 'relay-calls.jsonl'
        if self.log.exists():
            raise ValueError('Choose a NEW evidence directory; never overwrite a prior run')
        self.log.touch()
        self.clock = main._FixedClock(datetime(2026, 10, 10, 12, tzinfo=timezone.utc))
        os.environ[main.DATA_DIR_ENV] = str(self.root / 'sessions')
        os.environ['LOCALAPPDATA'] = str(self.root)
        self.preferences = self.root / 'preferences.json'
        self.preferences.write_text('{}', encoding='utf-8')
        seed(self.root / 'sessions')
        self.api = main.Api(str(self.root / 'sessions'), str(self.preferences), location_locked=True)
        self.api.core._clock = self.clock
        self.window = DialogBoundary(self.root)
        self.api.set_window(self.window)
        sys.modules['webview'] = SimpleNamespace(FileDialog=SimpleNamespace(SAVE='SAVE'))
        self.scan_fault = None

    def snapshot(self):
        hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in sorted(self.api.core._store.directory.glob('*'))
                  if p.is_file() and not p.is_symlink()}
        return dict(state=self.api.get_state(),
                    document=self.api.core._session.to_document() if self.api.core._session else None,
                    hashes=hashes, preferencesHash=hashlib.sha256(self.preferences.read_bytes()).hexdigest())

    def _exports_hashes(self):
        d = self.root / 'exports'
        return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(d.iterdir()) if p.is_file()}

    def call(self, method, args):
        before = self.snapshot()
        exports_before = self._exports_hashes()
        scan_fault_info = None
        if self.scan_fault and method in ('get_history', 'save_history_csv'):
            mode = self.scan_fault
            target = self.api.core._store.directory
            real_scandir = os.scandir
            yielded_names = []
            attempted = False
            closed = False
            _late_ref = [None]
            if mode == 'open':
                def _fake(path, *a, **kw):
                    nonlocal attempted
                    if Path(os.fspath(path)) == target:
                        attempted = True
                        raise PermissionError(errno.EACCES, 'Permission denied', str(path))
                    return real_scandir(path, *a, **kw)
            else:
                class _Late:
                    def __init__(self, it):
                        self._it = it
                        self._saw_json = False
                        self.closed = False
                    def __enter__(self): return self
                    def __exit__(self, *exc):
                        self._it.close()
                        self.closed = True
                        return False
                    def __iter__(self): return self
                    def __next__(self):
                        if self._saw_json:
                            raise OSError(errno.EIO, 'I/O error')
                        e = next(self._it)
                        if e.name.endswith('.json'):
                            self._saw_json = True
                            yielded_names.append(e.name)
                        return e
                    def close(self):
                        self._it.close()
                        self.closed = True
                def _fake(path, *a, **kw):
                    nonlocal attempted
                    if Path(os.fspath(path)) == target:
                        attempted = True
                        _late_ref[0] = _Late(real_scandir(path, *a, **kw))
                        return _late_ref[0]
                    return real_scandir(path, *a, **kw)
            with patch.object(os, 'scandir', _fake):
                result = getattr(self.api, method)(*args)
            if mode == 'late':
                closed = _late_ref[0].closed if _late_ref[0] else False
            scan_fault_info = dict(mode=mode, attempted=attempted, yielded=yielded_names,
                                   closed=closed, exportsBefore=exports_before)
        elif method == 'save_history_csv' and self.window.mode == 'write_failure':
            with patch.object(history_export.os, 'replace', side_effect=OSError('injected atomic write failure')):
                result = getattr(self.api, method)(*args)
        else:
            result = getattr(self.api, method)(*args)
        after = self.snapshot()
        exports_after = self._exports_hashes()
        readonly = method in ('get_history', 'save_history_csv')
        passed = not readonly or before == after
        item = dict(method=method, args=args, result=result, before=before, after=after,
                    readOnly=readonly, invariantPassed=passed)
        if scan_fault_info:
            scan_fault_info['exportsAfter'] = exports_after
            item['scanFault'] = scan_fault_info
        with self.log.open('a', encoding='utf-8') as handle:
            handle.write(json.dumps(item, ensure_ascii=False) + '\n')
        if not passed:
            raise AssertionError('Report/export mutated state/document/hash: ' + method)
        if scan_fault_info:
            sf = item['scanFault']
            assert sf['attempted'], 'scanFault not attempted'
            if sf['mode'] == 'late':
                assert sf['yielded'], 'late yielded no .json'
                assert sf['closed'], 'late not closed'
            assert result.get('ok') is False, 'fault result must not be ok'
            assert result.get('error') == 'internal_error', 'fault error code'
            assert result.get('message'), 'fault message nonempty'
            for k in ('report', 'csv', 'path', 'state'):
                assert k not in result, 'fault result has ' + k
            assert sf['exportsBefore'] == sf['exportsAfter'], 'exports changed during fault'
        return result

    def details(self):
        snap = self.snapshot()
        proc = subprocess.run([sys.executable, str(ROOT / 'tools/history_fresh_readback.py'),
                               str(self.api.core._store.directory), str(self.preferences)],
                              capture_output=True, encoding='utf-8', timeout=20)
        if proc.returncode:
            raise RuntimeError(proc.stderr)
        if snap != self.snapshot():
            raise AssertionError('Fresh process readback mutated data')
        dest = self.root / 'exports/history.csv'
        text = dest.read_text(encoding='utf-8-sig') if dest.exists() else None
        return dict(**snap, fresh=json.loads(proc.stdout), csv=text,
                    csvRows=list(csv.DictReader(io.StringIO(text, newline=''))) if text else [],
                    exportFiles=[p.name for p in (self.root / 'exports').iterdir()],
                    dialogMode=self.window.mode, dataRoot=str(self.root))


def bootstrap():
    return ('<script>window.__relayCalls=[];window.__relayErrors=[];'
            'window.addEventListener("error",e=>window.__relayErrors.push(e.message));'
            'window.addEventListener("unhandledrejection",e=>window.__relayErrors.push(String(e.reason)));'
            'window.pywebview={api:{}};for(const n of ' + json.dumps(METHODS) + '){'
            'window.pywebview.api[n]=async(...args)=>{const r=await fetch("/api/"+n,{method:"POST",'
            'headers:{"Content-Type":"application/json"},body:JSON.stringify(args)});'
            'if(!r.ok)throw new Error(await r.text());const result=await r.json();'
            'window.__relayCalls.push({method:n,args,result});return result;};}'
            'window.addEventListener("DOMContentLoaded",()=>window.dispatchEvent(new Event("pywebviewready")));'
            '</script>')


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def send(self, content, mime='application/json; charset=utf-8', code=200):
        if isinstance(content, (dict, list)):
            content = json.dumps(content, ensure_ascii=False).encode('utf-8')
        if isinstance(content, str):
            content = content.encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(content)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(content)

    def do_GET(self):
        path = unquote(urlsplit(self.path).path)
        try:
            with LOCK:
                if path == '/__test__/health':
                    self.send(dict(ok=True, contract=main.CONTRACT_VERSION, dataRoot=str(self.server.relay.root)))
                    return
                if path == '/__test__/snapshot':
                    self.send(self.server.relay.details())
                    return
                if path == '/__test__/probe.js':
                    self.send((ROOT / 'tools/history_frontend_probe.js').read_bytes(), 'text/javascript; charset=utf-8')
                    return
                if path in ('/', '/index.html'):
                    html = (ROOT / 'web/index.html').read_text(encoding='utf-8')
                    # Inject only the transport; app/history assets and rendering are unmodified.
                    self.send(html.replace('</body>', bootstrap() + '</body>'), 'text/html; charset=utf-8')
                    return
                web = (ROOT / 'web').resolve()
                asset = (web / path.lstrip('/')).resolve()
                if not asset.is_relative_to(web) or not asset.is_file():
                    self.send(dict(error='not found'), code=404)
                    return
                mime = {'.js': 'text/javascript', '.css': 'text/css'}.get(asset.suffix,
                         mimetypes.guess_type(str(asset))[0] or 'application/octet-stream')
                self.send(asset.read_bytes(), mime)
        except Exception as exc:
            self.send(dict(error=str(exc)), code=500)

    def do_POST(self):
        try:
            # Localhost-only dev harness. Reject cross-origin web requests and huge bodies.
            origin = self.headers.get('Origin')
            if origin and origin != 'http://' + self.headers.get('Host', ''):
                self.send(dict(error='cross-origin request'), code=403)
                return
            size = int(self.headers.get('Content-Length', '0'))
            if not 0 < size <= 1024 * 1024:
                raise ValueError('bounded JSON body required')
            body = json.loads(self.rfile.read(size))
            path = urlsplit(self.path).path
            with LOCK:
                if path.startswith('/api/'):
                    method = path[5:]
                    if method not in METHODS or not isinstance(body, list):
                        raise ValueError('method/arguments not allowed')
                    self.send(self.server.relay.call(method, body))
                elif path == '/__test__/dialog':
                    mode = body['mode']
                    if mode not in ('cancel', 'save', 'invalid', 'unavailable', 'write_failure'):
                        raise ValueError('bad dialog mode')
                    self.server.relay.window.mode = mode
                    self.send(dict(ok=True))
                elif path == '/__test__/scan-fault':
                    mode = body['mode']
                    if mode not in ('none', 'open', 'late'):
                        raise ValueError('bad scan-fault mode')
                    self.server.relay.scan_fault = None if mode == 'none' else mode
                    self.send(dict(ok=True))
                elif path == '/__test__/advance':
                    seconds = body['seconds']
                    if not isinstance(seconds, int) or not 0 <= seconds <= 86400:
                        raise ValueError('bad clock advance')
                    self.server.relay.clock.advance(seconds=seconds)
                    self.send(dict(ok=True))
                elif path == '/__test__/receipt':
                    (self.server.relay.evidence / 'frontend-results.json').write_text(
                        json.dumps(body, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
                    self.send(dict(ok=True))
                elif path == '/__test__/shutdown':
                    self.send(dict(ok=True))
                    threading.Thread(target=self.server.shutdown, daemon=True).start()
                else:
                    self.send(dict(error='not found'), code=404)
        except Exception as exc:
            self.send(dict(error=str(exc)), code=500)


def run():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=18742)
    parser.add_argument('--evidence-dir', type=Path, required=True)
    args = parser.parse_args()
    main.check_contract_version()
    relay = Relay(args.evidence_dir.resolve())
    server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    server.relay = relay
    print(json.dumps(dict(url='http://127.0.0.1:' + str(server.server_port), dataRoot=str(relay.root))), flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()
        relay.tmp.cleanup()


if __name__ == '__main__':
    run()

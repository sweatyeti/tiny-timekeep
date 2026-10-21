"""Production frontend pagination with real API session records; not a visual test."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from main import Api

ROOT = Path(__file__).resolve().parents[1]
NODE = r"""
const fs = require('fs'), vm = require('vm'), assert = require('assert');
const sessions = JSON.parse(fs.readFileSync(0, 'utf8'));
function element() {
  return {children: [], _html: '', textContent: '',
    set innerHTML(v) { this._html = v; this.children = []; },
    get innerHTML() { return this._html; },
    appendChild(v) { this.children.push(v); },
    querySelector() { return this.button ||= {}; }};
}
const list = element();
let resumed = null;
const ctx = {document: {getElementById() { return list; }, createElement: element}, console};
ctx.window = {addEventListener() {}, pywebview: {api: {
  list_sessions: async () => sessions,
  resume_session: async id => { resumed = id; return {}; }
}}};
vm.createContext(ctx);
vm.runInContext(fs.readFileSync(process.argv[1], 'utf8'), ctx);
vm.runInContext('handleResult = () => {};', ctx);
const rows = () => list.children.filter(e => e.className === 'session-item');
const more = () => list.children.find(e => e.textContent === 'Show more');
(async () => {
  await vm.runInContext('renderSessionList()', ctx);
  assert.equal(rows().length, Math.min(5, sessions.length), 'initial five');
  assert.equal(Boolean(more()), sessions.length > 5);
  if (!sessions.length) assert.match(list.innerHTML, /No saved sessions yet/);
  let visible = 5;
  while (more()) {
    await more().onclick();
    visible += 5;
    assert.equal(rows().length, Math.min(visible, sessions.length));
    await vm.runInContext('renderSessionList()', ctx);
    assert.equal(rows().length, Math.min(visible, sessions.length), 'refresh preserves expansion');
    assert.equal(Boolean(more()), sessions.length > visible);
  }
  assert.equal(resumed, null, 'paging must not resume');
  for (let i = 0; i < rows().length; i++) {
    assert.ok(rows()[i].innerHTML.includes(sessions[i].name), 'API ordering preserved');
    await rows()[i].querySelector('button').onclick();
    assert.equal(resumed, sessions[i].id, 'resume targets exact displayed record');
  }
})().catch(e => { console.error(e); process.exitCode = 1; });
"""

class SessionPaginationTests(unittest.TestCase):
    def test_page_boundaries_and_resume(self):
        for count in (0, 1, 4, 5, 6, 10, 11, 16):
            with self.subTest(count=count), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                api = Api(str(root / 'sessions'), str(root / 'prefs.json'))
                for i in range(count):
                    now = datetime(2026, 10, 1, tzinfo=timezone.utc) + timedelta(days=i)
                    api.core._clock = lambda: now
                    self.assertTrue(api.start_session(f'Session {i:02}', 'Work')['ok'])
                    self.assertTrue(api.stop_and_exit()['ok'])
                before = {str(p): p.read_bytes() for p in root.rglob('*') if p.is_file()}
                state = api.get_state()
                process = subprocess.run(['node', '-e', NODE, str(ROOT / 'web/app.js')],
                                         input=json.dumps(api.list_sessions()), text=True,
                                         encoding='utf-8', capture_output=True, timeout=30)
                self.assertEqual(process.returncode, 0, process.stderr)
                self.assertEqual(api.get_state(), state)
                self.assertEqual({str(p): p.read_bytes() for p in root.rglob('*') if p.is_file()}, before)

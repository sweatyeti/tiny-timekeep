"""Current-task totals: real Api/core snapshots rendered by the production JS.

Node supplies only a minimal DOM for this fast suite. Rendering and end-to-end
bridge checks are deliberately left to the user; these tests do not prove pixels.
"""
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from main import Api

ROOT = Path(__file__).resolve().parents[1]
NODE = r"""
const fs = require('fs'), vm = require('vm');
const states = JSON.parse(fs.readFileSync(0, 'utf8'));
const elements = {};
function element(id) {
  const classes = new Set(id.startsWith('current-task-') ? ['hidden'] : []);
  return {textContent: '', title: '', attrs: {},
    classList: {
      add: n => classes.add(n), remove: n => classes.delete(n),
      contains: n => classes.has(n),
      toggle(n, on) { if (on) classes.add(n); else classes.delete(n); }
    },
    setAttribute(n, v) { this.attrs[n] = v; },
    querySelector() { return null; }
  };
}
const ctx = {document: {getElementById(id) { return elements[id] ||= element(id); }},
  Date, console, setInterval, clearInterval};
ctx.window = {addEventListener() {}, pywebview: {api: new Proxy({}, {
  get() { throw new Error('Display must not call an API'); }
})}};
vm.createContext(ctx);
vm.runInContext(fs.readFileSync(process.argv[1], 'utf8'), ctx);
const out = states.map(s => {
  ctx.input = s;
  vm.runInContext('state = input; renderCurrent();', ctx);
  const get = id => ctx.document.getElementById(id);
  const totals = get('current-task-totals');
  return {hidden: totals.classList.contains('hidden'), title: totals.title,
    aria: totals.attrs['aria-label'] || '',
    unlogged: get('current-task-unlogged').textContent,
    total: get('current-task-total').textContent};
});
process.stdout.write(JSON.stringify(out));
"""


class CurrentTaskTotalsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.api = Api(str(self.root / 'sessions'), str(self.root / 'prefs.json'))
        self.now = datetime(2026, 10, 13, 9, tzinfo=timezone.utc)
        self.api.core._clock = lambda: self.now
        self.ok(self.api.start_session('Totals fixture', 'Work'))

    def ok(self, result):
        self.assertTrue(result['ok'], result)
        return result['state']

    def advance(self, seconds):
        self.now += timedelta(seconds=seconds)

    def files(self):
        return {str(p.relative_to(self.root)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in self.root.rglob('*') if p.is_file()}

    def render(self, *states):
        before = (self.api.get_state(), self.files())
        process = subprocess.run(['node', '-e', NODE, str(ROOT / 'web/app.js')],
                                 input=json.dumps(states or [self.api.get_state()]),
                                 text=True, encoding='utf-8', capture_output=True, timeout=30)
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual((self.api.get_state(), self.files()), before)
        return json.loads(process.stdout)

    def history(self):
        # Each completed entry rounds separately: 61s -> 2m and 1s -> 1m.
        self.advance(61)
        self.ok(self.api.stop_and_start_entry('wOrK'))
        self.ok(self.api.edit_entry(1, logged=True))
        self.advance(1)
        self.ok(self.api.stop_and_start_entry('WORK'))

    def assert_totals(self, row, unlogged, total):
        self.assertFalse(row['hidden'])
        self.assertEqual(row['unlogged'], 'U ' + unlogged)
        self.assertEqual(row['total'], 'T ' + total)
        self.assertIn('U = unlogged time', row['title'])
        self.assertIn('T = total time', row['title'])
        self.assertIn('current session', row['title'])
        self.assertIn('completed entries only', row['title'])
        self.assertIn('running timer is excluded', row['title'])
        self.assertEqual(row['aria'], row['title'])

    def test_new_task_has_no_totals(self):
        row = self.render()[0]
        self.assertTrue(row['hidden'])
        self.assertEqual(row['unlogged'], '')
        self.assertEqual(row['total'], '')

    def test_matches_case_and_uses_completed_core_rounding_not_live_time(self):
        self.history()
        before = self.api.get_state()
        self.advance(7200)
        self.assert_totals(self.render()[0], '0h 1m', '0h 3m')
        self.assertEqual(self.api.get_state(), before)

    def test_log_unlog_updates_including_zero_unlogged(self):
        self.history()
        logged = self.ok(self.api.log_task_group('Work'))
        unlogged = self.ok(self.api.unlog_task_group('WORK'))
        rows = self.render(logged, unlogged)
        self.assert_totals(rows[0], '0h 0m', '0h 3m')
        self.assert_totals(rows[1], '0h 3m', '0h 3m')

    def test_delete_last_completed_hides_and_restore_reveals(self):
        self.history()
        self.ok(self.api.delete_entry(1))
        empty = self.ok(self.api.delete_entry(2))
        restored = self.ok(self.api.restore_entry(1))
        rows = self.render(empty, restored)
        self.assertTrue(rows[0]['hidden'])
        self.assert_totals(rows[1], '0h 0m', '0h 2m')

    def test_rename_current_and_completed_entries_refreshes_match(self):
        self.history()
        other = self.ok(self.api.edit_entry(3, task='Elsewhere'))
        moved = self.ok(self.api.edit_entry(2, task='ELSEWHERE'))
        rows = self.render(other, moved)
        self.assertTrue(rows[0]['hidden'])
        self.assert_totals(rows[1], '0h 1m', '0h 1m')

    def test_switching_to_task_without_history_clears_old_values(self):
        self.history()
        work = self.api.get_state()
        other = self.ok(self.api.stop_and_start_entry('Different'))
        rows = self.render(work, other)
        self.assertFalse(rows[0]['hidden'])
        self.assertTrue(rows[1]['hidden'])
        self.assertEqual(rows[1]['title'], '')
        self.assertEqual(rows[1]['unlogged'], '')
        self.assertEqual(rows[1]['total'], '')

    def test_stop_and_close_clear_totals(self):
        self.history()
        active = self.api.get_state()
        stopped = self.ok(self.api.stop_tracking())
        closed = self.ok(self.api.stop_and_exit())
        rows = self.render(active, stopped, closed)
        self.assertFalse(rows[0]['hidden'])
        for row in rows[1:]:
            self.assertTrue(row['hidden'])
            self.assertEqual(row['unlogged'], '')
            self.assertEqual(row['total'], '')
            self.assertEqual(row['title'], '')

    def test_other_sessions_excluded_and_resumed_history_included(self):
        self.history()
        session_id = self.api.get_state()['session']['id']
        self.advance(1)  # A zero-duration completed entry legitimately contributes zero.
        self.ok(self.api.stop_and_exit())
        fresh = self.ok(self.api.start_session('Separate session', 'WORK'))
        self.ok(self.api.stop_and_exit())
        self.ok(self.api.resume_session(session_id))
        resumed = self.ok(self.api.stop_and_start_entry('work'))
        rows = self.render(fresh, resumed)
        self.assertTrue(rows[0]['hidden'])
        self.assert_totals(rows[1], '0h 2m', '0h 4m')

    def test_unnamed_uses_its_summary_group_not_session_grand_totals(self):
        self.ok(self.api.edit_entry(1, task=''))
        self.advance(61)
        self.ok(self.api.stop_and_start_entry(None))
        self.assert_totals(self.render()[0], '0h 2m', '0h 2m')

    def test_zero_duration_history_is_visible_and_not_rounded_up_to_one(self):
        self.ok(self.api.stop_and_start_entry('Work'))
        self.assert_totals(self.render()[0], '0h 0m', '0h 0m')

    def test_hour_format_does_not_wrap_at_one_day(self):
        self.advance(90060)
        self.ok(self.api.stop_and_start_entry('Work'))
        self.assert_totals(self.render()[0], '25h 1m', '25h 1m')


if __name__ == '__main__':
    unittest.main()

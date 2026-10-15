"""Fast compact-mode guards; browser interaction checks live in tools/check_compact_now.py."""
import ast
import json
from pathlib import Path
import re
import subprocess
import unittest
from main import Api

ROOT = Path(__file__).resolve().parents[1]


class CompactNowTests(unittest.TestCase):
    def test_elapsed_duration_is_not_a_clock_time(self):
        source = ROOT / 'web/compact.js'
        self.assertTrue(source.exists(), 'compact mode script missing')
        script = "const vm=require('vm'),fs=require('fs'); const c={};vm.createContext(c);vm.runInContext(fs.readFileSync(process.argv[1],'utf8'),c); console.log(JSON.stringify([0,1,3599,3600,90061,360000,-1].map(c.compactDuration)));"
        p = subprocess.run(['node', '-e', script, str(source)], capture_output=True,
                           text=True, encoding='utf-8', timeout=30)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(json.loads(p.stdout), ['00:00:00','00:00:01','00:59:59','01:00:00','25:01:01','100:00:00','00:00:00'])

    def test_compact_is_wired_and_uses_only_existing_api(self):
        html = (ROOT / 'web/index.html').read_text(encoding='utf-8')
        self.assertIn('src="compact.js"', html)
        for name in ['compact-toggle', 'compact-strip', 'compact-task', 'compact-elapsed', 'compact-stop', 'compact-expand']:
            self.assertIn(f'id="{name}"', html)
        js = (ROOT / 'web/compact.js').read_text(encoding='utf-8')
        calls = set(re.findall(r'api\(\)\.(\w+)', js))
        self.assertIn('stop_and_start_entry', calls)
        self.assertIn('resize_window_to', calls)
        self.assertTrue(all(hasattr(Api, m) for m in calls), calls)
        self.assertFalse(calls & {'edit_entry','start_session','set_preference','stop_and_exit'})
        app = (ROOT / 'web/app.js').read_text(encoding='utf-8')
        for hook in ['wireCompactMode()', 'renderCompactMode()', 'updateCompactElapsed()', 'compactOverlayChanged(true)', 'compactOverlayChanged(false)']:
            self.assertIn(hook, app)

    def test_native_minimum_allows_compact_height(self):
        tree = ast.parse((ROOT / 'main.py').read_text(encoding='utf-8'))
        create = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == 'create_window']
        self.assertEqual(len(create), 1)
        size = ast.literal_eval(next(k.value for k in create[0].keywords if k.arg == 'min_size'))
        self.assertLessEqual(size[1], 80)
        self.assertEqual(size[0], 300)


if __name__ == '__main__':
    unittest.main()

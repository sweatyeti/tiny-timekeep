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
        script = "const vm=require('vm'),fs=require('fs'); const c={};vm.createContext(c);vm.runInContext(fs.readFileSync(process.argv[1],'utf8'),c); console.log(JSON.stringify([0,0.01,1,60,60.01,3599,3600,11101,11160,90061,360000,-1].map(c.compactDuration)));"
        p = subprocess.run(['node', '-e', script, str(source)], capture_output=True,
                           text=True, encoding='utf-8', timeout=30)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(json.loads(p.stdout), ['0h 0m','0h 1m','0h 1m','0h 1m','0h 2m','1h 0m','1h 0m','3h 6m','3h 6m','25h 2m','100h 0m','0h 0m'])

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

    def test_compact_width_resize_changes_width_only_and_persists(self):
        source = ROOT / 'web/compact.js'
        script = (
            "const vm=require('vm'),fs=require('fs'); const calls=[];"
            "const c={console,Math,Number,window:{outerHeight:90,addEventListener(){}},"
            "api:()=>({resize_window_to:(w,h)=>{calls.push([w,h]);}})};"
            "vm.createContext(c);vm.runInContext(fs.readFileSync(process.argv[1],'utf8'),c);"
            "vm.runInContext('compactFullSize={width:380,height:680};compactResizeWidth(500.4);compactResizeWidth(250);',c);"
            "console.log(JSON.stringify({width:vm.runInContext('compactFullSize.width',c),calls}));"
        )
        p = subprocess.run(['node', '-e', script, str(source)], capture_output=True,
                           text=True, encoding='utf-8', timeout=30)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(json.loads(p.stdout),
                         {'width': 300, 'calls': [[500, 90], [300, 90]]})

    def test_compact_width_resize_is_wired(self):
        app = (ROOT / 'web/app.js').read_text(encoding='utf-8')
        self.assertIn("classList.contains('compact-now')", app)
        self.assertIn('compactResizeWidth(targetW)', app)
        css = (ROOT / 'web/compact.css').read_text(encoding='utf-8')
        self.assertIn('cursor: ew-resize', css)
        grip_rule = re.search(r'\.compact-now #resize-grip\s*\{([^}]*)\}', css)
        self.assertIsNotNone(grip_rule, 'compact mode must style the resize grip')
        self.assertNotIn('display: none', grip_rule.group(1),
                         'the grip must stay reachable in compact mode, not hidden')


if __name__ == '__main__':
    unittest.main()

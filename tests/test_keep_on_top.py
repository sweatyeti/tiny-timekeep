import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from main import Api
from preferences import PreferencesStore
from window_topmost import apply_topmost


class KeepOnTopTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = str(Path(self.temp.name) / 'preferences.json')
        self.api = Api(str(Path(self.temp.name) / 'sessions'), self.path)
        self.window = SimpleNamespace(on_top=False)
        self.api.set_window(self.window)

    def test_default_and_invalid_saved_values(self):
        self.assertIs(self.api.get_preferences()['keepOnTop'], False)
        for value in [1, 'true', None, [], {}]:
            with self.subTest(value=value):
                Path(self.path).write_text(json.dumps({'keepOnTop': value}))
                self.assertIs(PreferencesStore(self.path).get_all()['keepOnTop'], False)

    def test_toggle_persists_without_changing_session(self):
        self.api.start_session('test', 'task')
        before = {p.name: p.read_bytes() for p in Path(self.temp.name, 'sessions').glob('*')}
        with patch('main.apply_topmost', side_effect=lambda w, v: setattr(w, 'on_top', v)):
            for value in [True, False, True]:
                result = self.api.set_preference('keepOnTop', value)
                self.assertTrue(result['ok'], result)
                self.assertIs(self.window.on_top, value)
                self.assertIs(PreferencesStore(self.path).get_all()['keepOnTop'], value)
        self.assertEqual(before, {p.name: p.read_bytes() for p in Path(self.temp.name, 'sessions').glob('*')})

    def test_invalid_requests_never_touch_native_window(self):
        with patch('main.apply_topmost') as apply:
            for value in [1, 0, 'true', None, []]:
                self.assertFalse(self.api.set_preference('keepOnTop', value)['ok'])
            apply.assert_not_called()

    def test_save_failure_rolls_back_memory_native_and_disk(self):
        self.api.prefs.set('keepOnTop', False)
        before = Path(self.path).read_bytes()
        with patch('main.apply_topmost', side_effect=lambda w, v: setattr(w, 'on_top', v)), patch('preferences.os.replace', side_effect=OSError('disk failure')):
            self.assertFalse(self.api.set_preference('keepOnTop', True)['ok'])
        self.assertIs(self.window.on_top, False)
        self.assertIs(self.api.get_preferences()['keepOnTop'], False)
        self.assertEqual(Path(self.path).read_bytes(), before)

    def test_native_failure_does_not_save(self):
        with patch('main.apply_topmost', side_effect=RuntimeError('native failure')), patch.object(self.api.prefs, 'set') as save:
            result = self.api.set_preference('keepOnTop', True)
            self.assertFalse(result['ok'])
            self.assertIn('native failure', result['message'])
            save.assert_not_called()

    def test_windows_marshals_to_ui_thread(self):
        calls = []
        form = SimpleNamespace(IsDisposed=False, IsHandleCreated=True, InvokeRequired=True, TopMost=False)
        class Window:
            native = form
            @property
            def on_top(self):
                return form.TopMost
            @on_top.setter
            def on_top(self, value):
                self.assert_ui()
                form.TopMost = value
            def assert_ui(self):
                if not calls or calls[-1] != 'UI':
                    raise AssertionError('unsafe worker-thread write')
        def invoke(action):
            calls.append('UI')
            action()
        form.Invoke = invoke
        with patch('window_topmost.sys.platform', 'win32'), patch.dict('sys.modules', {'System': SimpleNamespace(Action=lambda f: f)}):
            apply_topmost(Window(), True)
        self.assertEqual(calls, ['UI'])
        self.assertTrue(form.TopMost)

    def test_missing_window_rejected(self):
        with self.assertRaisesRegex(RuntimeError, 'not ready'):
            apply_topmost(None, True)

    def test_frontend_and_startup_wiring(self):
        root = Path(__file__).resolve().parents[1]
        self.assertIn('on_top=api.prefs.get_all()["keepOnTop"]', (root/'main.py').read_text(encoding='utf-8'))
        html = (root/'web/index.html').read_text(encoding='utf-8')
        self.assertIn('id="keep-on-top-btn"', html)
        js = (root/'web/app.js').read_text(encoding='utf-8')
        self.assertIn('renderKeepOnTop(prefs);', js)
        self.assertIn("api().set_preference('keepOnTop',", js)
        self.assertIn('if (pin.disabled) return;', js)
        self.assertIn('if (result.ok) renderKeepOnTop(result.preferences)', js)

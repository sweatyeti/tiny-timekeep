"""Opt-in Windows/WebView2 integration probe, run twice with shared scratch prefs.
Usage: python tests/native_keep_on_top_probe.py PATH_TO_SCRATCH first|restart
Not unittest-discovered: requires a native GUI backend. Never uses real user data.
"""
import ctypes
import json
import sys
import threading
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import main
import webview

scratch = Path(sys.argv[1]).resolve()
scratch.mkdir(parents=True, exist_ok=True)
phase = sys.argv[2]
api = main.Api(str(scratch/'sessions'), str(scratch/'preferences.json'))
api.start_session('Topmost verification', 'test')
initial = api.get_preferences()['keepOnTop']
w = webview.create_window('TTK topmost probe', main.INDEX_HTML, js_api=api,
                          frameless=True, easy_drag=False, width=380, height=680,
                          min_size=(300,80), on_top=initial)
api.set_window(w)
report = {'phase': phase, 'startup_preference': initial, 'checks': []}


def run():
    try:
        from System import Action
        from System.Windows.Forms import Control
        Control.CheckForIllegalCrossThreadCalls = True
        deadline = time.monotonic()+90
        while time.monotonic()<deadline:
            if w.evaluate_js("!!document.getElementById('keep-on-top-btn') && !document.getElementById('keep-on-top-btn').disabled"):
                break
            time.sleep(.1)
        else:
            raise AssertionError('UI not ready')
        native = w.native
        handles = []
        native.Invoke(Action(lambda: handles.append(native.Handle.ToInt64())))
        user32 = ctypes.WinDLL('user32', use_last_error=True)
        get_style = user32.GetWindowLongW
        get_style.argtypes = [ctypes.c_void_p, ctypes.c_int]
        get_style.restype = ctypes.c_long
        def topmost():
            return bool(get_style(handles[0], -20) & 8)
        def check(value, label):
            assert topmost() is value, (label, 'native style', topmost(), value)
            assert w.evaluate_js("document.getElementById('keep-on-top-btn').getAttribute('aria-pressed')") == str(value).lower()
            report['checks'].append(label)
        assert initial is (phase == 'restart')
        check(initial, 'startup native style and button')
        if phase == 'first':
            # The upstream direct setter should be rejected with cross-thread checking.
            try:
                w.on_top = True
            except Exception as exc:
                report['upstream_cross_thread_error'] = str(exc)
            else:
                report['upstream_cross_thread_error'] = 'not reproduced'
            main.apply_topmost(w, initial)
        snapshot = {p.name:p.read_bytes() for p in (scratch/'sessions').glob('*.json')}
        values = ([True, False]*10+[True]) if phase == 'first' else [False, True, False]
        for i, value in enumerate(values):
            w.evaluate_js("window.__pinDone=false; document.getElementById('keep-on-top-btn').onclick().then(()=>window.__pinDone=true)")
            deadline=time.monotonic()+10
            while not w.evaluate_js('window.__pinDone'):
                assert time.monotonic()<deadline, 'bridge toggle timeout'
                time.sleep(.02)
            check(value, f'bridge toggle {i}: {value}')
            assert json.loads((scratch/'preferences.json').read_text())['keepOnTop'] is value
        # Topmost was stress-tested with strict cross-thread checks. Existing
        # pywebview resize accesses Handle off-thread too; that unrelated upstream
        # path is outside this feature. Restore its normal setting for layout checks.
        Control.CheckForIllegalCrossThreadCalls = False
        # The same titlebar toggle remains available in compact mode at minimum width.
        w.evaluate_js("document.getElementById('compact-toggle').click()")
        time.sleep(.4)
        w.resize(300,120)
        time.sleep(.3)
        metrics = w.evaluate_js("(()=>{const b=document.getElementById('keep-on-top-btn');const r=b.getBoundingClientRect();return {left:r.left,right:r.right,width:r.width,inner:innerWidth,display:getComputedStyle(b).display,compact:document.body.classList.contains('compact-now')}})()")
        assert metrics['width'] > 0 and metrics['left'] >= 0 and metrics['right'] <= metrics['inner'], metrics
        assert metrics['compact'], metrics
        report['compact_button_metrics'] = metrics
        # Minimize/restore must not clear the pinned state or force visibility.
        from System.Windows.Forms import Form, FormWindowState
        native.Invoke(Action(lambda: setattr(native, 'WindowState', FormWindowState.Minimized)))
        time.sleep(.1)
        native.Invoke(Action(lambda: setattr(native, 'WindowState', FormWindowState.Normal)))
        check(values[-1], 'minimize and restore preserve topmost')
        if values[-1]:
            others = []
            def show_other():
                other = Form()
                other.Text = 'Normal comparison window'
                other.Show()
                other.Activate()
                others.append(other)
            native.Invoke(Action(show_other))
            get_window = user32.GetWindow
            get_window.argtypes = [ctypes.c_void_p, ctypes.c_uint]
            get_window.restype = ctypes.c_void_p
            other_handles = []
            native.Invoke(Action(lambda: other_handles.append(others[0].Handle.ToInt64())))
            below = get_window(handles[0], 2)
            found = False
            for _ in range(200):
                if not below: break
                if below == other_handles[0]:
                    found = True
                    break
                below = get_window(below, 2)
            assert found, 'pinned window was not above the normal comparison window'
            native.Invoke(Action(others[0].Close))
            report['checks'].append('pinned window above activated non-topmost comparison form')
        assert snapshot == {p.name:p.read_bytes() for p in (scratch/'sessions').glob('*.json')}
        report['checks'].append('session bytes unchanged')
        report['ok'] = True
    except Exception:
        report['ok'] = False
        report['error'] = traceback.format_exc()
    finally:
        (scratch/f'{phase}.json').write_text(json.dumps(report,indent=2))
        w.destroy()

webview.start(run, gui='edgechromium')
print(json.dumps(report,indent=2))
sys.exit(0 if report.get('ok') else 1)

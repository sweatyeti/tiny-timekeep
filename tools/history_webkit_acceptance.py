"""Reproducible real-browser acceptance using already-installed WebKitGTK.

Run: TZ=America/New_York xvfb-run -a /usr/bin/python3 tools/history_webkit_acceptance.py
     --evidence-dir /absolute/new/evidence/dir

The browser driver uses system PyGObject; the REAL Api relay runs Python 3.14.7.
No packages, system configuration, native Windows dialog or VM are involved.
"""
import argparse
import json
import os
import platform
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('WebKit2', '4.1')
from gi.repository import GLib, Gtk, WebKit2

ROOT = Path(__file__).resolve().parents[1]


def evaluate(view, script):
    loop = GLib.MainLoop()
    box = {}
    def finished(webview, result, _):
        try:
            value = webview.evaluate_javascript_finish(result)
            box['value'] = value.to_string()
        except Exception as exc:
            box['error'] = exc
        loop.quit()
    view.evaluate_javascript(script, -1, None, None, None, finished, None)
    timeout = GLib.timeout_add_seconds(20, lambda: (box.update(error=TimeoutError('JS evaluate timeout')), loop.quit(), False)[-1])
    loop.run()
    if 'error' in box:
        raise box['error']
    GLib.source_remove(timeout)
    return box['value']


def poll(view, expression, timeout=40):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        data = json.loads(evaluate(view, 'JSON.stringify(' + expression + ')'))
        if data:
            return data
        time.sleep(.05)
    raise TimeoutError('Browser poll timeout: ' + expression)


def screenshot(view, dest):
    loop = GLib.MainLoop()
    errors = []
    def finished(webview, result, _):
        try:
            surface = webview.get_snapshot_finish(result)
            surface.write_to_png(str(dest))
        except Exception as exc:
            errors.append(str(exc))
        loop.quit()
    view.get_snapshot(WebKit2.SnapshotRegion.VISIBLE, WebKit2.SnapshotOptions.NONE,
                      None, finished, None)
    loop.run()
    if errors:
        raise RuntimeError('WebKit snapshot: ' + '; '.join(errors))


def run():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence-dir', required=True, type=Path)
    parser.add_argument('--api-python', default='python3.14')
    args = parser.parse_args()
    evidence = args.evidence_dir.resolve()
    evidence.mkdir(parents=True, exist_ok=True)
    logfile = (evidence / 'relay-process.txt').open('w', encoding='utf-8')
    relay = subprocess.Popen([args.api_python, str(ROOT / 'tools/history_browser_relay.py'),
                              '--port', '0', '--evidence-dir', str(evidence)],
                             cwd=ROOT, stdout=subprocess.PIPE, stderr=logfile,
                             text=True, encoding='utf-8')
    window = Gtk.Window()
    window.set_decorated(False)
    window.set_default_size(380, 680)
    manager = WebKit2.UserContentManager()
    # No default browser profile/cache: this task's fixtures must stay ephemeral.
    context = WebKit2.WebContext.new_ephemeral()
    view = WebKit2.WebView(web_context=context, user_content_manager=manager)
    view.set_size_request(0, 0)
    window.add(view)
    window.show_all()
    loaded = GLib.MainLoop()
    load_errors = []
    def on_load(webview, event):
        if event == WebKit2.LoadEvent.FINISHED:
            loaded.quit()
    def on_fail(webview, event, uri, error):
        load_errors.append(str(error))
        loaded.quit()
        return False
    view.connect('load-changed', on_load)
    view.connect('load-failed', on_fail)
    result = dict(ok=False, driverPython=sys.version, platform=platform.platform(),
                  engine='WebKitGTK ' + '.'.join(str(x) for x in (WebKit2.get_major_version(), WebKit2.get_minor_version(), WebKit2.get_micro_version())),
                  layouts=[], limits='Linux real-browser/real Python Api only. Native Save boundary substituted; no Windows/WebView2/native executable verification.')
    try:
        line = relay.stdout.readline()
        if not line:
            raise RuntimeError('Relay failed to start; see relay-process.txt')
        startup = json.loads(line)
        logfile.write(line)
        logfile.flush()
        url = startup['url']
        with urllib.request.urlopen(url + '/__test__/health', timeout=10) as response:
            health = json.load(response)
        result['health'] = health
        print('Real Api relay health:', json.dumps(health), flush=True)
        view.load_uri(url)
        timeout = GLib.timeout_add_seconds(60, lambda: (load_errors.append('Page load timed out'), loaded.quit(), False)[-1])
        loaded.run()
        GLib.source_remove(timeout)
        if load_errors:
            raise RuntimeError('Page load: ' + '; '.join(load_errors))
        evaluate(view, (ROOT / 'tools/history_frontend_probe.js').read_text(encoding='utf-8') + '\n;null;')
        evaluate(view, 'window.__driverDone=false;runHistoryAcceptance().then(r=>{window.__driverResult=r;window.__driverDone=true;},e=>{window.__driverResult={ok:false,error:String(e.stack||e)};window.__driverDone=true;});null;')
        acceptance = poll(view, 'window.__driverDone && window.__driverResult', timeout=150)
        result['acceptance'] = acceptance
        if not acceptance.get('ok'):
            raise AssertionError(acceptance)
        print('Frontend acceptance:', json.dumps(acceptance), flush=True)
        themes = ['cute', 'cyber', 'poolside', 'evergreen', 'citrus-pop', 'dune']
        for width, height in ((300, 420), (380, 680)):
            window.resize(width, height)
            poll(view, f'(innerWidth==={width}&&innerHeight==={height})', timeout=20)
            for theme in themes:
                evaluate(view, 'window.__layoutDone=false;measureHistoryLayout(' + json.dumps(theme) + ').then(r=>{window.__layoutResult={ok:true,result:r};window.__layoutDone=true;},e=>{window.__layoutResult={ok:false,error:String(e.stack||e)};window.__layoutDone=true;});null;')
                measured = poll(view, 'window.__layoutDone && window.__layoutResult', timeout=25)
                if not measured.get('ok'):
                    raise AssertionError(measured)
                result['layouts'].append(measured['result'])
                screenshot(view, evidence / (theme + '-' + str(width) + '.png'))
                print('Layout:', json.dumps({k:measured['result'][k] for k in ('theme','width','height','bodyClientWidth','bodyScrollWidth','scrollHeight','clientHeight')}), flush=True)
        result['ok'] = True
    except Exception as exc:
        result['error'] = repr(exc)
        try:
            result['page'] = json.loads(evaluate(view, 'JSON.stringify({url:location.href,errors:window.__relayErrors,body:document.body.innerText,acceptance:window.__historyAcceptance})'))
            screenshot(view, evidence / 'failure.png')
        except Exception as screenshot_error:
            result['screenshotError'] = repr(screenshot_error)
        print('ACCEPTANCE FAILED:', result['error'], flush=True)
    finally:
        (evidence / 'browser-results.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        window.destroy()
        if relay.poll() is None:
            # Ask the task-owned server to clean its isolated TemporaryDirectory.
            try:
                request = urllib.request.Request(url + '/__test__/shutdown', data=b'{}', headers={'Content-Type':'application/json'})
                with urllib.request.urlopen(request, timeout=5) as response:
                    response.read()
                relay.wait(timeout=10)
            except Exception:
                relay.terminate()
                relay.wait(timeout=10)
        logfile.close()
    print('Evidence:', evidence, flush=True)
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(run())

"""Run with a Python environment containing Playwright + Chromium.
Real frontend and Api/core/storage; only the native window/transport are substituted.
Not a Windows/WebView2 acceptance test. All session data is disposable.
"""
import asyncio
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
import tempfile
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from main import Api


async def run():
    with tempfile.TemporaryDirectory(prefix='ttk-compact-') as tmp:
        data = Path(tmp)
        api = Api(str(data / 'sessions'), str(data / 'prefs.json'))
        now = datetime.now(timezone.utc) - timedelta(hours=25, minutes=1, seconds=1)
        api.core._clock = lambda: now
        calls, errors, metrics = [], [], []
        fail_switch = False
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page(viewport={'width': 380, 'height': 680})
            page.on('pageerror', lambda e: errors.append(str(e)))
            # Offline fallback is intentional and deterministic; native gate also tests CDN fonts.
            await page.route('https://fonts.googleapis.com/**', lambda r: r.abort())
            async def bridge(method, args):
                calls.append((method, args))
                if method == 'resize_window_to':
                    await page.set_viewport_size({'width': int(args[0]), 'height': int(args[1])})
                    return None
                if method == 'stop_and_start_entry' and fail_switch:
                    return {'ok': False, 'error': 'injected', 'message': 'Injected save failure'}
                return getattr(api, method)(*args)
            await page.expose_function('_bridge', bridge)
            await page.add_init_script("""
                Object.defineProperty(window, 'outerWidth', {get: () => innerWidth});
                Object.defineProperty(window, 'outerHeight', {get: () => innerHeight});
                window.pywebview = {api: new Proxy({}, {get: (_, m) => (...a) => window._bridge(m,a)})};
                window.addEventListener('DOMContentLoaded', () => window.dispatchEvent(new Event('pywebviewready')));
            """)
            await page.goto((ROOT / 'web/index.html').as_uri())
            await page.wait_for_function("state !== null")
            assert await page.locator('#compact-toggle').is_disabled()
            await page.fill('#new-session-task', 'Original task')
            await page.click('#start-session-btn')
            await page.wait_for_function('state.currentEntry !== null')
            before = api.get_state()
            def files():
                return {str(f.relative_to(data)): f.read_bytes() for f in data.rglob('*.json')}
            saved = files()
            async def compact():
                await page.wait_for_function('compactApplied && !compactOverlayOpen')
                await page.evaluate('compactLayoutQueue')
            async def expanded():
                await page.wait_for_function('!compactApplied')
                await page.evaluate('compactLayoutQueue')
            await page.click('#compact-toggle')
            await compact()
            assert await page.locator('#compact-elapsed').inner_text() >= '25:01:01'
            assert not await page.locator('#app').is_visible()
            assert files() == saved and api.get_state() == before
            # All three cancellation paths must preserve the exact timer and stored bytes.
            for cancel in ['#compact-cancel', '#overlay-close', 'Escape']:
                await page.click('#compact-task')
                await expanded()
                assert page.viewport_size == {'width': 380, 'height': 680}
                assert files() == saved and api.get_state() == before
                await page.fill('#compact-next-task', 'Must not be saved')
                if cancel == 'Escape':
                    await page.keyboard.press('Escape')
                else:
                    await page.click(cancel)
                await compact()
                assert files() == saved and api.get_state() == before
            # Save failure keeps dialog/input open and timer unchanged; retry commits once.
            await page.click('#compact-task')
            await expanded()
            await page.fill('#compact-next-task', 'Next <task> & details')
            fail_switch = True
            await page.click('#compact-confirm')
            await page.wait_for_function("document.getElementById('compact-switch-error').textContent === 'Injected save failure'")
            assert files() == saved and api.get_state() == before
            assert await page.input_value('#compact-next-task') == 'Next <task> & details'
            fail_switch = False
            now += timedelta(hours=25, minutes=1, seconds=1)
            await page.keyboard.press('Enter')
            await compact()
            switched = api.get_state()
            assert switched['currentEntry']['task'] == 'Next <task> & details'
            assert len(switched['entries']) == 2
            old_entry = next(e for e in switched['entries'] if e['id'] == before['currentEntry']['id'])
            assert old_entry['endTime'] == switched['currentEntry']['startTime']
            reopened = Api(str(data / 'sessions'), str(data / 'prefs.json'))
            assert reopened.resume_session(switched['session']['id'])['ok']
            assert reopened.get_state()['currentEntry'] == switched['currentEntry']
            # Stop, stopped dialog cancellation, then start from stopped.
            await page.click('#compact-stop')
            await page.wait_for_function('state.currentEntry === null')
            assert await page.locator('#compact-elapsed').inner_text() == 'Stopped'
            assert await page.locator('#compact-stop').is_disabled()
            stopped_files = files()
            await page.click('#compact-task')
            await expanded()
            await page.click('#compact-cancel')
            await compact()
            assert files() == stopped_files and api.get_state()['currentEntry'] is None
            await page.click('#compact-task')
            await expanded()
            await page.fill('#compact-next-task', 'A very long task name ' * 12)
            await page.click('#compact-confirm')
            await compact()
            # Restore exact normal size and selected tab; collapse again at minimum width.
            await page.click('#compact-expand')
            await expanded()
            assert page.viewport_size == {'width': 380, 'height': 680}
            await page.click('[data-tab="log"]')
            await page.set_viewport_size({'width': 300, 'height': 540})
            await page.click('#compact-toggle')
            await compact()
            for theme in ['cute','cyber','poolside','evergreen','citrus-pop','dune']:
                await page.evaluate('(t) => applyTheme(t)', theme)
                metric = await page.evaluate("""() => {
                    const ids=['compact-task','compact-elapsed','compact-stop','compact-expand'];
                    return {theme: document.body.dataset.theme, width: innerWidth, height: innerHeight,
                        boxes: ids.map(id => {const r=document.getElementById(id).getBoundingClientRect();return {id,x:r.x,y:r.y,right:r.right,bottom:r.bottom,width:r.width};}),
                        scroll: document.documentElement.scrollWidth};
                }""")
                assert metric['scroll'] <= metric['width'], metric
                for b in metric['boxes']:
                    assert b['x'] >= 0 and b['right'] <= metric['width'] and b['bottom'] <= metric['height'] and b['width'] > 0, metric
                for a, b in zip(metric['boxes'], metric['boxes'][1:]):
                    assert a['right'] <= b['x'], metric
                metrics.append(metric)
            await page.click('#compact-expand')
            await expanded()
            assert page.viewport_size == {'width': 300, 'height': 540}
            assert await page.locator('#tab-log').is_visible()
            # Reload starts expanded; session is explicitly resumed, never silently started.
            await page.reload()
            await page.wait_for_function('state !== null')
            assert not await page.evaluate('compactRequested')
            assert not errors, errors
            await browser.close()
        print(json.dumps({'status':'PASS', 'checks':'no-session, cancel/x/Escape, exact file preservation, failed save/retry, atomic switch and persisted reload, stop/start, 25-hour timer, long title, six themes at 300px, full-size/tab restoration, launch reset', 'layout':metrics}, indent=2))


if __name__ == '__main__':
    asyncio.run(run())

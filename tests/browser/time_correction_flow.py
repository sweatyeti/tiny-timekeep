"""Real frontend + real main.Api, using Playwright only as the bridge transport.

Run explicitly (not part of unittest discovery):
  python tests/browser/time_correction_flow.py --output <evidence-directory>
Requires playwright==1.63.0 and its Chromium browser. This is NOT native WebView2 evidence.
"""
import argparse
import asyncio
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

from playwright.async_api import async_playwright, expect


async def run(app, output):
    sys.path.insert(0, str(app))
    from main import Api
    output.mkdir(parents=True, exist_ok=True)
    report = {"transport": "Playwright Chromium -> real main.Api -> real core -> isolated JSON files",
              "native_webview2": False, "checks": [], "layouts": [], "calls": [], "page_errors": []}
    with tempfile.TemporaryDirectory(prefix="ttk-browser-") as directory:
        root = Path(directory)
        service = Api(storage_path=str(root / "sessions"), preferences_path=str(root / "prefs.json"))
        clock = [datetime(2026, 10, 12, 9, tzinfo=timezone.utc)]
        service.core._clock = lambda: clock[0]
        assert service.start_session("Browser acceptance", "Work")["ok"]
        sid = service.get_state()["session"]["id"]
        clock[0] = clock[0].replace(hour=10)
        assert service.stop_tracking()["ok"]
        assert service.edit_entry(1, None, "original description", True)["ok"]
        clock[0] = clock[0].replace(hour=11)
        assert service.stop_and_start_entry("Running")["ok"]
        clock[0] = clock[0].replace(hour=12)
        failure = [False]

        def files():
            return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (root / "sessions").iterdir()}

        def snapshot():
            return service.get_state(), files()

        def document():
            return json.loads(next((root / "sessions").glob("*.json")).read_text(encoding="utf-8"))

        def checked(name):
            report["checks"].append(name)
            print("PASS", name, flush=True)

        async def invoke(source, name, args):
            assert not name.startswith("_")
            if name in {"add_completed_entry", "correct_entry_time"}:
                await asyncio.sleep(0.08)  # exercise repeated input during a genuine in-flight request
            if failure[0] and name in {"add_completed_entry", "correct_entry_time"}:
                with patch("timetracker_core.storage.os.replace", side_effect=OSError("injected storage failure")) as fault:
                    result = getattr(service, name)(*args)
                    assert fault.call_count == 1
            else:
                result = getattr(service, name)(*args)
            report["calls"].append({"method": name, "arguments": args, "result": result})
            return result

        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            context = await browser.new_context(viewport={"width": 680, "height": 720}, timezone_id="America/Chicago")
            page = await context.new_page()
            page.set_default_timeout(5000)
            page.on("pageerror", lambda error: report["page_errors"].append(str(error)))
            await page.expose_binding("_ttkCall", invoke)
            methods = [name for name in dir(service) if not name.startswith("_") and callable(getattr(service, name))]
            await page.add_init_script("window.pywebview = {api: Object.fromEntries(" + json.dumps(methods) + ".map(name => [name, (...args) => window._ttkCall(name, args)]))};")
            try:
                await page.goto((app / "web/index.html").as_uri(), wait_until="load")
                await page.evaluate("window.dispatchEvent(new Event('pywebviewready'))")
                await expect(page.locator("#current-label")).to_have_text("Running")
                await page.locator('[data-tab="log"]').click()
                await expect(page.locator("#add-missed-time-btn")).to_be_visible()
                assert await page.locator('[aria-label="Correct time for entry 2"]').count() == 0
                checked("controls wired; running entries cannot be corrected")

                async def opened():
                    await page.locator("#add-missed-time-btn").click()
                    await expect(page.locator("#interval-task")).to_be_focused()

                async def fill(start, end):
                    await page.locator("#interval-start").fill(start)
                    await page.locator("#interval-end").fill(end)

                async def submit_error(code):
                    await page.locator("#interval-save").click()
                    await expect(page.locator("#interval-error")).to_have_attribute("data-error-code", code)
                    await expect(page.locator("#interval-save")).to_be_enabled()

                before = snapshot()
                await opened()
                await page.locator("#interval-task").fill("discard me")
                await page.locator("#interval-cancel").click()
                assert snapshot() == before
                await opened()
                await page.keyboard.press("Escape")
                await expect(page.locator("#overlay")).to_have_class("overlay hidden")
                assert snapshot() == before
                checked("Cancel and Escape preserve JSON and active state")

                await opened()
                await page.locator("#interval-task").fill(" Past ")
                await page.locator("#interval-desc").fill(' notes <b>literal</b> & "quotes" ')
                await fill("2026-02-30T03:00:00-05:00", "2026-10-12T03:30:00-05:00")
                await submit_error("invalid_timestamp")
                assert snapshot() == before
                assert await page.locator("#interval-task").input_value() == " Past "
                assert await page.locator("#interval-start").input_value() == "2026-02-30T03:00:00-05:00"
                checked("invalid calendar date reaches core; inline error retains inputs")

                await fill("2026-10-12T03:00:00-05:00", "2026-10-12T03:30:00-05:00")
                await page.locator("#interval-save").click()
                await expect(page.locator("#overlay")).to_have_class("overlay hidden")
                saved = document()
                assert saved["entries"][-1]["task"] == "Past"
                assert saved["entries"][-1]["description"] == 'notes <b>literal</b> & "quotes"'
                assert saved["entries"][-1]["startTime"] == "2026-10-12T08:00:00+00:00"
                assert service.get_state()["currentEntry"] == before[0]["currentEntry"]
                await expect(page.locator("#entry-rows")).to_contain_text("Past")
                checked("manual add persists real data, updates Log, and preserves running timer")

                await page.locator('[aria-label="Correct time for entry 1"]').click()
                await expect(page.locator("#interval-start")).to_have_value("2026-10-12T04:00:00-05:00")
                await expect(page.locator("#overlay-body")).to_contain_text("Unlogged again")
                before = snapshot()
                await page.locator("#interval-save").click()
                await expect(page.locator("#overlay")).to_have_class("overlay hidden")
                assert snapshot() == before
                assert document()["entries"][0]["logged"]
                checked("local-offset prefill and unchanged Save preserve Logged and file bytes")

                await page.locator('[aria-label="Correct time for entry 1"]').click()
                await fill("2026-10-12T09:00:00Z", "2026-10-12T11:01:00Z")
                await submit_error("interval_overlap")
                assert snapshot() == before
                await fill("2026-10-12T09:00:00Z", "2026-10-12T13:00:00Z")
                await submit_error("future_interval")
                assert snapshot() == before
                checked("overlap and future corrections fail without changing state")

                await fill("2026-10-12T09:05:00Z", "2026-10-12T09:55:00Z")
                failure[0] = True
                await submit_error("internal_error")
                assert snapshot() == before
                assert await page.locator("#interval-end").input_value() == "2026-10-12T09:55:00Z"
                failure[0] = False
                checked("real os.replace failure is reached; JSON/state/input retention proven")
                await page.locator("#interval-save").click()
                await expect(page.locator("#overlay")).to_have_class("overlay hidden")
                saved = document()["entries"][0]
                assert not saved["logged"] and saved["description"] == "original description"
                assert saved["startTime"] == "2026-10-12T09:05:00+00:00"
                assert service.get_state()["totals"] == {"unloggedMinutes": 80, "totalMinutes": 80}
                checked("retry corrects persisted timestamps, clears Logged, and refreshes totals")

                await page.locator('[aria-label="Correct time for entry 1"]').click()
                before = snapshot()
                await fill("2026-10-12T09:06:00Z", "2026-10-12T09:54:00Z")
                await page.locator("#interval-cancel").click()
                assert snapshot() == before
                checked("correction Cancel does not save edited fields")

                await opened()
                await fill("2026-10-12T07:00:00Z", "2026-10-12T07:30:00Z")
                await page.locator("#interval-task").fill("Double click")
                count_before = len([c for c in report["calls"] if c["method"] == "add_completed_entry"])
                await page.evaluate("document.getElementById('interval-save').click(); document.getElementById('interval-save').click();")
                await expect(page.locator("#overlay")).to_have_class("overlay hidden")
                assert len([c for c in report["calls"] if c["method"] == "add_completed_entry"]) == count_before + 1
                assert len(document()["entries"]) == 4
                checked("duplicate submit while awaiting bridge produces exactly one write")

                # A stale UI snapshot deliberately misses a session switch: the backend guard must still work.
                await opened()
                await fill("2026-10-12T06:00:00Z", "2026-10-12T06:30:00Z")
                assert service.stop_and_exit()["ok"]
                assert service.start_session("Other session", "Different running entry")["ok"]
                before = snapshot()
                await submit_error("session_changed")
                assert snapshot() == before
                await page.locator("#interval-cancel").click()
                assert service.stop_and_exit()["ok"]
                assert service.resume_session(sid)["ok"]
                await page.evaluate("refresh()")
                checked("backend session guard rejects a stale dialog despite reused entry ids")

                await page.locator('[aria-label="Correct time for entry 3"]').click()
                assert service.delete_entry(3)["ok"]
                before = snapshot()
                await submit_error("entry_not_found")
                assert snapshot() == before
                await page.locator("#interval-cancel").click()
                assert service.restore_entry(3)["ok"]
                await page.evaluate("refresh()")
                checked("deleted correction target is rejected without resurrecting it")

                offsets = await page.evaluate("[localIntervalTimestamp('2025-11-02T06:30:00Z'), localIntervalTimestamp('2025-11-02T07:30:00Z')]")
                assert offsets == ["2025-11-02T01:30:00-05:00", "2025-11-02T01:30:00-06:00"], offsets
                checked("DST repeated hour retains separate explicit offsets")

                for theme in ["cute", "cyber", "poolside", "evergreen", "citrus-pop", "dune"]:
                    for width, height in [(300, 380), (364, 520), (680, 720)]:
                        await page.set_viewport_size({"width": width, "height": height})
                        await page.evaluate("theme => applyTheme(theme)", theme)
                        for mode in ["add", "correct"]:
                            if mode == "add":
                                await page.locator("#add-missed-time-btn").click()
                            else:
                                await page.locator('[aria-label="Correct time for entry 1"]').click()
                            await page.locator("#interval-save").scroll_into_view_if_needed()
                            metrics = await page.evaluate("""() => {
                              const body = document.getElementById('overlay-body');
                              const rect = (id) => { const r = document.getElementById(id).getBoundingClientRect(); return {x:r.x,y:r.y,right:r.right,bottom:r.bottom,width:r.width,height:r.height}; };
                              const panel = document.querySelector('.overlay-panel').getBoundingClientRect();
                              return { viewport: innerWidth, scrollWidth: document.documentElement.scrollWidth,
                                bodyWidth:body.clientWidth, bodyScroll:body.scrollWidth, panelRight:panel.right,
                                save:rect('interval-save'), cancel:rect('interval-cancel'),
                                input:rect('interval-start'), close:rect('overlay-close') };
                            }""")
                            assert metrics["scrollWidth"] <= width + 1, metrics
                            assert metrics["bodyScroll"] <= metrics["bodyWidth"] + 1, metrics
                            assert metrics["panelRight"] <= width, metrics
                            for control in ["save", "cancel", "close"]:
                                r = metrics[control]
                                assert r["width"] > 0 and r["height"] > 0 and r["x"] >= 0 and r["right"] <= width and r["bottom"] <= height, metrics
                            report["layouts"].append({"theme": theme, "width": width, "height": height, "mode": mode, "metrics": metrics})
                            if width == 364 and theme == "cute":
                                await page.screenshot(path=str(output / (mode + "-dialog.png")))
                            await page.locator("#interval-cancel").click()
                checked("all six themes: add/correct dialogs fit and controls reachable at three sizes")
                assert not report["page_errors"], report["page_errors"]
                checked("no uncaught frontend exceptions")
                report["font_loaded"] = await page.evaluate("document.fonts.check(\"16px 'VT323'\")")
                report["final_state"] = service.get_state()
                report["file_hashes"] = files()
                report["passed"] = True
                (output / "persisted-session.json").write_text(json.dumps(document(), indent=2), encoding="utf-8")
            except Exception as exc:
                report["passed"] = False
                report["failure"] = repr(exc)
                await page.screenshot(path=str(output / "failure.png"))
                raise
            finally:
                (output / "browser-results.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
                await browser.close()
    print(json.dumps({"passed": report["passed"], "checks": len(report["checks"]), "layouts": len(report["layouts"]), "api_calls": len(report["calls"]), "font_loaded": report.get("font_loaded")}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--app", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    asyncio.run(run(args.app.resolve(), args.output.resolve()))

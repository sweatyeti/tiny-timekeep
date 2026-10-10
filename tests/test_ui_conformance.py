"""UI ⇄ core conformance: the checks that catch a swap mismatch without a screen.

The frontend talks to `pywebview.api`, which is `main.Api` — a wrapper that carries window chrome
and UI preferences around the core. Nothing verifies that contract at runtime, so these tests read
the actual frontend source and assert it against the actual core:

  * every `api().<method>` the frontend calls exists on `Api`
  * `Api` exposes no method outside the core contract's surface plus a small app-level allowlist
  * every view-model / query-row field the frontend reads exists in a live payload
  * the frontend never reads a field the contract removed (`isActive` since v1.3)
  * the wrapper passes arguments through in the right positions (a swapped pair would show up in
    the UI as "renaming a task changed its description")
"""

import os
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import main as app_main  # noqa: E402

WEB = os.path.join(ROOT, "web")
APP_JS = os.path.join(WEB, "app.js")
HISTORY_JS = os.path.join(WEB, "history.js")
INDEX_HTML = os.path.join(WEB, "index.html")

# Methods on Api that are NOT part of the core contract: window chrome and UI preferences.
APP_LEVEL_METHODS = {
    "set_window",            # internal wiring, not reachable from JS in practice
    "move_window_to", "resize_window_to", "minimize_window", "exit_app",
    "get_preferences", "set_preference", "choose_entry_save_location",
    "set_entry_save_location", "restore_default_save_location",
    "open_entry_save_location",
    "save_history_csv",
}

# Fields the frontend reads, by payload. Every one must be present in a live payload.
FIELDS_READ = {
    "session": {"id", "name", "startedAt"},
    "currentEntry": {"id", "task", "startTime"},
    "entries[]": {"id", "task", "description", "startTime", "endTime", "isComplete",
                  "loggedStatus"},
    "summary[]": {"task", "count", "unloggedMinutes", "totalMinutes", "callout"},
    "totals": {"unloggedMinutes", "totalMinutes"},
    "list_sessions[]": {"id", "name", "startedAt", "endedAt", "isUnfinished"},
    "list_loggable_task_groups[]": {"task", "unloggedCount"},
    "list_deleted_entries[]": {"id", "task", "startTime", "endTime", "description"},
}


def _read(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def _strip_html_comments(text):
    return re.sub(r"<!--.*?-->", "", text, flags=re.S)


def _strip_css_comments(text):
    return re.sub(r"/\*.*?\*/", "", text, flags=re.S)


def _strip_js_comments(text):
    """Strip JS comments so absence guards scan code, not parked prose.

    This project parks retired UI paths as comments that necessarily name
    the identifiers they retired; a naive search would match the comment
    text.  Only whole-line ``//`` comments are removed (after ``/* */``
    blocks) because a naive strip would mangle a ``//`` inside a string
    literal.
    """
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    text = re.sub(r"(?m)^[ \t]*//[^\n]*$", "", text)
    return text


class FrontendCase(unittest.TestCase):
    """Shared fixture: a real Api over a throwaway data directory."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="koot-ui-conformance-")
        self.api = app_main.Api(storage_path=os.path.join(self.tmp, "sessions"),
                                preferences_path=os.path.join(self.tmp, "preferences.json"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.api.start_session("Garden work", "weeding")
        self.api.edit_entry(1, None, "front bed", None)
        self.api.stop_and_start_entry("weeding")
        self.api.edit_entry(2, None, "back bed", None)


class TestFrontendCallsExist(unittest.TestCase):
    def test_every_api_call_in_app_js_exists_on_api(self):
        # Parked handlers must not feed phantom calls into the extractor.
        called = set(re.findall(r"api\(\)\.([A-Za-z_][A-Za-z0-9_]*)", _strip_js_comments(_read(APP_JS))))
        assert os.path.isfile(HISTORY_JS), f"history.js not found at {HISTORY_JS} — canary scan is vacuous without it"
        called |= set(re.findall(r"api\(\)\.([A-Za-z_][A-Za-z0-9_]*)", _strip_js_comments(_read(HISTORY_JS))))
        assert called, "no api() calls found in app.js — the extractor or the frontend changed"
        missing = sorted(m for m in called if not hasattr(app_main.Api, m))
        assert missing == [], f"app.js calls methods Api does not have: {missing}"
        # Canary: retired Log group call is parked, not live
        assert "list_loggable_task_groups" not in called, "list_loggable_task_groups should be parked, not called"
        # Live Summary group toggle still uses these
        assert "log_task_group" in called, "log_task_group call missing from app.js"
        assert "unlog_task_group" in called, "unlog_task_group call missing from app.js"
        # History canaries
        assert "get_history" in called, "get_history call missing from history.js"
        assert "save_history_csv" in called, "save_history_csv call missing from history.js"

    def test_api_surface_is_the_contract_plus_the_app_level_methods(self):
        public = {name for name in dir(app_main.Api) if not name.startswith("_")}
        public.discard("core")        # attributes, not bridge methods
        public.discard("prefs")
        core_surface = {name for name in dir(app_main.Api)
                        if not name.startswith("_")} & set(dir(app_main.TimeTrackerCore))
        unexpected = sorted(public - core_surface - APP_LEVEL_METHODS)
        assert unexpected == [], (
            f"Api grew methods that are neither core contract nor declared app-level: {unexpected}"
        )

    def test_core_passthrough_methods_exist_on_the_core(self):
        for name in ("get_state", "list_sessions", "start_session", "resume_session",
                     "stop_and_start_entry", "edit_entry", "delete_entry", "restore_entry",
                     "list_loggable_task_groups", "log_task_group", "unlog_task_group",
                     "list_deleted_entries",
                     "stop_tracking", "stop_and_exit",
                     "get_history"):
            assert hasattr(app_main.TimeTrackerCore, name), f"core is missing {name}"


class TestFrontendFieldsExist(FrontendCase):
    def test_every_field_the_frontend_reads_exists_in_a_live_payload(self):
        state = self.api.get_state()
        with self.subTest(group="session"):
            missing = FIELDS_READ["session"] - set(state["session"])
            assert missing == set(), f"session is missing {sorted(missing)}"
        with self.subTest(group="currentEntry"):
            missing = FIELDS_READ["currentEntry"] - set(state["currentEntry"])
            assert missing == set(), f"currentEntry is missing {sorted(missing)}"
        with self.subTest(group="totals"):
            missing = FIELDS_READ["totals"] - set(state["totals"])
            assert missing == set(), f"totals is missing {sorted(missing)}"
        with self.subTest(group="entries[]"):
            missing = FIELDS_READ["entries[]"] - set(state["entries"][0])
            assert missing == set(), f"entries[] is missing {sorted(missing)}"
        with self.subTest(group="summary[]"):
            missing = FIELDS_READ["summary[]"] - set(state["summary"][0])
            assert missing == set(), f"summary[] is missing {sorted(missing)}"
        rows = {
            "list_sessions[]": self.api.list_sessions(),
            "list_loggable_task_groups[]": self.api.list_loggable_task_groups(),
        }
        self.api.stop_tracking()          # a running entry cannot be deleted
        self.api.delete_entry(2)
        rows["list_deleted_entries[]"] = self.api.list_deleted_entries()
        with self.subTest(group="list_sessions[]"):
            assert rows["list_sessions[]"], "list_sessions[] came back empty — cannot check its shape"
            missing = FIELDS_READ["list_sessions[]"] - set(rows["list_sessions[]"][0])
            assert missing == set(), f"list_sessions[] is missing {sorted(missing)}"
        with self.subTest(group="list_loggable_task_groups[]"):
            assert rows["list_loggable_task_groups[]"], "list_loggable_task_groups[] came back empty — cannot check its shape"
            missing = FIELDS_READ["list_loggable_task_groups[]"] - set(rows["list_loggable_task_groups[]"][0])
            assert missing == set(), f"list_loggable_task_groups[] is missing {sorted(missing)}"
        with self.subTest(group="list_deleted_entries[]"):
            assert rows["list_deleted_entries[]"], "list_deleted_entries[] came back empty — cannot check its shape"
            missing = FIELDS_READ["list_deleted_entries[]"] - set(rows["list_deleted_entries[]"][0])
            assert missing == set(), f"list_deleted_entries[] is missing {sorted(missing)}"

    def test_frontend_carries_no_removed_surface(self):
        for path in (APP_JS, INDEX_HTML, os.path.join(WEB, "style.css")):
            assert "isActive" not in _read(path), (
                f"{os.path.basename(path)} still reads isActive, removed in contract v1.3"
            )
        html = _read(INDEX_HTML)
        js = _read(APP_JS)
        css = _read(os.path.join(WEB, "style.css"))
        # canary: the live surface is still present
        assert 'id="tab-summary"' in html
        assert 'id="tab-log"' in html
        assert "renderSummary" in js
        assert ".summary-row" in css
        # the removed Tasks view is gone from both markup and renderer
        for needle in ('data-tab="tasks"', "tab-tasks", "task-rows", "renderTasks"):
            assert needle not in html, f"{os.path.basename(INDEX_HTML)} still contains {needle!r}"
            assert needle not in js, f"{os.path.basename(APP_JS)} still contains {needle!r}"
        # the two surviving tabs are the only tab buttons
        assert 'data-tab="log"' in html
        assert 'data-tab="summary"' in html
        assert "const TABS = ['log', 'summary'];" in js
        # Summary actions that replaced the Tasks view are wired in app.js
        assert "summary-log-btn" in js
        assert "summary-start-btn" in js
        assert "api().log_task_group(" in js
        assert "api().unlog_task_group(" in js
        assert "api().stop_and_start_entry(" in js
        html_code = _strip_html_comments(html)
        js_code = _strip_js_comments(js)
        css_code = _strip_css_comments(css)
        # A. Retired Log group control
        assert "log-group-btn" not in html_code, "index.html still renders the Log group button"
        assert "Log group" not in html_code, "index.html still has 'Log group' in the accessibility tree"
        assert "log-group-btn" not in js_code, "app.js still binds the removed Log group button"
        assert "openLogGroup" not in js_code, "app.js still calls the removed Log group popup"
        # Parking is NOT deletion — the raw text must still carry the parked code
        assert "openLogGroup" in js, "app.js should still contain parked openLogGroup code"
        assert "Parked" in js, "app.js should contain a 'Parked' note"
        assert "Parked" in css, "style.css should contain a 'Parked' note"
        assert "Parked" in html, "index.html should contain a 'Parked' note"
        assert "summary-log-btn" in js_code, "app.js lost the Summary log button binding"
        assert "api().log_task_group(" in js_code, "app.js lost the live log_task_group call"
        assert "api().unlog_task_group(" in js_code, "app.js lost the live unlog_task_group call"
        # B. Deleted control moved into the tab row
        assert 'class="tab-bar"' in html_code, "index.html missing the new .tab-bar wrapper"
        assert 'id="deleted-btn"' in html_code, "index.html missing #deleted-btn"
        assert 'id="deleted-count"' in html_code, "index.html missing #deleted-count"
        assert "action-bar" not in html_code, "the emptied action bar must be gone, not left as a blank spacer"
        assert html_code.index('class="tabs"') < html_code.index('id="deleted-btn"') < html_code.index('id="tab-log"'), \
            "Deleted button must sit between .tabs and #tab-log in the tab-bar row"
        assert "getElementById('deleted-btn').onclick = openDeletedEntries" in js_code, \
            "app.js lost the #deleted-btn click binding"
        # C. No wired .onclick may target an element index.html does not have
        bound = set(re.findall(r"getElementById\('([^']+)'\)\.onclick", js_code))
        assert bound, "canary: no getElementById(...).onclick bindings found in app.js"
        overlay_ids = {"sn-go", "ef-save", "choose-entry-save-location", "restore-default-save-location", "open-entry-save-location"}
        orphans = sorted(id for id in bound if f'id="{id}"' not in html_code and id not in overlay_ids)
        assert orphans == [], f"app.js binds onclick to ids not in index.html: {orphans}"
        assert "log-group-btn" not in bound, "app.js still has an onclick binding for the removed log-group-btn"
        # C2. Restore default path
        assert "restore-default-save-location" in bound, "app.js must bind the restore-default-save-location button"
        assert "api().restore_default_save_location(" in js_code, "app.js must call api().restore_default_save_location("
        assert "Restore default path" in js_code, "app.js must reference the 'Restore default path' label"
        # C3. Open folder
        assert "open-entry-save-location" in bound, "app.js must bind the open-entry-save-location button"
        assert "api().open_entry_save_location(" in js_code, "app.js must call api().open_entry_save_location("
        assert "Open folder" in js_code, "app.js must reference the 'Open folder' label"
        assert "entrySaveLocationIsDefault" in js_code, "app.js must reference entrySaveLocationIsDefault"
        assert "entrySaveLocationDefault" in js_code, "app.js must reference entrySaveLocationDefault"
        _start = js_code.index("getElementById('restore-default-save-location').onclick")
        _end = js_code.index("api().restore_default_save_location(", _start)
        assert "confirmSaveLocation" in js_code[_start:_end], "restore handler must confirm before changing the folder"
        # D. CSS
        assert "action-bar" not in css_code, "the retired .action-bar rule must be parked, not live"
        tab_bar_match = re.search(r"\.tab-bar\s*\{([^}]*)\}", css_code)
        assert tab_bar_match, "style.css missing the .tab-bar rule"
        assert re.search(r"display\s*:\s*flex", tab_bar_match.group(1)), ".tab-bar must declare display: flex"
        assert re.search(r"justify-content\s*:\s*space-between", tab_bar_match.group(1)), ".tab-bar must declare justify-content: space-between"
        btn_compact_match = re.search(r"\.btn-compact\s*\{([^}]*)\}", css_code)
        assert btn_compact_match, "style.css missing the .btn-compact rule"
        assert re.search(r"flex\s*:\s*0\s+0\s+auto", btn_compact_match.group(1)), ".btn-compact must declare flex: 0 0 auto"
        assert re.search(r"width\s*:\s*auto", btn_compact_match.group(1)), ".btn-compact must declare width: auto"
        assert re.search(r"white-space\s*:\s*nowrap", btn_compact_match.group(1)), ".btn-compact must declare white-space: nowrap"
        assert not re.search(r"\.tabs\s*\{[^}]*margin-bottom", css_code), ".tabs must not declare margin-bottom (moved to .tab-bar)"
        assert ".save-location-restore" in css_code, "style.css must contain the .save-location-restore rule"
        assert ".save-location-restore:disabled" in css_code, "style.css must contain the .save-location-restore:disabled rule"

        # E. Session list reads in the viewer's local time
        for fn in ("parseSessionTimestamp", "fmtLocalDateTime", "coreGeneratedSessionName",
                   "sessionDisplayName", "sessionTimeLine"):
            assert fn in js_code, f"js must define helper {fn}"
        assert "coreGeneratedSessionName(s.startedAt)" in js_code, \
            "generated-name guard must compare against the session's own startedAt"
        assert "s.name === generated" in js_code, \
            "generated-name guard must be an exact-match against s.name"
        assert 'class="session-info"' in js_code, "rendered row must carry class=\"session-info\""
        assert 'class="session-times"' in js_code, "rendered row must carry class=\"session-times\""
        assert "escapeAttr('Resume ' + nameLine)" in js_code, \
            "resume button must use escapeAttr('Resume ' + nameLine)"
        start = js_code.index("async function renderSessionList")
        end = js_code.index("function renderCurrent", start)
        body = js_code[start:end]
        assert body, "renderSessionList slice is empty"
        assert "resume_session(" in body, "renderSessionList must call resume_session("
        calls = set(re.findall(r"api\(\)\.(\w+)", body))
        assert calls == {"list_sessions", "resume_session"}, \
            f"renderSessionList must only call list_sessions and resume_session, found {sorted(calls)}"
        css_stripped = re.sub(r"/\*.*?\*/", "", css_code, flags=re.DOTALL)
        m = re.search(r"\.session-info\s*\{([^}]*)\}", css_stripped)
        assert m is not None, "style.css must contain a .session-info rule"
        assert "min-width: 0" in m.group(1), ".session-info must declare min-width: 0"
        assert "flex: 1 1 auto" in m.group(1), ".session-info must declare flex: 1 1 auto"
        m = re.search(r"\.session-name\s*\{([^}]*)\}", css_stripped)
        assert m is not None, "style.css must contain a .session-name rule"
        assert "overflow-wrap: anywhere" in m.group(1), ".session-name must declare overflow-wrap: anywhere"
        m = re.search(r"\.session-times\s*\{([^}]*)\}", css_stripped)
        assert m is not None, "style.css must contain a .session-times rule"
        assert "overflow-wrap: anywhere" in m.group(1), ".session-times must declare overflow-wrap: anywhere"
        assert "color: var(--text-dim)" in m.group(1), ".session-times must declare color: var(--text-dim)"
        m = re.search(r"\.session-item\s+button\s*\{([^}]*)\}", css_stripped)
        assert m is not None, "style.css must contain a .session-item button rule"
        assert "flex: 0 0 auto" in m.group(1), ".session-item button must declare flex: 0 0 auto"
        assert "white-space: nowrap" in m.group(1), ".session-item button must declare white-space: nowrap"


class TestWrapperPassesArgumentsThrough(FrontendCase):
    """The wrapper's positional argument order is what the frontend depends on."""

    def test_description_edit_does_not_touch_the_task(self):
        self.api.edit_entry(2, None, "back bed, weeded")
        entry = next(e for e in self.api.get_state()["entries"] if e["id"] == 2)
        assert entry["task"] == "weeding", entry
        assert entry["description"] == "back bed, weeded", entry

        started = self.api.stop_and_start_entry()
        new_id = started["state"]["currentEntry"]["id"]
        assert new_id != 2, started

        saved = self.api.edit_entry(new_id, "composting", 'raised <bed> & "bins"')
        assert saved["ok"] is True, saved
        assert saved["state"]["currentEntry"]["task"] == "composting", saved
        session_id = saved["state"]["session"]["id"]

        reopened = app_main.Api(storage_path=os.path.join(self.tmp, "sessions"), preferences_path=os.path.join(self.tmp, "preferences.json"))
        reopened.resume_session(session_id)
        entry2 = next(e for e in reopened.get_state()["entries"] if e["id"] == new_id)
        assert entry2["task"] == "composting", entry2
        assert entry2["description"] == 'raised <bed> & "bins"', entry2
        assert entry2["endTime"] is None, entry2

        blank = self.api.edit_entry(new_id, "composting", "")
        assert blank["ok"] is True, blank
        reopened2 = app_main.Api(storage_path=os.path.join(self.tmp, "sessions"), preferences_path=os.path.join(self.tmp, "preferences.json"))
        reopened2.resume_session(session_id)
        entry3 = next(e for e in reopened2.get_state()["entries"] if e["id"] == new_id)
        assert entry3["description"] == "", entry3

    def test_task_edit_does_not_touch_the_description(self):
        self.api.edit_entry(2, "mulching")
        entry = next(e for e in self.api.get_state()["entries"] if e["id"] == 2)
        assert entry["task"] == "mulching", entry
        assert entry["description"] == "back bed", entry
        # entry 2 is the active (running) entry
        state = self.api.get_state()
        assert state["currentEntry"]["id"] == 2, state["currentEntry"]
        # record startTime so we can verify editing does not re-timestamp
        recorded_start = state["currentEntry"]["startTime"]
        # edit both task and description in a single call
        result = self.api.edit_entry(2, "composting", "raised bed")
        assert result["ok"] is True, result
        state = result["state"]
        assert state["currentEntry"]["task"] == "composting", state["currentEntry"]
        # editing must not restart or re-timestamp the running entry
        assert state["currentEntry"]["startTime"] == recorded_start, state["currentEntry"]
        # restart: build a fresh Api over the same paths and resume the session
        api2 = app_main.Api(storage_path=os.path.join(self.tmp, "sessions"),
                            preferences_path=os.path.join(self.tmp, "preferences.json"))
        api2.resume_session(state["session"]["id"])
        state2 = api2.get_state()
        entry2 = next(e for e in state2["entries"] if e["id"] == 2)
        # persistence: new task and description survived the restart
        assert entry2["task"] == "composting", entry2
        assert entry2["description"] == "raised bed", entry2
        # still the same running entry: startTime unchanged, no end, N/A status
        assert entry2["startTime"] == recorded_start, entry2
        assert entry2["endTime"] is None, entry2
        assert entry2["loggedStatus"] == "N/A", entry2

    def test_logged_flag_only_applies_to_completed_named_entries(self):
        result = self.api.edit_entry(1, None, None, True)
        assert result["ok"] is True, result
        entry = next(e for e in self.api.get_state()["entries"] if e["id"] == 1)
        assert entry["loggedStatus"] == "Logged", entry
        running = self.api.edit_entry(2, None, None, True)
        assert running["ok"] is False and running["error"] == "logged_not_applicable", running

class TestThemePreference(FrontendCase):
    """Theme preference: default, validation, and persistence."""

    def test_defaults_are_cute_and_summary(self):
        prefs = self.api.get_preferences()
        assert prefs["theme"] == "cute", prefs
        # default tab changed to "summary" with the removal of the Tasks view
        assert prefs["activeTab"] == "summary", prefs

    def test_all_themes_round_trip_through_store_reopen(self):
        for theme in ("cute", "cyber", "poolside", "evergreen", "citrus-pop", "dune"):
            with self.subTest(theme=theme):
                result = self.api.set_preference("theme", theme)
                assert result["theme"] == theme, result
                reopened = app_main.PreferencesStore(os.path.join(self.tmp, "preferences.json"))
                assert reopened.get_all()["theme"] == theme, f"{theme} did not persist"

    def test_unknown_theme_falls_back_to_cute_on_set(self):
        result = self.api.set_preference("theme", "dark")
        assert result["theme"] == "cute", result
        reopened = app_main.PreferencesStore(os.path.join(self.tmp, "preferences.json"))
        assert reopened.get_all()["theme"] == "cute", "invalid theme was persisted as-is"

    def test_corrupt_theme_and_retired_tab_fall_back(self):
        prefs_path = os.path.join(self.tmp, "preferences.json")
        for invalid in (42, None):
            with self.subTest(theme=invalid):
                # "tasks" is a tab an older build saved; this file is exactly the migration case
                with open(prefs_path, "w", encoding="utf-8") as f:
                    json.dump({"activeTab": "tasks", "theme": invalid}, f)
                reopened = app_main.PreferencesStore(prefs_path)
                assert reopened.get_all()["theme"] == "cute"
                assert reopened.get_all()["activeTab"] == "summary", reopened.get_all()


class TestChromeAndTheming(unittest.TestCase):
    """Window chrome and themed surfaces — the parts a contract test cannot see."""

    def test_theme_selection_updates_persists_and_restores_after_reload(self):
        js = _read(APP_JS)
        self.assertIn("const THEMES = ['cute', 'cyber', 'poolside', 'evergreen', 'citrus-pop', 'dune']", js)
        self.assertIn("if (!THEMES.includes(theme)) return;", js)
        self.assertIn("applyTheme(theme);", js)
        self.assertIn("api().set_preference('theme', theme)", js)
        self.assertIn("applyTheme(typeof prefs.theme === 'string' && THEMES.includes(prefs.theme)", js)
        for theme in ("poolside", "evergreen", "citrus-pop", "dune"):
            self.assertIn(f'"{theme}"', _read(os.path.join(ROOT, "preferences.py")))
        html = _read(os.path.join(ROOT, "web", "index.html"))
        css = _strip_css_comments(_read(os.path.join(ROOT, "web", "style.css")))
        self.assertEqual(
            html.count('class="theme-btn" type="button" data-theme="'),
            6,
            "theme picker must offer six theme buttons",
        )
        self.assertIn('id="save-location-btn"', html, "folder button must be present in the picker")
        btn_width_m = re.search(r"\.theme-btn\s*\{[^}]*width\s*:\s*(\d+)px", css)
        self.assertIsNotNone(btn_width_m, "could not find .theme-btn width in CSS")
        theme_btn_width = int(btn_width_m.group(1))
        gap_m = re.search(r"#theme-picker\s*\{[^}]*gap\s*:\s*(\d+)px", css)
        self.assertIsNotNone(gap_m, "could not find #theme-picker gap in CSS")
        gap = int(gap_m.group(1))
        pad_m = re.search(r"#theme-picker\s*\{[^}]*padding\s*:\s*(\d+)px\s+(\d+)px\s+(\d+)px\s+(\d+)px", css)
        self.assertIsNotNone(pad_m, "could not find #theme-picker padding in CSS")
        padding_right = int(pad_m.group(2))
        padding_left = int(pad_m.group(4))
        self.assertLessEqual(
            7 * theme_btn_width + 6 * gap + padding_left + padding_right,
            300,
            "picker must fit within the 300 px minimum window width",
        )

def _run_node_session_list(script, *args, tz=None):
    cmd = ["node", "-e", script] + [str(a) for a in args]
    kwargs = {"capture_output": True, "text": True, "encoding": "utf-8", "timeout": 30}
    if tz is not None:
        kwargs["env"] = {**os.environ, "TZ": tz}
    proc = subprocess.run(cmd, **kwargs)
    if proc.returncode != 0:
        raise AssertionError("Node script failed (exit {})\nstdout: {}\nstderr: {}".format(
            proc.returncode, proc.stdout, proc.stderr))
    return json.loads(proc.stdout)


_NODE_SESSION_LIST = r"""
const fs = require('fs');
const vm = require('vm');

const appPath = process.argv[1];
const rows = JSON.parse(process.argv[2]);

function makeStub() {
  var attrs = {};
  var classes = new Set();
  var stub = {
    className: '',
    innerHTML: '',
    style: {},
    children: [],
    onclick: null,
    appendChild: function(child) { this.children.push(child); return child; },
    classList: {
      add: function() { for (var i = 0; i < arguments.length; i++) classes.add(arguments[i]); },
      remove: function() { for (var i = 0; i < arguments.length; i++) classes.delete(arguments[i]); },
      contains: function(c) { return classes.has(c); },
      toggle: function(c) { if (classes.has(c)) classes.delete(c); else classes.add(c); }
    },
    setAttribute: function(k, v) { attrs[k] = v; },
    getAttribute: function(k) { return Object.prototype.hasOwnProperty.call(attrs, k) ? attrs[k] : null; },
    querySelector: function() { return makeStub(); },
    querySelectorAll: function() { return []; },
    focus: function() {},
    click: function() {},
    addEventListener: function() {},
    removeEventListener: function() {}
  };
  return stub;
}

var elementMap = {};
var bodyStub = makeStub();

var document = {
  getElementById: function(id) {
    if (!elementMap[id]) elementMap[id] = makeStub();
    return elementMap[id];
  },
  createElement: function() { return makeStub(); },
  querySelector: function() { return null; },
  querySelectorAll: function() { return []; },
  body: bodyStub,
  addEventListener: function() {},
  removeEventListener: function() {}
};

var source = fs.readFileSync(appPath, 'utf8');

var ctx = vm.createContext({
  console: console,
  Date: Date,
  Math: Math,
  Promise: Promise,
  setTimeout: setTimeout,
  clearTimeout: clearTimeout,
  setInterval: setInterval,
  clearInterval: clearInterval,
  document: document,
  addEventListener: function() {},
  removeEventListener: function() {}
});
ctx.window = ctx;

vm.runInContext(source, ctx);

ctx.window.pywebview = {
  api: {
    list_sessions: function() { return Promise.resolve(rows); },
    resume_session: function() { return Promise.resolve({ ok: true, state: { session: null } }); }
  }
};

ctx.renderSessionList().then(function() {
  var listEl = document.getElementById('session-list');
  var out = {
    rows: listEl.children.map(function(child) {
      var html = child.innerHTML;
      var nameMatch = html.match(/class="session-name">([^<]*)/);
      var timesMatch = html.match(/class="session-times">([^<]*)/);
      var ariaMatch = html.match(/aria-label="([^"]*)"/);
      return {
        className: child.className,
        html: html,
        name: nameMatch ? nameMatch[1] : null,
        times: timesMatch ? timesMatch[1] : null,
        aria: ariaMatch ? ariaMatch[1] : null
      };
    }),
    containerHtml: listEl.innerHTML
  };
  process.stdout.write(JSON.stringify(out));
}).catch(function(err) {
  process.stderr.write(String(err && err.stack || err));
  process.exit(1);
});
"""


class TestSessionListLocalization(unittest.TestCase):
    """Pins two rules: (1) generated session names and the list view display in the viewer's local time;
    (2) stored session documents are never rewritten, renamed, or migrated by the API or renderer."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="koot-session-list-")
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def _api(self, suffix=""):
        return app_main.Api(
            storage_path=os.path.join(self.tmp, "sessions" + suffix),
            preferences_path=os.path.join(self.tmp, "preferences" + suffix + ".json"),
        )

    @staticmethod
    def _parse_name_suffix(name):
        return datetime.strptime(name[len("Session "):], "%Y-%m-%d %H:%M")

    def test_session_list_localises_times_and_the_initial_name(self):
        # ── PART A: initial nameless session is named locally ──
        api = self._api()
        result = api.start_session(None, "weeding")
        self.assertIs(result["ok"], True, "start_session ok")
        row = api.list_sessions()[0]
        self.assertIsNotNone(
            re.fullmatch(r"Session \d{4}-\d{2}-\d{2} \d{2}:\d{2}", row["name"]),
            f"generated name format: {row['name']}")
        local_start = datetime.fromisoformat(row["startedAt"]).astimezone().replace(tzinfo=None)
        named = self._parse_name_suffix(row["name"])
        # Tolerance: the wrapper reads the wall clock just before the core stamps the session,
        # so a minute boundary between those two reads can shift the label by one minute;
        # the list itself always shows the authoritative startedAt.
        self.assertLessEqual(
            abs((named - local_start).total_seconds()), 60,
            f"name {row['name']} vs local start {local_start}")
        self.assertTrue(row["startedAt"].endswith("+00:00"), f"startedAt UTC: {row['startedAt']}")
        json_files = [f for f in os.listdir(os.path.join(self.tmp, "sessions")) if f.endswith(".json")]
        self.assertEqual(len(json_files), 1, f"expected exactly one session file, found: {json_files}")
        with open(os.path.join(self.tmp, "sessions", json_files[0]), "r") as f:
            doc = json.load(f)
        self.assertEqual(doc["startedAt"], row["startedAt"], "stored startedAt unchanged")
        self.assertEqual(doc["name"], row["name"], "stored name matches local-time name shown in list")
        api.start_session("Garden work", "weeding")
        self.assertIn("Garden work", [r["name"] for r in api.list_sessions()], "explicit name preserved")

        # ── PART B: existing document is never rewritten, renamed, or migrated ──
        legacy_path = os.path.join(self.tmp, "sessions", "legacy-session.json")
        os.makedirs(os.path.dirname(legacy_path), exist_ok=True)
        legacy_doc = {
            "schemaVersion": 2,
            "sessionId": "11111111-2222-3333-4444-555555555555",
            "name": "Session 2026-10-01 13:30",
            "startedAt": "2026-10-01T13:30:46+00:00",
            "endedAt": "2026-10-01T14:15:12+00:00",
            "entries": [],
        }
        with open(legacy_path, "w") as f:
            json.dump(legacy_doc, f)

        def _read_bytes(path):
            with open(path, "rb") as handle:
                return handle.read()

        snapshot = _read_bytes(legacy_path)
        api2 = self._api()
        rows = api2.list_sessions()
        legacy_row = next(r for r in rows if r["id"] == "11111111-2222-3333-4444-555555555555")
        self.assertEqual(legacy_row["name"], "Session 2026-10-01 13:30", "legacy name")
        self.assertEqual(legacy_row["startedAt"], "2026-10-01T13:30:46+00:00", "legacy startedAt")
        self.assertTrue(os.path.isfile(legacy_path), "legacy exists after list_sessions")
        self.assertEqual(_read_bytes(legacy_path), snapshot, "legacy bytes after list_sessions")
        api2.start_session("After the legacy", "x")
        self.assertTrue(os.path.isfile(legacy_path), "legacy exists after start_session")
        self.assertEqual(_read_bytes(legacy_path), snapshot, "legacy bytes after start_session")

        # ── PART C: TZ-pinned name generation (Windows has no time.tzset, so this is skipped there) ──
        if hasattr(time, "tzset"):
            orig_tz = os.environ.get("TZ")
            try:
                for zone in ("America/New_York", "Asia/Kolkata"):
                    with self.subTest(zone=zone):
                        os.environ["TZ"] = zone
                        time.tzset()
                        api_tz = self._api(suffix=f"-{zone.replace('/', '_')}")
                        api_tz.start_session(None, "task")
                        row_tz = api_tz.list_sessions()[0]
                        local_start_tz = datetime.fromisoformat(row_tz["startedAt"]).astimezone().replace(tzinfo=None)
                        named_tz = self._parse_name_suffix(row_tz["name"])
                        self.assertLessEqual(
                            abs((named_tz - local_start_tz).total_seconds()), 60,
                            f"{zone}: name {row_tz['name']} vs local {local_start_tz}")
                        utc_label = "Session " + datetime.fromisoformat(row_tz["startedAt"]).strftime("%Y-%m-%d %H:%M")
                        self.assertNotEqual(row_tz["name"], utc_label,
                                            f"{zone}: name must be local, not UTC ({utc_label})")
            finally:
                if orig_tz is None:
                    os.environ.pop("TZ", None)
                else:
                    os.environ["TZ"] = orig_tz
                time.tzset()

        # ── PART D: the real renderer under pinned timezones ──
        def _render(fixtures, tz):
            return _run_node_session_list(_NODE_SESSION_LIST, APP_JS, json.dumps(fixtures), tz=tz)

        with self.subTest(case=1, desc="NY generated name localised"):
            fixtures = [{"name": "Session 2026-10-01 13:30", "startedAt": "2026-10-01T13:30:00+00:00",
                         "endedAt": "2026-10-01T14:15:00+00:00", "isUnfinished": False, "isUnreadable": False}]
            out = _render(fixtures, "America/New_York")
            self.assertEqual(len(out["rows"]), len(fixtures), "canary row count")
            r = out["rows"][0]
            self.assertEqual(r["className"], "session-item", "className")
            self.assertEqual(r["name"], "Session 2026-10-01 09:30", f"NY name: {r['name']}")
            self.assertEqual(r["times"], "Started 2026-10-01 09:30 \u00b7 Ended 2026-10-01 10:15", f"NY times: {r['times']}")
            self.assertTrue(r["aria"].startswith("Resume "), f"aria prefix: {r['aria']}")
            self.assertIn("Session 2026-10-01 09:30", r["aria"], f"aria name: {r['aria']}")

        with self.subTest(case=2, desc="Kolkata half-hour offset"):
            fixtures = [{"name": "Session 2026-10-01 13:30", "startedAt": "2026-10-01T13:30:00+00:00",
                         "endedAt": "2026-10-01T14:15:00+00:00", "isUnfinished": False, "isUnreadable": False}]
            out = _render(fixtures, "Asia/Kolkata")
            self.assertEqual(len(out["rows"]), len(fixtures), "canary row count")
            r = out["rows"][0]
            self.assertEqual(r["className"], "session-item", "className")
            self.assertEqual(r["name"], "Session 2026-10-01 19:00", f"Kolkata name: {r['name']}")
            self.assertEqual(r["times"], "Started 2026-10-01 19:00 \u00b7 Ended 2026-10-01 19:45", f"Kolkata times: {r['times']}")
            self.assertTrue(r["aria"].startswith("Resume "), f"aria prefix: {r['aria']}")
            self.assertIn("Session 2026-10-01 19:00", r["aria"], f"aria name: {r['aria']}")

        with self.subTest(case=3, desc="DST one-hour difference"):
            fixtures = [
                {"name": "Session 2026-07-15 13:30", "startedAt": "2026-07-15T13:30:00+00:00",
                 "endedAt": None, "isUnfinished": False, "isUnreadable": False},
                {"name": "Session 2026-01-15 13:30", "startedAt": "2026-01-15T13:30:00+00:00",
                 "endedAt": None, "isUnfinished": False, "isUnreadable": False},
            ]
            out = _render(fixtures, "America/New_York")
            self.assertEqual(len(out["rows"]), len(fixtures), "canary row count")
            n1 = self._parse_name_suffix(out["rows"][0]["name"])
            n2 = self._parse_name_suffix(out["rows"][1]["name"])
            diff_min = abs((n1.hour * 60 + n1.minute) - (n2.hour * 60 + n2.minute))
            self.assertEqual(diff_min, 60, f"DST rows differ by {diff_min} min, expected 60")

        with self.subTest(case=4, desc="day rollover"):
            fixtures = [{"name": "rollover", "startedAt": "2026-10-02T03:00:00+00:00",
                         "endedAt": "2026-10-02T04:30:00+00:00", "isUnfinished": False, "isUnreadable": False}]
            out = _render(fixtures, "America/New_York")
            self.assertEqual(len(out["rows"]), len(fixtures), "canary row count")
            r = out["rows"][0]
            self.assertEqual(r["className"], "session-item", "className")
            self.assertEqual(r["times"], "Started 2026-10-01 23:00 \u00b7 Ended 2026-10-02 00:30", f"rollover: {r['times']}")
            self.assertTrue(r["aria"].startswith("Resume "), f"aria prefix: {r['aria']}")
            self.assertIn("rollover", r["aria"], f"aria name: {r['aria']}")

        with self.subTest(case=5, desc="custom name + unfinished"):
            fixtures = [{"name": "Garden work", "startedAt": "2026-10-01T13:30:00+00:00",
                         "endedAt": None, "isUnfinished": True, "isUnreadable": False}]
            out = _render(fixtures, "America/New_York")
            self.assertEqual(len(out["rows"]), len(fixtures), "canary row count")
            r = out["rows"][0]
            self.assertEqual(r["className"], "session-item", "className")
            self.assertEqual(r["name"], "Garden work (unfinished)", f"unfinished name: {r['name']}")
            self.assertEqual(r["times"], "Started 2026-10-01 09:30", f"unfinished times: {r['times']}")
            self.assertNotIn("Ended", r["times"], "no fabricated end")
            self.assertTrue(r["aria"].startswith("Resume "), f"aria prefix: {r['aria']}")
            self.assertIn("Garden work (unfinished)", r["aria"], f"aria name: {r['aria']}")

        with self.subTest(case=6, desc="handwritten lookalike not translated"):
            fixtures = [{"name": "Session 2020-01-01 09:00", "startedAt": "2026-10-01T13:30:00+00:00",
                         "endedAt": None, "isUnfinished": True, "isUnreadable": False}]
            out = _render(fixtures, "America/New_York")
            self.assertEqual(len(out["rows"]), len(fixtures), "canary row count")
            r = out["rows"][0]
            self.assertEqual(r["className"], "session-item", "className")
            self.assertEqual(r["name"], "Session 2020-01-01 09:00 (unfinished)", f"lookalike: {r['name']}")
            self.assertTrue(r["aria"].startswith("Resume "), f"aria prefix: {r['aria']}")
            self.assertIn("Session 2020-01-01 09:00 (unfinished)", r["aria"], f"aria name: {r['aria']}")

        with self.subTest(case=7, desc="wrapper local name not double-translated"):
            fixtures = [{"name": "Session 2026-10-01 09:30", "startedAt": "2026-10-01T13:30:00+00:00",
                         "endedAt": None, "isUnfinished": True, "isUnreadable": False}]
            out = _render(fixtures, "America/New_York")
            self.assertEqual(len(out["rows"]), len(fixtures), "canary row count")
            r = out["rows"][0]
            self.assertEqual(r["className"], "session-item", "className")
            self.assertEqual(r["name"], "Session 2026-10-01 09:30 (unfinished)", f"no double-translate: {r['name']}")
            self.assertTrue(r["aria"].startswith("Resume "), f"aria prefix: {r['aria']}")
            self.assertIn("Session 2026-10-01 09:30 (unfinished)", r["aria"], f"aria name: {r['aria']}")

        with self.subTest(case=8, desc="unreadable timestamps"):
            fixtures = [
                {"name": "broken", "startedAt": "not-a-timestamp", "endedAt": "also-bad",
                 "isUnfinished": False, "isUnreadable": False},
                {"name": "unreadable", "startedAt": None, "endedAt": None,
                 "isUnfinished": False, "isUnreadable": False},
            ]
            out = _render(fixtures, "America/New_York")
            self.assertEqual(len(out["rows"]), len(fixtures), "canary row count")
            for i, (r, exp) in enumerate(zip(out["rows"], ["broken", "unreadable"])):
                self.assertEqual(r["className"], "session-item", f"className row {i}")
                self.assertIsNone(r["times"], f"times None row {i}: {r['times']}")
                self.assertEqual(r["name"], exp, f"name row {i}: {r['name']}")
                self.assertTrue(r["aria"].startswith("Resume "), f"aria prefix row {i}")
                self.assertIn(exp, r["aria"], f"aria name row {i}")

        with self.subTest(case=9, desc="HTML escaping"):
            fixtures = [{"name": 'Garden <b>work</b> & "co"', "startedAt": "2026-10-01T13:30:00+00:00",
                         "endedAt": None, "isUnfinished": False, "isUnreadable": False}]
            out = _render(fixtures, "America/New_York")
            self.assertEqual(len(out["rows"]), len(fixtures), "canary row count")
            r = out["rows"][0]
            self.assertEqual(r["className"], "session-item", "className")
            self.assertIn("&lt;b&gt;", r["html"], f"escaped: {r['html']}")
            self.assertNotIn("<b>", r["html"], f"no raw tag: {r['html']}")
            self.assertTrue(r["aria"].startswith("Resume "), f"aria prefix: {r['aria']}")

        with self.subTest(case=10, desc="empty list"):
            out = _render([], "America/New_York")
            self.assertEqual(out["rows"], [], "empty rows")
            self.assertIn("No saved sessions yet.", out["containerHtml"], f"empty msg: {out['containerHtml']}")


if __name__ == "__main__":
    unittest.main()

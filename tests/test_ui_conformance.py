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
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import main as app_main  # noqa: E402

WEB = os.path.join(ROOT, "web")
APP_JS = os.path.join(WEB, "app.js")
INDEX_HTML = os.path.join(WEB, "index.html")

# Methods on Api that are NOT part of the core contract: window chrome and UI preferences.
APP_LEVEL_METHODS = {
    "set_window",            # internal wiring, not reachable from JS in practice
    "move_window_to", "resize_window_to", "minimize_window", "exit_app",
    "get_preferences", "set_preference", "choose_entry_save_location",
    "set_entry_save_location",
}

# Fields the frontend reads, by payload. Every one must be present in a live payload.
FIELDS_READ = {
    "session": {"id", "name", "startedAt"},
    "currentEntry": {"id", "task", "startTime"},
    "entries[]": {"id", "task", "description", "startTime", "endTime", "isComplete",
                  "loggedStatus"},
    "summary[]": {"task", "count", "unloggedMinutes", "totalMinutes", "callout"},
    "totals": {"unloggedMinutes", "totalMinutes"},
    "list_sessions[]": {"id", "name", "isUnfinished"},
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
        assert called, "no api() calls found in app.js — the extractor or the frontend changed"
        missing = sorted(m for m in called if not hasattr(app_main.Api, m))
        assert missing == [], f"app.js calls methods Api does not have: {missing}"
        # Canary: retired Log group call is parked, not live
        assert "list_loggable_task_groups" not in called, "list_loggable_task_groups should be parked, not called"
        # Live Summary group toggle still uses these
        assert "log_task_group" in called, "log_task_group call missing from app.js"
        assert "unlog_task_group" in called, "unlog_task_group call missing from app.js"

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
                     "stop_tracking", "stop_and_exit"):
            assert hasattr(app_main.TimeTrackerCore, name), f"core is missing {name}"


class TestFrontendFieldsExist(FrontendCase):
    def test_live_view_model_carries_every_field_the_frontend_reads(self):
        state = self.api.get_state()
        for group in ("session", "currentEntry", "totals"):
            missing = FIELDS_READ[group] - set(state[group])
            assert missing == set(), f"{group} is missing {sorted(missing)}"
        for group, payload in (("entries[]", state["entries"]), ("summary[]", state["summary"])):
            missing = FIELDS_READ[group] - set(payload[0])
            assert missing == set(), f"{group} is missing {sorted(missing)}"

    def test_query_rows_carry_every_field_the_frontend_reads(self):
        rows = {
            "list_sessions[]": self.api.list_sessions(),
            "list_loggable_task_groups[]": self.api.list_loggable_task_groups(),
        }
        self.api.stop_tracking()          # a running entry cannot be deleted
        self.api.delete_entry(2)
        rows["list_deleted_entries[]"] = self.api.list_deleted_entries()
        for group, payload in rows.items():
            assert payload, f"{group} came back empty — cannot check its shape"
            missing = FIELDS_READ[group] - set(payload[0])
            assert missing == set(), f"{group} is missing {sorted(missing)}"

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
        overlay_ids = {"sn-go", "ef-save", "choose-entry-save-location"}
        orphans = sorted(id for id in bound if f'id="{id}"' not in html_code and id not in overlay_ids)
        assert orphans == [], f"app.js binds onclick to ids not in index.html: {orphans}"
        assert "log-group-btn" not in bound, "app.js still has an onclick binding for the removed log-group-btn"
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


class TestWrapperPassesArgumentsThrough(FrontendCase):
    """The wrapper's positional argument order is what the frontend depends on."""

    def test_description_edit_does_not_touch_the_task(self):
        self.api.edit_entry(2, None, "back bed, weeded")
        entry = next(e for e in self.api.get_state()["entries"] if e["id"] == 2)
        assert entry["task"] == "weeding", entry
        assert entry["description"] == "back bed, weeded", entry

    def test_task_edit_does_not_touch_the_description(self):
        self.api.edit_entry(2, "mulching")
        entry = next(e for e in self.api.get_state()["entries"] if e["id"] == 2)
        assert entry["task"] == "mulching", entry
        assert entry["description"] == "back bed", entry

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

if __name__ == "__main__":
    unittest.main()

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
from timetracker_core import CONTRACT_VERSION  # noqa: E402

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
        called = set(re.findall(r"api\(\)\.([A-Za-z_][A-Za-z0-9_]*)", _read(APP_JS)))
        assert called, "no api() calls found in app.js — the extractor or the frontend changed"
        missing = sorted(m for m in called if not hasattr(app_main.Api, m))
        assert missing == [], f"app.js calls methods Api does not have: {missing}"

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
                     "list_loggable_task_groups", "log_task_group", "list_deleted_entries",
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

    def test_frontend_never_reads_a_field_the_contract_removed(self):
        for path in (APP_JS, INDEX_HTML, os.path.join(WEB, "style.css")):
            assert "isActive" not in _read(path), (
                f"{os.path.basename(path)} still reads isActive, removed in contract v1.3"
            )


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

    def test_preferences_round_trip_through_the_bridge(self):
        assert self.api.get_preferences()["activeTab"] == "tasks"     # default
        self.api.set_preference("activeTab", "log")
        assert self.api.get_preferences()["activeTab"] == "log"
        reopened = app_main.PreferencesStore(os.path.join(self.tmp, "preferences.json"))
        assert reopened.get_all()["activeTab"] == "log", "preference did not persist"


class TestThemePreference(FrontendCase):
    """Theme preference: default, validation, and persistence."""

    def test_default_theme_is_cute(self):
        prefs = self.api.get_preferences()
        assert prefs["theme"] == "cute", prefs
        assert prefs["activeTab"] == "tasks", prefs

    def test_set_theme_cyber_persists_and_reloads(self):
        result = self.api.set_preference("theme", "cyber")
        assert result["theme"] == "cyber", result
        assert result["activeTab"] == "tasks", result
        reopened = app_main.PreferencesStore(os.path.join(self.tmp, "preferences.json"))
        assert reopened.get_all()["theme"] == "cyber", "cyber theme did not persist"

    def test_unknown_theme_falls_back_to_cute_on_set(self):
        result = self.api.set_preference("theme", "dark")
        assert result["theme"] == "cute", result
        reopened = app_main.PreferencesStore(os.path.join(self.tmp, "preferences.json"))
        assert reopened.get_all()["theme"] == "cute", "invalid theme was persisted as-is"

    def test_corrupt_persisted_theme_falls_back_to_cute(self):
        prefs_path = os.path.join(self.tmp, "preferences.json")
        with open(prefs_path, "w", encoding="utf-8") as f:
            json.dump({"activeTab": "tasks", "theme": 42}, f)
        reopened = app_main.PreferencesStore(prefs_path)
        assert reopened.get_all()["theme"] == "cute"

    def test_non_string_persisted_theme_falls_back_to_cute(self):
        prefs_path = os.path.join(self.tmp, "preferences.json")
        with open(prefs_path, "w", encoding="utf-8") as f:
            json.dump({"activeTab": "tasks", "theme": None}, f)
        reopened = app_main.PreferencesStore(prefs_path)
        assert reopened.get_all()["theme"] == "cute"


class TestFrontendNamesTheApp(unittest.TestCase):
    def test_page_and_title_bar_use_tinytimekeep(self):
        html = _read(INDEX_HTML)
        assert "<title>tinyTimekeep</title>" in html, "page title is not tinyTimekeep"
        assert "tinyTimekeep" in html.split('id="titlebar"')[1].split("</div>")[0], (
            "title bar label is not tinyTimekeep"
        )

    def test_window_title_constant_matches(self):
        assert app_main.WINDOW_TITLE == "tinyTimekeep", app_main.WINDOW_TITLE

    def test_contract_version_pinned_by_the_app_is_the_contract_in_the_specs(self):
        spec = _read(os.path.join(ROOT, "specs", "core-logic-contract.md"))
        assert f"version: {CONTRACT_VERSION}" in spec, (
            f"specs do not declare {CONTRACT_VERSION} — the gate would pass on a stale spec"
        )
        assert app_main.EXPECTED_CONTRACT_VERSION == CONTRACT_VERSION


class TestChromeAndTheming(unittest.TestCase):
    """Window chrome and themed surfaces — the parts a contract test cannot see."""

    def test_deleted_button_shows_and_refreshes_the_deleted_entry_count(self):
        html = _read(INDEX_HTML)
        js = _read(APP_JS)
        assert 'id="deleted-count">0</span>' in html, "deleted button count must start at zero"
        render = js.split("function render()", 1)[1].split("\n}", 1)[0]
        assert "refreshDeletedCount();" in render, "count must refresh whenever the app renders"
        assert "api().list_deleted_entries()" in js
        assert "setDeletedCount(deleted.length);" in js
        assert "countEl.textContent = String(count);" in js

    def test_title_bar_has_a_minimize_control_and_it_is_wired(self):
        assert 'id="min-btn"' in _read(INDEX_HTML), "no minimize control in the title bar"
        assert "api().minimize_window()" in _read(APP_JS), "the minimize control is not wired"

    def test_minimize_is_a_window_action_not_a_tray_action(self):
        """The ask was a normal minimize to the taskbar. A tray minimize hides the window
        and drops it off the taskbar, which is a different behaviour — pin the distinction."""
        import inspect
        src = inspect.getsource(app_main.Api.minimize_window)
        body = src.split('"""')[-1]      # the docstring names the alternative on purpose
        assert "self._window.minimize()" in body, src
        assert "hide()" not in body, src

    def test_the_scrolling_containers_style_their_scrollbars(self):
        css = _read(os.path.join(WEB, "style.css"))
        assert "::-webkit-scrollbar" in css, "scrollbar left at the platform default"
        tail = css.split("::-webkit-scrollbar", 1)[1]
        for token in ("--panel-row", "--text-dim", "--accent-mint"):
            assert token in tail, f"{token} missing from the scrollbar styling"

    def test_scrollbar_width_is_not_overridden_by_the_standard_properties(self):
        """Chromium ignores ::-webkit-scrollbar entirely when scrollbar-width is set, so a
        stray standard property would silently undo the theming."""
        css = _read(os.path.join(WEB, "style.css"))
        css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)   # the comment below names them
        for prop in ("scrollbar-width", "scrollbar-color"):
            assert prop not in css, f"{prop} would disable the webkit scrollbar rules"

    def test_inactive_banner_does_not_reuse_the_title_bar_pink(self):
        css = _read(os.path.join(WEB, "style.css"))
        rules = [line for line in css.splitlines() if ".status-banner.inactive" in line]
        assert rules, "the inactive banner rule is missing"
        rule = rules[0]
        assert "--inactive" in rule, rule
        assert "--titlebar" not in rule and "--accent-pink" not in rule, (
            f"the inactive banner is sharing a token again: {rule}"
        )
        assert "--inactive:" in css, "the --inactive token is not defined on :root"


if __name__ == "__main__":
    unittest.main()

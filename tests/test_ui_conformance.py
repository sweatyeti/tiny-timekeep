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
from html.parser import HTMLParser

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


class _ThemeBarParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.bar = None
        self.buttons = []
        self.bar_text = []
        self.in_app = False
        self.in_bar = False
        self.in_button = False
        self.bar_inside_app = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "main" and attrs.get("id") == "app":
            self.in_app = True
        if attrs.get("id") == "theme-picker":
            self.bar = attrs
            self.bar_inside_app = self.in_app
            self.in_bar = True
        if self.in_bar:
            if tag == "button":
                self.buttons.append(attrs)
                self.in_button = True
            elif tag not in ("div", "span"):
                self.bar_text.append(f"<{tag}>")

    def handle_endtag(self, tag):
        if tag == "main":
            self.in_app = False
        if tag == "button":
            self.in_button = False
        if tag == "div" and self.in_bar:
            self.in_bar = False

    def handle_data(self, data):
        if self.in_bar and not self.in_button and data.strip():
            self.bar_text.append(data.strip())


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
    def test_bottom_status_bar_has_only_five_themes_and_folder_control(self):
        parser = _ThemeBarParser()
        parser.feed(_read(INDEX_HTML))
        self.assertEqual(parser.bar.get("role"), "toolbar")
        self.assertTrue(parser.bar.get("aria-label"))
        self.assertFalse(parser.bar_inside_app)
        self.assertEqual(parser.bar_text, [])
        self.assertEqual(len(parser.buttons), 6)
        self.assertEqual([button.get("id") for button in parser.buttons],
                         [None, None, None, None, None, "save-location-btn"])
        self.assertEqual([button.get("data-theme") for button in parser.buttons],
                         ["cute", "cyber", "poolside", "evergreen", "citrus-pop", None])
        self.assertTrue(all(button.get("aria-label") and button.get("title")
                            for button in parser.buttons))
        self.assertTrue(all(button.get("aria-pressed") in ("true", "false")
                            for button in parser.buttons[:-1]))

    def test_bottom_status_bar_layout_and_existing_control_wiring(self):
        css = _read(os.path.join(WEB, "style.css"))
        bar = re.search(r"#theme-picker\s*\{([^}]*)\}", css).group(1)
        for declaration in ("position: fixed", "left: 0", "right: 0", "bottom: 0",
                            "justify-content: flex-end", "background: var(--panel)"):
            self.assertIn(declaration, bar)
        app = re.search(r"#app\s*\{([^}]*)\}", css).group(1)
        self.assertIn("height: calc(100% - 90px)", app)
        self.assertIn("#resize-grip", css)
        self.assertIn("padding: 3px 24px 3px 8px", bar)
        js = _read(APP_JS)
        self.assertIn("document.querySelectorAll('.theme-btn').forEach", js)
        self.assertIn("document.getElementById('save-location-btn').onclick", js)
        html = _read(INDEX_HTML)
        for theme in ("cute", "cyber", "poolside", "evergreen", "citrus-pop"):
            self.assertIn(f'data-theme="{theme}"', html)
            self.assertIn(f'body[data-theme="{theme}"]', css)
            self.assertIn(f"'{theme}'", js)

    def test_theme_glyphs_are_larger_without_resizing_folder_or_buttons(self):
        css = re.sub(r"/\*.*?\*/", "", _read(os.path.join(WEB, "style.css")), flags=re.DOTALL)
        base = re.search(r"\.theme-btn\s*\{([^}]*)\}", css)
        self.assertIsNotNone(base)
        base_rules = base.group(1)
        self.assertIn("font-size: 10px", base_rules)
        self.assertIn("width: 22px", base_rules)
        self.assertIn("height: 22px", base_rules)

        icons = re.search(r"button\.theme-btn\[data-theme\]\s*\{([^}]*)\}", css)
        self.assertIsNotNone(icons, "larger glyph rule must target theme buttons only")
        self.assertIn("font-size: 16px", icons.group(1))
        self.assertNotRegex(icons.group(1), r"(?:width|height|padding|gap|line-height)\s*:")
        self.assertNotRegex(css, r"#save-location-btn\s*\{[^}]*font-size\s*:")
        html = _read(INDEX_HTML)
        self.assertEqual(len(re.findall(
            r'data-theme="(?:cute|cyber|poolside|evergreen|citrus-pop)"', html)), 5)

    def test_theme_tree_is_larger_and_all_button_glyphs_are_optically_centered(self):
        html = _read(INDEX_HTML)
        self.assertEqual(html.count('class="theme-icon"'), 6,
                         "all five theme glyphs and the folder icon need a centering wrapper")
        css = re.sub(r"/\*.*?\*/", "", _read(os.path.join(WEB, "style.css")), flags=re.DOTALL)
        centered = re.search(r"\.theme-icon\s*\{([^}]*)\}", css)
        self.assertIsNotNone(centered)
        self.assertIn("transform: translateY(-2px)", centered.group(1))
        tree = re.search(
            r'button\.theme-btn\[data-theme="evergreen"\] \.theme-icon\s*\{([^}]*)\}', css)
        self.assertIsNotNone(tree, "Evergreen's tree glyph needs its own larger size")
        self.assertIn("font-size: 18px", tree.group(1))
        self.assertNotRegex(tree.group(1), r"(?:width|height|padding|gap)\s*:")

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

    def test_all_themes_round_trip_through_store_reopen(self):
        for theme in ("cute", "cyber", "poolside", "evergreen", "citrus-pop"):
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

    def test_theme_selection_updates_persists_and_restores_after_reload(self):
        js = _read(APP_JS)
        self.assertIn("const THEMES = ['cute', 'cyber', 'poolside', 'evergreen', 'citrus-pop']", js)
        self.assertIn("if (!THEMES.includes(theme)) return;", js)
        self.assertIn("applyTheme(theme);", js)
        self.assertIn("api().set_preference('theme', theme)", js)
        self.assertIn("applyTheme(typeof prefs.theme === 'string' && THEMES.includes(prefs.theme)", js)
        for theme in ("poolside", "evergreen", "citrus-pop"):
            self.assertIn(f'"{theme}"', _read(os.path.join(ROOT, "preferences.py")))

    def test_new_palettes_split_accent_fill_and_text_roles(self):
        css = _read(os.path.join(WEB, "style.css"))
        for theme in ("poolside", "evergreen", "citrus-pop"):
            match = re.search(rf'body\[data-theme="{theme}"\]\s*\{{([^}}]*)\}}', css)
            self.assertIsNotNone(match, f"missing CSS palette for {theme}")
            block = match.group(1) if match else ""
            self.assertIn("--accent-pink-text:", block)
            self.assertIn("--accent-mint-text:", block)
        self.assertIn("color: var(--accent-mint-text)", css)
        self.assertIn("color: var(--accent-pink-text)", css)

    def test_theme_font_families_match_between_cute_and_cyber(self):
        css = _read(os.path.join(WEB, "style.css"))
        css_nc = re.sub(r"/\*.*?\*/", "", css, flags=re.DOTALL)

        root_m = re.search(r":root\s*\{([^}]*)\}", css_nc)
        self.assertIsNotNone(root_m, "root block not found")
        root_block = root_m.group(1)
        self.assertIn("--font-body: 'VT323', monospace;", root_block)
        self.assertIn("--font-display: 'Press Start 2P', monospace;", root_block)

        cyber_m = re.search(r'body\[data-theme="cyber"\]\s*\{([^}]*)\}', css_nc)
        self.assertIsNotNone(cyber_m, 'cyber block not found')
        cyber_block = cyber_m.group(1)
        self.assertNotIn("--font-body:", cyber_block)
        self.assertNotIn("--font-display:", cyber_block)

        font_decls = re.findall(r"font-family\s*:\s*([^;]+);", css_nc)
        self.assertIn("var(--font-body)", font_decls)
        self.assertIn("var(--font-display)", font_decls)

        allowed = {"var(--font-body)", "var(--font-display)"}
        for val in font_decls:
            self.assertIn(val.strip(), allowed, f"Unexpected font-family value: {val!r}")

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

    def test_cyber_uses_same_typography_sizes_as_cute(self):
        css = _read(os.path.join(WEB, "style.css"))
        css = re.sub(r"/\*.*?\*/", "", css, flags=re.DOTALL)
        for token in [
            "--cyber-size-bump",
            "--cyber-size-title",
            "--cyber-size-control",
            "--cyber-size-compact",
            "--cyber-size-header",
            "--cyber-size-icon",
        ]:
            assert token not in css, f"obsolete cyber typography token remains: {token}"
        assert "Cyber VT323 readability overrides" not in css
        assert 'body[data-theme="cyber"]' not in css or not re.search(
            r'body\[data-theme="cyber"\][^{]*\{[^}]*font-(?:family|size)\s*:', css
        ), "cyber should not override the shared typography"

    def test_base_sizes_unchanged(self):
        css = _read(os.path.join(WEB, "style.css"))
        base_sizes = [
            ("#titlebar", "12px"),
            (".chrome-btn", "13px"),
            ("h2", "12px"),
            (".btn", "11px"),
            (".btn-mini", "10px"),
            (".session-item button", "10px"),
            (".status-banner", "11px"),
            (".tab-btn", "10px"),
            (".icon-btn", "13px"),
            (".summary-head", "9px"),
            (".overlay-head", "11px"),
            (".theme-btn", "10px"),
        ]
        for sel, size in base_sizes:
            m = re.search(re.escape(sel) + r"\s*\{[^}]*font-size:\s*" + re.escape(size), css)
            assert m, f"base font-size {size} for {sel} not found"
        pane_sizes = [
            (".row-title", "19px"),
            (".row-sub", "15px"),
            (".row-time", "15px"),
            (".summary-row", "17px"),
            (".summary-totals", "17px"),
        ]
        for sel, size in pane_sizes:
            m = re.search(re.escape(sel) + r"\s*\{[^}]*font-size:\s*" + re.escape(size), css)
            assert m, f"pane font-size {size} for {sel} not found"
        m = re.search(r"\.log-entry-row\s*\{([^}]*)\}", css)
        assert m, ".log-entry-row rule not found"
        assert "flex-wrap: nowrap" in m.group(1), ".log-entry-row lost flex-wrap: nowrap"
        assert "align-items: baseline" in m.group(1), ".log-entry-row lost align-items: baseline"


class TestLogEntryRow(unittest.TestCase):
    def _split_render_entries(self, src):
        start = src.index("function renderEntries")
        depth = 0
        i = src.index("{", start)
        for j in range(i, len(src)):
            if src[j] == "{":
                depth += 1
            elif src[j] == "}":
                depth -= 1
                if depth == 0:
                    return src[start:j + 1]
        raise ValueError("unbalanced braces in renderEntries")

    def _split_render_tasks(self, src):
        start = src.index("function renderTasks")
        depth = 0
        i = src.index("{", start)
        for j in range(i, len(src)):
            if src[j] == "{":
                depth += 1
            elif src[j] == "}":
                depth -= 1
                if depth == 0:
                    return src[start:j + 1]
        raise ValueError("unbalanced braces in renderTasks")

    def _scoped_css(self, css):
        marker = "/* Log entry row"
        idx = css.index(marker)
        return css[idx:]

    def test_render_entries_structure(self):
        src = _read(APP_JS)
        fn = self._split_render_entries(src)
        self.assertIn("row.className = 'log-entry-row'", fn)
        self.assertIn('<div class="log-entry-content">', fn)
        self.assertIn('<span class="log-entry-title">', fn)
        self.assertIn('<span class="log-entry-sub">', fn)
        self.assertIn('<div class="log-entry-actions">', fn)
        self.assertNotIn("entry.title", fn)
        c = fn.index('<div class="log-entry-content">')
        t = fn.index('log-entry-title')
        s = fn.index('log-entry-sub')
        a = fn.index('log-entry-actions')
        self.assertLess(c, t)
        self.assertLess(t, s)
        self.assertLess(s, a)
        c_close = fn.index("</div>", s)
        self.assertLess(c_close, a)

    def test_render_tasks_no_log_entry(self):
        src = _read(APP_JS)
        fn = self._split_render_tasks(src)
        self.assertNotIn("log-entry-", fn)

    def test_scoped_css_properties(self):
        css = _read(os.path.join(WEB, "style.css"))
        scoped = self._scoped_css(css)
        self.assertIn("flex-wrap: nowrap", scoped)
        self.assertIn("align-items: baseline", scoped)
        self.assertIn("flex: 1 1 0", scoped)
        self.assertIn("min-width: 0", scoped)
        self.assertIn("overflow-wrap: anywhere", scoped)
        self.assertIn("flex-wrap: wrap", scoped)
        self.assertIn("margin-left: auto", scoped)
        self.assertIn("var(--panel-row-alt)", scoped)
        self.assertIn("gap: 0.25rem 1rem", scoped)
        self.assertIn("padding: 0.3rem 0", scoped)
        self.assertNotIn("width: 100%", scoped)
        self.assertNotIn("margin-left: 0", scoped)
        self.assertNotIn("@media (max-width: 640px)", scoped)

    def test_scoped_css_no_truncation(self):
        css = _read(os.path.join(WEB, "style.css"))
        scoped = self._scoped_css(css)
        self.assertNotIn("white-space: nowrap", scoped)
        self.assertNotIn("text-overflow", scoped)
        self.assertNotIn("ellipsis", scoped)


if __name__ == "__main__":
    unittest.main()

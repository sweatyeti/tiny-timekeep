import json
import os
import re
import subprocess
import unittest
from html.parser import HTMLParser

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX_HTML = os.path.join(ROOT, "web", "index.html")
APP_JS = os.path.join(ROOT, "web", "app.js")
STYLE_CSS = os.path.join(ROOT, "web", "style.css")

_VOID_TAGS = frozenset(
    ("area", "base", "br", "col", "embed", "hr", "img", "input",
     "link", "meta", "param", "source", "track", "wbr")
)

_NODE_COMPANION_SCRIPT = r"""
const fs = require('fs');
const vm = require('vm');

const appPath = process.argv[1];
const source = fs.readFileSync(appPath, 'utf8');

function makeElement(id) {
  return {
    id: id,
    dataset: {},
    textContent: '',
    innerHTML: '',
    style: {},
    children: [],
    classList: {
      _set: new Set(),
      add: function () {
        for (var i = 0; i < arguments.length; i++) this._set.add(arguments[i]);
      },
      remove: function () {
        for (var i = 0; i < arguments.length; i++) this._set.delete(arguments[i]);
      },
      toggle: function (c, force) {
        if (force === undefined) {
          if (this._set.has(c)) this._set.delete(c); else this._set.add(c);
        } else if (force) { this._set.add(c); } else { this._set.delete(c); }
      },
      contains: function (c) { return this._set.has(c); }
    },
    appendChild: function (ch) { this.children.push(ch); return ch; },
    removeChild: function (ch) {
      this.children = this.children.filter(function (x) { return x !== ch; });
      return ch;
    },
    addEventListener: function () {},
    removeEventListener: function () {},
    querySelector: function () { return null; },
    querySelectorAll: function () { return []; },
    getAttribute: function () { return null; },
    setAttribute: function () {},
    removeAttribute: function () {},
    cloneNode: function () { return makeElement(id + '-clone'); },
    focus: function () {},
    blur: function () {},
    click: function () {},
    scrollIntoView: function () {},
    getBoundingClientRect: function () { return { top: 0, left: 0, width: 0, height: 0 }; }
  };
}

function buildContext(getEl) {
  var doc = {
    getElementById: getEl,
    querySelector: function () { return null; },
    querySelectorAll: function () { return []; },
    createElement: function (t) { return makeElement('el-' + t); },
    addEventListener: function () {},
    removeEventListener: function () {},
    body: makeElement('body'),
    documentElement: makeElement('html'),
    head: makeElement('head')
  };
  var ctx = {
    document: doc,
    console: { log: function () {}, error: function () {}, warn: function () {} },
    state: {},
    window: null,
    localStorage: {
      getItem: function () { return null; },
      setItem: function () {},
      removeItem: function () {}
    },
    setTimeout: function () { return 0; },
    clearTimeout: function () {},
    setInterval: function () { return 0; },
    clearInterval: function () {},
    requestAnimationFrame: function () { return 0; },
    cancelAnimationFrame: function () {},
    navigator: { userAgent: 'test' },
    location: { href: '', hash: '', search: '' },
    history: { pushState: function () {}, replaceState: function () {} },
    alert: function () {},
    confirm: function () { return true; },
    prompt: function () { return null; },
    addEventListener: function () {},
    removeEventListener: function () {}
  };
  ctx.window = ctx;
  vm.createContext(ctx);
  vm.runInContext(source, ctx);
  return ctx;
}

var results = {};

var els = {};
var ctx = buildContext(function (id) {
  if (!els[id]) els[id] = makeElement(id);
  return els[id];
});

var activeVM = { currentEntry: { id: 1 } };
results.activeState = ctx.getCompanionState(activeVM);

ctx.renderCompanion(activeVM);
results.activeRender = {
  mode: els['companion'] ? els['companion'].dataset.mode : null,
  label: els['companion-label'] ? els['companion-label'].textContent : null
};

var sleepInputs = [{ currentEntry: null }, {}, null];
results.sleepingStates = sleepInputs.map(function (v) { return ctx.getCompanionState(v); });

delete els['companion'];
delete els['companion-label'];
ctx.renderCompanion(null);
results.sleepingRender = {
  mode: els['companion'] ? els['companion'].dataset.mode : null,
  label: els['companion-label'] ? els['companion-label'].textContent : null
};

var emptyCtx = buildContext(function () { return null; });
try {
  emptyCtx.renderCompanion(null);
  results.noElements = { threw: false };
} catch (e) {
  results.noElements = { threw: true, error: e.message };
}

process.stdout.write(JSON.stringify(results));
"""


def _run_node(script, *args):
    cmd = ["node", "-e", script] + [str(a) for a in args]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if proc.returncode != 0:
        raise AssertionError(
            "Node script failed (exit {})\nstdout: {}\nstderr: {}".format(
                proc.returncode, proc.stdout, proc.stderr
            )
        )
    return proc.stdout


def _run_node_json(script, *args):
    out = _run_node(script, *args)
    return json.loads(out)


class _CompanionHTMLParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_companion = False
        self.companion_depth = 0
        self.companion_tag = None
        self.companion_attrs = {}
        self.has_aria_hidden_scene = False
        self.has_sr_label = False
        self.forbidden_descendants = []
        self.companion_found = False

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        if not self.in_companion:
            if tag == "aside" and attrs_dict.get("id") == "companion":
                self.in_companion = True
                self.companion_depth = 1
                self.companion_tag = tag
                self.companion_attrs = attrs_dict
                self.companion_found = True
            return
        if tag not in _VOID_TAGS:
            self.companion_depth += 1
        if attrs_dict.get("aria-hidden") == "true":
            self.has_aria_hidden_scene = True
        if tag == "span" and attrs_dict.get("id") == "companion-label":
            self.has_sr_label = True
        if tag in ("button", "input", "a", "select", "textarea"):
            self.forbidden_descendants.append(tag)

    def handle_endtag(self, tag):
        if self.in_companion and tag not in _VOID_TAGS:
            self.companion_depth -= 1
            if self.companion_depth == 0:
                self.in_companion = False


class TestPixelCompanionJavaScript(unittest.TestCase):
    """Execute real getCompanionState and renderCompanion via Node vm."""

    @classmethod
    def setUpClass(cls):
        if not os.path.isfile(APP_JS):
            raise unittest.SkipTest("app.js not found at {}".format(APP_JS))
        cls.results = _run_node_json(_NODE_COMPANION_SCRIPT, APP_JS)

    def assert_pixel_companion_state(self, actual, mode):
        self.assertEqual(actual["mode"], mode)
        if mode == "awake":
            expected_label = "Pixel Companion is awake while a task is being tracked."
        else:
            expected_label = "Pixel Companion is sleeping because no task is being tracked."
        self.assertEqual(actual["label"], expected_label)

    def test_active_state_yields_awake(self):
        self.assert_pixel_companion_state(self.results["activeState"], "awake")

    def test_active_render_updates_dom(self):
        self.assert_pixel_companion_state(self.results["activeRender"], "awake")

    def test_null_currentEntry_yields_sleeping(self):
        self.assert_pixel_companion_state(self.results["sleepingStates"][0], "sleeping")

    def test_empty_object_yields_sleeping(self):
        self.assert_pixel_companion_state(self.results["sleepingStates"][1], "sleeping")

    def test_null_viewmodel_yields_sleeping(self):
        self.assert_pixel_companion_state(self.results["sleepingStates"][2], "sleeping")

    def test_sleeping_render_updates_dom(self):
        self.assert_pixel_companion_state(self.results["sleepingRender"], "sleeping")

    def test_render_companion_no_elements_no_throw(self):
        self.assertFalse(
            self.results["noElements"]["threw"],
            "renderCompanion threw when elements absent: {}".format(
                self.results["noElements"].get("error")
            ),
        )


class TestPixelCompanionMarkup(unittest.TestCase):
    """Verify #companion HTML structure and accessibility attributes."""

    @classmethod
    def setUpClass(cls):
        if not os.path.isfile(INDEX_HTML):
            raise unittest.SkipTest("index.html not found at {}".format(INDEX_HTML))
        with open(INDEX_HTML, "r", encoding="utf-8") as f:
            cls.html = f.read()
        parser = _CompanionHTMLParser()
        parser.feed(cls.html)
        cls.parser = parser

    def test_companion_is_aside(self):
        self.assertTrue(self.parser.companion_found, "#companion element not found")
        self.assertEqual(self.parser.companion_tag, "aside")

    def test_companion_role_status(self):
        self.assertEqual(self.parser.companion_attrs.get("role"), "status")

    def test_companion_aria_live_polite(self):
        self.assertEqual(self.parser.companion_attrs.get("aria-live"), "polite")

    def test_contains_aria_hidden_scene(self):
        self.assertTrue(
            self.parser.has_aria_hidden_scene,
            "No aria-hidden='true' descendant found inside #companion",
        )

    def test_contains_screen_reader_label(self):
        self.assertTrue(
            self.parser.has_sr_label,
            "No span#companion-label found inside #companion",
        )

    def test_no_interactive_descendants(self):
        self.assertEqual(
            self.parser.forbidden_descendants,
            [],
            "Forbidden interactive elements inside #companion: {}".format(
                self.parser.forbidden_descendants
            ),
        )


class TestPixelCompanionStyles(unittest.TestCase):
    """Verify CSS constraints for the Pixel Companion."""

    @classmethod
    def setUpClass(cls):
        if not os.path.isfile(STYLE_CSS):
            raise unittest.SkipTest("style.css not found at {}".format(STYLE_CSS))
        with open(STYLE_CSS, "r", encoding="utf-8") as f:
            cls.css = f.read()

    def _companion_rules(self):
        """Extract all rule blocks whose selector mentions companion."""
        rules = []
        for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", self.css):
            selector = m.group(1).strip()
            body = m.group(2)
            if "companion" in selector.lower():
                rules.append((selector, body))
        return rules

    def test_width_64px(self):
        rules = self._companion_rules()
        found = any(
            re.search(r"width\s*:\s*64px", body) for _, body in rules
        )
        self.assertTrue(found, "No companion rule sets width: 64px")

    def test_height_48px(self):
        rules = self._companion_rules()
        found = any(
            re.search(r"height\s*:\s*48px", body) for _, body in rules
        )
        self.assertTrue(found, "No companion rule sets height: 48px")

    def test_uses_panel_row_token(self):
        rules = self._companion_rules()
        found = any("var(--panel-row)" in body for _, body in rules)
        self.assertTrue(found, "Companion section does not use var(--panel-row)")

    def test_cute_theme_scoping(self):
        rules = self._companion_rules()

        def find_display(selector):
            for sel, body in rules:
                if sel == selector:
                    m = re.search(r"display\s*:\s*(\S+?);", body)
                    self.assertIsNotNone(
                        m,
                        f"No display declaration in rule for {selector!r}",
                    )
                    return m.group(1)
            self.fail(f"No rule found for selector {selector!r}")

        self.assertEqual(
            find_display('body[data-theme="cute"] .companion-cat'),
            "block",
        )
        self.assertEqual(
            find_display(".companion-cat"),
            "none",
        )
        self.assertEqual(
            find_display('body[data-theme="cyber"] .companion-cyber'),
            "block",
        )
        self.assertEqual(
            find_display(".companion-cyber"),
            "none",
        )

    def test_cat_eye_color_literal(self):
        self.assertRegex(
            self.css,
            r"\.companion-eye\s*\{[^}]*background\s*:\s*#246b35",
        )

    def test_cyber_lens_color(self):
        self.assertRegex(
            self.css,
            r"\.companion-cyber-eye-lens\s*\{[^}]*background\s*:\s*#00e6c8",
        )

    def test_cyber_skin_tones(self):
        self.assertIn("#986342", self.css)
        self.assertIn("#b87e5b", self.css)
        self.assertIn("#704630", self.css)

    def test_sleep_cue_uses_theme_font_token(self):
        self.assertRegex(
            self.css,
            r"\.companion-sleep-cue\s*\{[^}]*font-family\s*:\s*var\(--font-body\)",
            "Sleep cue must use the theme body font so cyber stays VT323-only",
        )

    def test_sleeping_mode_selector(self):
        rules = self._companion_rules()
        found = any("sleeping" in sel for sel, _ in rules)
        self.assertTrue(found, "No companion rule for sleeping mode")

    def test_awake_mode_selector(self):
        rules = self._companion_rules()
        found = any("awake" in sel for sel, _ in rules)
        self.assertTrue(found, "No companion rule for awake mode")

    def test_cat_body_attached_below_face(self):
        face_m = re.search(r"\.companion-face\s*\{([^}]*)\}", self.css)
        body_m = re.search(r"\.companion-body\s*\{([^}]*)\}", self.css)
        self.assertIsNotNone(face_m, "No .companion-face rule found")
        self.assertIsNotNone(body_m, "No .companion-body rule found")

        face_top = int(re.search(r"top\s*:\s*(\d+)px", face_m.group(1)).group(1))
        face_h = int(re.search(r"height\s*:\s*(\d+)px", face_m.group(1)).group(1))
        body_top = int(re.search(r"top\s*:\s*(\d+)px", body_m.group(1)).group(1))
        self.assertEqual(body_top, face_top + face_h)
        sleeping_body_m = re.search(r'#companion\[data-mode="sleeping"\]\s*\.companion-body\s*\{([^}]*)\}', self.css)
        self.assertIsNotNone(sleeping_body_m, "No sleeping .companion-body rule found")
        sleeping_body_top = int(re.search(r"top\s*:\s*(\d+)px", sleeping_body_m.group(1)).group(1))
        self.assertEqual(sleeping_body_top, face_top + face_h)

    def test_cyber_jaw_plate(self):
        self.assertRegex(
            self.css,
            r"\.companion-cyber-jaw\s*\{[^}]*background\s*:\s*#704630",
        )

    def test_reduced_motion_media_query(self):
        m = re.search(
            r"@media\s*\(\s*prefers-reduced-motion\s*:\s*reduce\s*\)\s*\{",
            self.css,
        )
        self.assertIsNotNone(m, "No @media (prefers-reduced-motion: reduce) block")
        start = m.end()
        depth = 1
        i = start
        while i < len(self.css) and depth > 0:
            if self.css[i] == "{":
                depth += 1
            elif self.css[i] == "}":
                depth -= 1
            i += 1
        block = self.css[start : i - 1]
        self.assertIn("companion-cat", block,
                      "Reduced-motion block does not target .companion-cat")
        self.assertIn("companion-cyber", block,
                      "Reduced-motion block does not target .companion-cyber")
        self.assertRegex(block, r"animation\s*:\s*none",
                         "Reduced-motion block does not disable animation")
        self.assertRegex(block, r"transform\s*:\s*none",
                         "Reduced-motion block does not set transform: none")


class TestPixelCompanionWiring(unittest.TestCase):
    """Verify render() calls renderCompanion(state) before session branch."""

    @classmethod
    def setUpClass(cls):
        if not os.path.isfile(APP_JS):
            raise unittest.SkipTest("app.js not found at {}".format(APP_JS))
        with open(APP_JS, "r", encoding="utf-8") as f:
            cls.source = f.read()

    def _render_body(self):
        m = re.search(r"function\s+render\s*\(\s*\)\s*\{", self.source)
        self.assertIsNotNone(m, "render() function not found in app.js")
        start = m.end()
        depth = 1
        i = start
        while i < len(self.source) and depth > 0:
            if self.source[i] == "{":
                depth += 1
            elif self.source[i] == "}":
                depth -= 1
            i += 1
        return self.source[start : i - 1]

    def test_render_companion_called_before_session_branch(self):
        body = self._render_body()
        rc_idx = body.find("renderCompanion(state)")
        self.assertNotEqual(rc_idx, -1,
                            "renderCompanion(state) not found in render() body")
        branch_match = re.search(r"if\s*\(\s*noSession\s*\)", body)
        self.assertIsNotNone(branch_match,
                             "Session branch (if noSession) not found in render()")
        self.assertLess(
            rc_idx, branch_match.start(),
            "renderCompanion(state) must be called before the session branch",
        )

    def test_get_companion_state_uses_current_entry(self):
        m = re.search(
            r"function\s+getCompanionState\s*\(\s*viewModel\s*\)\s*\{",
            self.source,
        )
        self.assertIsNotNone(m, "getCompanionState not found")
        start = m.end()
        depth = 1
        i = start
        while i < len(self.source) and depth > 0:
            if self.source[i] == "{":
                depth += 1
            elif self.source[i] == "}":
                depth -= 1
            i += 1
        fn_body = self.source[start : i - 1]
        self.assertIn("currentEntry", fn_body,
                      "getCompanionState does not reference viewModel.currentEntry")


if __name__ == "__main__":
    unittest.main()

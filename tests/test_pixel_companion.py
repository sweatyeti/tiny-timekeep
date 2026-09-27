import json
import os
import re
import subprocess
import unittest
import glob
from html.parser import HTMLParser

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX_HTML = os.path.join(ROOT, "web", "index.html")
APP_JS = os.path.join(ROOT, "web", "app.js")
STYLE_CSS = os.path.join(ROOT, "web", "style.css")
COMPANION_CSS = os.path.join(ROOT, "web", "companions")
COMPANION_SHARED_CSS = os.path.join(COMPANION_CSS, "companion.css")
COMPANION_REGISTRY_JS = os.path.join(COMPANION_CSS, "registry.js")

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

    def test_awake_and_sleeping_states_update_the_live_region(self):
        self.assert_pixel_companion_state(self.results["activeState"], "awake")
        self.assert_pixel_companion_state(self.results["activeRender"], "awake")
        self.assert_pixel_companion_state(self.results["sleepingStates"][0], "sleeping")
        self.assert_pixel_companion_state(self.results["sleepingStates"][1], "sleeping")
        self.assert_pixel_companion_state(self.results["sleepingStates"][2], "sleeping")
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

    def test_markup_preserves_status_and_artwork_accessibility(self):
        self.assertTrue(self.parser.companion_found, "#companion element not found")
        self.assertEqual(self.parser.companion_tag, "aside")
        self.assertEqual(self.parser.companion_attrs.get("role"), "status")
        self.assertEqual(self.parser.companion_attrs.get("aria-live"), "polite")
        self.assertTrue(
            self.parser.has_aria_hidden_scene,
            "No aria-hidden='true' descendant found inside #companion",
        )
        self.assertTrue(
            self.parser.has_sr_label,
            "No span#companion-label found inside #companion",
        )
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
        paths = [STYLE_CSS] + glob.glob(os.path.join(COMPANION_CSS, "*.css"))
        contents = []
        for path in paths:
            with open(path, "r", encoding="utf-8") as f:
                contents.append(f.read())
        cls.css = "\n".join(contents)
        with open(COMPANION_SHARED_CSS, "r", encoding="utf-8") as f:
            cls.shared_css = f.read()

    def _companion_rules(self):
        """Extract all rule blocks whose selector mentions companion."""
        rules = []
        for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", self.css):
            selector = m.group(1).strip()
            body = m.group(2)
            if "companion" in selector.lower():
                rules.append((selector, body))
        return rules

    def _match_group(self, pattern, source, message):
        match = re.search(pattern, source)
        if match is None:
            self.fail(message)
        return match.group(1)

    def _rule_body(self, source, selector):
        return self._match_group(
            re.escape(selector) + r"\s*\{([^{}]*)\}",
            source,
            "Missing CSS rule for {}".format(selector),
        )

    def _registered_avatars(self):
        with open(COMPANION_REGISTRY_JS, "r", encoding="utf-8") as f:
            registry = f.read()
        avatars_block = re.search(
            r"const\s+COMPANION_AVATARS\s*=\s*\{([^}]*)\}", registry, re.S
        )
        if avatars_block is None:
            self.fail("Missing COMPANION_AVATARS registry")
        avatars = re.findall(r"^\s*([a-z][a-z0-9-]*)\s*:", avatars_block.group(1), re.M)
        self.assertTrue(avatars, "No avatar renderers are registered")
        for avatar in avatars:
            path = os.path.join(COMPANION_CSS, avatar + ".css")
            self.assertTrue(os.path.isfile(path), "Missing CSS for registered avatar {}".format(avatar))
        return avatars

    def _avatar_dimensions(self, slug, source):
        root = ".companion-{}".format(slug)
        declarations = self._rule_body(source, root)

        def pixels(name):
            value = self._match_group(
                r"\b{}\s*:\s*(\d+(?:\.\d+)?)px".format(name),
                declarations,
                "{} must declare its {} canvas size".format(root, name),
            )
            return float(value)

        scale_match = re.search(r"--companion-scale\s*:\s*(\d+(?:\.\d+)?)", declarations)
        scale = float(scale_match.group(1)) if scale_match else 1.0
        self.assertGreater(scale, 0, "{} scale must be positive".format(root))
        return pixels("width"), pixels("height"), scale

    def _motion_distance(self, keyframe):
        body = self._match_group(
            r"@keyframes\s+{}\s*\{{([\s\S]*?)\n\}}".format(keyframe),
            self.shared_css,
            "Missing {} keyframes".format(keyframe),
        )
        distances = [
            float(value)
            for value in re.findall(
                r"calc\(\s*-50%\s*-\s*(\d+(?:\.\d+)?)px\s*\)",
                body,
            )
        ]
        self.assertTrue(distances, "{} must declare its vertical motion envelope".format(keyframe))
        self.assertRegex(
            body,
            r"scale\(\s*var\(--companion-scale,\s*1\)\s*\)",
            "{} must preserve each avatar's scale".format(keyframe),
        )
        return max(distances)

    def test_avatar_root_motion_and_reduced_motion_are_generic(self):
        root_selector = ".companion-scene > :not(.companion-sleep-cue)"
        root_rule = self._rule_body(self.shared_css, root_selector)
        self.assertRegex(
            root_rule, r"position\s*:\s*absolute"
        )
        self.assertRegex(root_rule, r"left\s*:\s*50%")
        self.assertRegex(root_rule, r"top\s*:\s*50%")
        self.assertRegex(
            root_rule,
            r"transform\s*:\s*translate\(-50%,\s*-50%\)\s*"
            r"scale\(var\(--companion-scale,\s*1\)\)",
            "Every avatar root must use the shared centered, per-avatar transform",
        )
        self.assertRegex(
            self.shared_css,
            r'#companion\[data-mode="awake"\]\s*' + re.escape(root_selector)
            + r"\s*\{[^}]*animation\s*:\s*companion-awake-bob",
        )
        self.assertRegex(
            self.shared_css,
            r'#companion\[data-mode="sleeping"\]\s*' + re.escape(root_selector)
            + r"\s*\{[^}]*animation\s*:\s*companion-sleep-bob",
        )
        reduced = re.search(
            r"@media\s*\(\s*prefers-reduced-motion\s*:\s*reduce\s*\)\s*\{([\s\S]*)\}\s*$",
            self.shared_css,
        )
        if reduced is None:
            self.fail("No reduced-motion rules in shared companion CSS")
        reduced_rules = reduced.group(1)
        self.assertRegex(reduced_rules, r"animation\s*:\s*none\s*!important")
        self.assertIn(root_selector, reduced_rules)
        self.assertRegex(
            reduced_rules,
            r"transform\s*:\s*translate\(-50%,\s*-50%\)\s*"
            r"scale\(var\(--companion-scale,\s*1\)\)",
            "Reduced motion must retain the centered per-avatar scale",
        )

    def test_registered_and_nonstandard_avatar_canvases_fit_every_motion_state(self):
        frame = self._rule_body(self.shared_css, "#companion")
        width = float(self._match_group(
            r"\bwidth\s*:\s*(\d+(?:\.\d+)?)px", frame, "Frame width is missing"
        ))
        height = float(self._match_group(
            r"\bheight\s*:\s*(\d+(?:\.\d+)?)px", frame, "Frame height is missing"
        ))
        border = float(self._match_group(
            r"\bborder\s*:\s*(\d+(?:\.\d+)?)px", frame, "Frame border is missing"
        ))
        self.assertEqual((width, height), (128, 96))
        self.assertRegex(frame, r"box-sizing\s*:\s*border-box")
        self.assertRegex(frame, r"overflow\s*:\s*hidden")
        inner_width = width - 2 * border
        inner_height = height - 2 * border

        cases = []
        for avatar in self._registered_avatars():
            path = os.path.join(COMPANION_CSS, avatar + ".css")
            with open(path, "r", encoding="utf-8") as f:
                source = f.read()
            cases.append((avatar, self._avatar_dimensions(avatar, source)))

        # A test-only authoring canary: neither the historical canvas nor 2x scaling.
        fixture_css = (
            ".companion-fit-fixture { width: 46px; height: 54px; "
            "--companion-scale: 1; }"
        )
        fixture_dimensions = self._avatar_dimensions("fit-fixture", fixture_css)
        self.assertNotEqual(fixture_dimensions[0], 32)
        self.assertNotEqual(fixture_dimensions[1], 36)
        self.assertNotEqual(fixture_dimensions[2], 2)
        cases.append(("fit-fixture", fixture_dimensions))

        awake_motion = self._motion_distance("companion-awake-bob")
        sleep_motion = self._motion_distance("companion-sleep-bob")
        for avatar, (canvas_width, canvas_height, scale) in cases:
            rendered_width = canvas_width * scale
            rendered_height = canvas_height * scale
            self.assertLessEqual(
                rendered_width, inner_width,
                "{} artwork exceeds the frame width".format(avatar),
            )
            for state, vertical_offset in (
                ("awake", awake_motion),
                ("sleeping", sleep_motion),
                ("reduced motion", 0),
            ):
                top = (inner_height - rendered_height) / 2 - vertical_offset
                bottom = top + rendered_height
                self.assertGreaterEqual(
                    top, 0, "{} {} animation clips at the top".format(avatar, state)
                )
                self.assertLessEqual(
                    bottom, inner_height,
                    "{} {} animation clips at the bottom".format(avatar, state),
                )

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
        self.assertEqual(
            find_display('body[data-theme="poolside"] .companion-sun'),
            "block",
        )
        self.assertEqual(
            find_display(".companion-sun"),
            "none",
        )

class TestPixelCompanionWiring(unittest.TestCase):
    """Verify mapped renderers and the theme-to-registry connection."""

    @classmethod
    def setUpClass(cls):
        if not os.path.isfile(APP_JS):
            raise unittest.SkipTest("app.js not found at {}".format(APP_JS))
        with open(APP_JS, "r", encoding="utf-8") as f:
            cls.source = f.read()

    def test_registry_renders_mapped_avatar_for_each_existing_theme(self):
        script = r"""
const fs = require('fs');
const vm = require('vm');
const cat = fs.readFileSync(process.argv[1], 'utf8');
const cyber = fs.readFileSync(process.argv[2], 'utf8');
const sun = fs.readFileSync(process.argv[3], 'utf8');
const registry = fs.readFileSync(process.argv[4], 'utf8');
const scene = { innerHTML: '' };
const ctx = { document: { querySelector: () => scene } };
vm.createContext(ctx);
vm.runInContext(cat + '\n' + cyber + '\n' + sun + '\n' + registry, ctx);
const themes = ['cute', 'cyber', 'poolside', 'evergreen', 'citrus-pop'];
const rendered = {};
themes.forEach(theme => {
  ctx.renderCompanionScene(theme);
  rendered[theme] = scene.innerHTML;
});
process.stdout.write(JSON.stringify({
  mapping: themes.map(theme => ctx.resolveCompanionAvatar(theme)), rendered
}));
"""
        result = _run_node_json(
            script,
            os.path.join(COMPANION_CSS, "cat.js"),
            os.path.join(COMPANION_CSS, "cyber.js"),
            os.path.join(COMPANION_CSS, "sun.js"),
            COMPANION_REGISTRY_JS,
        )
        self.assertEqual(result["mapping"], ["cat", "cyber", "sun", None, None])
        self.assertIn('class="companion-cat"', result["rendered"]["cute"])
        self.assertNotIn('class="companion-cyber"', result["rendered"]["cute"])
        self.assertNotIn('class="companion-sun"', result["rendered"]["cute"])
        self.assertIn('class="companion-cyber"', result["rendered"]["cyber"])
        self.assertNotIn('class="companion-cat"', result["rendered"]["cyber"])
        self.assertNotIn('class="companion-sun"', result["rendered"]["cyber"])
        self.assertIn('class="companion-sun"', result["rendered"]["poolside"])
        self.assertNotIn('class="companion-cat"', result["rendered"]["poolside"])
        self.assertNotIn('class="companion-cyber"', result["rendered"]["poolside"])
        for theme in ("evergreen", "citrus-pop"):
            self.assertNotIn('class="companion-cat"', result["rendered"][theme])
            self.assertNotIn('class="companion-cyber"', result["rendered"][theme])
            self.assertNotIn('class="companion-sun"', result["rendered"][theme])
            self.assertIn('class="companion-sleep-cue"', result["rendered"][theme])

    def test_theme_application_loads_and_calls_registry_renderer(self):
        with open(INDEX_HTML, "r", encoding="utf-8") as f:
            html = f.read()
        self.assertLess(html.index('src="companions/cat.js"'),
                        html.index('src="companions/registry.js"'))
        self.assertLess(html.index('src="companions/registry.js"'),
                        html.index('src="app.js"'))
        match = re.search(r"function\s+applyTheme\s*\(theme\)\s*\{", self.source)
        if match is None:
            self.fail("applyTheme() not found")
        body_start = match.end()
        depth = 1
        index = body_start
        while index < len(self.source) and depth:
            if self.source[index] == "{":
                depth += 1
            elif self.source[index] == "}":
                depth -= 1
            index += 1
        self.assertIn("renderCompanionScene(theme)", self.source[body_start:index - 1])


if __name__ == "__main__":
    unittest.main()

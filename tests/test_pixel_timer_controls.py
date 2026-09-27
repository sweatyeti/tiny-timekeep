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


_NODE_SCRIPT = r"""
const fs = require('fs');
const vm = require('vm');
const source = fs.readFileSync(process.argv[1], 'utf8');
const elements = {};

function makeElement(id) {
  let text = '';
  const classes = new Set();
  return {
    id,
    attrs: {},
    title: '',
    value: '',
    children: [],
    style: {},
    onclick: null,
    className: '',
    classList: {
      add: (...names) => names.forEach(name => classes.add(name)),
      remove: (...names) => names.forEach(name => classes.delete(name)),
      contains: name => classes.has(name),
      toggle: (name, force) => {
        const enabled = force === undefined ? !classes.has(name) : Boolean(force);
        if (enabled) classes.add(name); else classes.delete(name);
        return enabled;
      }
    },
    get textContent() { return text; },
    set textContent(value) { text = String(value); this.children = []; },
    setAttribute(name, value) {
      this.attrs[name] = String(value);
      if (name === 'title') this.title = String(value);
    },
    getAttribute(name) { return this.attrs[name] || null; },
    querySelector(selector) {
      if (selector === '.timer-refresh') return this.refresh && this.children.includes(this.refresh) ? this.refresh : null;
      return null;
    },
    addEventListener() {},
    removeEventListener() {},
    appendChild(child) { this.children.push(child); return child; },
    focus() {},
    click() {}
  };
}

const document = {
  getElementById(id) { return elements[id] || (elements[id] = makeElement(id)); },
  querySelectorAll() { return []; },
  querySelector() { return null; },
  createElement(tag) { return makeElement('created-' + tag); },
  addEventListener() {},
  removeEventListener() {},
  body: makeElement('body')
};
const stop = document.getElementById('stop-btn');
stop.classList.add('hidden');
const start = document.getElementById('stop-start-btn');
const playIcon = makeElement('play-icon');
const refreshIcon = makeElement('refresh-icon');
refreshIcon.classList.add('hidden');
start.refresh = refreshIcon;
start.children.push(playIcon, refreshIcon);

const ctx = {
  document,
  console,
  Date,
  Math,
  Promise,
  setTimeout,
  clearTimeout,
  setInterval,
  clearInterval,
  addEventListener() {},
  removeEventListener() {}
};
ctx.window = ctx;
vm.createContext(ctx);
vm.runInContext(source, ctx);

function setState(value) {
  ctx.__testState = value;
  vm.runInContext('state = __testState', ctx);
  delete ctx.__testState;
}
const initialEntry = {
  id: 1,
  task: 'A deliberately long task name that should remain accessible',
  startTime: '2026-09-27T15:04:00Z'
};
const childrenBeforeRender = start.children.slice();
setState({ session: { id: 1 }, currentEntry: initialEntry });
ctx.renderCurrent();
const active = {
  stopHidden: stop.classList.contains('hidden'),
  startHidden: start.classList.contains('hidden'),
  stopLabel: stop.getAttribute('aria-label'),
  stopTitle: stop.title,
  startLabel: start.getAttribute('aria-label'),
  startTitle: start.title,
  taskText: document.getElementById('current-label').textContent,
  taskTitle: document.getElementById('current-label').title,
  refreshHidden: refreshIcon.classList.contains('hidden'),
  iconChildrenPreserved: start.children.length === childrenBeforeRender.length && start.children.every((child, i) => child === childrenBeforeRender[i])
};

setState({ session: { id: 1 }, currentEntry: null });
ctx.renderCurrent();
const idle = {
  stopHidden: stop.classList.contains('hidden'),
  startHidden: start.classList.contains('hidden'),
  startLabel: start.getAttribute('aria-label'),
  startTitle: start.title,
  refreshHidden: refreshIcon.classList.contains('hidden'),
  iconChildrenPreserved: start.children.length === childrenBeforeRender.length && start.children.every((child, i) => child === childrenBeforeRender[i])
};

const calls = [];
let overlay = null;
let closed = false;
let renderCalls = 0;
ctx.window.pywebview = { api: {
  async stop_tracking() {
    calls.push(['stop_tracking']);
    return { ok: true, state: { session: { id: 1 }, currentEntry: null } };
  },
  async stop_and_start_entry(...args) {
    calls.push(['stop_and_start_entry', ...args]);
    return { ok: true, state: { session: { id: 1 }, currentEntry: { id: 42, task: 'unnamed', startTime: '2026-09-27T15:05:00Z' } } };
  },
  async edit_entry(...args) {
    calls.push(['edit_entry', ...args]);
    return { ok: true, state: { session: { id: 1 }, currentEntry: { id: 42, task: args[1], startTime: '2026-09-27T15:05:00Z' } } };
  }
} };
ctx.render = function () { renderCalls += 1; ctx.renderCurrent(); };
ctx.openOverlay = function (title, body) { overlay = { title, body }; };
ctx.closeOverlay = function () { closed = true; };
ctx.wireActiveScreen();
setState({ session: { id: 1 }, currentEntry: initialEntry });
ctx.renderCurrent();

(async () => {
  await stop.onclick();
  const afterStop = {
    stopHidden: stop.classList.contains('hidden'),
    startLabel: start.getAttribute('aria-label'),
    refreshHidden: refreshIcon.classList.contains('hidden')
  };
  await start.onclick();
  document.getElementById('sn-task').value = 'Next task';
  await document.getElementById('sn-go').onclick();
  process.stdout.write(JSON.stringify({ active, idle, afterStop, calls, overlay, closed, renderCalls,
    finalTask: document.getElementById('current-label').textContent,
    finalRefreshHidden: refreshIcon.classList.contains('hidden') }));
})().catch(error => { console.error(error); process.exitCode = 1; });
"""


def _run_node_json(script, *args):
    proc = subprocess.run(
        ["node", "-e", script, *[str(arg) for arg in args]],
        capture_output=True, text=True, timeout=30,
    )
    if proc.returncode != 0:
        raise AssertionError(
            "Node script failed (exit {})\nstdout: {}\nstderr: {}".format(
                proc.returncode, proc.stdout, proc.stderr
            )
        )
    return json.loads(proc.stdout)


class _TrackingHTMLParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.stack = []
        self.nodes = []

    def handle_starttag(self, tag, attrs):
        node = {"tag": tag, "attrs": dict(attrs), "ancestors": list(self.stack), "text": ""}
        self.nodes.append(node)
        if tag not in _VOID_TAGS:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.nodes.append({"tag": tag, "attrs": dict(attrs), "ancestors": list(self.stack), "text": ""})

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index]["tag"] == tag:
                del self.stack[index:]
                return

    def handle_data(self, data):
        for node in reversed(self.stack):
            if node["tag"] == "button":
                node["text"] += data
                return


def _classes(node):
    return set(node["attrs"].get("class", "").split())


def _contrast_ratio(foreground, background):
    def luminance(color):
        channels = [int(color[index:index + 2], 16) / 255 for index in (1, 3, 5)]
        linear = [value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4 for value in channels]
        return sum(component * weight for component, weight in zip(linear, (0.2126, 0.7152, 0.0722)))

    high, low = sorted((luminance(foreground), luminance(background)), reverse=True)
    return (high + 0.05) / (low + 0.05)


class TestPixelTimerControlMarkup(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(INDEX_HTML, "r", encoding="utf-8") as source:
            cls.html = source.read()
        cls.parser = _TrackingHTMLParser()
        cls.parser.feed(cls.html)
        cls.nodes = cls.parser.nodes

    def _by_id(self, element_id):
        matches = [node for node in self.nodes if node["attrs"].get("id") == element_id]
        self.assertEqual(len(matches), 1, "expected exactly one #{}".format(element_id))
        return matches[0]

    def test_two_existing_buttons_and_companion_share_the_top_grid(self):
        top = next(node for node in self.nodes if "now-tracking-top" in _classes(node))
        actions = next(node for node in self.nodes if "now-tracking-actions" in _classes(node))
        companion = self._by_id("companion")
        self.assertIs(actions["ancestors"][-1], top)
        self.assertIs(companion["ancestors"][-1], top)
        action_buttons = [
            node for node in self.nodes
            if node["tag"] == "button" and actions in node["ancestors"]
        ]
        self.assertEqual(
            [node["attrs"].get("id") for node in action_buttons],
            ["stop-btn", "stop-start-btn"],
        )
        self.assertTrue(all(node["ancestors"][-1] is actions for node in action_buttons))
        card = next(node for node in self.nodes if "now-tracking" in _classes(node))
        card_buttons = [
            node for node in self.nodes
            if node["tag"] == "button" and card in node["ancestors"]
        ]
        self.assertEqual(
            [node["attrs"].get("id") for node in card_buttons],
            ["stop-btn", "stop-start-btn"],
        )

    def test_timer_actions_are_icon_only_native_buttons_with_accessible_names(self):
        expected = {
            "stop-btn": "Stop tracking",
            "stop-start-btn": "Stop and start a new task",
        }
        for element_id, accessible_name in expected.items():
            button = self._by_id(element_id)
            self.assertEqual(button["tag"], "button")
            self.assertEqual(button["attrs"].get("type"), "button")
            self.assertEqual(button["attrs"].get("aria-label"), accessible_name)
            self.assertEqual(button["attrs"].get("title"), accessible_name)
            self.assertEqual(button["text"].strip(), "", "timer control must not render visible copy")
            icon = next(
                (node for node in self.nodes if node["tag"] == "svg" and button in node["ancestors"]),
                None,
            )
            if icon is None:
                self.fail("#{} has no inline icon".format(element_id))
            self.assertEqual(icon["attrs"].get("aria-hidden"), "true")
            self.assertEqual(icon["attrs"].get("focusable"), "false")
            interactive = [
                node["tag"] for node in self.nodes
                if button in node["ancestors"] and node["tag"] in {"button", "input", "a", "select", "textarea"}
            ]
            self.assertEqual(interactive, [])

        stop_icon = [
            node for node in self.nodes
            if node["tag"] == "rect" and self._by_id("stop-btn") in node["ancestors"]
        ]
        self.assertTrue(stop_icon, "stop control needs a square glyph")
        refresh_marks = [
            node for node in self.nodes
            if "timer-refresh" in _classes(node) and self._by_id("stop-start-btn") in node["ancestors"]
        ]
        if len(refresh_marks) != 1:
            self.fail("play control must include one grouped refresh motif")
        play_marks = [
            node for node in self.nodes
            if "timer-play" in _classes(node) and self._by_id("stop-start-btn") in node["ancestors"]
        ]
        refresh_paths = [
            node for node in self.nodes
            if node["tag"] == "path" and refresh_marks[0] in node["ancestors"]
        ]
        self.assertEqual(len(play_marks), 1, "play control must have one triangle")
        self.assertEqual(len(refresh_paths), 2, "refresh motif must have two arrow paths")


class TestPixelTimerControlJavaScript(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.results = _run_node_json(_NODE_SCRIPT, APP_JS)

    def test_active_and_idle_render_preserve_icons_and_accessible_actions(self):
        active = self.results["active"]
        self.assertFalse(active["stopHidden"])
        self.assertFalse(active["startHidden"])
        self.assertEqual(active["stopLabel"], "Stop tracking")
        self.assertEqual(active["stopTitle"], "Stop tracking")
        self.assertEqual(active["startLabel"], "Stop and start a new task")
        self.assertEqual(active["startTitle"], "Stop and start a new task")
        self.assertEqual(active["taskText"], "A deliberately long task name that should remain accessible")
        self.assertEqual(active["taskTitle"], active["taskText"])
        self.assertFalse(active["refreshHidden"])
        self.assertTrue(active["iconChildrenPreserved"])
        idle = self.results["idle"]
        self.assertTrue(idle["stopHidden"])
        self.assertFalse(idle["startHidden"])
        self.assertEqual(idle["startLabel"], "Start a new task")
        self.assertEqual(idle["startTitle"], "Start a new task")
        self.assertTrue(idle["refreshHidden"])
        self.assertTrue(idle["iconChildrenPreserved"])

    def test_stop_then_start_new_keeps_api_and_naming_overlay_flow(self):
        self.assertEqual(self.results["calls"], [
            ["stop_tracking"],
            ["stop_and_start_entry"],
            ["edit_entry", 42, "Next task"],
        ])
        self.assertEqual(self.results["afterStop"], {
            "stopHidden": True,
            "startLabel": "Start a new task",
            "refreshHidden": True,
        })
        self.assertEqual(self.results["overlay"]["title"], "Name this task")
        self.assertIn('class="btn btn-primary overlay-submit"', self.results["overlay"]["body"])
        self.assertTrue(self.results["closed"])
        self.assertEqual(self.results["finalTask"], "Next task")
        self.assertFalse(self.results["finalRefreshHidden"])


class TestPixelTimerControlStyles(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(STYLE_CSS, "r", encoding="utf-8") as source:
            cls.css = re.sub(r"/\*.*?\*/", "", source.read(), flags=re.S)

    def _rule(self, selector):
        match = re.search(re.escape(selector) + r"\s*\{([^}]*)\}", self.css)
        self.assertIsNotNone(match, "missing CSS rule {}".format(selector))
        if match is None:
            raise AssertionError("missing CSS rule {}".format(selector))
        return match.group(1)

    def _palette_token(self, selector, token):
        block = self._rule(selector)
        match = re.search(re.escape(token) + r"\s*:\s*(#[0-9a-fA-F]{6})", block)
        if match is None:
            raise AssertionError("{} has no literal {} token".format(selector, token))
        return match.group(1)

    def test_companion_and_actions_are_fixed_in_three_grid_rows(self):
        self.assertRegex(
            self.css,
            r'grid-template-areas\s*:\s*"label companion"\s+"start companion"\s+"actions companion"',
        )
        self.assertRegex(self.css, r"grid-template-columns\s*:\s*minmax\(0,\s*1fr\)\s+128px")
        self.assertRegex(self.css, r"column-gap\s*:\s*8px")
        self.assertRegex(self._rule(".now-tracking-actions"), r"grid-area\s*:\s*actions")
        self.assertRegex(self._rule(".now-tracking-actions"), r"gap\s*:\s*4px")
        self.assertRegex(self._rule(".now-tracking-actions"), r"flex-wrap\s*:\s*nowrap")
        self.assertRegex(self._rule("#companion"), r"grid-area\s*:\s*companion")
        self.assertRegex(self._rule(".now-tracking-label"), r"text-overflow\s*:\s*ellipsis")
        self.assertRegex(self._rule(".now-tracking-label"), r"white-space\s*:\s*nowrap")

    def test_minimum_window_accounts_for_scrollbar_before_companion(self):
        breakpoint = re.search(r"@media\s*\(max-width\s*:\s*(\d+)px\)", self.css)
        margins = re.search(
            r"@media\s*\(max-width\s*:\s*\d+px\)\s*\{\s*\.now-tracking-top\s*\{([^}]*)\}",
            self.css,
        )
        if breakpoint is None or margins is None:
            self.fail("Missing narrow-window timer-grid compensation")
        self.assertGreaterEqual(int(breakpoint.group(1)), 300)
        left_margin = re.search(r"margin-left\s*:\s*(-\d+)px", margins.group(1))
        right_margin = re.search(r"margin-right\s*:\s*(-\d+)px", margins.group(1))
        if left_margin is None or right_margin is None:
            self.fail("Narrow timer grid must reclaim symmetric panel padding")

        def css_px(source, pattern, description):
            match = re.search(pattern, source)
            if match is None:
                raise AssertionError("Missing CSS measurement: {}".format(description))
            return int(match.group(1))

        app_padding = css_px(self._rule("#app"), r"padding\s*:\s*(\d+)px", "#app padding")
        scrollbar_width = css_px(self.css, r"#app::-webkit-scrollbar[^}]*width\s*:\s*(\d+)px", "#app scrollbar width")
        panel = self._rule(".now-tracking")
        panel_padding = css_px(panel, r"padding\s*:\s*(\d+)px", "tracking panel padding")
        panel_border = css_px(panel, r"border\s*:\s*(\d+)px", "tracking panel border")
        grid = self._rule(".now-tracking-top")
        column_gap = css_px(grid, r"column-gap\s*:\s*(\d+)px", "grid column gap")
        companion_width = css_px(grid, r"grid-template-columns\s*:\s*minmax\(0,\s*1fr\)\s+(\d+)px", "companion column")
        action_gap = css_px(self._rule(".now-tracking-actions"), r"gap\s*:\s*(\d+)px", "timer action gap")
        stop_width = css_px(self._rule(".now-tracking-actions #stop-btn"), r"width\s*:\s*(\d+)px", "stop button width")
        start_width = css_px(self._rule(".now-tracking-actions #stop-start-btn"), r"width\s*:\s*(\d+)px", "start button width")

        app_width = 300
        content_width = app_width - (2 * app_padding) - scrollbar_width - (2 * panel_border) - (2 * panel_padding)
        expanded_width = content_width - int(left_margin.group(1)) - int(right_margin.group(1))
        left_column = expanded_width - companion_width - column_gap
        self.assertGreaterEqual(left_column, stop_width + action_gap + start_width)

    def test_controls_have_compact_geometry_and_visible_focus(self):
        stop = self._rule(".now-tracking-actions #stop-btn")
        start = self._rule(".now-tracking-actions #stop-start-btn")
        for declarations, width in ((stop, "36px"), (start, "60px")):
            self.assertRegex(declarations, r"width\s*:\s*" + width)
            self.assertRegex(declarations, r"height\s*:\s*32px")
        compact = self._rule(".now-tracking-actions .btn-mini")
        self.assertRegex(compact, r"padding\s*:\s*0")
        self.assertRegex(compact, r"font-size\s*:\s*0")
        focus = self._rule(".now-tracking-actions .btn:focus-visible")
        self.assertRegex(focus, r"outline\s*:\s*2px")

    def test_stop_icon_and_border_have_theme_contrast(self):
        stop_rule = self._rule(".now-tracking-actions #stop-btn")
        self.assertRegex(stop_rule, r"background\s*:\s*var\(--callout\)")
        self.assertRegex(stop_rule, r"color\s*:\s*var\(--stop-ink\)")
        self.assertRegex(stop_rule, r"border-color\s*:\s*var\(--stop-ink\)")
        themes = {
            ":root": None,
            'body[data-theme="cyber"]': "cyber",
            'body[data-theme="poolside"]': "poolside",
            'body[data-theme="evergreen"]': "evergreen",
            'body[data-theme="citrus-pop"]': "citrus-pop",
        }
        for selector, name in themes.items():
            with self.subTest(theme=name or "cute"):
                callout = self._palette_token(selector, "--callout")
                ink = self._palette_token(selector, "--stop-ink")
                self.assertGreaterEqual(_contrast_ratio(ink, callout), 3.0)

if __name__ == "__main__":
    unittest.main()

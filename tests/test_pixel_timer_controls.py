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
    innerHTML: '',
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
      if (selector === '.badge') return makeElement('badge-stub');
      return null;
    },
    querySelectorAll(selector) {
      if (selector === '.icon-btn') return [makeElement('edit-stub'), makeElement('delete-stub')];
      return [];
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

const entriesFixture = [
  { id: 7, task: 'weeding', startTime: '2026-09-27T15:04:00Z', endTime: '2026-09-27T15:30:00Z',
    description: 'back bed, weeded "and" trimmed <b>carefully</b> & fast',
    loggedStatus: 'Unlogged', isComplete: true },
  { id: 8, task: 'planning', startTime: '2026-09-27T15:30:00Z', endTime: '2026-09-27T15:45:00Z',
    description: '', loggedStatus: 'N/A', isComplete: false },
  { id: 9, task: 'x', startTime: '2026-09-27T15:45:00Z', endTime: '2026-09-27T16:00:00Z',
    description: null, loggedStatus: 'Logged', isComplete: false }
];
setState({ session: { id: 1 }, currentEntry: null, entries: entriesFixture });
ctx.renderEntries();
const rows = document.getElementById('entry-rows').children.map((row) => ({ className: row.className, html: row.innerHTML }));

setState({ session: { id: 1 }, currentEntry: initialEntry });
ctx.renderCurrent();

// --- task-name selection: capture and re-apply across a re-render ---
const nameTextNode = { nodeType: 3, parentElement: null };
const nameElement = {
  id: '',
  className: 'summary-task',
  classList: { contains: (name) => name === 'summary-task' },
  textContent: 'weeding the front bed',
  firstChild: nameTextNode,
  parentElement: null,
  closest: () => nameElement
};
nameTextNode.parentElement = nameElement;
const selectionStub = {
  rangeCount: 1,
  isCollapsed: false,
  removed: 0,
  added: 0,
  getRangeAt: () => ({ startContainer: nameTextNode, startOffset: 2, endContainer: nameTextNode, endOffset: 5 }),
  removeAllRanges() { this.removed += 1; },
  addRange() { this.added += 1; }
};
ctx.getSelection = () => selectionStub;
let lastRange = null;
const makeRange = () => {
  lastRange = { start: null, end: null, setStart(node, offset) { this.start = [node, offset]; }, setEnd(node, offset) { this.end = [node, offset]; } };
  return lastRange;
};
ctx.document.createRange = makeRange;
ctx.document.querySelectorAll = (selector) => (selector === '.summary-task' ? [nameElement] : []);
const capturedSelection = ctx.captureTaskNameSelection();
ctx.restoreTaskNameSelection({ anchor: { kind: 'summary', key: 'weeding the front bed' }, start: 2, end: 5 });
const restoredSelection = {
  removed: selectionStub.removed,
  added: selectionStub.added,
  startOffset: lastRange && lastRange.start ? lastRange.start[1] : null,
  endOffset: lastRange && lastRange.end ? lastRange.end[1] : null,
  usedTextNode: Boolean(lastRange && lastRange.start && lastRange.start[0] === nameTextNode)
};
// a rename can shorten the name: the saved offsets must clamp to the new text
nameElement.textContent = 'short';
ctx.document.createRange = makeRange;
ctx.restoreTaskNameSelection({ anchor: { kind: 'summary', key: 'short' }, start: 0, end: 99 });
const clampedEndOffset = lastRange && lastRange.end ? lastRange.end[1] : null;
// nothing to restore: a collapsed selection, and a selection outside the three name elements
selectionStub.isCollapsed = true;
const collapsedCapture = ctx.captureTaskNameSelection();
selectionStub.isCollapsed = false;
selectionStub.getRangeAt = () => ({
  startContainer: { nodeType: 3, parentElement: { closest: () => null } },
  startOffset: 0,
  endContainer: { nodeType: 3, parentElement: { closest: () => null } },
  endOffset: 1
});
const outsideCapture = ctx.captureTaskNameSelection();
// the Summary row renders its task cell with the selectable class
setState({ session: { id: 1 }, currentEntry: null, entries: entriesFixture,
  summary: [{ task: 'weeding', count: 2, unloggedMinutes: 30, totalMinutes: 75, callout: true }],
  totals: { unloggedMinutes: 30, totalMinutes: 75 } });
ctx.renderSummary();
const summaryRowHtml = document.getElementById('summary-rows').children.map((row) => row.innerHTML);

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
  process.stdout.write(JSON.stringify({ active, idle, afterStop, calls, overlay, closed, renderCalls, rows,
    finalTask: document.getElementById('current-label').textContent,
    finalRefreshHidden: refreshIcon.classList.contains('hidden'),
    selection: { captured: capturedSelection, restored: restoredSelection, clampedEndOffset,
      collapsedCapture, outsideCapture, summaryRowHtml } }));
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

        # Fix (4): the status banner is plain copy — no bullet or circle mark anywhere.
        banner = re.search(
            r'<div class="status-banner inactive" id="status-banner">([^<]*)</div>', self.html
        )
        if banner is None:
            self.fail("the idle banner must stay a plain-text div")
        self.assertEqual(banner.group(1).strip(), "NOT TRACKING")
        self.assertNotRegex(self.html, r"[\u25cf\u25cb]", "banner must not carry a bullet or circle")
        # Fix (5): the elapsed counter is a sibling of the start time inside the same line,
        # hidden until something is actually running.
        start_line = next(node for node in self.nodes if "now-tracking-start" in _classes(node))
        self.assertIn("hidden", _classes(self._by_id("elapsed-counter")))
        self.assertEqual(
            [node["attrs"].get("id") for node in self.nodes
             if node["ancestors"] and node["ancestors"][-1] is start_line],
            ["current-start", "elapsed-counter"],
        )


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

        # Fixes (1), (4), (5) live in app.js. Read the source rather than the run so the
        # guards cover the copy and the counter arithmetic, not just the painted classes.
        with open(APP_JS, "r", encoding="utf-8") as source:
            js = source.read()
        self.assertIn("'play-centered'", js)
        self.assertNotIn("\u25cf ACTIVE", js)
        self.assertNotIn("\u25cb NOT TRACKING", js)
        self.assertNotIn("in progress", js, "a running entry's time cell must not spell out 'in progress'")
        # Whole minutes since the entry started, from the wall clock, re-checked every second.
        self.assertRegex(
            js,
            r"Math\.floor\(\s*\(Date\.now\(\)\s*-\s*Date\.parse\(state\.currentEntry\.startTime\)\)\s*/\s*60000\s*\)",
        )
        self.assertIn("setInterval(updateElapsedCounter, 1000)", js)

        # Fix (7): The Log row now renders as a single line with specific markup.
        rows = self.results["rows"]
        self.assertEqual(len(rows), 3, "Expected exactly three rendered rows")
        for row in rows:
            self.assertEqual(row["className"], "log-entry-row")

        # Row 0: id 7, 'weeding', full description, Unlogged, isComplete true
        row0 = rows[0]["html"]

        # Verify the task cell title is the escaped full description
        # Extract title value to ensure raw characters are absent
        title_start = row0.index('<div class="log-entry-task" title="') + len('<div class="log-entry-task" title="')
        title_end = row0.index('"', title_start)
        title_val = row0[title_start:title_end]

        expected_escaped_desc = 'back bed, weeded &quot;and&quot; trimmed &lt;b&gt;carefully&lt;/b&gt; &amp; fast'
        self.assertEqual(title_val, expected_escaped_desc, "Task cell title must be the escaped full description")

        # Ensure raw characters are not present in the title value
        self.assertNotIn('"', title_val)
        self.assertNotIn('<', title_val)
        self.assertNotIn('>', title_val)
        self.assertNotIn('&', title_val.replace('&quot;', '').replace('&lt;', '').replace('&gt;', '').replace('&amp;', ''))

        # Verify description span exists with escaped content
        self.assertIn('<span class="log-entry-desc">', row0)
        self.assertIn(expected_escaped_desc, row0)

        # Verify title span has no title attribute
        self.assertIn('<span class="log-entry-title">', row0)

        # Verify description is inside task cell, before time cell
        desc_idx = row0.index('<span class="log-entry-desc">')
        time_idx = row0.index('class="log-entry-time"')
        self.assertLess(desc_idx, time_idx, "Description preview must be inside task cell, before time cell")

        # Verify 'No description' is not present
        self.assertNotIn('No description', row0)

        # Verify accessibility attributes on task cell
        self.assertIn('tabindex="0"', row0)
        # aria-label should contain task name and description
        aria_label_match = re.search(r'aria-label="([^"]*)"', row0)
        self.assertIsNotNone(aria_label_match)
        aria_val = aria_label_match.group(1)
        self.assertIn('weeding', aria_val)
        self.assertIn('back bed', aria_val) # Part of the description

        # Verify buttons
        self.assertIn('title="Edit entry 7"', row0)
        self.assertIn('title="Delete entry 7"', row0)
        self.assertIn('title="Click to toggle logged status"', row0)

        # Verify exactly one occurrence of each cell class
        for cell_class in ['log-entry-task', 'log-entry-time', 'log-entry-duration', 'log-entry-status', 'log-entry-actions']:
            self.assertEqual(row0.count('class="{}"'.format(cell_class)), 1, "Expected exactly one {} cell".format(cell_class))

        # Row 1: id 8, 'planning', empty description, N/A, isComplete false
        row1 = rows[1]["html"]
        self.assertNotIn('log-entry-desc', row1)
        self.assertNotIn('No description', row1)

        # Task cell title should be exactly 'planning'
        title_start = row1.index('<div class="log-entry-task" title="') + len('<div class="log-entry-task" title="')
        title_end = row1.index('"', title_start)
        title_val = row1[title_start:title_end]
        self.assertEqual(title_val, 'planning')

        # No Delete button
        self.assertNotIn('title="Delete entry', row1)

        # Badge is span with badge-na, no toggle title
        self.assertIn('<span class="badge badge-na">', row1)
        self.assertNotIn('Click to toggle logged status', row1)
        self.assertNotIn('<button type="button" class="badge', row1)

        # Row 2: id 9, 'x', null description, Logged, isComplete false
        row2 = rows[2]["html"]
        self.assertNotIn('log-entry-desc', row2)
        self.assertNotIn('No description', row2)

        # Task cell title should be exactly 'x'
        title_start = row2.index('<div class="log-entry-task" title="') + len('<div class="log-entry-task" title="')
        title_end = row2.index('"', title_start)
        title_val = row2[title_start:title_end]
        self.assertEqual(title_val, 'x')

        # No Delete button
        self.assertNotIn('title="Delete entry', row2)

        # Badge is button with toggle title
        self.assertIn('<button type="button" class="badge badge-logged clickable"', row2)
        self.assertIn('title="Click to toggle logged status"', row2)
        self.assertNotIn('<span class="badge', row2)

        # Verify Log hint in index.html
        with open(INDEX_HTML, "r", encoding="utf-8") as f:
            html_content = f.read()

        hint_div = '<div class="log-hint hint-text" id="log-hint">(hover an entry\'s task info to see its full description)</div>'
        self.assertIn(hint_div, html_content)

        tab_log_idx = html_content.index('id="tab-log"')
        entry_rows_idx = html_content.index('id="entry-rows"')
        hint_idx = html_content.index(hint_div)

        # Hint must be after tab-log and before entry-rows
        self.assertGreater(hint_idx, tab_log_idx)
        self.assertLess(hint_idx, entry_rows_idx)

        # Ensure no other tabs between tab-log and hint
        segment = html_content[tab_log_idx:hint_idx]
        self.assertNotIn('id="tab-tasks"', segment)
        self.assertNotIn('id="tab-summary"', segment)

        # Selection: the Summary task cell carries the selectable class, render() captures and
        # re-applies the selection around the rebuild, and the offsets survive it.
        self.assertIn('class="summary-task"', js)
        self.assertRegex(js, r"const savedSelection = captureTaskNameSelection\(\);")
        self.assertRegex(js, r"restoreTaskNameSelection\(savedSelection\);")
        selection = self.results["selection"]
        self.assertEqual(
            selection["captured"],
            {"anchor": {"kind": "summary", "key": "weeding the front bed"}, "start": 2, "end": 5},
        )
        self.assertEqual(selection["restored"], {
            "removed": 1, "added": 1, "startOffset": 2, "endOffset": 5, "usedTextNode": True,
        })
        self.assertEqual(selection["clampedEndOffset"], 5, "offsets must clamp to a shorter name")
        self.assertIsNone(selection["collapsedCapture"])
        self.assertIsNone(selection["outsideCapture"])
        self.assertEqual(len(selection["summaryRowHtml"]), 1)
        self.assertIn('class="summary-task"', selection["summaryRowHtml"][0])
        self.assertRegex(
            js,
            r'<span class="summary-task" title="\$\{escapeAttr\(g\.task\)\}">')
        self.assertIn(
            'title="weeding"', selection["summaryRowHtml"][0],
            "a clipped Summary name must still expose its full text on hover")

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

    def test_compact_geometry_visible_focus_and_log_column_template(self):
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

        # Fix (1): with the refresh motif hidden the lone play glyph is nudged onto the
        # button's centre (the triangle occupies x 3..15 of the 38px icon canvas).
        play_centered = self._rule(".now-tracking-actions #stop-start-btn.play-centered .timer-play")
        shift = re.search(r"translateX\(\s*(\d+)px\s*\)", play_centered)
        if shift is None:
            self.fail("idle play glyph must be translated onto the button centre")
        self.assertGreaterEqual(int(shift.group(1)), 1)
        # Fix (5): one line of dim text with a separator before it.
        self.assertRegex(self._rule(".elapsed-counter"), r"white-space\s*:\s*nowrap")
        self.assertRegex(self._rule(".elapsed-counter::before"), r"content\s*:\s*'\u00b7'")

        # Fix (7): the Log list owns ONE column template and every row inherits it through
        # subgrid, which is what makes the columns line up between rows. Each row is a single
        # line where the task cell contains the ID, title, and description as flex children.
        log_list = self._rule("#entry-rows")
        self.assertRegex(log_list, r"display\s*:\s*grid")
        self.assertRegex(
            log_list,
            r"grid-template-columns\s*:\s*minmax\(0,\s*1fr\)\s+auto\s+auto\s+auto\s+auto",
        )
        row = self._rule(".log-entry-row")
        self.assertRegex(row, r"grid-template-columns\s*:\s*subgrid")
        self.assertRegex(row, r"grid-column\s*:\s*1\s*/\s*-1")
        self.assertRegex(row, r"align-items\s*:\s*center")
        self.assertRegex(row, r"grid-template-rows\s*:\s*auto\s*;")
        self.assertNotRegex(row, r"auto\s+auto")
        self.assertNotRegex(row, r"row-gap")
        for cell, column in ((".log-entry-task", 1), (".log-entry-time", 2), (".log-entry-duration", 3),
                             (".log-entry-status", 4), (".log-entry-actions", 5)):
            declarations = self._rule(cell)
            self.assertRegex(declarations, r"grid-column\s*:\s*\b{}\b".format(column))
            self.assertRegex(declarations, r"grid-row\s*:\s*1\b")
        task_cell = self._rule(".log-entry-task")
        self.assertRegex(task_cell, r"display\s*:\s*flex")
        self.assertRegex(task_cell, r"min-width\s*:\s*0")
        title = self._rule(".log-entry-title")
        self.assertRegex(title, r"flex\s*:\s*0\s+1\s+auto")
        self.assertRegex(title, r"text-overflow\s*:\s*ellipsis")
        self.assertRegex(title, r"white-space\s*:\s*nowrap")
        description = self._rule(".log-entry-desc")
        self.assertRegex(description, r"flex\s*:\s*1\s+1\s+0")
        self.assertRegex(description, r"min-width\s*:\s*0")
        self.assertRegex(description, r"overflow\s*:\s*hidden")
        self.assertRegex(description, r"text-overflow\s*:\s*ellipsis")
        self.assertRegex(description, r"white-space\s*:\s*nowrap")
        self.assertNotRegex(description, r"grid-column")
        self.assertNotRegex(description, r"grid-row")
        self.assertNotRegex(description, r"overflow-wrap")
        self.assertRegex(self._rule(".log-entry-time"), r"white-space\s*:\s*nowrap")
        self.assertRegex(self._rule(".log-entry-duration"), r"white-space\s*:\s*nowrap")
        self.assertRegex(self._rule(".log-entry-status"), r"align-items\s*:\s*center")
        self.assertRegex(self._rule(".log-entry-status"), r"justify-content\s*:\s*center")
        media_match = re.search(r"@media\s*\(max-width\s*:\s*340px\)\s*\{", self.css)
        if media_match is None:
            self.fail("340px media query not found")
        media_text = self.css[media_match.start():]
        self.assertNotRegex(media_text, r"grid-template-columns")
        self.assertNotRegex(media_text, r"grid-row\s*:\s*2")
        self.assertNotRegex(media_text, r"log-entry-desc")
        self.assertRegex(media_text, r"\.log-entry-time\s*,\s*\.log-entry-duration\s*\{[^}]*font-size\s*:\s*11px")
        self.assertRegex(self._rule(".log-hint"), r"padding\s*:\s*0\s+4px\s+8px")

        # Summary: ONE grid owns the five column tracks and the header + every row inherit them
        # through subgrid. Sized as two independent grids the tracks drifted (measured on real
        # WebView2: Count values 13-37 px left of the Count header at 380 px, 28 px right of it
        # at 300 px). Both halves must stay in the shared-grid shape.
        summary_table = self._rule("#summary-table")
        self.assertRegex(summary_table, r"display\s*:\s*grid")
        self.assertRegex(
            summary_table,
            r"grid-template-columns\s*:\s*minmax\(0,\s*1\.8fr\)\s+minmax\(min-content,\s*0\.7fr\)"
            r"\s+minmax\(min-content,\s*1\.1fr\)\s+minmax\(min-content,\s*0\.8fr\)\s+auto",
        )
        self.assertRegex(summary_table, r"gap\s*:\s*6px")
        summary_rows = self._rule("#summary-rows")
        self.assertRegex(summary_rows, r"display\s*:\s*grid")
        self.assertRegex(summary_rows, r"grid-template-columns\s*:\s*subgrid")
        self.assertRegex(summary_rows, r"grid-column\s*:\s*1\s*/\s*-1")
        for rule_name in (".summary-head", ".summary-row"):
            declarations = self._rule(rule_name)
            self.assertRegex(declarations, r"grid-template-columns\s*:\s*subgrid")
            self.assertRegex(declarations, r"grid-column\s*:\s*1\s*/\s*-1")
            self.assertNotRegex(
                declarations, r"minmax\(",
                "{} must inherit the shared tracks, not declare its own".format(rule_name),
            )
        # canary: the five tracks are declared in exactly one place
        self.assertEqual(self.css.count("minmax(0,1.8fr)"), 1)

        # Containment: both selectable task-name cells must clip to their own track.
        for selector in (".now-tracking-label", ".summary-task"):
            for prop in (r"min-width\s*:\s*0\b",
                         r"overflow\s*:\s*hidden",
                         r"text-overflow\s*:\s*ellipsis",
                         r"white-space\s*:\s*nowrap"):
                self.assertRegex(
                    self._rule(selector), prop,
                    "{} must confine its text to its own track".format(selector))
        self.assertGreaterEqual(
            self.css.count("text-overflow: ellipsis"), 2,
            "both selectable task-name cells must clip with an ellipsis")
        # The track is what shrinks, the containment is what stops the glyphs.
        self.assertRegex(self._rule("#summary-table"), r"minmax\(0,1\.8fr\)")

        # Only task-name text is selectable; the app-wide default stays unselectable.
        for selector in (".now-tracking-label", ".log-entry-title", ".summary-task"):
            self.assertRegex(self._rule(selector), r"user-select\s*:\s*text")
        self.assertRegex(self._rule("html, body"), r"user-select\s*:\s*none")
        self.assertRegex(self._rule("input, textarea"), r"user-select\s*:\s*text")
        for selector in (".summary-row", ".summary-head", "#entry-rows", ".log-entry-desc",
                         ".log-entry-time", ".log-entry-id", "#titlebar-label"):
            self.assertNotRegex(self._rule(selector), r"user-select",
                                "{} must not become selectable".format(selector))

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

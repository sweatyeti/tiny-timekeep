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
document.getElementById('current-edit-btn').classList.add('hidden');

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
  editHidden: document.getElementById('current-edit-btn').classList.contains('hidden'),
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
  editHidden: document.getElementById('current-edit-btn').classList.contains('hidden'),
  iconChildrenPreserved: start.children.length === childrenBeforeRender.length && start.children.every((child, i) => child === childrenBeforeRender[i])
};

const calls = [];
let overlay = null;
let closed = false;
let renderCalls = 0;
let taskInputFocused = false;
document.getElementById('sn-task').focus = () => { taskInputFocused = true; };
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
  const focusedOnOpen = taskInputFocused;
  document.getElementById('sn-task').value = 'Next task';
  document.getElementById('sn-desc').value = 'Next task description';
  await document.getElementById('sn-go').onclick();

  // --- current-entry edit control ---
  // Snapshot first: the existing stop/start test pins the calls made by the older flows.
  const callsBeforeCurrentEdit = calls.slice();
  // The new section below reuses the same stub sinks (overlay object, #current-label,
  // refreshIcon) that the older tests read at the end, so capture their values now.
  const overlayBeforeCurrentEdit = overlay;
  const finalTaskBeforeCurrentEdit = document.getElementById('current-label').textContent;
  const finalRefreshHiddenBeforeCurrentEdit = refreshIcon.classList.contains('hidden');
  // --- new-task naming popup: stale guard, cross-session guard, blank description ---
  const editEntryCount = () => calls.filter(c => c[0] === 'edit_entry').length;
  // stale entry id
  await start.onclick();
  const snStaleCountBefore = editEntryCount();
  setState({ session: { id: 1 }, currentEntry: { id: 77, task: 'something else', startTime: '2026-09-27T16:00:00Z' } });
  document.getElementById('sn-task').value = 'Wrong row';
  await document.getElementById('sn-go').onclick();
  const snStaleGuard = { callsAdded: editEntryCount() - snStaleCountBefore, overlayBody: overlay.body };
  // cross-session
  await start.onclick();
  const snCrossSessionCountBefore = editEntryCount();
  setState({ session: { id: 2 }, currentEntry: { id: 42, task: 'unnamed', startTime: '2026-09-27T16:00:00Z' } });
  document.getElementById('sn-task').value = 'Wrong session';
  await document.getElementById('sn-go').onclick();
  const snCrossSessionGuard = { callsAdded: editEntryCount() - snCrossSessionCountBefore, overlayBody: overlay.body };
  // blank description
  await start.onclick();
  document.getElementById('sn-task').value = 'Blank task';
  document.getElementById('sn-desc').value = '';
  await document.getElementById('sn-go').onclick();
  const blankDescCall = calls[calls.length - 1];
  const currentEditFixture = {
    session: { id: 1 },
    currentEntry: { id: 42, task: 'weeding the front bed', startTime: '2026-09-27T15:04:00Z' },
    entries: [
      { id: 42, task: 'weeding the front bed', description: 'front bed, "quoted" & <b>bolded</b>', startTime: '2026-09-27T15:04:00Z', endTime: null, isComplete: false, loggedStatus: 'N/A' },
      { id: 7, task: 'mulching', description: 'back bed', startTime: '2026-09-27T15:00:00Z', endTime: '2026-09-27T15:30:00Z', isComplete: true, loggedStatus: 'Unlogged' }
    ]
  };
  setState(currentEditFixture);
  let efTaskFocused = false;
  document.getElementById('ef-task').focus = () => { efTaskFocused = true; };
  ctx.renderCurrent();
  document.getElementById('current-edit-btn').onclick();
  const currentEditOverlay = { title: overlay.title, body: overlay.body, focused: efTaskFocused };
  document.getElementById('ef-task').value = 'weeding the back bed';
  document.getElementById('ef-desc').value = 'back bed';
  await document.getElementById('ef-save').onclick();
  const currentEditCall = calls[calls.length - 1];
  // stale guard: re-open, swap the active entry, then save must be refused
  // (the stubbed edit_entry returns a partial state, so restore the fixture before reopening)
  setState(currentEditFixture);
  document.getElementById('current-edit-btn').onclick();
  const editCallsBeforeStale = calls.filter(c => c[0] === 'edit_entry').length;
  setState({ ...currentEditFixture, currentEntry: { id: 99, task: 'something else', startTime: '2026-09-27T16:00:00Z' } });
  await document.getElementById('ef-save').onclick();
  const editCallsAfterStale = calls.filter(c => c[0] === 'edit_entry').length;
  const staleGuard = { callsAdded: editCallsAfterStale - editCallsBeforeStale, overlayTitle: overlay.title, overlayBody: overlay.body };
  // cross-session guard: the dialog was opened on session 1, then the app switched to a
  // DIFFERENT session whose running entry happens to carry the SAME entry id (42). Entry ids are
  // per-session integers, so the id check alone must not be enough — save must be refused.
  setState(currentEditFixture);
  document.getElementById('current-edit-btn').onclick();
  const editCallsBeforeCrossSession = calls.filter(c => c[0] === 'edit_entry').length;
  setState({ ...currentEditFixture, session: { id: 2 } });
  await document.getElementById('ef-save').onclick();
  const crossSessionGuard = { callsAdded: calls.filter(c => c[0] === 'edit_entry').length - editCallsBeforeCrossSession, overlayTitle: overlay.title, overlayBody: overlay.body };
  // missing record: the view model has no state.entries row for the active entry id, so the
  // dialog must normalise the entry as running (empty description, no Logged toggle) instead of
  // falling back to the raw currentEntry object (which has neither description nor loggedStatus).
  setState({ session: { id: 1 },
    currentEntry: { id: 55, task: 'orphan task', startTime: '2026-09-27T17:00:00Z' },
    entries: currentEditFixture.entries });
  document.getElementById('current-edit-btn').onclick();
  const missingRecordOverlay = { title: overlay.title, body: overlay.body };

  // --- current-entry description line ---
  // The description must come from the RUNNING entry's own state.entries record (matched by id),
  // be set as text (never HTML), and be hidden — occupying no space — when it is absent or blank.
  const descEl = document.getElementById('current-desc');
  const descSamples = {};
  function sampleDesc(name, fixture) {
    setState(fixture);
    ctx.renderCurrent();
    descSamples[name] = {
      text: descEl.textContent,
      hidden: descEl.classList.contains('hidden'),
      html: descEl.innerHTML
    };
  }
  const runningEntry = currentEditFixture.currentEntry;
  sampleDesc('matched', currentEditFixture);
  sampleDesc('empty', { session: { id: 1 }, currentEntry: runningEntry,
    entries: [{ id: 42, task: 'weeding the front bed', description: '   ', startTime: 'x' }] });
  sampleDesc('nullDescription', { session: { id: 1 }, currentEntry: runningEntry,
    entries: [{ id: 42, task: 'weeding the front bed', description: null, startTime: 'x' }] });
  sampleDesc('staleIdOnly', { session: { id: 1 }, currentEntry: runningEntry,
    entries: [{ id: 7, task: 'another row', description: 'another row description', startTime: 'x' }] });
  sampleDesc('noEntries', { session: { id: 1 }, currentEntry: runningEntry });
  sampleDesc('idle', { session: { id: 1 }, currentEntry: null, entries: currentEditFixture.entries });

  process.stdout.write(JSON.stringify({ active, idle, afterStop, focusedOnOpen, calls: callsBeforeCurrentEdit, overlay: overlayBeforeCurrentEdit, closed, renderCalls, rows,
    finalTask: finalTaskBeforeCurrentEdit,
    finalRefreshHidden: finalRefreshHiddenBeforeCurrentEdit,
    selection: { captured: capturedSelection, restored: restoredSelection, clampedEndOffset,
      collapsedCapture, outsideCapture, summaryRowHtml },
    currentEditOverlay, currentEditCall, staleGuard, crossSessionGuard, missingRecordOverlay, descSamples,
    snStaleGuard, snCrossSessionGuard, blankDescCall }));
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

def _rgb_distance(first, second):
    """Euclidean distance between two #rrggbb colours, 0..441."""
    left = [int(first[index:index + 2], 16) for index in (1, 3, 5)]
    right = [int(second[index:index + 2], 16) for index in (1, 3, 5)]
    return sum((a - b) ** 2 for a, b in zip(left, right)) ** 0.5


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
            ["current-edit-btn", "stop-btn", "stop-start-btn"],
        )
        # The Edit control for the active entry lives with the task name it edits, on a title line
        # whose only children are the task name and the button, so the button can sit beside the
        # rendered title instead of at the far edge of the cell.
        edit_btn = self._by_id("current-edit-btn")
        self.assertEqual(edit_btn["tag"], "button")
        self.assertEqual(edit_btn["attrs"].get("type"), "button")
        self.assertEqual(edit_btn["attrs"].get("aria-label"), "Edit current entry")
        self.assertEqual(edit_btn["attrs"].get("title"), "Edit current entry")
        self.assertIn("hidden", _classes(edit_btn))
        title_line = edit_btn["ancestors"][-1]
        self.assertIn("now-tracking-title-line", _classes(title_line))
        title_line_children = [
            node for node in self.nodes
            if node["ancestors"] and node["ancestors"][-1] is title_line
        ]
        self.assertEqual(
            [node["attrs"].get("id") for node in title_line_children],
            ["current-label", "current-edit-btn"],
        )
        label_row = title_line["ancestors"][-1]
        self.assertIn("now-tracking-label-row", _classes(label_row))
        # The muted description line is the row's second child: under the title, and shipped empty
        # and hidden so a running entry with no description reserves no space.
        desc = self._by_id("current-desc")
        self.assertEqual(desc["tag"], "div")
        self.assertEqual(_classes(desc), {"now-tracking-desc", "hidden"})
        label_row_children = [
            node for node in self.nodes
            if node["ancestors"] and node["ancestors"][-1] is label_row
        ]
        self.assertEqual(
            [_classes(node) for node in label_row_children],
            [{"now-tracking-title-line"}, {"now-tracking-desc", "hidden"}],
        )
        self.assertIs(label_row["ancestors"][-1], top)

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

        self.assertFalse(active["editHidden"], "edit button must be visible when an entry is active")
        self.assertTrue(idle["editHidden"], "edit button must be hidden when no entry is active")

        # The muted description under the title is read from the running entry's OWN state.entries
        # record (matched by id), set as text, and hidden with no reserved space when it is absent.
        desc = self.results["descSamples"]
        self.assertEqual(desc["matched"]["text"], "front bed, \"quoted\" & <b>bolded</b>")
        self.assertFalse(desc["matched"]["hidden"], "a running entry's description must be shown")
        self.assertEqual(desc["matched"]["html"], "", "the description must be set as text, never HTML")
        # A blank, null, missing, or other-row description must never leak onto the running entry.
        for name in ("empty", "nullDescription", "staleIdOnly", "noEntries", "idle"):
            with self.subTest(sample=name):
                self.assertEqual(desc[name]["text"], "", "no description must leave the line empty")
                self.assertTrue(desc[name]["hidden"], "no description must hide the line entirely")

        edit_ov = self.results["currentEditOverlay"]
        self.assertEqual(edit_ov["title"], "Edit current entry")
        body = edit_ov["body"]

        # Description: escaped form present in the overlay body
        self.assertIn("front bed, &quot;quoted&quot; &amp; &lt;b&gt;bolded&lt;/b&gt;", body, "escaped description must appear in overlay body")
        # Extract the ef-desc value attribute and confirm no raw special characters are unescaped
        m = re.search(r'id="ef-desc"[^>]*value="([^"]*)"', body)
        self.assertIsNotNone(m, "ef-desc field not found in overlay body")
        desc_val = m.group(1)
        self.assertEqual(desc_val, "front bed, &quot;quoted&quot; &amp; &lt;b&gt;bolded&lt;/b&gt;", "ef-desc value must be the HTML-escaped description")

        # Task field carries the running entry's task
        self.assertIn("weeding the front bed", body, "task field must carry the running entry's task")

        # No ef-logged field (a running entry has loggedStatus 'N/A')
        self.assertNotIn("ef-logged", body, "running entry must not render an ef-logged field")

        # Task field was focused on open
        self.assertTrue(edit_ov["focused"], "ef-task must be focused when the overlay opens")

        # Recorded API call
        self.assertEqual(
            self.results["currentEditCall"],
            ["edit_entry", 42, "weeding the back bed", "back bed", None],
        )

        # Stale guard: zero edit_entry calls and a refusal overlay
        stale = self.results["staleGuard"]
        self.assertEqual(stale["callsAdded"], 0, "stale guard must not call edit_entry")
        self.assertIn("tracked entry changed", stale["overlayBody"],
                      "refusal overlay must mention the tracked entry changed")

        # Cross-session guard: the same entry id in a different session must not be saved
        cross = self.results["crossSessionGuard"]
        self.assertEqual(cross["callsAdded"], 0,
                         "a different session with the same entry id must not call edit_entry")
        self.assertIn("tracked entry changed", cross["overlayBody"],
                      "cross-session refusal overlay must mention the tracked entry changed")

        # Missing view-model record: normalised as a running entry, so no Logged toggle and an
        # empty (not blank-undefined) description
        missing = self.results["missingRecordOverlay"]
        self.assertEqual(missing["title"], "Edit current entry")
        self.assertNotIn("ef-logged", missing["body"],
                         "an active entry with no view-model record must not render a Logged toggle")
        self.assertIn('id="ef-desc" value=""', missing["body"],
                      "the normalised record must render an empty description value")

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

        # Summary tab DOM order: totals -> guidance -> header -> rows
        guidance_text = 'Log/Unlog marks every completed entry of that task'
        tab_summary_idx = html_content.index('id="tab-summary"')
        summary_totals_idx = html_content.index('id="summary-totals"')
        guidance_idx = html_content.index(guidance_text)
        summary_head_idx = html_content.index('class="summary-head"')
        summary_rows_idx = html_content.index('id="summary-rows"')
        self.assertLess(tab_summary_idx, summary_totals_idx,
                        "Summary tab must open before the totals block")
        self.assertLess(summary_totals_idx, guidance_idx,
                        "totals must sit above the guidance in the Summary tab")
        self.assertLess(guidance_idx, summary_head_idx,
                        "guidance must sit above the table header in the Summary tab")
        self.assertLess(summary_head_idx, summary_rows_idx,
                        "table header must sit above the rows in the Summary tab")
        # Exactly one of each element, nothing extra between tab and table
        summary_table_idx = html_content.index('id="summary-table"')
        summary_segment = html_content[tab_summary_idx:summary_table_idx]
        self.assertEqual(summary_segment.count('id="summary-totals"'), 1,
                         "exactly one summary-totals element expected")
        self.assertEqual(summary_segment.count(guidance_text), 1,
                         "exactly one guidance sentence expected")
        self.assertEqual(summary_segment.count('id="summary-table"'), 0,
                         "summary-table must not appear inside the pre-table segment")
        # Reading order must come from the DOM, not a CSS `order` shortcut.
        with open(STYLE_CSS, "r", encoding="utf-8") as source:
            css_text = source.read()
        css_stripped = re.sub(r"/\*.*?\*/", "", css_text, flags=re.S)
        self.assertIsNone(
            re.search(r"(?<![\w-])order\s*:", css_stripped),
            "CSS order property must not reorder the Summary tab",
        )
        # Values still sourced from state (presentation-only change)
        totals_writer_idx = js.index("document.getElementById('summary-totals').innerHTML")
        totals_slice = js[totals_writer_idx:]
        self.assertIn("state.totals.unloggedMinutes", totals_slice,
                      "totals must read unloggedMinutes from state")
        self.assertIn("state.totals.totalMinutes", totals_slice,
                      "totals must read totalMinutes from state")
        self.assertIn("state.summary", js,
                      "summary rows must be sourced from state.summary")
        self.assertIn("document.getElementById('summary-rows')", js,
                      "summary-rows element must be referenced in render code")

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
            ["edit_entry", 42, "Next task", "Next task description"],
        ])
        self.assertEqual(self.results["afterStop"], {
            "stopHidden": True,
            "startLabel": "Start a new task",
            "refreshHidden": True,
        })
        self.assertEqual(self.results["overlay"]["title"], "Name this task")
        self.assertTrue(self.results["focusedOnOpen"], "the task-name field should take keyboard focus when its popup opens")
        self.assertIn('class="btn btn-primary overlay-submit"', self.results["overlay"]["body"])
        self.assertTrue(self.results["closed"])
        self.assertEqual(self.results["finalTask"], "Next task")
        self.assertFalse(self.results["finalRefreshHidden"])

        body = self.results["overlay"]["body"]
        self.assertIn('<label>Description</label>', body,
                      "Description label must appear in the overlay body")
        self.assertIn('id="sn-task"', body,
                      "Task field id must appear in the overlay body")
        self.assertIn('id="sn-desc"', body,
                      "Description field id must appear in the overlay body")
        self.assertTrue(
            body.index('id="sn-task"') < body.index('id="sn-desc"'),
            "Task field must come before Description field in the overlay body",
        )
        self.assertIn('placeholder="Description (optional)"', body,
                      "Description placeholder must appear in the overlay body")
        self.assertNotIn('sn-logged', body,
                         "Running-entry popup must not offer a Logged control (sn-logged)")
        self.assertNotIn('Logged', body,
                         "Running-entry popup must not offer a Logged control (text)")

        self.assertEqual(self.results["blankDescCall"], ["edit_entry", 42, "Blank task", ""])

        for key in ("snStaleGuard", "snCrossSessionGuard"):
            guard = self.results[key]
            self.assertEqual(guard["callsAdded"], 0, f"{key} must not call edit_entry")
            self.assertIn("tracked entry changed", guard["overlayBody"],
                          f"{key} refusal must mention the tracked entry changed")


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
        self.assertRegex(self._rule(".now-tracking-label-row"), r"grid-area\s*:\s*label")
        self.assertRegex(self._rule(".now-tracking-label-row"), r"display\s*:\s*flex")
        self.assertRegex(self._rule(".now-tracking-label-row"), r"flex-direction\s*:\s*column")
        self.assertRegex(self._rule(".now-tracking-label-row"), r"gap\s*:\s*6px")
        self.assertRegex(self._rule(".now-tracking-label-row"), r"min-width\s*:\s*0")
        # The title line holds the task name and the Edit control: a fixed small gap, and the name
        # shrinks (flex-grow 0) so the button stays beside the RENDERED title rather than being
        # pushed to the far edge of the cell next to the companion.
        self.assertRegex(self._rule(".now-tracking-title-line"), r"display\s*:\s*flex")
        self.assertRegex(self._rule(".now-tracking-title-line"), r"gap\s*:\s*6px")
        self.assertRegex(self._rule(".now-tracking-title-line"), r"min-width\s*:\s*0")
        self.assertRegex(self._rule(".now-tracking-label"), r"flex\s*:\s*0\s+1\s+auto")
        self.assertRegex(self._rule(".now-tracking-label"), r"min-width\s*:\s*0")
        # The running entry's description: muted, under the title, wrapping inside the cell.
        desc_rule = self._rule(".now-tracking-desc")
        self.assertRegex(desc_rule, r"min-width\s*:\s*0")
        self.assertRegex(desc_rule, r"color\s*:\s*var\(--text-dim\)")
        self.assertRegex(desc_rule, r"overflow-wrap\s*:\s*anywhere")
        edit_rule = self._rule(".now-tracking-label-row .current-edit-btn")
        self.assertRegex(edit_rule, r"flex\s*:\s*0\s+0\s+auto")
        edit_w = re.search(r"width\s*:\s*(\d+)px", edit_rule)
        edit_h = re.search(r"height\s*:\s*(\d+)px", edit_rule)
        self.assertIsNotNone(edit_w, "Edit button width not found in CSS")
        self.assertIsNotNone(edit_h, "Edit button height not found in CSS")
        self.assertEqual(edit_w.group(1), edit_h.group(1))
        focus_rule = self._rule(".now-tracking-label-row .current-edit-btn:focus-visible")
        self.assertRegex(focus_rule, r"outline\s*:\s*2px\s+solid\s+var\(--text-main\)")
        self.assertRegex(focus_rule, r"outline-offset\s*:\s*1px")

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
        edit_width = css_px(self._rule(".now-tracking-label-row .current-edit-btn"), r"width\s*:\s*(\d+)px", "edit button width")
        label_row_gap = css_px(self._rule(".now-tracking-label-row"), r"gap\s*:\s*(\d+)px", "label row gap")
        self.assertGreaterEqual(left_column, edit_width + label_row_gap)

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

        # Summary tab reorder: totals moved from footer to header
        self.assertRegex(
            self._rule(".summary-totals"),
            r"border-bottom\s*:\s*2px solid var\(--panel-row-alt\)",
            "the totals separator must sit on the block's bottom edge now that the totals are above the table",
        )
        self.assertRegex(
            self._rule(".summary-totals"),
            r"padding-bottom\s*:\s*8px",
            "the totals block must have bottom padding to separate it from the table",
        )
        self.assertRegex(
            self._rule(".summary-totals"),
            r"margin-bottom\s*:\s*8px",
            "the totals block must have bottom margin to space it from the table",
        )
        self.assertNotRegex(
            self._rule(".summary-totals"),
            r"border-top",
            "the old footer top border must be removed",
        )
        self.assertNotRegex(
            self._rule(".summary-totals"),
            r"margin-top",
            "the old footer top margin must be removed",
        )
        with self.subTest("summary guidance spacing"):
            block = self._rule("#tab-summary > .hint-text")
            self.assertRegex(
                block,
                r"padding\s*:\s*0\s+4px\s+8px",
                "the Summary guidance must use the Log tab hint rhythm",
            )
            self.assertNotRegex(
                block,
                r"padding-top\s*:\s*10px",
                "the Summary guidance must not inherit the shared .hint-text top padding",
            )
        self.assertRegex(
            self._rule(".log-hint"),
            r"padding\s*:\s*0\s+4px\s+8px",
            "the Log tab hint keeps its own spacing",
        )
        self.assertIn(
            ".summary-totals {",
            self.css,
            "the Summary totals rule must stay present",
        )
        self.assertIn(
            "#tab-summary > .hint-text {",
            self.css,
            "the Summary guidance rule must stay present",
        )

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
                         ".now-tracking-desc", ".log-entry-time", ".log-entry-id", "#titlebar-label"):
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
            'body[data-theme="dune"]': "dune",
        }
        for selector, name in themes.items():
            with self.subTest(theme=name or "cute"):
                callout = self._palette_token(selector, "--callout")
                ink = self._palette_token(selector, "--stop-ink")
                self.assertGreaterEqual(_contrast_ratio(ink, callout), 3.0)
        # Status-banner guard
        active_rule = self._rule(".status-banner.active")
        self.assertRegex(active_rule, r"background\s*:\s*var\(--status-active\)")
        self.assertRegex(active_rule, r"color\s*:\s*var\(--status-active-ink\)")
        inactive_rule = self._rule(".status-banner.inactive")
        self.assertRegex(inactive_rule, r"background\s*:\s*var\(--status-inactive\)")
        self.assertRegex(inactive_rule, r"color\s*:\s*var\(--status-inactive-ink\)")
        # --inactive is superseded by --status-inactive; no live declaration may remain
        self.assertIsNone(re.search(r"--inactive\s*:", self.css), "live --inactive declaration found")
        banner_rule = self._rule(".status-banner")
        self.assertRegex(banner_rule, r"margin\s*:\s*-14px -14px 12px -14px")
        self.assertRegex(banner_rule, r"border-bottom\s*:\s*3px solid")
        banner_themes = {
            ":root": "cute",
            'body[data-theme="cyber"]': "cyber",
            'body[data-theme="poolside"]': "poolside",
            'body[data-theme="evergreen"]': "evergreen",
            'body[data-theme="citrus-pop"]': "citrus-pop",
            'body[data-theme="dune"]': "dune",
        }
        for selector, name in banner_themes.items():
            with self.subTest(theme=name):
                active = self._palette_token(selector, "--status-active")
                active_ink = self._palette_token(selector, "--status-active-ink")
                inactive = self._palette_token(selector, "--status-inactive")
                inactive_ink = self._palette_token(selector, "--status-inactive-ink")
                self.assertGreaterEqual(_contrast_ratio(active_ink, active), 4.5)
                self.assertGreaterEqual(_contrast_ratio(inactive_ink, inactive), 4.5)
                surfaces = {
                    "--titlebar": self._palette_token(selector, "--titlebar"),
                    "--bg-top": self._palette_token(selector, "--bg-top"),
                    "--bg-bottom": self._palette_token(selector, "--bg-bottom"),
                    "--panel": self._palette_token(selector, "--panel"),
                }
                for token, surface in surfaces.items():
                    self.assertGreaterEqual(_rgb_distance(active, surface), 120, f"active banner too close to {token}")
                    self.assertGreaterEqual(_rgb_distance(inactive, surface), 120, f"inactive banner too close to {token}")
                self.assertGreaterEqual(_rgb_distance(active, inactive), 120, "active and inactive banners must not look alike")

if __name__ == "__main__":
    unittest.main()

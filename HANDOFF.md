# Keeper of Time — handoff

> Normalized 2026-09-24: app renamed from `tinyTimekeep` to **Keeper of Time**, data paths
> `TinyTimesheet` → `KeeperOfTime`, spec files moved under `specs/`, frontend folder is `web/`.
> Status sections below were updated against the live repo, not from the original document.

Read `SKILL.md` first (what this app is, architecture, conventions). This
document is state: what's done, what's pending, and what to watch out for.

## Current state

**UI (`web/` + `main.py` + `preferences.py`):** built and working against
the contract, currently on **contract v1.4**. Covers:
- Start/resume screen (`list_sessions`, `start_session`, `resume_session`)
- Active session: ACTIVE/NOT TRACKING banner, "Started HH:MM" (not a live
  elapsed clock — decided against ticking display), Stop / Start new /
  Stop & start new actions (entry starts immediately on click with task
  `unnamed`, then a separate `edit_entry` rename — timestamp reflects the
  actual moment of intent, not when naming finishes)
- Tasks tab (per-task rows, click to switch), Log tab (entries, wrapping
  descriptions, clickable logged/unlogged badge, edit/delete), Summary tab
- Log a task group, view + restore deleted entries (with description and
  time range, per v1.4)
- Frameless window: custom drag (title bar) and custom resize grip
  (bottom-right corner), both using an anchor-once/absolute-target pattern
- UI preferences store (currently just remembers last-active tab)
- Global Enter-to-submit for overlays and the start screen

**Core:** built and now **vendored into this repo** — `timetracker_core/` sits at the repo root
(flat, no `src/`), a verbatim copy of `keeper-of-time-core` @ `1afc7fa`, contract **v1.4**.
Verified here: **94 tests OK** (the core's 73, 8 boundary tests, 13 UI-conformance tests), and
`python main.py --check` prints `contract v1.4 (expected v1.4)` and the golden fixture exactly.

**Merged:** the UI layer's `main.py` + `preferences.py` + `web/` are in this repo and the scaffold
`main.py` is gone. Theirs owns window creation and chrome — `Api` wraps the real core and adds
`move_window_to`/`resize_window_to`/`get_preferences`/`set_preference`. The scaffold's version gate
and `--check` were folded in, and `tests/test_ui_conformance.py` pins every `pywebview.api.*` call
in `app.js` to a real `Api` or core method. `core_mock.py` is deleted.

## Contract state — v1.4, full history

- v1.0: initial contract
- v1.1: `session.isActive` semantics clarified; `session: null` documented
  as valid; `list_sessions` gained `isUnreadable`/`reason`; added
  `no_active_session`/`internal_error` error codes; corrupt-id entries on
  load → refuse-whole-session decision made
- v1.2: fixed a self-contradiction from v1.1 (`stop_and_exit` now
  unambiguously resolves to `session: null`)
- v1.3: removed `session.isActive` entirely — once v1.2 made every closed
  state resolve to `null`, the field was pure redundancy with
  `session != null`, and had already caused two bugs
- v1.4: `list_deleted_entries` gained a `description` field (UI needed it
  to show what a deleted entry was before restoring)

**✅ v1.4's `description` field — confirmed present and persisted (2026-09-24).**
Live probe against the vendored core: `list_deleted_entries()` returns
`{id, task, startTime, endTime, description}`, and the same row comes back after a restart.
One nuance found while confirming: **a fresh process with no session open returns `[]`**, because
the core does not auto-open a session on startup (`get_state().session` is `null` until
`resume_session`). The restore screen must be reached through a resumed session or it will look
empty when it is not.

## Immediate next step

Drop the **UI layer's files** into this repo: its `main.py` (replacing the scaffold), its
`preferences.py`, and `web/index.html`, `web/style.css`, `web/app.js`. Then delete `core_mock.py`.
The core is already in place at the repo root (flat, alongside `main.py`) and matches:
```python
from timetracker_core import TimeTrackerCore   # re-exported at package level
from timetracker_core import CONTRACT_VERSION   # must equal "v1.4"
```
```python
class TimeTrackerCore:
    def __init__(self, storage_path, clock=None) -> None: ...
```
`main.py` already imports and instantiates it this way — nothing there
should need to change unless the constructor signature has drifted.
`core_mock.py` can be deleted once this is confirmed working; nothing
imports it anymore.

## Open items — not yet built or verified

- **Real acceptance testing.** The core's existing tests were LLM-generated
  (Qwen) from the functional spec's acceptance checklist. Flagged by the
  engineer as "a smoke net, not a trusted acceptance record" — worth an
  actual line-by-line pass against the checklist before trusting this for
  real use, especially given how many contract ambiguities (isActive,
  corrupt-entry handling) turned out to need resolving by hand.
- ~~pywebview version isn't pinned~~ — **done**: `pywebview==6.2.1` (exact, looked up live from
  PyPI) in `requirements.txt`, `pyinstaller==6.22.3` in `requirements-dev.txt`. No lockfile
  (`uv`/pip-tools) yet — exact top-level pins only.
- ~~No packaging/distribution~~ — **built and run on Windows**: `packaging/keeper-of-time.spec`
  (one-file, windowed, bundles `web/`, collects pywebview's WebView2 backend) produced
  `dist\KeeperOfTime.exe` (13.8 MB) on Windows 11 / Python 3.11.9. It launched into the console
  session, spawned 13 WebView2 child processes, rendered its start screen, and wrote sessions to
  `%LOCALAPPDATA%\KeeperOfTime\sessions` rather than the one-file extraction directory.
  `packaging/build.ps1` still refuses to build unless the suite and `--check` pass.
  Remaining: no installer, no startup shortcut, no icon, no code signing.
- **Google Fonts are fetched from the CDN** by `web/index.html`, so a cold first launch waits on
  the network — measured **25.9 s** to `loaded` on a cold cache. Vendoring the font files into
  `web/` and dropping the remote `@import`/`<link>` removes both the stall and the offline
  dependency. This is the last known user-visible defect.
- **Minimize-to-tray was requested but never built.** The original ask was
  "toggleable between always-on-top and minimize-to-tray." Always-on-top
  was implemented, then removed entirely after `w.on_top` hung/crashed the
  app (see SKILL.md's gotchas). Tray-minimize was never started. If
  revisiting always-on-top, root-cause the `on_top` hang first — don't
  just re-add the same code.
- **Google Fonts requires network on load.** No offline fallback bundled.
  Worth fixing before this is expected to run without internet.
- **No design-system pass beyond the initial pixel-art styling.** Palette/
  type tokens exist in `style.css` but haven't been revisited since the
  original build — reasonable to expect more visual polish requests.

## Where things live (quick reference)

| What | Where |
|---|---|
| Behavioral rules (source of truth) | `specs/functional-spec.md` |
| Core/UI contract | `specs/core-logic-contract.md` (v1.4) |
| App architecture + conventions | `SKILL.md` |
| Packaging + build gate | `packaging/keeper-of-time.spec`, `packaging/build.ps1` |
| Which core copy this repo holds | `CORE-VERSION` |
| pywebview host, `Api` glue | `main.py` |
| UI settings store | `preferences.py` |
| Real core (vendored, verbatim) | `timetracker_core/` (root) |
| Dev-time mock core | `core_mock.py` — **delete** |
| Frontend | `web/index.html`, `web/style.css`, `web/app.js` |
| Session data (runtime) | `%LOCALAPPDATA%\KeeperOfTime\sessions` |
| UI prefs (runtime) | `%LOCALAPPDATA%\KeeperOfTime\preferences.json` |

# Pixel Companion timer controls — implementation spec v1.0

**Status:** Approved for implementation. This is a follow-up to the app-wide 128×96 companion layout, not a new avatar design. The approved direction is the corrected two-control sketch at `/home/hermes/.hermes/cache/scratch/stop-controls-beside-avatar-sketch-v2.png`. The sketch is illustrative; this document resolves its rough erasure/artifact details and is authoritative for behavior.

**Goal:** In an active tinyTimeKeep session, place two *compact, icon-only* tracking actions on the LEFT of the avatar, alongside the task text. The avatar stays on the RIGHT. The actions must not sit underneath the avatar or stretch across the card.

**Architecture:** UI-only change to the existing `#screen-active .now-tracking` markup, its grid CSS, and `renderCurrent()` in `web/app.js`. Keep the existing button IDs, click handlers, Python bridge/API, tracking behavior, and shared avatar renderer untouched. No dependency or storage change.

**Tech stack:** pywebview's WebView2 HTML/CSS/JS frontend; Python `unittest` tests; Windows VM for live layout checks.

## Baseline (verified against branch `feat/pixel-companion-sun-avatar` at `d5d2505c0ff10692a8b82ec1d6404590bf637fcf`)

- `web/index.html`: `.now-tracking-top` contains `#current-label`, `#current-start` and `#companion`, but `.now-tracking-actions` is a *sibling after that grid*. It contains `#stop-btn` and `#stop-start-btn`. This is why the actions render below the companion now.
- `web/style.css`: `.now-tracking-top` has a `minmax(0, 1fr) 128px` grid and `"label companion" "start companion"` areas. `#companion` is 128×96 in `web/companions/companion.css`. `.now-tracking-actions` is a wrapping flex row. The minimum app window is 300×420 (`main.py`); the default is 380 px wide.
- `web/app.js`: `renderCurrent()` writes `textContent` to both action buttons, which would erase SVG/CSS-icon markup if left unchanged. `#stop-btn.onclick` calls `api().stop_tracking()`; `#stop-start-btn.onclick` calls `openStartNewTask()`, which calls `api().stop_and_start_entry()` then prompts to name the task. Do not alter either behavior. `renderTasks()` currently says `No tasks yet — use Start new below.`; moving the button above makes that instruction wrong.
- `tests/test_pixel_companion.py` asserts the existing two-row grid and compact text-button styling; update those tests to assert the new structure and behavior. `tests/test_ui_conformance.py` tests other shared UI affordances; avoid weakening them.
- `#theme-picker` has six existing 22×22 controls including the folder control; `Log group`, `Deleted`, tabs and session-start controls are separate from these two tracking actions and must remain as they are.

## Visual and behavioral contract

1. **Exactly two tracking actions in the active card, no third action.** In the active-tracking state both `#stop-btn` and `#stop-start-btn` are visible. When the session is open but not tracking, hide `#stop-btn` and keep `#stop-start-btn` visible. The separate `Log group`, `Deleted`, Tasks/Log/Summary, and initial-session controls are *not* extra timer actions; leave them in place. Never duplicate the stop/start buttons to solve layout.
2. **Placement.** The top of the card reads task/session text at upper left, then start time below it. The two icon buttons sit horizontally immediately under this left-side text, within the SAME 128×96-tall grid band as the companion. Avatar stays right; neither button overlaps it or drops beneath its bottom edge at 380 px width or the 300 px minimum. Preserve the full-width `ACTIVE`/`NOT TRACKING` banner above and the separate action bar/tabs below. For a long task name, ellipsize the *visual* label within its left column and keep its full content accessible and available as a tooltip; do not let wrapping push the controls under the avatar.
3. **Size.** Compact controls, not full-width `.btn` defaults: 36×32 CSS px for Stop and 60×32 px for Stop & Start, with a 4 px inter-button gap. Reduce the existing grid column gap from 12 to 8 px. With the current 14 px `#app` and panel padding and 3 px panel border, this leaves 102 px in the left grid column at the 300 px minimum window; the two buttons use 100 px, leaving 2 px clearance. Keep both keyboard-focusable and do not change the theme-toolbar's 22×22 sizing. At other widths preserve this placement without horizontal scrolling.
4. **Stop:** red/destructive-looking square pixel button using the theme's semantic `--callout` (or another demonstrably high-contrast stop color); inside is a single square glyph. No visible text. A contrasting border and square glyph must remain distinguishable in Cute, Cyber and Poolside; do not assume the same foreground works against every theme token.
5. **Stop & start new:** compact theme-accent button, containing a conventional right-pointing play triangle plus a clearly recognizable pair of refresh arrows *beside* it. The marks are decorative and must not accidentally produce their own tab stops/live regions or a second control. Use crisp inline SVG or pixel-aligned CSS art; do not depend on emoji/font glyph rendering for the arrows. No visible label. In the NOT TRACKING state this existing button remains usable as *Start new*; the play icon remains, while refresh arrows should be hidden so the idle state does not imply there is a current task to stop.
6. **Accessible names and state.** Keep native `<button type="button">` semantics, unique IDs, focus order Stop → Stop & Start when both visible, keyboard activation, and visible focus treatment. Use `aria-label` **and** `title` on the buttons. Set them to `Stop tracking` and `Stop and start a new task` when active; when idle the second becomes `Start a new task`. Decorative SVGs have `aria-hidden="true"` and `focusable="false"`. Do not replace icon markup with `textContent` in `renderCurrent()`; update button attributes and the refresh icon's visibility/state instead. Do not change the companion's status/live-region semantics.
7. **Behavior and copy.** The square button must still stop tracking without ending the session. The play/refresh button must still start the next entry immediately and show the existing naming overlay; cancellation/empty names and error handling remain unchanged. Update the empty Tasks-tab hint to point **above** (e.g. `No tasks yet — use the play button above.`). Do not rename or wire the separate initial-session `Start new session` button. Icon-only buttons still require explanatory hover title and assistive label.
8. **Scope.** App-wide across all five theme palettes. Cute, Cyber and Poolside currently have registered avatars; Evergreen and Citrus Pop presently have no registered art but keep the shared frame/layout. Do not add avatars or change theme→avatar mapping, session storage, the Python core or the author's 128×96 avatar size guide. Existing 32×36 logical sprites remain 2×.

## Engineer tasks (sequential, small Qwen requests)

### 1. Pin the DOM/layout and states in tests

- Edit `/home/hermes/keeper-of-time/.worktrees/pool-avatar-verify/tests/test_pixel_companion.py` and, if useful, `/home/hermes/keeper-of-time/.worktrees/pool-avatar-verify/tests/test_ui_conformance.py`.
- Write a failing test that parses actual `web/index.html`: `.now-tracking-actions` belongs **inside** `.now-tracking-top`; exactly two timer buttons with the existing IDs in that container; the `#companion` is their right-hand grid neighbor; SVG/icon descendants cannot be interactive; both buttons have accessible labels/titles.
- Verify CSS grid has an `actions` area in the left column and `companion` spanning right; controls have fixed compact dimensions, `flex-wrap: nowrap`, and theme-aware stop/accent colors. Check no `button.textContent = ...` replacement remains in `renderCurrent()` and the idle/active accessible labels/refresh visibility are updated. A JS DOM-stub test is preferable to brittle string matching for state transitions.
- Run the focused test *before* implementation and confirm it fails because actions are still below the grid/labels are visible. Preserve existing companion/theme and accessibility tests; do not delete a test to make the suite green.

### 2. Move the two existing buttons into the left column

- Edit `/home/hermes/keeper-of-time/.worktrees/pool-avatar-verify/web/index.html` and `/home/hermes/keeper-of-time/.worktrees/pool-avatar-verify/web/style.css`.
- Move `.now-tracking-actions` under `.now-tracking-top` without recreating either button or changing its ID, then add a third grid row: `"label companion" "start companion" "actions companion"`. Assign `grid-area: actions` to the action group, keep `#companion` on the right. Set enough explicit sizing/alignment to avoid the parent `.btn { width:100% }`, flex wrapping, avatar overlap, and controls below the avatar on a 300-px-wide window.
- Replace visible text with one square graphic and one play-plus-refresh graphic. Use theme tokens; avoid styling unrelated `.btn-mini` controls. Preserve the separate `action-bar` and theme picker unchanged. Run focused tests.

### 3. Preserve functionality and accessibility with icons

- Edit `/home/hermes/keeper-of-time/.worktrees/pool-avatar-verify/web/app.js` only as necessary: `renderCurrent()` sets `title`/`aria-label` based on `state.currentEntry` and exposes/hides refresh art in the idle state without rewriting the button contents. Keep the full task name in `#current-label` for assistive technology and use a tooltip/title for the ellipsized visual label. Preserve the existing `wireActiveScreen()` event handlers and `openStartNewTask()` flow. Correct the stale empty-state hint to say **above**; do not change task-row play behavior.
- Add state-transition/DOM tests for active → stop → idle → start-new and for icon markup surviving every `renderCurrent()` invocation. Run focused tests and full suite.

### 4. Live GUI acceptance, then publish the feature branch

- Run `python3 -m unittest discover -s tests`, `python3 main.py --check`, `node --check web/app.js`, `for f in web/companions/*.js; do node --check "$f"; done`, and `git diff --check`.
- On Windows VM `timetracker-win11` (hypervisor `smithy@10.10.0.33`, guest `ttdev@192.168.122.129`, SSH identity `/home/hermes/.ssh/gpu_fedora`), run the **real main app window** from the feature-branch source with isolated preference and session directories. Capture active and idle states at the default 380 px width, plus a 300 px width check, for Cute, Cyber and Poolside; inspect an unmapped theme's empty frame for layout. Verify window identity/HWND and branch build, not a separate session tester or an old app. Screenshot measurements should show `stop.right < companion.left`, `start.right < companion.left` and the buttons' bottoms within the companion's vertical band, with no clipped controls. Check keyboard focus and tooltip/accessible names by DOM or accessibility probe; a screenshot cannot establish a11y. Report any visual judgment left to Matt rather than calling the model's pixel measurements aesthetic approval.
- Keep the source/user's existing data intact; clean only your own VM test files/processes after capture. Commit on `feat/pixel-companion-sun-avatar`. Fetch and verify fast-forward from current remote head; push **only** this branch (not `dev`/`main`, no force push) and read back the exact remote SHA. Leave a clean tree and provide screenshot paths/commit/tests in the handoff.

## Acceptance checklist

- [ ] Exactly two timer controls in the active card; both icon-only, with no text fallback rendered on the face and no duplicate/wide row below avatar.
- [ ] Stop square and play + two refresh arrows recognizable at 1×; sensible theme colors and visible keyboard focus.
- [ ] Both action buttons left of the 128×96 right-side companion at default and minimum width, awake and sleeping; task/time at upper left.
- [ ] Idle state shows only the play action without refresh arrows; semantic names/titles reflect active/idle behavior.
- [ ] Stop and Stop & Start retain their existing API behavior; initial session start and `Log group`/`Deleted`/tabs are untouched.
- [ ] Tasks empty-state hint points above; theme toolbar remains 22×22; all themes/mappings unaffected.
- [ ] Automated suite, real Windows main-window captures, and branch push all verified; no claim of aesthetic approval without Matt.

## Risks / resolved decisions

- **Small minimum width:** the left grid column at 300 px is narrower than the 380 px sketch. Use compact icon-button widths and test both widths, not a CSS breakpoint that moves them below the avatar.
- **Icon contrast and scaling:** `--callout`/`--accent-pink` mean different colors by theme. Judge the filled rectangle and icon foreground in the actual themes; do not use emoji for the two-arrow motif.
- **Sketch correction:** an earlier rough mock appeared to show an extra timer button; this is explicitly rejected. The corrected sketch establishes two controls, but preserve unrelated lower action-bar buttons.
- **No open user decision is needed** for the icon-only, left-of-avatar two-control layout: Matt explicitly asked to spec it and hand it to engineering.

## Changelog

- **v1.0:** Initial implementation contract after Matt's two-control correction. Defines placement, symbols, active/idle/a11y behavior, minimum-width and Windows verification gates. No earlier version was overwritten.

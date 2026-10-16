---
created: 2026-10-14
version: 1.0
---
# Compact Now — implementation and verification

## Scope

Implemented in-session on `feat/compact-now`, directly from fetched `origin/dev`
`99d9ea056e67988b2048a9f52534fa5ae8f367d5`. No merge or release is implied.

- Title-bar Compact button becomes available with a loaded session.
- Compact strip: clickable task name, elapsed `hh:mm:ss`, Stop, Expand.
- Title bar remains draggable; minimize and stop-and-exit retain existing behavior.
- Normal tabs, avatar and bottom toolbar are hidden only while compact.
- Native height is requested from the rendered strip bounds, not a fixed design guess.
  Normal width and height are retained for explicit expansion and temporary dialogs.
- Switching uses a confirmation-first dialog and the existing atomic
  `stop_and_start_entry(task)` operation. Opening/cancelling never starts a task.
- Cancel, X and Escape return to compact; confirmed success returns to compact;
  returned command errors retain the input/dialog for retry. Submission is guarded
  against double activation. Background controls are inert during the switch dialog.
- Stopped state reads `Stopped`; clicking `Start task` opens the same confirmation flow.
- Layout is per launch; no preference, storage schema, core or contract change.
- Existing normal play-button semantics remain unchanged.

## Checks executed

- Baseline: 84 app tests passed.
- New guards first failed on the unimplemented feature: missing script/wiring,
  missing formatter, and native minimum height 420 exceeding compact's 80px floor.
- Final local Python 3.14 app discovery: **87 tests passed**.
- `python3.14 main.py --check`: **OK**, contract v1.5 golden fixture.
- `node --check web/app.js` and `node --check web/compact.js`: passed.
- `git diff --check`: passed.
- Core package, specs and preferences are unchanged from the branch base.

Before the user requested normal-suite-only verification, the runnable
`tools/check_compact_now.py` check passed against the real frontend, `main.Api`,
core and disposable session files. Playwright substituted only the bridge transport
and native window resize. It exercised no-session gating; Cancel/X/Escape;
byte-for-byte session preservation; injected command-error/retry; confirmed switch
and persisted reload; stop/start; >24h timer; long task names; six themes at 300px;
size/tab restoration; and per-launch reset. At 300px, its fallback-font strip
measured 90px high, with controls contained and no horizontal overflow. This is a
browser measurement, NOT Windows/native or appearance acceptance. The subsequent
small focus/inert and transition/refit guards received the final suite/syntax gates,
not another rendering pass, in accordance with the user's testing limit.

Windows Python 3.14 also completed **87 tests and `main.py --check`** before the
user stopped Windows verification. The initial setup run lacked Node on PATH and
found one new test file using the Windows default text encoding; the new test now
reads UTF-8 explicitly, and the successful rerun used a checksum-verified portable
Node. No assertions were weakened.

## Explicitly unverified / skipped

- Windows GUI/WebView2 native resizing and screenshots: not completed. The guest
  had no logged-in interactive user, so the scheduled GUI probe did not start;
  the user subsequently declined Windows testing. Do not report it as a GUI pass.
- No Fedora GUI tests; user declined them.
- No EXE build, packaged acceptance, release, main promotion or dev merge.
- Native DPI/display-scaling behavior and aesthetic fit await user evaluation.

## Reproduction

Normal checks from the app root:

```text
python3.14 -m unittest discover -s tests
python3.14 main.py --check
node --check web/app.js
node --check web/compact.js
git diff --check
```

Optional browser regression (requires Playwright and its Chromium install):
`python tools/check_compact_now.py`. It is intentionally separate from normal
unit discovery and uses only disposable session/preferences paths.

## Changelog

- v1.0: initial compact-mode implementation, normal-suite results and explicitly
  bounded browser/native evidence.

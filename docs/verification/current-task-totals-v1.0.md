# Current-task totals — scope and verification v1.0

Historical record: display formatting is superseded by [v1.1](current-task-totals-v1.1.md).

## Confirmed behavior

- Scope: the current session only; match task names case-insensitively as Summary does.
- Show only when tracking a task with at least one completed, non-deleted entry.
- U = unlogged time; T = total time, including both logged and unlogged completed entries.
- Exclude the running interval from both figures. Keep the live timer separate.
- Display explicit hours/minutes (`U 1h 15m`, `T 2h 30m`), including zero values and hours beyond 24.
- Reuse Summary's already-rounded values, including zero-duration entries. Do not recalculate from timestamps.
- Hide and clear totals when tracking stops, the session closes, or the running task has no history.
- Include existing/resumed-session entries immediately. No migration, cross-session query, or new store.
- Update on the existing render path after rename, Log/Unlog, delete, restore, switch, and state refresh.
- Provide a hover title and a keyboard-focusable group with an accessible explanation of U/T, scope and exclusions.
- Allow wrapping in the timer area rather than deliberately clipping the totals. Summary's formatting is unchanged.

## Isolation

Branch `feat/current-task-totals` starts at app dev `afb6d5f9a153de5e7f5cf6c93afcc4788e604ff6`.
Implemented directly in-session, without Kanban or another profile. No merge or release is included.
The time-correction experiment is not incorporated. Core package, main.Api, storage, JSON schema,
CORE-VERSION and contract v1.5 are unchanged; this is a read-only UI presentation of existing fields.

## Executed verification

- Baseline: 71 app tests passed before modification.
- Final: 82 app tests passed on Python 3.14.7, including 11 new current-task-totals tests.
- `python3.14 main.py --check`, `node --check web/app.js`, and `git diff --check` passed.
- New tests use real main.Api/core state against isolated JSON files, then execute production
  `renderCurrent()` in Node with a minimal DOM. They assert totals, visibility, tooltip text,
  case matching, per-entry rounding, live-time exclusion, zero/unlogged values, rename,
  delete/restore, stop/close, unrelated sessions, resumed history, unnamed tasks, and >24-hour formatting.
- Display execution prohibits API access and compares active state and session-file hashes before/after.
- Existing markup tests additionally pin placement beside the timer, initial hidden state,
  child IDs, keyboard focusability and group role. CSS tests pin wrapping and a focus outline.
- RED: the first 10 new tests were run against unchanged dev UI; nine failed because expected totals
  stayed hidden (`AssertionError: True is not false`). The no-history test passed. A separate zero-duration
  case was added after checking the core rule: zero seconds contributes zero minutes, not one.

Reproduce from this checkout (Python 3.14 and Node available):

```text
python -m unittest discover -s tests -v
python main.py --check
node --check web/app.js
```

## Deliberately unverified

Rendering tests were skipped at the user's request; visual testing is left to the user.
No Chromium layout measurement, Fedora-host/VM rendering, native Windows WebView2 interaction,
packaged EXE, screenshot, or release claim is made. The Node DOM stub tests do not establish
pixel layout, native tooltip appearance, screen-reader behavior, or end-to-end bridge operation.

## Changelog

- v1.0: initial confirmed scope and local non-rendering verification.

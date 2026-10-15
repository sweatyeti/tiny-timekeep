---
created: 2026-10-14
version: 1.4
---
# Compact Now — Expand control moved to the title bar

Supersedes only the Expand control's location in v1.0–v1.3; those records stay
historical.

Requested: move the Expand button to the title bar, where the Compact button
already lives.

Implemented:
- The `#compact-expand` button moved from the compact strip into `#titlebar`,
  placed after the Compact toggle. It is hidden by default and shown only while
  compact (`#compact-expand { display: none }` / `.compact-now #compact-expand {
  display: block }`), the inverse of the Compact toggle. The strip now shows only
  the task name, elapsed timer, and Stop.
- No logic changed: the existing `wireCompactMode` binding and the
  `renderCompactMode` disabled-state handling still target the element by id.

Verification (normal suite, per the user's testing limit):
- `tests/test_compact_now.py` gained `test_expand_control_lives_in_titlebar`,
  asserting the button id sits inside `#titlebar`, is absent from `#compact-strip`,
  and that compact.css hides it by default and shows it in `.compact-now`.
- Full suite: 98 app tests passed on Python 3.14.
- `main.py --check`, `node --check` on both scripts, and `git diff --check` passed.
- The optional browser harness's geometry check was updated for the new location
  (strip controls remain ordered; Expand is asserted above the strip). Not rerun
  under the normal-suite-only instruction.

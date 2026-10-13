# Current-task totals — display revision v1.1

## Changes from v1.0

- First row: `Started 08:15 (123 min ago)` — elapsed whole minutes follow the
  start timestamp, update on the existing timer, and disappear when tracking stops.
- Separate second row: `Total task time: 02:30 (01:15 unlogged)`.
- Totals use zero-padded `hh:mm`; hours may exceed 24 or two digits.
- Both timing rows span the card below the task controls and avatar, rather than
  being confined beside the avatar. Text can wrap when the window is narrow.
- Tooltip labels reflect the displayed names; a further user-supplied tooltip
  rewrite is pending and is not part of this revision.
- Current-session/completed-entry scope, rounding, visibility, update behavior,
  core, storage and Summary formatting remain unchanged.

## Verification

- 84 app tests passed on Python 3.14, including 13 current-task-total/timer tests.
- `main.py --check`, JavaScript syntax and `git diff --check` passed.
- RED before implementation: 10 of the 13 updated feature tests failed against
  v1.0. The elapsed assertion showed `123 min` instead of `(123 min ago)`;
  totals still showed the old U/T hours/minutes text.
- Tests execute real core/API snapshots through the production JS in a minimal
  Node DOM, including `Total task time: 02:30 (01:15 unlogged)`, zero padding,
  zero values, >24-hour totals, and hiding the elapsed counter on stop.
- Markup/CSS tests pin the Started/elapsed wrapper, totals on a distinct row,
  total-before-unlogged ordering and the full-width timing grid area.
- Rendering, native Windows and packaged EXE tests remain skipped at the user's
  request. No pixel-layout or actual tooltip-rendering result is claimed.

## Changelog

- v1.1: hh:mm totals, full text labels, Started + parenthesized live timer, separate totals row.
- [v1.0](current-task-totals-v1.0.md): initial current-task totals implementation and verification.

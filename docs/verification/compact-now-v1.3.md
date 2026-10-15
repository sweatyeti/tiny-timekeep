---
created: 2026-10-14
version: 1.3
---
# Compact Now — width adjustment

Supersedes only the resize behavior in v1.0–v1.2; those records stay historical.

Requested: allow width adjustment while in compact mode.

Implemented:
- The resize grip is no longer hidden in compact mode; it becomes a narrow (8px)
  right-edge handle with an `ew-resize` cursor, and the compact strip's right
  padding is widened so the handle never overlaps the Stop/Expand controls or the
  title-bar buttons.
- Dragging the handle changes width only; the content-locked strip height is
  preserved. `compactResizeWidth` clamps to the native 300px minimum, keeps the
  current window height, and writes the new width back to `compactFullSize.width`
  so Expand restores the adjusted width rather than the pre-collapse width.
- The normal (expanded) resize grip keeps its existing width+height behavior;
  only the compact branch changed.

Verification (normal suite, per the user's testing limit):
- `tests/test_compact_now.py` gained two checks: `compactResizeWidth` clamps to
  300 and calls `resize_window_to` with the compact height only (width 500 then
  clamped 300, height 90 both times), and the wiring source check confirms app.js
  branches on `.compact-now`, calls `compactResizeWidth`, and compact.css styles
  the grip with `ew-resize` without `display: none`.
- Full suite: 97 app tests passed on Python 3.14.
- `main.py --check`, `node --check` on both scripts, and `git diff --check` passed.
- No browser/native/VM or appearance tests run, following the normal-suite-only
  instruction. The exact grip feel (8px target, overlap with window chrome) is
  unverified visually.

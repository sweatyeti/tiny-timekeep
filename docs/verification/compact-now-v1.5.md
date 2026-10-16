---
created: 2026-10-14
version: 1.5
---
# Compact Now — larger Expand arrow and stable compact height

Supersedes only the Expand glyph size and the width-resize height source in v1.0–v1.4;
those records stay historical.

Requested: enlarge the Expand arrow; stop the compact height from changing when the
window is made wider or narrower.

Implemented:
- `#compact-expand` is now drawn at 22px (was the 13px chrome-button default), so the
  return-to-normal arrow reads clearly against the min/close glyphs.
- `compactResizeWidth` no longer reads `window.outerHeight` live during a width drag.
  The height is captured once at collapse into `compactStripHeight` (set in
  `queueCompactLayout`), and width resizes reuse that fixed value. Re-reading
  `window.outerHeight` is the same class of drift the title-bar drag already avoids:
  the resize mutates the value being read, so it compounds across mousemove events.

Verification (normal suite, per the user's testing limit):
- `tests/test_compact_now.py` updated: the width-resize node check now sets
  `window.outerHeight` to a deliberately wrong value (120) and asserts the resize
  still uses `compactStripHeight` (88), proving the height is pinned rather than
  re-read. `test_expand_control_lives_in_titlebar` pins the enlarged 22px rule.
- Full suite: 98 app tests passed on Python 3.14.
- `main.py --check`, `node --check` on both scripts, and `git diff --check` passed.
- No browser/native/VM or appearance tests run, following the normal-suite-only
  instruction. The actual visual size of the 22px arrow is unverified.

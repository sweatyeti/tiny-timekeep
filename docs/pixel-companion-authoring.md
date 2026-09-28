# Keeper of Time Pixel Companion: New Avatar Specification

Use this guide to create a **new** theme-specific avatar. It defines the frame constraint, integration points, behavior, and verification. Artwork and its theme assignment still need approval; this guide does not change tracking behavior or the Python API.

## Frame and artwork size

- The shared `#companion` frame is **128×96 CSS px**, including a **2 px border** on each side. With its border-box sizing, the usable interior is **124×92 CSS px**.
- Each avatar chooses its own canvas width, canvas height, and display scale. The shared companion stylesheet centers the avatar root and preserves its scale through awake/sleep motion and reduced-motion rendering. An avatar can use the default scale of `1` or set `--companion-scale` on its root; there is no universal logical canvas size or required scale.
- The sole size constraint is that the **complete rendered artwork envelope** fits within the usable frame interior in every state. Account for every painted descendant, outline, and animation position in awake, sleeping, and reduced-motion modes. Nothing may be clipped by the frame or cover task text, start time, or timer controls. Do not rely on the frame's overflow clipping to hide oversized artwork.
- The frame occupies the **right** side of the active-session card. Task text, start time, and two icon-only timer controls occupy the **left** side. Do not add controls to the artwork or change the frame to make artwork fit. Check clearance at both the 380 px default and 300 px minimum window widths; the app scrollbar consumes some of the narrow window's content width.

## Integration steps

Use a lowercase hyphenated `<slug>` for filenames, the root class, and the registry key. Replace `<theme-key>` with an **approved, selectable** theme key; do not invent a theme preference as part of avatar artwork.

1. **Create `web/companions/<slug>.js`.** Define a global renderer function, such as `renderNewAvatar()`, that returns one static decorative HTML fragment rooted at `.companion-<slug>`. Keep character parts scoped under that root. Do not create interactive descendants, user-data bindings, another status region, or a separate sleep cue: the shared registry appends the cue.
2. **Create `web/companions/<slug>.css`.** Set the root canvas width and height to suit the artwork. Set `--companion-scale` on the root when the default scale is not suitable; shared CSS supplies the centered anchor and applies that scale. Hide the root by default and display it only for `body[data-theme="<theme-key>"]`. Prefix part classes with the slug. Reuse theme color tokens where possible, and check any deliberate character color against its actual frame/background. Keep the complete rendered artwork envelope inside the usable frame interior at the selected size and scale.
3. **Load both files in [`web/index.html`](../web/index.html).** Add the stylesheet beside the companion styles in the head and the renderer script before `companions/registry.js`; the registry must load before `app.js`. Use relative paths that work both in pywebview and in the packaged app.
4. **Add mappings in [`web/companions/registry.js`](../web/companions/registry.js).** Add `<slug> → renderNewAvatar` to `COMPANION_AVATARS` and `<theme-key> → <slug>` to `COMPANION_REGISTRY`, preserving all other entries. Register only an approved theme/character pairing. An unmapped theme deliberately has an empty character scene with the shared cue.
5. **Preserve state behavior.** The shared stylesheet applies awake/sleeping motion and reduced-motion centering to the rendered avatar root while retaining its selected scale. Add rules in the avatar stylesheet for eyes or other state-dependent parts using `#companion[data-mode="awake"]` and `[data-mode="sleeping"]` as needed. Include all resulting positions in the rendered-envelope fit check. Keep the shared sleep cue working.
6. **Preserve accessibility.** The artwork stays inside `.companion-scene` (`aria-hidden="true"`). [`web/app.js`](../web/app.js) updates the shared `#companion` status/live region and `#companion-label` for awake/sleeping state; a renderer must not duplicate or replace that announcement.
7. **Extend [`tests/test_pixel_companion.py`](../tests/test_pixel_companion.py).** Verify the renderer loads and is selected by its approved theme, only one character is rendered, unknown/unmapped themes fail safely, and the chosen canvas and scale fit the shared frame including the animation envelope. Use a test-only nonstandard canvas/scale fixture so the test protects per-avatar sizing rather than a universal dimension. Cover awake, sleeping, reduced motion, and accessibility.

## Visual and runtime verification

From the app repository root:

```bash
python3 -m unittest discover -s tests
python3 main.py --check
node --check web/app.js
for file in web/companions/*.js; do node --check "$file"; done
git diff --check
```

Then run the **real main app window** with isolated test data. At 380 px and 300 px window widths, inspect the approved theme in active/awake and idle/sleeping states, switch themes, and measure the complete rendered artwork bounds against the 124×92 usable frame interior. Include animation extremes and reduced-motion mode; confirm the avatar does not cover the left-hand controls or task text and does not cause horizontal scroll. Check the empty frame for an unmapped theme. Tests and measurements do not substitute for a human look at the actual-size art.

## Scope boundary

An avatar is presentation only. Do not change the Python API/core contract, session storage, theme preference schema, tracking flow, or shared status/live-region semantics as part of artwork work.

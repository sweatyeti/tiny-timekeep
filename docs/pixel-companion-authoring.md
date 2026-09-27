# Keeper of Time Pixel Companion: New Avatar Specification

Use this guide to create a **new** theme-specific avatar. It defines the required dimensions, integration points, behavior, and verification. Artwork and its theme assignment still need approval; this guide does not change tracking behavior or the Python API.

## Size and placement contract

- The shared `#companion` frame is **128×96 CSS px**, including a **2 px border** on each side. Its usable interior is **124×92 CSS px**; artwork and outlines must stay inside it in every state. The frame clips overflow.
- Make the avatar root **32×36 logical CSS px**, positioned with `left: 50%`, `top: 50%`, and `transform: translate(-50%, -50%) scale(2)`. Its rendered footprint is **64×72 CSS px** within the frame. Do not size the root to 128×96 and scale it again. The registry-wide style test enforces the 32×36 root and 2× scale; a different logical size requires a separately approved contract and deliberate test/motion changes.
- The frame occupies the **right** side of the active-session card. Task text, start time, and two icon-only timer controls occupy the **left** side. Do not add controls to the artwork or change the frame to make artwork fit. Check clearance at both the 380 px default and 300 px minimum window widths; the app scrollbar consumes some of the narrow window's content width.

## Integration steps

Use a lowercase hyphenated `<slug>` for filenames, the root class, and the registry key. Replace `<theme-key>` with an **approved, selectable** theme key; do not invent a theme preference as part of avatar artwork.

1. **Create `web/companions/<slug>.js`.** Define a global renderer function, such as `renderNewAvatar()`, that returns one static decorative HTML fragment rooted at `.companion-<slug>`. Keep character parts scoped under that root. Do not create interactive descendants, user-data bindings, another status region, or a separate sleep cue: the shared registry appends the cue.
2. **Create `web/companions/<slug>.css`.** Center and size the root to the 32×36 logical dimensions above; hide it by default and display it only for `body[data-theme="<theme-key>"]`. Prefix part classes with the slug. Reuse theme color tokens where possible, and check any deliberate character color against its actual frame/background. Keep artwork readable as crisp pixel art at its rendered 2× size.
3. **Load both files in [`web/index.html`](../web/index.html).** Add the stylesheet beside the companion styles in the head and the renderer script before `companions/registry.js`; the registry must load before `app.js`. Use relative paths that work both in pywebview and in the packaged app.
4. **Add mappings in [`web/companions/registry.js`](../web/companions/registry.js).** Add `<slug> → renderNewAvatar` to `COMPANION_AVATARS` and `<theme-key> → <slug>` to `COMPANION_REGISTRY`, preserving all other entries. Register only an approved theme/character pairing. An unmapped theme deliberately has an empty character scene with the shared cue.
5. **Wire both states in [`web/companions/companion.css`](../web/companions/companion.css) or equivalent scoped CSS.** Add the new root to awake and sleeping animation rules and reduced-motion centering, and wire its eyes or other state-dependent parts to `#companion[data-mode="awake"]` and `[data-mode="sleeping"]` as needed. Preserve the centered 2× transform through both bob animations; under `prefers-reduced-motion: reduce`, remove movement while retaining centering and scale. Keep the shared sleep cue working.
6. **Preserve accessibility.** The artwork stays inside `.companion-scene` (`aria-hidden="true"`). [`web/app.js`](../web/app.js) updates the shared `#companion` status/live region and `#companion-label` for awake/sleeping state; a renderer must not duplicate or replace that announcement.
7. **Extend [`tests/test_pixel_companion.py`](../tests/test_pixel_companion.py).** Verify the renderer loads and is selected by its approved theme, only one character is rendered, unknown/unmapped themes fail safely, and the registered root obeys the sizing/scale rule. Cover awake, sleeping, reduced motion, and accessibility. Do not weaken the registry-wide size test merely to accommodate unapproved artwork.

## Visual and runtime verification

From the app repository root:

```bash
python3 -m unittest discover -s tests
python3 main.py --check
node --check web/app.js
for file in web/companions/*.js; do node --check "$file"; done
git diff --check
```

Then run the **real main app window** with isolated test data. At 380 px and 300 px window widths, inspect the approved theme in active/awake and idle/sleeping states, switch themes, and confirm the avatar remains inside the 128×96 frame without covering the left-hand controls or causing horizontal scroll. Check the empty frame for an unmapped theme, and verify reduced-motion behavior. Tests and measurements do not substitute for a human look at the actual-size art.

## Scope boundary

An avatar is presentation only. Do not change the Python API/core contract, session storage, theme preference schema, tracking flow, or shared status/live-region semantics as part of artwork work.

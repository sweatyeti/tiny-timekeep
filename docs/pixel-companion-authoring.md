# Keeper of Time Pixel Companion: Avatar Authoring Guide

This guide is for adding or refining a theme-specific Pixel Companion in Keeper of Time. It describes the current implementation and the extension path; it does not approve a character design or ask for a change to the app's tracking behavior.

## Current architecture

- [`web/index.html`](../web/index.html) owns the shared `#companion` status region. Its `.companion-scene` is `aria-hidden`; the sibling `#companion-label` is the screen-reader text.
- [`web/companions/companion.css`](../web/companions/companion.css) owns the fixed frame and shared awake/sleeping behavior, animations, sleep cue, and reduced-motion rules.
- Each avatar has a small JS markup renderer and a CSS file: `cat.js` + `cat.css`, `cyber.js` + `cyber.css`, and `sun.js` + `sun.css`.
- [`web/companions/registry.js`](../web/companions/registry.js) maps themes to avatar renderer names and renders the selected static markup into `.companion-scene`.
- [`web/app.js`](../web/app.js) supplies the theme and awake/sleeping state and updates the accessible label. Keep business/session logic out of avatar renderers.

The outer frame is **128×96 CSS px including its 2px border** (124×92 px of interior). Existing cat, cyborg, and sun art use centered **32×36 px** logical sprites rendered at **2×** (64×72 CSS px). The frame and sprite are separate dimensions: do not set the sprite to 128×96 and then scale it again. The five selectable themes are `cute`, `cyber`, `poolside`, `evergreen`, and `citrus-pop`; Cute, Cyber, and Poolside map to avatars. An unmapped theme intentionally shows no character, while the shared frame and sleep cue remain.

In the active-session card, the frame occupies the **right** column of `.now-tracking-top`; task name, start time, and the two compact icon-only timer actions occupy the **left** column. The controls are beside the frame, not inside it or below it. The 300 px minimum window has a vertical scrollbar that narrows the usable card width, so new art must stay within the existing frame and must not push, cover, or add controls.

## Adding an avatar

Example: add an avatar named `tree` for the `evergreen` theme. Replace `tree`/`evergreen` with the approved avatar and theme slugs.

1. **Design for the real footprint.** The shared frame is 128×96 CSS px; keep all visible pixels, outlines, and bobbing inside its 124×92 inner area. The current contract uses a centered 32×36 logical root with CSS `left: 50%`, `top: 50%`, `transform: translate(-50%, -50%) scale(2)`; that renders at 64×72 CSS px. The shared awake/sleep animations and reduced-motion rule must preserve the 2× scale and centering. The registry-wide style test currently requires every registered root to use these dimensions. If an approved future design needs a different logical size, change that test and the shared motion/centering deliberately, then verify all existing avatars still fit the same 128×96 frame. Use a small palette and chunky shapes readable at actual widget size.
2. **Add a renderer** at `web/companions/tree.js`. Follow the current `renderCatAvatar()` / `renderCyberAvatar()` / `renderSunAvatar()` pattern: return a static HTML fragment with a unique root class such as `.companion-tree`. Keep decorative markup inside the scene; do not add controls, user data, or another live region.
3. **Add scoped styling** at `web/companions/tree.css`. Position and center the sprite within the frame, hide it by default, then show it only for its theme, e.g. `body[data-theme="evergreen"] .companion-tree { display: block; }`. Prefix character-specific classes with the avatar slug to prevent style collisions. Reuse theme tokens such as `--text-main`, `--panel-row`, and `--border-dark` where they fit; use a deliberate character-specific color only when the design needs it.
4. **Load the new files** in `web/index.html`: add the stylesheet in the head alongside the existing companion CSS and the script near the other avatar scripts. Preserve script order: avatar renderer scripts load **before** `registry.js`, which loads **before** `app.js`.
5. **Register the renderer and theme** in `web/companions/registry.js`:

   ```js
   const COMPANION_AVATARS = {
     cat: renderCatAvatar,
     cyber: renderCyberAvatar,
     sun: renderSunAvatar,
     tree: renderTreeAvatar
   };

   const COMPANION_REGISTRY = {
     cute: 'cat',
     cyber: 'cyber',
     poolside: 'sun',
     evergreen: 'tree'
   };
   ```

   Keep the existing entries. Only map a theme after its design is approved. A theme may map to a renderer already used by another theme if that is the intended design.

6. **Preserve shared behavior.** The shared stylesheet names `.companion-cat`, `.companion-cyber`, and `.companion-sun` in awake/sleep animations and reduced-motion centering, with separate rules for their eyes. A new root or eye does not inherit every rule automatically. Reuse the shared eye hooks where they fit and extend the awake/sleep/reduced-motion selectors (or add equivalent avatar-scoped rules), preserving `translate(-50%, -50%) scale(2)` when motion is off. Keep the sleep cue and `#companion-label` behavior; test the existing characters after any shared change.
7. **Update tests** in `tests/test_pixel_companion.py` (and UI conformance tests only if needed). Prove the renderer is loaded and invoked for its mapped theme, existing mappings remain intact, no two sprites appear together, and unknown/unmapped themes fail safely. Its registry-wide style test checks each registered root's current 32×36 sizing and 2× scale; update this contract intentionally if the approved art needs different logical dimensions. Check the 128×96 frame, accessible structure, awake/sleeping states, and reduced motion. Prefer testing the render path over merely checking that a filename or selector exists.

## Visual conventions

- Match the app's crisp pixel-art style: rectangular blocks, square corners, dark outlines, no photorealistic texture, no box shadows, and no fine details that disappear at widget size.
- The 128×96 box is the shared frame; the current 32×36 logical art appears as 64×72 inside it. Measure both at CSS pixel scale and keep the full character inside the frame in awake and sleeping poses. Future avatars use this shared frame without changing unrelated theme mappings or accessibility.
- Keep the artwork decorative (`aria-hidden="true"`). Keep `#companion` as the single status/live region and let `renderCompanion()` update `#companion-label` as tracking starts and stops.
- Preserve the existing theme token system. Check contrast against the actual theme background and frame, not just against a white artboard.
- Do not add external image downloads, runtime dependencies, frameworks, or a build step. Keep asset paths relative to `web/index.html` so they work in the pywebview app and packaged build.

## Verification checklist

From the app repository root, run:

```bash
python3 -m unittest discover -s tests
python3 main.py --check
node --check web/app.js
for file in web/companions/*.js; do node --check "$file"; done
git diff --check
```

Also inspect the **real main app window** with the artwork at its rendered 2× size: active/awake and idle/sleeping at 380 px default width and 300 px minimum width, in the new theme and the existing avatar themes. Confirm the frame stays right of the icon-only timer controls without clipping/overlap or horizontal scrolling; verify theme switching, the empty frame for an unmapped theme, and reduced-motion centering without movement. Automated checks do not replace a human review of the artwork at actual size.

## Out of scope

An avatar is presentation only. Do not change the Python API/core contract, session files, theme preference schema, tracking logic, or the shared companion's accessibility semantics as part of artwork work. Do not silently map a theme to a new design without approval.

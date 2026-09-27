# Keeper of Time Pixel Companion: Avatar Authoring Guide

This guide is for adding or refining a small theme-specific companion in Keeper of Time. It describes the current implementation and the extension path; it does not approve a character design or ask for a change to the app's tracking behavior.

## Current architecture

- [`web/index.html`](../web/index.html) owns the shared `#companion` status region. Its `.companion-scene` is `aria-hidden`; the sibling `#companion-label` is the screen-reader text.
- [`web/companions/companion.css`](../web/companions/companion.css) owns the fixed frame and shared awake/sleeping behavior, animations, sleep cue, and reduced-motion rules.
- Each avatar has a small JS markup renderer and a CSS file: `cat.js` + `cat.css`, `cyber.js` + `cyber.css`.
- [`web/companions/registry.js`](../web/companions/registry.js) maps themes to avatar renderer names and renders the selected static markup into `.companion-scene`.
- [`web/app.js`](../web/app.js) supplies the theme and awake/sleeping state and updates the accessible label. Keep business/session logic out of avatar renderers.

The outer frame is **128×96 CSS px including its 2px border** (124×92 px of interior). Existing cat, cyborg, and sun art use centered **32×36 px** logical sprites rendered at **2×** (64×72 CSS px). The five themes already selectable in the app are `cute`, `cyber`, `poolside`, `evergreen`, and `citrus-pop`; currently Cute, Cyber, and Poolside map to avatars. An unmapped theme intentionally shows no character, while the shared frame and sleep cue remain.

## Adding an avatar

Example: add an avatar named `tree` for the `evergreen` theme. Replace `tree`/`evergreen` with the approved avatar and theme slugs.

1. **Design for the real footprint.** The shared frame is 128×96 CSS px; keep the visible character inside its 124×92 inner area. Use a centered 32×36 logical sprite with CSS `left: 50%`, `top: 50%`, `transform: translate(-50%, -50%) scale(2)`. The shared awake/sleep animations must preserve that 2× scale. Use a small palette and chunky shapes that remain readable at the rendered 2× size.
2. **Add a renderer** at `web/companions/tree.js`. Follow the current `renderCatAvatar()` / `renderCyberAvatar()` pattern: return a static HTML fragment with a unique root class such as `.companion-tree`. Keep decorative markup inside the scene; do not add controls, user data, or another live region.
3. **Add scoped styling** at `web/companions/tree.css`. Position and center the sprite within the frame, hide it by default, then show it only for its theme, e.g. `body[data-theme="evergreen"] .companion-tree { display: block; }`. Prefix character-specific classes with the avatar slug to prevent style collisions. Reuse theme tokens such as `--text-main`, `--panel-row`, and `--border-dark` where they fit; use a deliberate character-specific color only when the design needs it.
4. **Load the new files** in `web/index.html`: add the stylesheet in the head alongside the existing companion CSS and the script near the other avatar scripts. Preserve script order: avatar renderer scripts load **before** `registry.js`, which loads **before** `app.js`.
5. **Register the renderer and theme** in `web/companions/registry.js`:

   ```js
   const COMPANION_AVATARS = {
     cat: renderCatAvatar,
     cyber: renderCyberAvatar,
     tree: renderTreeAvatar
   };

   const COMPANION_REGISTRY = {
     cute: 'cat',
     cyber: 'cyber',
     evergreen: 'tree'
   };
   ```

   Keep the existing entries. Only map a theme after its design is approved. A theme may map to a renderer already used by another theme if that is the intended design.

6. **Preserve shared behavior.** The shared stylesheet currently has selectors for the existing `.companion-cat` and `.companion-cyber` roots and their eye classes. A new character does not automatically inherit every animation or eye-state rule. Reuse the shared eye hooks where their shape fits, and add the new root/eye class to the shared awake/sleep/reduced-motion rules—or add equivalent rules in the avatar's CSS—so both modes work. If changing shared selectors, test the old characters too.
7. **Update tests** in `tests/test_pixel_companion.py` (and UI conformance tests only if needed). Prove the renderer is actually loaded and invoked for its mapped theme, that other themes keep their intended mappings, that no two sprites appear together, and that unknown/unmapped themes fail safely. Check accessible structure, the shared 128×96 frame, 32×36 sprites at 2×, both awake/sleeping states, and reduced motion. Prefer testing the mapping/render path over merely checking that a filename or selector exists.

## Visual conventions

- Match the app's crisp pixel-art style: rectangular blocks, square corners, dark outlines, no photorealistic texture, no box shadows, and no fine details that disappear at widget size.
- The 128×96 box is the shared frame. Measure the box and 2× sprite at CSS pixel scale; future avatars use this standard frame without changing theme mappings or accessibility.
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

Also inspect the rendered character in the 128×96 frame in both modes, verify the theme switch updates the character, and confirm reduced-motion removes movement. The test suite checks structure and behavior; it does not replace visual review at actual size.

## Out of scope

An avatar is presentation only. Do not change the Python API/core contract, session files, theme preference schema, tracking logic, or the shared companion's accessibility semantics as part of artwork work. Do not silently map a theme to a new design without approval.

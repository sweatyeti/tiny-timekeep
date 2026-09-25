---
name: keeper-of-time-app
description: How Keeper of Time works — a pixel-art Windows widget for time tracking, its three-layer architecture (spec / contract / UI), and the conventions to follow when extending it.
---

# Keeper of Time

A small, always-visible Windows desktop widget for time tracking: start/stop
tasks, see what's currently running, review and edit a log of entries, and
summarize time per task. Built as a pixel-art, anime-cutesy floating window
(frameless, resizable, custom title bar).

## What this is, in one paragraph

Keeper of Time is a pywebview desktop app: a Python process hosts a small local
web UI (HTML/CSS/JS) in a native, chromeless window. The UI never touches
storage or business rules directly — it only calls a fixed set of methods on
a Python object (`pywebview.api`), defined once in a contract document, and
that same object's real implementation (`timetracker_core`) handles sessions,
entries, and all the rounding/logging/deletion rules.

## Architecture: three layers, in order of authority

1. **Functional spec** (`specs/functional-spec.md`) — the actual
   behavioral rules: how entries work, rounding, logged/unlogged, deletion
   and restore, session lifecycle. This is the source of truth; nothing else
   overrides it.
2. **Core-logic contract** (`specs/core-logic-contract.md`) — maps that spec onto
   concrete Python method signatures, a JSON-shaped "view model," and error
   codes. This is the one document both the core and the UI are built
   against, so they can be developed independently and swapped in without
   either side knowing the other's internals. Currently **v1.4**.
3. **This app** — `main.py` (pywebview host + `Api` glue), `timetracker_core`
   (the real core, implementing the contract), `preferences.py` (a small,
   separate UI-settings store), and `web/` (the frontend, which only ever
   calls `pywebview.api.*`).

If you're changing behavior (rounding rules, what counts as loggable, how
deletion works), that's a functional-spec + contract change first, then
core, then UI — in that order. If you're changing how something looks or
is laid out, that's UI-only.

## Theming & visual design

One fixed theme — no light/dark or day/night switching. (The original
screenshot reference had Day/Night and a timer-speed toggle; both were
explicitly dropped as "style reference only, not spec" early on — see
`HANDOFF.md`'s history if that's ever reconsidered.) Everything below lives
in `web/style.css`.

**Color tokens** — all defined once on `:root`, referenced everywhere else
by variable, never hardcoded inline:

| Token | Hex | Used for |
|---|---|---|
| `--bg-top` / `--bg-bottom` | `#1b1330` / `#4a3668` | Full-window background gradient (top→bottom) |
| `--panel` | `#3a2b52` | Main panel/card backgrounds (now-tracking box, overlay panel) |
| `--panel-row` | `#2c2043` | Inset/recessed surfaces — inputs, task rows, checkbox fill |
| `--panel-row-alt` | `#342650` | Dashed row-divider color in lists |
| `--titlebar` | `#ff9ebb` | Title bar background |
| `--titlebar-text` | `#2a1f3d` | Text/icons on the title bar, and chrome-button background |
| `--accent-pink` | `#ff8fa3` | Primary action color — buttons, inactive-status banner, stop-adjacent actions |
| `--accent-mint` | `#7de8c8` | Secondary/positive accent — active-status banner, play icons, checked checkbox |
| `--text-main` | `#f2e9da` | Primary text |
| `--text-dim` | `#b9a9d1` | Secondary/muted text — labels, hints, timestamps |
| `--callout` | `#ff6b6b` | "Needs attention" red — unlogged-time callouts in the summary, unlogged badge |
| `--logged` | `#8de0a0` | Logged badge (green, distinct from `--accent-mint` so summary and log-tab meanings don't blur together) |
| `--border-dark` | `#1b1330` | The one border color, everywhere — same value as `--bg-top` on purpose (see Pixel-art conventions) |

When adding a new UI state that needs its own color (a new badge type, a
new banner state), reuse an existing token if it's semantically close
enough; only add a new `:root` variable for a genuinely new meaning, and
slot it into the table above.

**Typography** — two fonts, both pixel-style, used for different jobs:
- **`'Press Start 2P'`** — chunky, low-detail, used sparingly for short
  strings only: the title bar label, section headers (`h2`), the status
  banner, buttons, the summary table header. It's illegible at length, so
  never use it for body copy, descriptions, or anything that wraps.
- **`'VT323'`** — the readable pixel font, used for everything else: body
  text, list rows, inputs, hints. This is `html, body`'s default
  (`font-family: 'VT323', monospace`), so most elements get it for free
  and only need an override when they specifically want the blocky font.
- Both load from Google Fonts (`index.html`'s `<link>` tags) — see the
  "needs network on first load" gotcha below.

**Pixel-art conventions** — the visual rules that make new elements look
like they belong, rather than looking "off" against the rest of the UI:
- **Borders are always 2–3px solid `--border-dark`**, never a lighter
  shade, never `border-radius` (flat/sharp corners throughout — rounding
  anything breaks the pixel-art look immediately).
- **No box-shadows, no gradients on individual elements** — the only
  gradient in the whole app is the full-window background
  (`--bg-top`→`--bg-bottom`); everything else is flat fill + hard border.
- **Dashed dividers** (`border-bottom: 2px dashed var(--panel-row-alt)`)
  separate rows within a list — solid borders are reserved for panel/card
  boundaries, dashed for internal row separation.
- **Banners bleed to the panel's edges** via negative margin (see
  `.status-banner`'s `margin: -14px -14px 12px -14px`) rather than sitting
  inset with visible padding around them — this is what makes a banner
  read as its own distinct strip instead of just another row.
- **Buttons and interactive chrome use `'Press Start 2P'` at 10–13px**,
  giving them a distinct "this is clickable UI chrome" weight against the
  `'VT323'` body text around them.

## Technical specifications

**Runtime:** Python 3.11; pywebview pinned exactly (`pywebview==6.2.1`) in
`requirements.txt` — the JS bridge this app rides on has changed shape across
major versions. Core has zero non-stdlib dependencies (`json`, `uuid`,
`dataclasses`, `pathlib`, timezone-aware `datetime`).

**Storage:**
- Sessions: `%LOCALAPPDATA%\KeeperOfTime\sessions` (default; overridable —
  `TimeTrackerCore.__init__(storage_path, clock=None)`, or
  `KEEPER_OF_TIME_DATA_DIR` at the app level).
- UI preferences: `%LOCALAPPDATA%\KeeperOfTime\preferences.json` — a
  sibling file, deliberately *not* inside the sessions folder, since it's
  app/UI settings, not session data. Atomic writes (temp file + `os.replace`),
  same pattern as the core uses for session files. `theme` defaults to `cute`;
  the compact bottom picker can select `cute` or `cyber`, and invalid stored
  values safely fall back to `cute`.

**Frontend:** vanilla HTML/CSS/JS, no build step, no framework. Fonts:
'Press Start 2P' (headers, banner, buttons) and 'VT323' (body/list text),
both loaded from Google Fonts CDN — **this app needs network access on
first load** to fetch them (no local fallback bundled yet).

**Window:** frameless (`frameless=True`), resizable, custom title bar with
hand-rolled drag, and a hand-rolled resize grip (bottom-right corner) —
both necessary *because* frameless windows have no OS-drawn drag/resize
affordances; `resizable=True` alone does nothing without them. Windows
target uses the WebView2 runtime (ships with Win10/11 by default).

**Contract version gate:** `main.py` hard-fails at startup if
`timetracker_core.CONTRACT_VERSION` doesn't match the pinned
`EXPECTED_CONTRACT_VERSION` constant — a deliberate tripwire so a stale
core/UI pairing fails loudly instead of silently disagreeing.

## File layout

```
keeper-of-time/
├── main.py              # pywebview host + Api (window chrome, prefs, core passthrough)
├── preferences.py        # small standalone UI-settings store (JSON, atomic writes)
├── timetracker_core/     # the real core (place here — flat import, `from timetracker_core import ...`)
├── core_mock.py          # dev-time stand-in for timetracker_core — unused now, safe to delete
├── core-logic-contract.md
├── README.md
└── web/
    ├── index.html
    ├── style.css
    └── app.js
```

## Conventions to follow when extending this app

- **The UI only ever calls `pywebview.api.*`.** Never reach past that
  boundary from `app.js` — no direct file access, no assumptions about how
  the core stores or computes anything.
- **Every command result flows through `handleResult(r)`** in `app.js` —
  it applies `r.state` on success or opens an error overlay on failure
  (the contract's `{ok, error, message}` envelope). New actions should
  reuse this, not roll their own success/error handling.
- **New "enter something" UI is an overlay**, built with `openOverlay(title,
  bodyHtml)` / `closeOverlay()`. Give the primary button the
  `overlay-submit` class so it's reachable by the global Enter-to-submit
  handler (`wireEnterToSubmit`) for free.
- **New settings go through `preferences.py`**, not ad-hoc localStorage or
  new files — `api().get_preferences()` / `api().set_preference(key, value)`.
  Add a default to `DEFAULT_PREFERENCES` in `preferences.py` so old prefs
  files upgrade cleanly.
- **New window-chrome interactions (drag/resize-like things) must use the
  anchor-once pattern**, not accumulated deltas. Read a stable starting
  point synchronously from the DOM (`window.screenX/Y`,
  `window.outerWidth/Height`) once at gesture-start, then always send an
  *absolute* target to Python (`move_window_to`, `resize_window_to`) on
  every move. Accumulating small deltas through an async round-trip is
  what caused the original drag-drift bug — don't reintroduce that shape.
- **Palette/type tokens** live at the top of `style.css` as CSS variables
  (`--bg-top`, `--panel`, `--accent-pink`, `--accent-mint`, etc.) — reuse
  them rather than hardcoding colors, so a future palette change is a
  one-place edit.
- **Any change to the view model, a command's signature, or an error code
  is a contract change** — bump `version:` in `specs/core-logic-contract.md`'s
  frontmatter, add a changelog line in its §6.3, and update
  `EXPECTED_CONTRACT_VERSION` in `main.py` to match. This is what makes the
  version gate meaningful instead of decorative.

## Known gotchas

- Frameless windows lose native drag/resize — already handled (see above),
  but keep in mind if you ever touch window creation flags.
- `w.on_top` (pywebview's always-on-top setter) hung/crashed the app on the
  builder's machine — that whole feature (pin button, `toggle_always_on_top`)
  was removed rather than fixed. Don't reintroduce it without root-causing
  that first.
- Google Fonts require network on first load; there's no bundled fallback
  yet if this needs to run fully offline.

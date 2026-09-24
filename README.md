# TinyTimesheet

A desktop time tracker: a stdlib-only Python **core** (sessions, entries, rules, storage) and a
**pywebview frontend**. One repo, one build, one `.exe`.

The core and the UI are separate layers by contract (`specs/core-logic-contract.md`, **v1.4**).
Combining them into one project does not merge the layers: `main.py` is the only place they meet,
and the UI reaches the core solely through the object passed as `js_api`.

## Drop your UI in

The frontend is the one thing not in this repository yet. Put it in `ui/` with `index.html` at
its root:

```
ui/
  index.html        <- loaded by main.py
  app.js  styles.css  ...   <- whatever your mock project already has
```

Then `python main.py`. If `ui/index.html` is missing, `main.py` says so instead of opening a
blank window. **Your mock object is now retired** — the real core replaces it, and the version
gate below stops a stale copy from running silently.

## Layout

```
main.py                   the only meeting point: builds the core, starts pywebview
src/timetracker_core/     the core, vendored verbatim (stdlib-only; do not edit here)
ui/                       the frontend (drop-in)
tests/                    the core's 79 tests, unmodified, plus tests/test_boundary.py
specs/                    the contract (v1.4) and the functional spec (v2.0)
packaging/                pyinstaller spec + build.ps1
CORE-VERSION              which core commit this copy came from
requirements.txt          pywebview, pinned exactly
requirements-dev.txt      + pyinstaller, for the build
```

## Run

```bash
py -3.11 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python main.py
```

Verify the wiring without opening a window — this is also what CI/your build script runs first:

```bash
python main.py --check        # prints the contract version, replays the golden fixture, needs no pywebview
python -m unittest discover -s tests
```

Sessions live in `%LOCALAPPDATA%\TinyTimesheet\sessions` (`TIMETRACKER_DATA_DIR` overrides it).
They are deliberately **not** stored beside the executable: a one-file build unpacks to a temp
directory and starts empty each run.

## Build the .exe

```powershell
.\packaging\build.ps1
```

Creates the venv, installs the pinned versions, runs `main.py --check` and the test suite, and
**refuses to package if either fails**, then produces `dist\TinyTimesheet.exe` via
`packaging\timetracker.spec`. The spec bundles `ui/` and collects pywebview's assets and its
Windows backend (`clr`/WebView2), which is the part that otherwise bites a `--onefile` build.

Target machines need the WebView2 runtime — present by default on Win10/11.

## The rules that keep the split honest

- The core directory is a **verbatim copy** of `timetracker-core-python`. Change it there, re-copy
  (or `git subtree pull`), and bump `CONTRACT_VERSION_EXPECTED` in `main.py` to match.
- The UI imports nothing from the core except `TimeTrackerCore` and `CONTRACT_VERSION`.
- `tests/test_boundary.py` enforces the rest: the core must import **only** the standard library,
  must never import the UI or pywebview, and the app's expected version must equal the core's.

## Verified in this copy

- `python -m unittest discover -s tests` → **79 tests, OK** on a bare Python 3.11 (no venv, no
  installed packages): the core's 73 plus 6 boundary tests.
- `python main.py --check` → contract `v1.4`, golden fixture matching the contract's §2 view model
  exactly (weeding 2/30/75 callout true; unnamed 1/15/15 callout false; totals 30/75), no
  `isActive` in the session object, and the sessions directory reported.
- The PyInstaller path has **not** been exercised here — there is no Windows host and no
  WebView2 on this machine. Build it on Windows and report what breaks; that is the one part of
  this scaffold that is reasoned rather than proven.
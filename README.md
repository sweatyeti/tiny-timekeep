# Keeper of Time

A desktop time tracker: a stdlib-only Python **core** (sessions, entries, rules, storage) and a
**pywebview frontend**. One repo, one build, one `.exe`.

The app is called **Keeper of Time**. The Python package (`timetracker_core`) and the core class
(`TimeTrackerCore`) keep their names deliberately — an import path and a contract-fixed interface
are not the app's name, and renaming either would be a contract change for no benefit.

The core and the UI are separate layers by contract (`specs/core-logic-contract.md`, **v1.4**).
Combining them into one project does not merge the layers: `main.py` is the only place they meet,
and the UI reaches the core solely through the object passed as `js_api`.

## Drop your UI in

The frontend is the one thing not in this repository yet. Put it in `web/` with `index.html` at
its root — the layout the UI layer already uses:

```
web/
  index.html        <- loaded by main.py
  app.js  styles.css  ...   <- the frontend's own files, unchanged
```

Then `python main.py`. If `web/index.html` is missing, `main.py` says so instead of opening a
blank window. **Your mock object is now retired** — the real core replaces it, and the version
gate below stops a stale copy from running silently.

## Layout

```
main.py                   the only meeting point: builds the core, starts pywebview
timetracker_core/         the core, vendored verbatim at the repo root (stdlib-only; do not edit here)
web/                      the frontend (drop-in)
tests/                    50 app-specific checks; canonical core tests stay in keeper-of-time-core
specs/                    the contract (v1.4) and the functional spec (v2.0)
packaging/                pyinstaller spec + build.ps1
CORE-VERSION              which core commit this copy came from
requirements.txt          pywebview, pinned exactly
requirements-dev.txt      + pyinstaller, for the build
```

## Run

```bash
py -3.14 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python main.py
```

`build.ps1` pins the interpreter: the project targets **Python 3.14.7** exactly, so `py -3.14`
selects the newest installed 3.14.x and the build then asserts the patch version rather than
assuming it. A `.venv` built with any other version is refused, not reused.

Verify the wiring without opening a window — this is also what CI/your build script runs first:

```bash
python main.py --check        # prints the contract version, replays the golden fixture, needs no pywebview
python -m unittest discover -s tests
```

Sessions default to `%LOCALAPPDATA%\KeeperOfTime\sessions` on Windows. Change the entry save
location from the folder button beside the theme controls; the choice persists in
`%LOCALAPPDATA%\KeeperOfTime\preferences.json`, independently of the selected sessions folder.
When changing folders, the app first confirms the new location and then asks whether to move
existing session files. A move is copy-first, collision-safe, and verified before the old copies
are removed. If you decline, existing files remain in the old folder and new sessions use the
selected folder. `KEEPER_OF_TIME_DATA_DIR` takes precedence over the saved preference and disables
the selector while set. Sessions are deliberately **not** stored beside the executable: a one-file
build unpacks to a temp directory and starts empty each run.

## Build the .exe

```powershell
.\packaging\build.ps1
```

Creates the venv, installs the pinned versions, runs `main.py --check` and the test suite, and
**refuses to package if either fails**, then produces `dist\KeeperOfTime.exe` via
`packaging\keeper-of-time.spec`. The spec bundles `web/` and collects pywebview's assets and its
Windows backend (`clr`/WebView2), which is the part that otherwise bites a `--onefile` build.

The script requires **Python 3.14.7**. An existing `.venv` built with another version is not
reused — it fails with the version it found, and `.\packaging\build.ps1 -RecreateVenv` deletes and
rebuilds it.

Target machines need the WebView2 runtime — present by default on Win10/11.

## Releases

Pushing a version tag starts the Windows release workflow. It checks out the tagged commit (not
the current branch tip), installs the pinned build requirements with Python 3.14.7, runs
`main.py --check` and the full unittest suite, then builds `dist\KeeperOfTime.exe` from
`packaging\keeper-of-time.spec`. A failed gate prevents the release from being created.

Promote the release commit from `dev` through a reviewed PR and ensure it is merged to `main`
before tagging. After that `main` commit is on the remote, create and push a tag such as:

```powershell
git tag -a v1.2.3 -m "Keeper of Time v1.2.3"
git push origin v1.2.3
```

Tags matching `v*` publish a GitHub Release. A tag name containing a hyphen, such as
`v1.2.3-rc.1`, is published as a prerelease; a tag without a hyphen is a stable release. The
workflow needs no personal access token or user-specific secret: only its release-publishing job
uses the scoped `GITHUB_TOKEN` with `contents: write`. You can also start **Windows Release Build**
manually from the Actions page to run the same build and test gates without publishing a release.

GitHub automatically supplies source-code ZIP and TAR archives for every release tag. The workflow
adds the Windows-only `KeeperOfTime.exe` asset; it does not create an installer or macOS/Linux
executables. The executable is currently **unsigned**—Windows may show a SmartScreen warning.
Target machines still need the WebView2 runtime (normally present on Windows 10/11).

For the first release tag, confirm in the Actions log that the `Windows Release Build` workflow
ran against that tag, that all gates passed, and that `KeeperOfTime.exe` is attached to the new
GitHub Release before announcing it.

## The rules that keep the split honest

- The core directory is a **verbatim copy** of `keeper-of-time-core`. Change it there, re-copy
  (or `git subtree pull`), and bump `CONTRACT_VERSION_EXPECTED` in `main.py` to match.
- The UI imports nothing from the core except `TimeTrackerCore` and `CONTRACT_VERSION`.
- `tests/test_boundary.py` enforces the rest: the core must import **only** the standard library,
  must never import the UI or pywebview, and the app's expected version must equal the core's.

## Verified in this copy

- `python -m unittest discover -s tests` → **50 app-specific tests, OK**. Verified on Python
  3.14.7 (the pinned interpreter) and on 3.11.9 on the same Windows machine, and on 3.11.15 on
  Linux. The byte-identical copies of the core's 73 canonical tests were removed from this app
  repository; they remain unchanged and run in the separate `keeper-of-time-core` repository.
- `python main.py --check` → `Keeper of Time: contract v1.4`, golden fixture matching the contract's §2 view model
  exactly (weeding 2/30/75 callout true; unnamed 1/15/15 callout false; totals 30/75), no
  `isActive` in the session object, and the sessions directory reported. Passes on 3.14.7.
- **Windows, end to end on the 3.14.7 interpreter** (Windows 11 Pro 26200, Python 3.14.7,
  pywebview 6.2.1 + pythonnet 3.1.0 over WebView2): the real app was booted and driven through
  its own bridge — **24 API methods** exposed, and `get_state`, `start_session`, `list_sessions`,
  `list_loggable_task_groups`, `get_preferences`, `set_preference`, `stop_and_start_entry`,
  `delete_entry`, `list_deleted_entries` (the deleted row carried its `description`) and
  `restore_entry` all round-tripped. The DOM rendered its task/summary rows with the real colour
  tokens applied (`VT323`, titlebar `rgb(255,158,187)`), zero JS errors. `pip check` clean on the
  resolved set; no dependency pin needed changing for 3.14 (PyInstaller 6.22.3 and pythonnet
  3.1.0 both ship 3.14 wheels).
- **The packaged exe was built and run on 3.14.7**: `dist\KeeperOfTime.exe`, 15,147,488 bytes
  (14.4 MB), one-file, windowed (sha256 `C5ECA359…`). It launched into `Session 1`, spawned 13
  WebView2 child processes, rendered its start screen and — after its own **Start new session**
  button was clicked through the UI — its active-tracking screen, then wrote a real
  `schemaVersion` 2 session document to the per-user data directory. Nothing was written beside
  the exe, and no session data appeared in the one-file extraction directory. The window icon
  Windows actually reports (`WM_GETICON`, 32x32) renders to the same pixel hash as
  `assets/keeper-of-time.ico` and as the icon embedded in the exe.
- Earlier full verification on the old 3.11.9 interpreter, kept as the historical baseline
  (Windows 11 Pro 26200, Python 3.11.9, WebView2 153): it booted the same way with 21 API methods
  and rendered 1 task row, 2 entry rows and 1 summary row, zero JS errors.
- Known gap: launch-to-loaded measured **25.9 s** on a cold first load, caused by `web/index.html`
  fetching Google Fonts from the CDN. Vendoring the fonts locally removes the stall and the
  offline dependency.
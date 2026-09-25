"""
Keeper of Time — pywebview host.

Wires the web UI (web/) to the real TimeTrackerCore (timetracker_core package), and exposes the
app-level surface the UI also needs: window chrome (frameless drag/resize) and UI preferences.

This file is the only place the two layers meet. `Api` carries three kinds of methods:

  * window chrome (move_window_to, resize_window_to, exit_app) — not part of the core contract
  * UI preferences (get_preferences, set_preference) — app settings, see preferences.py
  * the core contract's commands/queries — delegated straight through to the core

Provenance: the `Api` class, the window flags and the preference store come from the UI layer's
own bootstrap. The version gate, `--check` mode, the writability probe and the data-dir override
come from the scaffold that stood in for this file before the UI arrived. `core_mock.py`, the
dev-time stand-in for the core, was deleted at integration — the real core is the only
implementation now.

Run:    python main.py
Check:  python main.py --check      (no window, no pywebview — verifies the core wiring)
Build:  packaging/build.ps1         (Windows, produces dist/KeeperOfTime.exe)
"""
import argparse
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path

# The core package and preferences.py sit at the repo root, so the root is the import root.
# Running this file puts BASE_DIR on sys.path anyway; doing it explicitly keeps `python -m` and
# imported-from-tests runs working, and it has to happen before the local imports below.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from preferences import PreferencesStore  # noqa: E402
from timetracker_core import TimeTrackerCore, CONTRACT_VERSION  # noqa: E402

# Display name vs technical identifier: the window and title bar say "tinyTimekeep", while the
# executable, the data folder and the process name stay space-free.
APP_NAME = "KeeperOfTime"
WINDOW_TITLE = "tinyTimekeep"
DATA_DIR_ENV = "KEEPER_OF_TIME_DATA_DIR"

# Keep in lockstep with specs/core-logic-contract.md's frontmatter `version:`. This
# is a deliberate build-time tripwire (contract §6.3's compatibility rule) —
# if timetracker_core ships a contract change this UI hasn't been updated
# for, fail loudly here rather than disagree silently at runtime.
EXPECTED_CONTRACT_VERSION = "v1.4"

# Resolved relative to this file, not the current working directory — matters
# once this is launched via a shortcut/startup entry rather than a terminal
# already cd'd into this folder.
INDEX_HTML = os.path.join(BASE_DIR, "web", "index.html")


def _user_data_base():
    base = os.environ.get("LOCALAPPDATA")
    if not base:
        # Not on Windows (or LOCALAPPDATA unset) — dev-machine fallback only;
        # the real target is Windows per contract §6.1.
        base = os.path.expanduser("~/.local/share")
    return base


def _default_storage_path():
    """Per-user data, never beside the executable.

    A one-file PyInstaller build unpacks to a temp directory and starts empty each run, so the
    storage path has to be somewhere that outlives the process.
    """
    override = os.environ.get(DATA_DIR_ENV)
    if override:
        return os.path.expanduser(override)
    path = os.path.join(_user_data_base(), APP_NAME, "sessions")
    os.makedirs(path, exist_ok=True)
    return path


def _default_preferences_path():
    override = os.environ.get(DATA_DIR_ENV)
    if override:
        return os.path.join(os.path.expanduser(override), "preferences.json")
    return os.path.join(_user_data_base(), APP_NAME, "preferences.json")


def ensure_usable_sessions_dir(path):
    """Create the directory and prove we can write to it.

    The core deliberately does not raise on an unusable path (it answers `internal_error` on the
    first command instead), so the loud, human-readable failure belongs here, at startup.
    """
    try:
        os.makedirs(path, exist_ok=True)
        probe = os.path.join(path, ".write-probe")
        with open(probe, "w", encoding="utf-8") as f:
            f.write("ok")
        os.remove(probe)
    except OSError as exc:
        raise SystemExit(
            f"Cannot use the sessions directory:\n  {path}\n  {exc}\n"
            f"Set {DATA_DIR_ENV} to a writable folder and try again."
        )


def check_contract_version():
    if CONTRACT_VERSION != EXPECTED_CONTRACT_VERSION:
        raise SystemExit(
            f"Contract version mismatch: this UI build expects "
            f"{EXPECTED_CONTRACT_VERSION!r}, but timetracker_core reports "
            f"{CONTRACT_VERSION!r}. Re-check specs/core-logic-contract.md against "
            f"both sides before running — see §6.3's compatibility rule."
        )


class Api:
    """Exposed to the frontend as `pywebview.api`. Three kinds of methods:
    window chrome (move_window_to, exit_app), UI preferences (get/set_preference,
    separate from the core contract), and the core contract commands/queries,
    delegated straight through to the core implementation.
    """

    def __init__(self, storage_path=None, preferences_path=None):
        self.core = TimeTrackerCore(storage_path or _default_storage_path())
        self.prefs = PreferencesStore(preferences_path or _default_preferences_path())
        self._window = None

    def set_window(self, window):
        self._window = window

    # --- window chrome (not part of the core contract) ---

    def move_window_to(self, x, y):
        if self._window is not None:
            self._window.move(int(x), int(y))

    def resize_window_to(self, width, height):
        # Frameless windows have no OS-drawn resize handles, so resizable=True
        # alone does nothing — this backs a hand-built resize grip in the UI,
        # same reason the title bar needs hand-built drag.
        if self._window is not None:
            self._window.resize(int(width), int(height))

    def minimize_window(self):
        """Minimize to the taskbar (a normal minimize — this is deliberately not a
        minimize-to-tray: nothing here hides the process or removes it from the taskbar)."""
        if self._window is not None:
            self._window.minimize()

    def exit_app(self):
        if self._window is not None:
            self._window.destroy()

    # --- UI preferences (separate from the core contract — see preferences.py) ---

    def get_preferences(self):
        return self.prefs.get_all()

    def set_preference(self, key, value):
        return self.prefs.set(key, value)

    # --- core contract passthrough ---

    def get_state(self):
        return self.core.get_state()

    def list_sessions(self):
        return self.core.list_sessions()

    def start_session(self, name=None, first_task=None):
        return self.core.start_session(name, first_task)

    def resume_session(self, session_id):
        return self.core.resume_session(session_id)

    def stop_and_start_entry(self, next_task=None):
        return self.core.stop_and_start_entry(next_task)

    def edit_entry(self, entry_id, task=None, description=None, logged=None):
        return self.core.edit_entry(entry_id, task, description, logged)

    def delete_entry(self, entry_id):
        return self.core.delete_entry(entry_id)

    def restore_entry(self, entry_id):
        return self.core.restore_entry(entry_id)

    def list_loggable_task_groups(self):
        return self.core.list_loggable_task_groups()

    def log_task_group(self, task):
        return self.core.log_task_group(task)

    def list_deleted_entries(self):
        return self.core.list_deleted_entries()

    def stop_tracking(self):
        return self.core.stop_tracking()

    def stop_and_exit(self):
        return self.core.stop_and_exit()


# ---------------------------------------------------------------------------
# --check: verify the wiring without a window
# ---------------------------------------------------------------------------

class _FixedClock:
    """Deterministic clock so --check prints the same numbers every time."""

    def __init__(self, start):
        self._now = start

    def __call__(self):
        return self._now

    def advance(self, **kwargs):
        self._now = self._now + timedelta(**kwargs)


def run_checks():
    """Exercise the core end to end in a throwaway directory. Never opens a window."""
    print(f"{WINDOW_TITLE}: contract {CONTRACT_VERSION} (expected {EXPECTED_CONTRACT_VERSION})")
    check_contract_version()

    workdir = tempfile.mkdtemp(prefix="keeper-of-time-check-")
    try:
        clock = _FixedClock(datetime(2026, 9, 23, 9, 0, 0, tzinfo=timezone.utc))
        core = TimeTrackerCore(workdir, clock=clock)

        core.start_session("Garden work", "weeding")
        core.edit_entry(1, None, "front bed", None)
        clock.advance(minutes=45)
        core.stop_and_start_entry("weeding")
        core.edit_entry(2, None, "back bed", None)
        clock.advance(minutes=30)
        core.stop_and_start_entry("")
        clock.advance(minutes=15)
        core.stop_and_start_entry("planning")
        core.edit_entry(4, None, "weekly review", None)
        core.edit_entry(1, None, None, True)

        state = core.get_state()
        print("session keys:", sorted(state["session"].keys()))
        print("currentEntry:", json.dumps(state["currentEntry"]))
        print("summary:", json.dumps(state["summary"]))
        print("totals:", json.dumps(state["totals"]))

        expected = {
            "summary": [
                {"task": "weeding", "count": 2, "unloggedMinutes": 30, "totalMinutes": 75,
                 "callout": True},
                {"task": "unnamed", "count": 1, "unloggedMinutes": 15, "totalMinutes": 15,
                 "callout": False},
            ],
            "totals": {"unloggedMinutes": 30, "totalMinutes": 75},
        }
        for field, value in expected.items():
            if state[field] != value:
                print(f"FAIL: {field} did not match the contract's golden fixture", file=sys.stderr)
                print(f"  expected {json.dumps(value)}", file=sys.stderr)
                print(f"  got      {json.dumps(state[field])}", file=sys.stderr)
                return 1
        if "isActive" in state["session"]:
            print("FAIL: 'isActive' is not part of contract v1.4", file=sys.stderr)
            return 1

        # v1.4: a deleted row carries the description the restore screen renders.
        core.delete_entry(2)
        deleted = core.list_deleted_entries()
        if not deleted or sorted(deleted[0].keys()) != ["description", "endTime", "id",
                                                        "startTime", "task"]:
            print(f"FAIL: list_deleted_entries row shape wrong: {json.dumps(deleted)}",
                  file=sys.stderr)
            return 1

        if not os.path.exists(INDEX_HTML):
            print(f"note: no UI yet at {INDEX_HTML}")
        else:
            print(f"ui: {INDEX_HTML} present")
        print(f"sessions dir would be: {_default_storage_path()}")
        print("OK")
        return 0
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

def main(argv=None):
    parser = argparse.ArgumentParser(description=f"{WINDOW_TITLE} - desktop time tracker")
    parser.add_argument("--check", action="store_true",
                        help="verify the core wiring and exit without opening a window")
    parser.add_argument("--sessions-dir", type=Path, default=None,
                        help=f"where session documents live (default: {_default_storage_path()})")
    parser.add_argument("--debug", action="store_true", help="open the webview with devtools")
    args = parser.parse_args(argv)

    if args.check:
        return run_checks()

    check_contract_version()

    sessions_dir = str(args.sessions_dir) if args.sessions_dir else _default_storage_path()
    ensure_usable_sessions_dir(sessions_dir)
    if not os.path.exists(INDEX_HTML):
        raise SystemExit(
            f"No frontend found at {INDEX_HTML}.\n"
            f"Put the UI files in {os.path.join(BASE_DIR, 'web')} (index.html at its root) "
            f"and try again."
        )

    try:
        # Imported here rather than at module level so --check runs on a machine with no
        # pywebview installed and no display.
        import webview
    except ImportError as exc:
        raise SystemExit(
            f"pywebview is not installed ({exc}).\n"
            f"Install the pinned version:  python -m pip install -r requirements.txt"
        )

    api = Api(storage_path=sessions_dir)
    window = webview.create_window(
        WINDOW_TITLE,
        INDEX_HTML,
        js_api=api,
        frameless=True,
        easy_drag=False,  # we implement our own title-bar drag in JS
        resizable=True,
        width=380,
        height=680,
        min_size=(300, 420),
        background_color="#1b1330",
        on_top=False,
    )
    api.set_window(window)
    webview.start(debug=args.debug)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

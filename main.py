"""Keeper of Time — desktop entry point.

This file is the one place the two layers meet: it builds the tracking core and hands it to
pywebview as `js_api`. The core never imports anything from here, and the UI reaches the core
only through that object.

Run:      python main.py
Check:    python main.py --check      (no window, no pywebview — verifies the core wiring)
Build:    packaging/build.ps1         (Windows, produces dist/KeeperOfTime.exe)
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from datetime import datetime, timezone, timedelta

APP_NAME = "KeeperOfTime"          # technical identifier: data folder, process name
WINDOW_TITLE = "Keeper of Time"    # what a person sees
# The contract version this app was built against (contract 6.3: a mismatch is a build-time
# check, not a runtime surprise). Bump this together with the vendored core, never separately.
CONTRACT_VERSION_EXPECTED = "v1.4"

HERE = Path(__file__).resolve().parent
VENDORED_CORE = HERE / "src"
UI_INDEX = HERE / "web" / "index.html"

if str(VENDORED_CORE) not in sys.path:
    sys.path.insert(0, str(VENDORED_CORE))

from timetracker_core import CONTRACT_VERSION, TimeTrackerCore  # noqa: E402


# ---------------------------------------------------------------------------
# Where sessions live
# ---------------------------------------------------------------------------

def default_sessions_dir() -> Path:
    """Per-user data, never beside the executable.

    A one-file PyInstaller build unpacks to a temp directory and starts empty each run, so the
    storage path has to be somewhere that outlives the process.
    """
    override = os.environ.get("KEEPER_OF_TIME_DATA_DIR")
    if override:
        return Path(override).expanduser()
    local_appdata = os.environ.get("LOCALAPPDATA")          # Windows
    if local_appdata:
        return Path(local_appdata) / APP_NAME / "sessions"
    return Path.home() / ".local" / "share" / APP_NAME / "sessions"   # dev on other platforms


def ensure_usable_sessions_dir(directory: Path) -> None:
    """Create the directory and prove we can write to it.

    The core deliberately does not raise on an unusable path (it answers `internal_error` on the
    first command instead), so the check belongs here, where it can stop the app at startup with a
    message a person can act on.
    """
    try:
        directory.mkdir(parents=True, exist_ok=True)
        probe = directory / ".write-probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
    except OSError as exc:
        raise SystemExit(
            f"Cannot use the sessions directory:\n  {directory}\n  {exc}\n"
            f"Set KEEPER_OF_TIME_DATA_DIR to a writable folder and try again."
        )


# ---------------------------------------------------------------------------
# The version gate (contract 6.3)
# ---------------------------------------------------------------------------

def check_contract_version() -> None:
    if CONTRACT_VERSION != CONTRACT_VERSION_EXPECTED:
        raise SystemExit(
            f"Contract version mismatch: the app expects {CONTRACT_VERSION_EXPECTED}, "
            f"the vendored core says {CONTRACT_VERSION}.\n"
            f"The core and the UI were built against different contracts - update whichever is "
            f"behind before running."
        )


# ---------------------------------------------------------------------------
# --check: verify the wiring without a window
# ---------------------------------------------------------------------------

class _FixedClock:
    """Deterministic clock so --check prints the same numbers every time."""

    def __init__(self, start: datetime) -> None:
        self._now = start

    def __call__(self) -> datetime:
        return self._now

    def advance(self, **kwargs) -> None:
        self._now = self._now + timedelta(**kwargs)


def run_checks() -> int:
    """Exercise the core end to end in a throwaway directory. Never opens a window."""
    print(f"{WINDOW_TITLE}: contract {CONTRACT_VERSION} (expected {CONTRACT_VERSION_EXPECTED})")
    check_contract_version()

    workdir = Path(tempfile.mkdtemp(prefix="keeper-of-time-check-"))
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
        if not UI_INDEX.exists():
            print(f"note: no UI yet at {UI_INDEX} (drop your frontend folder in to run the app)")
        else:
            print(f"ui: {UI_INDEX} present")
        print(f"sessions dir would be: {default_sessions_dir()}")
        print("OK")
        return 0
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=f"{WINDOW_TITLE} - desktop time tracker")
    parser.add_argument("--check", action="store_true",
                        help="verify the core wiring and exit without opening a window")
    parser.add_argument("--sessions-dir", type=Path, default=None,
                        help=f"where session documents live (default: {default_sessions_dir()})")
    parser.add_argument("--debug", action="store_true", help="open the webview with devtools")
    args = parser.parse_args(argv)

    if args.check:
        return run_checks()

    check_contract_version()

    sessions_dir = args.sessions_dir or default_sessions_dir()
    ensure_usable_sessions_dir(sessions_dir)
    core = TimeTrackerCore(sessions_dir)

    if not UI_INDEX.exists():
        raise SystemExit(
            f"No frontend found at {UI_INDEX}.\n"
            f"Put the UI files in {HERE / 'web'} (index.html at its root) and try again."
        )

    try:
        import webview
    except ImportError as exc:
        raise SystemExit(
            f"pywebview is not installed ({exc}).\n"
            f"Install the pinned version:  python -m pip install -r requirements.txt"
        )

    window = webview.create_window(WINDOW_TITLE, str(UI_INDEX), js_api=core)
    _ = window
    webview.start(debug=args.debug)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

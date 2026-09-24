"""The boundary between the app and the vendored core.

These tests are what stop the merge from quietly undoing the split: the core must stay
stdlib-only, must never import the UI, and the app's expected contract version must match the
core's, or the swap gate is meaningless.
"""

import ast
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CORE = os.path.join(ROOT, "src", "timetracker_core")
sys.path.insert(0, os.path.join(ROOT, "src"))

import main as app_main  # noqa: E402
from timetracker_core import CONTRACT_VERSION  # noqa: E402

ALLOWED_THIRD_PARTY = set()  # deliberately empty: the core may import nothing outside the stdlib


def _imported_top_level_modules(path):
    with open(path, encoding="utf-8") as handle:
        tree = ast.parse(handle.read(), filename=path)
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.level:            # relative import inside the package
                continue
            if node.module:
                names.add(node.module.split(".")[0])
    return names


class TestCoreStaysIsolated(unittest.TestCase):
    def test_core_imports_only_the_standard_library(self):
        offenders = {}
        for name in sorted(os.listdir(CORE)):
            if not name.endswith(".py"):
                continue
            imported = _imported_top_level_modules(os.path.join(CORE, name))
            outside = {m for m in imported if m not in sys.stdlib_module_names}
            outside -= ALLOWED_THIRD_PARTY
            if outside:
                offenders[name] = sorted(outside)
        assert offenders == {}, f"core imports non-stdlib modules: {offenders}"

    def test_core_never_imports_the_ui_or_its_dependencies(self):
        forbidden = {"webview", "main", "pywebview", "ui"}
        for name in sorted(os.listdir(CORE)):
            if not name.endswith(".py"):
                continue
            clash = _imported_top_level_modules(os.path.join(CORE, name)) & forbidden
            assert not clash, f"{name} imports {sorted(clash)} - the core must not know about the UI"


class TestVersionGate(unittest.TestCase):
    def test_app_expects_the_contract_the_core_declares(self):
        assert app_main.CONTRACT_VERSION_EXPECTED == CONTRACT_VERSION, (
            f"app expects {app_main.CONTRACT_VERSION_EXPECTED}, core declares {CONTRACT_VERSION}"
        )

    def test_core_version_constant_is_importable_from_the_app_path(self):
        assert CONTRACT_VERSION.startswith("v"), CONTRACT_VERSION


class TestNaming(unittest.TestCase):
    """The app is Keeper of Time; the import path and the class are not renamed with it."""

    def test_display_name_and_technical_identifier(self):
        assert app_main.WINDOW_TITLE == "Keeper of Time", app_main.WINDOW_TITLE
        assert app_main.APP_NAME == "KeeperOfTime", app_main.APP_NAME

    def test_package_and_class_names_are_unchanged_by_the_rename(self):
        from timetracker_core import TimeTrackerCore
        assert TimeTrackerCore.__name__ == "TimeTrackerCore"
        assert TimeTrackerCore.__module__.startswith("timetracker_core")


class TestAppWiring(unittest.TestCase):
    def test_sessions_dir_is_not_beside_the_executable(self):
        """A one-file build unpacks to a temp dir, so storage must not live next to the exe."""
        candidate = app_main.default_sessions_dir()
        assert str(candidate).startswith(str(ROOT)) is False, candidate

    def test_check_mode_reports_ok(self):
        assert app_main.run_checks() == 0


if __name__ == "__main__":
    unittest.main()

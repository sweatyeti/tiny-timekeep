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
CORE = os.path.join(ROOT, "timetracker_core")
sys.path.insert(0, ROOT)

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
        forbidden = {"webview", "main", "pywebview", "ui", "web"}
        for name in sorted(os.listdir(CORE)):
            if not name.endswith(".py"):
                continue
            clash = _imported_top_level_modules(os.path.join(CORE, name)) & forbidden
            assert not clash, f"{name} imports {sorted(clash)} - the core must not know about the UI"


class TestVersionGate(unittest.TestCase):
    def test_app_core_and_spec_are_pinned_to_v15(self):
        self.assertEqual(CONTRACT_VERSION, "v1.5")
        assert app_main.EXPECTED_CONTRACT_VERSION == CONTRACT_VERSION, (
            f"app expects {app_main.EXPECTED_CONTRACT_VERSION}, core declares {CONTRACT_VERSION}"
        )
        with open(os.path.join(ROOT, "specs", "core-logic-contract.md"), encoding="utf-8") as handle:
            self.assertIn("version: v1.5", handle.read())


class TestAppWiring(unittest.TestCase):
    def test_sessions_dir_is_not_beside_the_executable(self):
        """A one-file build unpacks to a temp dir, so storage must not live next to the exe."""
        candidate = app_main._default_storage_path()
        assert str(candidate).startswith(str(ROOT)) is False, candidate

if __name__ == "__main__":
    unittest.main()

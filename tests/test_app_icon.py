import os
import struct
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

import main


ROOT = Path(__file__).resolve().parents[1]
ICON = ROOT / "assets" / "tinyTimeKeep.ico"


class AppIconTests(unittest.TestCase):
    def test_ico_has_required_native_sizes_and_is_used_for_both_packaging_paths(self):
        data = ICON.read_bytes()
        reserved, image_type, count = struct.unpack_from("<HHH", data)
        self.assertEqual((reserved, image_type), (0, 1))
        self.assertGreaterEqual(count, 4)

        sizes = set()
        for index in range(count):
            width, height, _, _, _, bit_count, byte_count, offset = struct.unpack_from(
                "<BBBBHHII", data, 6 + index * 16
            )
            width = width or 256
            height = height or 256
            self.assertEqual(bit_count, 32)
            self.assertEqual(data[offset:offset + 8], b"\x89PNG\r\n\x1a\n")
            png_width, png_height = struct.unpack_from(">II", data, offset + 16)
            self.assertEqual((png_width, png_height), (width, height))
            self.assertLessEqual(offset + byte_count, len(data))
            sizes.add((width, height))

        self.assertTrue({(16, 16), (32, 32), (48, 48), (256, 256)}.issubset(sizes))

        spec = (ROOT / "packaging" / "tinyTimeKeep.spec").read_text(encoding="utf-8")
        self.assertIn('(str(ICON), "assets")', spec)
        self.assertIn("icon=str(ICON)", spec)

        # --- Regression guard: consistent future executable filename ---
        self.assertEqual(
            spec.count('name="tinyTimeKeep"'),
            1,
            msg="spec: PyInstaller EXE name stem must appear exactly once as 'tinyTimeKeep'",
        )

        build_script = (ROOT / "packaging" / "build.ps1").read_text(encoding="utf-8")
        self.assertEqual(
            build_script.count("dist\\tinyTimeKeep.exe"),
            3,
            msg="build.ps1: must reference 'dist\\tinyTimeKeep.exe' exactly 3 times (Test-Path, error, Built)",
        )

        workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
        self.assertIn("packaging/tinyTimeKeep.spec", workflow)
        self.assertEqual(
            workflow.count("dist/tinyTimeKeep.exe"),
            5,
            msg="release.yml: must reference 'dist/tinyTimeKeep.exe' exactly 5 times (check, error, confirmation, upload, publish)",
        )
        self.assertEqual(
            workflow.count("          name: tinyTimeKeep-exe"),
            2,
            msg="release.yml: both artifact label lines must be exactly '          name: tinyTimeKeep-exe'",
        )
        artifact_name_lines = [ln for ln in workflow.splitlines() if ln.startswith("          name: ")]
        self.assertEqual(
            len(artifact_name_lines),
            2,
            msg="release.yml: exactly two indented artifact 'name:' lines expected (upload and download)",
        )

        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertEqual(
            readme.count("tinyTimeKeep.exe"),
            1,
            msg="README.md: 'tinyTimeKeep.exe' must appear exactly once",
        )

        self.assertIn(
            "section. As of the full v1.0 release, the name is `tinyTimeKeep.exe`.",
            readme,
            msg="README.md: must state the current executable name for v1.0",
        )

        # Old executable name must be absent from spec, build script, and release workflow
        self.assertNotIn(
            "KeeperOfTime.exe",
            spec,
            msg="spec: must not reference old 'KeeperOfTime.exe'",
        )
        self.assertNotIn(
            "KeeperOfTime.exe",
            build_script,
            msg="build.ps1: must not reference old 'KeeperOfTime.exe'",
        )
        self.assertNotIn(
            "KeeperOfTime.exe",
            workflow,
            msg="release.yml: must not reference old 'KeeperOfTime.exe'",
        )

    def test_html_title_and_titlebar_use_tinytimekeep_name(self):
        html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")

        self.assertIn("<title>tinyTimeKeep</title>", html)
        self.assertIn('id="titlebar-label">✦ tinyTimeKeep</span>', html)

    def test_main_passes_bundled_ico_to_pywebview(self):
        calls = {}
        fake_webview = types.ModuleType("webview")

        def create_window(*args, **kwargs):
            calls["create_window"] = (args, kwargs)
            return object()

        def start(**kwargs):
            calls["start"] = kwargs

        fake_webview.create_window = create_window
        fake_webview.start = start

        with tempfile.TemporaryDirectory() as directory:
            preferences = os.path.join(directory, "preferences.json")
            with mock.patch.dict(sys.modules, {"webview": fake_webview}), mock.patch.object(
                main, "_default_preferences_path", return_value=preferences
            ):
                result = main.main(["--sessions-dir", directory])

        self.assertEqual(result, 0)
        self.assertEqual(calls["create_window"][0][0], "tinyTimeKeep")
        self.assertTrue(calls["create_window"][1]["frameless"])
        self.assertEqual(calls["start"]["icon"], str(ICON))
        self.assertTrue(ICON.is_file())


if __name__ == "__main__":
    unittest.main()

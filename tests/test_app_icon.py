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
ICON = ROOT / "assets" / "keeper-of-time.ico"


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

        spec = (ROOT / "packaging" / "keeper-of-time.spec").read_text(encoding="utf-8")
        self.assertIn('(str(ICON), "assets")', spec)
        self.assertIn("icon=str(ICON)", spec)

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
        self.assertTrue(calls["create_window"][1]["frameless"])
        self.assertEqual(calls["start"]["icon"], str(ICON))
        self.assertTrue(ICON.is_file())


if __name__ == "__main__":
    unittest.main()

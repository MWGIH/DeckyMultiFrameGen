import hashlib
import lzma
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import support  # noqa: F401

import main
from multifg import fsr4lite


def _recipe(payload: bytes, before: bytes) -> tuple[bytes, dict]:
    """A packed stream made like AMD's installer (BCJ x86 + LZMA2) holding payload after some other bytes."""
    packed = lzma.compress(before + payload, format=lzma.FORMAT_RAW, filters=[
        {"id": lzma.FILTER_X86}, {"id": lzma.FILTER_LZMA2, "dict_size": 2 ** 20}])
    return packed, {"unpacked_offset": 0, "dict_size": 2 ** 20, "dll_offset": len(before), "dll_size": len(payload),
                    "sha256": hashlib.sha256(payload).hexdigest()}


class DecodeTests(unittest.TestCase):
    def test_keeps_only_the_checked_dll(self):
        payload = b"MZ" + bytes(range(256)) * 400
        packed, recipe = _recipe(payload, b"other file" * 1000)
        with tempfile.TemporaryDirectory() as d:
            src, dest = Path(d) / "packed", Path(d) / "amdxcffx64.dll"
            src.write_bytes(packed + b"trailing")
            fsr4lite.decode_amd_dll(src, dest, recipe)
            self.assertEqual(dest.read_bytes(), payload)

    def test_wrong_checksum_leaves_nothing(self):
        packed, recipe = _recipe(b"MZ" * 5000, b"x" * 100)
        recipe["sha256"] = "0" * 64
        with tempfile.TemporaryDirectory() as d:
            src, dest = Path(d) / "packed", Path(d) / "amdxcffx64.dll"
            src.write_bytes(packed)
            with self.assertRaises(fsr4lite.LiteError):
                fsr4lite.decode_amd_dll(src, dest, recipe)
            self.assertEqual(sorted(p.name for p in Path(d).iterdir()), ["packed"])

    def test_fsr4_injector_copy_is_reused_without_downloading(self):
        with tempfile.TemporaryDirectory() as d:
            reuse, dest = Path(d) / "theirs.dll", Path(d) / "cache" / "amdxcffx64.dll"
            reuse.write_bytes(b"amd")
            with mock.patch.object(fsr4lite, "amd_dll_valid", side_effect=lambda p: p.is_file()), \
                    mock.patch.object(fsr4lite, "_curl", side_effect=AssertionError("downloaded")):
                self.assertEqual(fsr4lite.fetch_amd_dll(dest, reuse), "fsr4injector")
            self.assertEqual(dest.read_bytes(), b"amd")

    def test_amd_recipe_matches_fsr4_injectors(self):
        fixtures = Path(__file__).parent / "fixtures" / "fsr4injector" / "fsr4_dll.py"
        if not fixtures.is_file():
            self.skipTest("no FSR4 Injector fixture")
        text = fixtures.read_text()
        for key in ("packed_offset", "packed_size", "unpacked_offset", "dll_offset", "dll_size"):
            if f'"{key}": {fsr4lite.AMD_DLL[key]}' not in text:
                self.skipTest(f"fixture is another FSR4 Injector version ({key})")
        self.assertIn(fsr4lite.AMD_DLL["sha256"], text)


class GameSettingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.settings = mock.patch.object(main, "SETTINGS", main.Settings(Path(self.tmp.name) / "s.json"))
        self.settings.start()

    def tearDown(self):
        self.settings.stop()
        self.tmp.cleanup()

    def test_default_is_the_deck_build_and_lite_is_picked_per_game(self):
        import asyncio
        p = main.Plugin()
        self.assertEqual(main._opti_variant("10"), main.FSR4_VARIANT)
        self.assertEqual(asyncio.run(p.optiscaler_fsr4_files("10", "lite")), "lite")
        self.assertEqual(main._opti_variant("10"), fsr4lite.VARIANT)
        self.assertFalse(asyncio.run(p.optiscaler_plain("10")))

    def test_phantom_blade_zero_still_defaults_to_plain(self):
        self.assertEqual(main._opti_fsr4("4115450"), "plain")

    def test_old_plain_setting_is_kept(self):
        main.SETTINGS.set_game_value("11", "opti_plain", True)
        self.assertEqual(main._opti_fsr4("11"), "plain")


if __name__ == "__main__":
    unittest.main()

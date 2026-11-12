import asyncio
import hashlib
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import support  # noqa: F401

import main
from multifg import fsr4overrides
from multifg.optiscaler import FSR4_VARIANTS, OptiScaler


class OverridesCatalogTests(unittest.TestCase):
    def test_every_ui_key_maps_to_a_registered_variant(self):
        for key, variant_id in main.OPTI_FSR4_FILES.items():
            self.assertIn(variant_id, FSR4_VARIANTS, key)

    def test_cyboman_options_are_on_demand(self):
        for files_key, info in fsr4overrides.BY_FILES.items():
            self.assertTrue(FSR4_VARIANTS[info["id"]].get("prepared_on_demand"), files_key)

    def test_downloads_the_small_7z(self):
        self.assertTrue(fsr4overrides.RELEASE["name"].endswith(".7z"))
        self.assertTrue(fsr4overrides.RELEASE["url"].endswith(fsr4overrides.RELEASE["name"]))


@unittest.skipUnless(shutil.which("7z"), "needs 7z")
class OverridesExtractTests(unittest.TestCase):
    def test_extract_upscaler_checks_size_and_hash(self):
        payload = b"MZ" + b"\x00" * 1000
        digest = hashlib.sha256(payload).hexdigest()
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "src"
            (src / "lossy").mkdir(parents=True)
            (src / "lossy" / "amd_fidelityfx_upscaler_dx12.dll").write_bytes(payload)
            (src / "exact").mkdir()
            (src / "exact" / "amd_fidelityfx_upscaler_dx12.dll").write_bytes(b"other")
            archive = Path(d) / "a.7z"
            subprocess.run(["7z", "a", str(archive), "exact", "lossy"], cwd=src, check=True, capture_output=True)
            dest = Path(d) / "out.dll"
            fsr4overrides.extract_upscaler(archive, "lossy", dest, digest, len(payload))
            self.assertEqual(dest.read_bytes(), payload)
            with self.assertRaises(fsr4overrides.OverridesError):
                fsr4overrides.extract_upscaler(archive, "lossy", dest, "0" * 64, len(payload))


class OverridesPrepareTests(unittest.TestCase):
    def test_prepare_from_copies_base_and_swaps_upscaler(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            fgmod, cache, base = root / "fgmod", root / "cache", root / "base"
            base.mkdir()
            (base / "OptiScaler.dll").write_bytes(b"opti")
            (base / "amdxcffx64.dll").write_bytes(b"amd")
            (base / "amdxc64.dll").write_bytes(b"xc")
            (base / "renames").mkdir()
            (base / "renames" / "dxgi.dll").write_bytes(b"opti")
            upscaler = b"MZ-CYBOMAN-LOSSY"
            info = fsr4overrides.BY_FILES["lossy"]
            dll = cache / "lossy" / "amd_fidelityfx_upscaler_dx12.dll"
            dll.parent.mkdir(parents=True)
            dll.write_bytes(upscaler)
            with mock.patch.object(fsr4overrides, "_valid", return_value=True), mock.patch.object(
                fsr4overrides, "dll_path", return_value=dll
            ):
                folder = fsr4overrides.prepare_from(
                    fgmod, cache, "lossy", base_dir=base, make_renames=lambda *_: False
                )
            self.assertEqual((folder / "amd_fidelityfx_upscaler_dx12.dll").read_bytes(), upscaler)
            self.assertEqual((folder / "OptiScaler.dll").read_bytes(), b"opti")
            self.assertEqual((folder / "amdxc64.dll").read_bytes(), b"xc")
            self.assertTrue((folder / "renames" / "dxgi.dll").is_file())
            self.assertEqual(folder, fgmod / info["dir_name"])

    def test_prepared_is_false_when_only_the_upscaler_is_present(self):
        with tempfile.TemporaryDirectory() as d:
            fgmod = Path(d)
            info = fsr4overrides.BY_FILES["lossy"]
            folder = fgmod / info["dir_name"]
            folder.mkdir(parents=True)
            upscaler = folder / "amd_fidelityfx_upscaler_dx12.dll"
            upscaler.write_bytes(b"x" * info["size"])
            with mock.patch.object(fsr4overrides, "sha256_file", return_value=info["sha256"]):
                self.assertFalse(fsr4overrides.prepared(fgmod, info["id"]))

    def test_prepare_from_fails_when_base_injector_is_missing(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            fgmod, cache, base = root / "fgmod", root / "cache", root / "base"
            base.mkdir()
            (base / "amdxcffx64.dll").write_bytes(b"amd")
            with self.assertRaises(fsr4overrides.OverridesError):
                fsr4overrides.prepare_from(
                    fgmod, cache, "lossy", base_dir=base, make_renames=lambda *_: True
                )


class GameSettingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.settings = mock.patch.object(main, "SETTINGS", main.Settings(Path(self.tmp.name) / "s.json"))
        self.settings.start()

    def tearDown(self):
        self.settings.stop()
        self.tmp.cleanup()

    def test_lossy_and_lite_lossy_can_be_selected(self):
        p = main.Plugin()
        with mock.patch.object(main, "_lite_unfit", return_value=None):
            self.assertEqual(asyncio.run(p.optiscaler_fsr4_files("10", "lossy"))["files"], "lossy")
            self.assertEqual(main._opti_variant("10"), fsr4overrides.BY_FILES["lossy"]["id"])
            self.assertEqual(asyncio.run(p.optiscaler_fsr4_files("10", "lite-lossy"))["files"], "lite-lossy")
            self.assertEqual(main._opti_variant("10"), fsr4overrides.BY_FILES["lite-lossy"]["id"])

    def test_lite_like_options_hidden_when_unfit(self):
        p = main.Plugin()
        with mock.patch.object(main, "_lite_unfit", return_value="needs DirectX 12"):
            state = asyncio.run(p.optiscaler_fsr4_files("10"))
        for key in main.OPTI_FSR4_LITE_LIKE:
            self.assertNotIn(key, state["options"])
        self.assertIn("lossy", state["options"])
        self.assertIn("deck", state["options"])


if __name__ == "__main__":
    unittest.main()

import asyncio
import hashlib
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

import support  # noqa: F401

import main
from multifg import fsr4decky, fsr4lite, fsr4overrides
from multifg.optiscaler import FSR4_VARIANTS, OptiScaler


class OverridesCatalogTests(unittest.TestCase):
    def test_every_ui_key_maps_to_a_registered_variant(self):
        for key, variant_id in main.OPTI_FSR4_FILES.items():
            self.assertIn(variant_id, FSR4_VARIANTS, key)

    def test_cyboman_and_decky_are_on_demand(self):
        for files_key, info in fsr4overrides.BY_FILES.items():
            self.assertTrue(FSR4_VARIANTS[info["id"]].get("prepared_on_demand"), files_key)
        self.assertTrue(FSR4_VARIANTS[fsr4decky.VARIANT].get("prepared_on_demand"))
        self.assertEqual(FSR4_VARIANTS[fsr4decky.VARIANT]["label"], "Decky (Steamdeck Optimised)")

    def test_decky_sidecars_are_in_variant_extra_cleanup_list(self):
        from multifg.optiscaler import VARIANT_EXTRA_FILENAMES
        for name in ("amd_fidelityfx_vk.dll", "fsr4_shaders.bin", "fsr4_shaders_dot2.bin"):
            self.assertIn(name, VARIANT_EXTRA_FILENAMES)


class OverridesExtractTests(unittest.TestCase):
    def test_extract_upscaler_checks_size_and_hash(self):
        payload = b"MZ" + b"\x00" * 1000
        digest = hashlib.sha256(payload).hexdigest()
        with tempfile.TemporaryDirectory() as d:
            archive = Path(d) / "a.zip"
            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("exact/amd_fidelityfx_upscaler_dx12.dll", payload)
            dest = Path(d) / "out.dll"
            fsr4overrides.extract_upscaler(archive, "exact", dest, digest, len(payload))
            self.assertEqual(dest.read_bytes(), payload)
            with self.assertRaises(fsr4overrides.OverridesError):
                fsr4overrides.extract_upscaler(archive, "exact", dest, "0" * 64, len(payload))


class OverridesPrepareTests(unittest.TestCase):
    def test_prepare_from_copies_base_and_swaps_upscaler(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            fgmod, cache, base = root / "fgmod", root / "cache", root / "base"
            base.mkdir()
            (base / "OptiScaler.dll").write_bytes(b"opti")
            (base / "amdxcffx64.dll").write_bytes(b"amd")
            (base / "renames").mkdir()
            (base / "renames" / "dxgi.dll").write_bytes(b"opti")
            upscaler = b"MZ-CYBOMAN-EXACT"
            info = fsr4overrides.BY_FILES["exact"]
            dll = cache / "exact" / "amd_fidelityfx_upscaler_dx12.dll"
            dll.parent.mkdir(parents=True)
            dll.write_bytes(upscaler)
            with mock.patch.object(fsr4overrides, "_valid", return_value=True), mock.patch.object(
                fsr4overrides, "dll_path", return_value=dll
            ):
                folder = fsr4overrides.prepare_from(
                    fgmod, cache, "exact", base_dir=base, make_renames=lambda *_: False
                )
            self.assertEqual((folder / "amd_fidelityfx_upscaler_dx12.dll").read_bytes(), upscaler)
            self.assertEqual((folder / "OptiScaler.dll").read_bytes(), b"opti")
            self.assertTrue((folder / "renames" / "dxgi.dll").is_file())
            self.assertEqual(folder, fgmod / info["dir_name"])


class GameSettingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.settings = mock.patch.object(main, "SETTINGS", main.Settings(Path(self.tmp.name) / "s.json"))
        self.settings.start()

    def tearDown(self):
        self.settings.stop()
        self.tmp.cleanup()

    def test_lossy_and_decky_can_be_selected(self):
        p = main.Plugin()
        with mock.patch.object(main, "_lite_unfit", return_value=None):
            self.assertEqual(asyncio.run(p.optiscaler_fsr4_files("10", "lossy"))["files"], "lossy")
            self.assertEqual(main._opti_variant("10"), fsr4overrides.BY_FILES["lossy"]["id"])
            self.assertEqual(asyncio.run(p.optiscaler_fsr4_files("10", "decky"))["files"], "decky")
            self.assertEqual(main._opti_variant("10"), fsr4decky.VARIANT)

    def test_lite_like_options_hidden_when_unfit(self):
        p = main.Plugin()
        with mock.patch.object(main, "_lite_unfit", return_value="needs DirectX 12"):
            state = asyncio.run(p.optiscaler_fsr4_files("10"))
        for key in main.OPTI_FSR4_LITE_LIKE:
            self.assertNotIn(key, state["options"])
        self.assertIn("exact", state["options"])
        self.assertIn("lossy", state["options"])
        self.assertIn("deck", state["options"])


class DetectTests(unittest.TestCase):
    def test_prefers_decky_over_lite_when_shader_packs_present(self):
        opti = OptiScaler()
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d)
            # shared stock upscaler SHA used by both lite and decky entries
            upscaler_sha = FSR4_VARIANTS[fsr4lite.VARIANT]["sha256"]
            (folder / "amdxcffx64.dll").write_bytes(b"x")
            (folder / "amd_fidelityfx_vk.dll").write_bytes(b"vk")
            (folder / "fsr4_shaders.bin").write_bytes(b"s1")
            (folder / "fsr4_shaders_dot2.bin").write_bytes(b"s2")

            def fake_sha(path: Path) -> str:
                name = path.name
                if name == "amdxcffx64.dll":
                    return fsr4lite.AMD_DLL["sha256"]
                if name == "amd_fidelityfx_vk.dll":
                    return fsr4decky.ASSETS["amd_fidelityfx_upscaler_vk.dll"]["sha256"]
                if name == "fsr4_shaders.bin":
                    return fsr4decky.ASSETS["fsr4_shaders.bin"]["sha256"]
                if name == "fsr4_shaders_dot2.bin":
                    return fsr4decky.ASSETS["fsr4_shaders_dot2.bin"]["sha256"]
                return "0" * 64

            with mock.patch.object(opti, "_file_sha256", side_effect=fake_sha):
                self.assertEqual(opti._detect_fsr4_variant(folder, upscaler_sha), fsr4decky.VARIANT)


class UnpatchCleanupTests(unittest.TestCase):
    def test_unpatch_removes_decky_shader_packs_and_restores_game_vk_dll(self):
        opti = OptiScaler()
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d)
            (folder / "dxgi.dll").write_bytes(b"opti")
            (folder / "amd_fidelityfx_upscaler_dx12.dll").write_bytes(b"upscaler")
            (folder / "amd_fidelityfx_vk.dll").write_bytes(b"decky-vk")
            (folder / "amd_fidelityfx_vk.dll.b").write_bytes(b"game-vk")
            (folder / "fsr4_shaders.bin").write_bytes(b"s1")
            (folder / "fsr4_shaders_dot2.bin").write_bytes(b"s2")
            (folder / "OptiScaler.ini").write_text("[Upscalers]\n")
            r = opti._manual_unpatch_directory_impl(folder)
            self.assertEqual(r["status"], "success", r)
            self.assertFalse((folder / "fsr4_shaders.bin").exists())
            self.assertFalse((folder / "fsr4_shaders_dot2.bin").exists())
            self.assertFalse((folder / "dxgi.dll").exists())
            self.assertEqual((folder / "amd_fidelityfx_vk.dll").read_bytes(), b"game-vk")
            self.assertFalse((folder / "amd_fidelityfx_vk.dll.b").exists())


if __name__ == "__main__":
    unittest.main()

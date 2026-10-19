import asyncio
import os
import shutil
import unittest
from pathlib import Path

import support

from multifg import helix_opti

REAL_RELEASE = os.environ.get("HELIXSR_RELEASE_DIR")

INI = "[Upscalers]\r\nDx12Upscaler=auto\r\n\r\n[FSR]\r\nFsr4Update=true\r\n\r\n[Libraries]\r\nFfxDx12Path=auto\r\nFfxDx12SRPath=auto\r\n"


class IniTests(unittest.TestCase):
    def test_set_and_get_inside_the_section(self):
        text = "[A]\nKey=1\n[B]\nKey=2\n"
        self.assertEqual(helix_opti.ini_get(text, "B", "Key"), "2")
        self.assertEqual(helix_opti.ini_set(text, "B", "Key", "x"), "[A]\nKey=1\n[B]\nKey=x\n")
        self.assertEqual(helix_opti.ini_set(text, "A", "New", "y"), "[A]\nNew=y\nKey=1\n[B]\nKey=2\n")
        self.assertEqual(helix_opti.ini_set(text, "C", "K", "z"), "[A]\nKey=1\n[B]\nKey=2\n\n[C]\nK=z\n")


class ModTests(unittest.TestCase):
    def setUp(self):
        self.home = support.reset_home()
        self.rel = self.home / "rel"
        self.rel.mkdir()
        (self.rel / helix_opti.DLL).write_bytes(b"MZhelix" + b"HXSRNET1" + b"\0" * 24)
        self.game = self.home / "game"
        self.game.mkdir()
        (self.game / "OptiScaler.ini").write_bytes(INI.encode())

    def test_round_trip_puts_optiscaler_ini_back(self):
        self.assertFalse(helix_opti.status(self.game)["installed"])
        r = helix_opti.install(self.rel, self.game, "v1.9.3")
        self.assertTrue(r["ok"], r)
        st = helix_opti.status(self.game)
        self.assertEqual((st["installed"], st["ini_ok"], st["helixsr"]), (True, True, "v1.9.3"))
        text = (self.game / "OptiScaler.ini").read_bytes().decode()
        mod = self.game / helix_opti.MOD_DIR
        self.assertIn("FfxDx12SRPath=" + helix_opti.win_path(mod / helix_opti.OWN_SR) + "\r\n", text)
        self.assertIn("Fsr4Update=false\r\n", text)
        self.assertIn("Dx12Upscaler=fsr31\r\n", text)
        self.assertEqual((mod / helix_opti.OWN).read_bytes(), (self.rel / helix_opti.DLL).read_bytes())
        self.assertTrue(helix_opti.install(self.rel, self.game, "v1.9.4")["ok"])   # update keeps the first values
        self.assertTrue(helix_opti.uninstall(self.game)["removed"])
        self.assertEqual((self.game / "OptiScaler.ini").read_bytes().decode(), INI)
        self.assertFalse(mod.exists())

    def test_helixsr_2_layout_uses_the_dll_built_into_helixsr_fsrfg(self):
        # 2.0's setup builds the DLL into HelixSR-fsrfg; the one in the release folder has no network
        (self.rel / helix_opti.DLL).write_bytes(b"MZunbuilt" + b"\0" * 40)
        fsrfg = self.rel / "HelixSR-fsrfg"
        fsrfg.mkdir()
        built = b"MZhelix2" + b"HXSRNET1" + b"\0" * 24
        (fsrfg / helix_opti.DLL).write_bytes(built)
        self.assertEqual(helix_opti.built_dll(self.rel), fsrfg / helix_opti.DLL)
        self.assertTrue(helix_opti.install(self.rel, self.game, "v2.0.0")["ok"])
        self.assertEqual((self.game / helix_opti.MOD_DIR / helix_opti.OWN).read_bytes(), built)

    def test_no_built_dll_before_the_setup(self):
        (self.rel / helix_opti.DLL).write_bytes(b"MZunbuilt" + b"\0" * 40)
        self.assertIsNone(helix_opti.built_dll(self.rel))
        self.assertFalse(helix_opti.install(self.rel, self.game, "v2.0.0")["ok"])

    def test_needs_optiscaler_in_the_game(self):
        (self.game / "OptiScaler.ini").unlink()
        self.assertFalse(helix_opti.install(self.rel, self.game, "v1.9.3")["ok"])


@unittest.skipUnless(REAL_RELEASE and shutil.which("7z") and os.environ.get("MULTIFG_NETWORK_TESTS") == "1",
                     "needs HELIXSR_RELEASE_DIR, 7z and MULTIFG_NETWORK_TESTS=1 (OptiScaler's download)")
class InOptiScalerEndToEnd(unittest.TestCase):
    def test_choice_patches_optiscaler_with_helixsr_and_switching_away_removes_it(self):
        import main
        from test_optiscaler import install_and_wait
        home = support.reset_home()
        rel = home / "HelixSR" / "v1.9.3"
        shutil.copytree(REAL_RELEASE, rel)
        with open(rel / "amd_fidelityfx_dx12.dll", "ab") as f:
            f.write(b"HXSRNET1" + b"\0" * 24)
        steam = home / ".local" / "share" / "Steam"
        support.add_game(steam, "123", "DLSS Game", "DLSS Game")
        game = steam / "steamapps" / "common" / "DLSS Game"
        (game / "Game.exe").write_bytes(b"MZ" + b"\0" * 2048)
        (game / "nvngx_dlss.dll").write_bytes(b"x")

        async def flow(p):
            self.assertEqual((await install_and_wait(p))["state"], "done")
            r = await p.set_game_backend("123", "optiscaler+helixsr", "-dx12")
            self.assertTrue(r["ok"], r)
            self.assertIsNone(r["helix_in_opti"])   # not patched yet
            r = await p.optiscaler_patch_game("123", "dxgi.dll", "-dx12")
            self.assertEqual(r["status"], "success", r)
            self.assertTrue(r["helix_in_opti"]["ok"], r)
            st = await p.helixsr_opti_status("123")
            self.assertEqual((st["installed"], st["ini_ok"]), (True, True), st)
            self.assertFalse((await p.helixsr_game_status("123"))["installed"])   # HelixSR's setup doesn't see it
            r = await p.set_game_backend("123", "optiscaler", r["launch_options"])
            self.assertEqual(r["removed"], ["HelixSR (in OptiScaler)"])
            self.assertFalse((await p.helixsr_opti_status("123"))["installed"])
            r = await p.set_game_backend("123", "optiscaler+helixsr", None)
            r = await p.set_game_backend("123", "optiscaler+helixsr", "x")   # same choice again: nothing to clear
            st = await p.helixsr_opti_status("123")
            self.assertTrue(st["installed"], st)
            r = await p.set_game_backend("123", "none", "WINEDLLOVERRIDES=dxgi=n,b SteamDeck=0 %command%")
            self.assertEqual(r["removed"], ["HelixSR (in OptiScaler)", "OptiScaler"])
            self.assertEqual(sorted(x.name for x in game.iterdir()), ["Game.exe", "nvngx_dlss.dll"])
        asyncio.run(flow(main.Plugin()))


if __name__ == "__main__":
    unittest.main()

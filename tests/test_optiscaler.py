import asyncio
import os
import shutil
import unittest

import support  # noqa: F401

import main

# Downloads OptiScaler and its FSR4 files from upstream (a few hundred MB) and needs 7z: opt-in.
NETWORK = os.environ.get("MULTIFG_NETWORK_TESTS") == "1" and shutil.which("7z")


def run(coro):
    return asyncio.run(coro)


@unittest.skipUnless(NETWORK, "set MULTIFG_NETWORK_TESTS=1 (and have 7z) to run the OptiScaler install end to end")
class OptiScalerEndToEnd(unittest.TestCase):
    def test_install_patch_unpatch(self):
        home = support.reset_home()
        steam = home / ".local" / "share" / "Steam"
        support.add_game(steam, "1091500", "Cyberpunk 2077", "Cyberpunk 2077")
        exe_dir = steam / "steamapps" / "common" / "Cyberpunk 2077" / "bin" / "x64"
        exe_dir.mkdir(parents=True)
        (exe_dir / "Cyberpunk2077.exe").write_bytes(b"MZ" + b"\0" * 2048)
        p = main.Plugin()

        self.assertEqual(run(p.optiscaler_install(""))["status"], "success")
        self.assertTrue(run(p.optiscaler_status())["exists"])
        r = run(p.optiscaler_patch_game("1091500", "dxgi.dll", "-skipStartScreen", ""))
        self.assertEqual(r["status"], "success", r)
        self.assertEqual(r["launch_options"], "WINEDLLOVERRIDES=dxgi=n,b SteamDeck=0 %command%")
        self.assertTrue((exe_dir / "dxgi.dll").exists())
        self.assertTrue(run(p.optiscaler_game_status("1091500"))["patched"])
        r = run(p.optiscaler_unpatch_game("1091500"))
        self.assertEqual(r["launch_options"], "-skipStartScreen")
        self.assertEqual([x.name for x in exe_dir.iterdir()], ["Cyberpunk2077.exe"])


if __name__ == "__main__":
    unittest.main()

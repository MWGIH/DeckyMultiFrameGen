import asyncio
import os
import shutil
import unittest
from pathlib import Path

import support  # noqa: F401

import main

# Downloads the MAKO Renderer (a few MB) from MAKO's GitHub releases: opt-in.
NETWORK = os.environ.get("MULTIFG_NETWORK_TESTS") == "1"


def run(coro):
    return asyncio.run(coro)


class MakoLaunchOptionTests(unittest.TestCase):
    def test_launcher_goes_in_front_of_command_and_comes_out_again(self):
        runner = main._mako_runner()
        self.assertEqual(main._with_mako(""), f"{runner} %command%")
        self.assertEqual(main._with_mako("-dx12"), f"{runner} %command% -dx12")
        self.assertEqual(main._with_mako("PROTON_LOG=1 %command% -dx12"), f"PROTON_LOG=1 {runner} %command% -dx12")
        self.assertEqual(main._with_mako(main._with_mako("-dx12")), f"{runner} %command% -dx12")
        self.assertEqual(main._without_mako("/home/deck/.local/bin/mako-run %command% -dx12"), "-dx12")
        self.assertEqual(main._without_mako("'/home/de ck/.local/bin/mako-run' %command%"), "")

    def test_mako_methods_are_exposed_with_a_prefix(self):
        for name in ("mako_install_mako", "mako_check_mako_installed", "mako_get_profiles", "mako_get_launch_option"):
            self.assertTrue(callable(getattr(main.Plugin, name)), name)


@unittest.skipUnless(NETWORK, "set MULTIFG_NETWORK_TESTS=1 to install the MAKO Renderer end to end")
class MakoEndToEnd(unittest.TestCase):
    def test_install_choose_and_switch_away(self):
        home = support.reset_home()
        steam = home / ".local" / "share" / "Steam"
        support.add_game(steam, "1091500", "Cyberpunk 2077", "Cyberpunk 2077")
        p = main.Plugin()
        run(self.flow(p))

    async def flow(self, p):   # one event loop, as in Decky: MAKO keeps a helper process across calls
        r = await p.mako_install_mako()
        self.assertTrue(r.get("success"), r)
        self.assertTrue((await p.mako_check_mako_installed()).get("installed"))
        self.assertTrue(Path(main._mako_runner()).is_file())
        r = await p.set_game_backend("1091500", "mako", "-skipStartScreen")
        self.assertEqual(r["launch_options"], f"{main._mako_runner()} %command% -skipStartScreen")
        r = await p.set_game_backend("1091500", "none", r["launch_options"])
        self.assertEqual((r["removed"], r["launch_options"]), (["MAKO"], "-skipStartScreen"))
        self.assertTrue((await p.mako_uninstall_mako()).get("success"))

    @unittest.skipUnless(shutil.which("7z"), "OptiScaler's install needs 7z")
    def test_optiscaler_and_mako_together(self):
        home = support.reset_home()
        steam = home / ".local" / "share" / "Steam"
        support.add_game(steam, "1091500", "Cyberpunk 2077", "Cyberpunk 2077")
        exe_dir = steam / "steamapps" / "common" / "Cyberpunk 2077" / "bin" / "x64"
        exe_dir.mkdir(parents=True)
        (exe_dir / "Cyberpunk2077.exe").write_bytes(b"MZ" + b"\0" * 2048)
        run(self.together(main.Plugin()))

    async def together(self, p):
        from test_optiscaler import install_and_wait
        self.assertTrue((await p.mako_install_mako()).get("success"))
        self.assertEqual((await install_and_wait(p))["state"], "done")
        runner = main._mako_runner()
        r = await p.set_game_backend("1091500", "optiscaler+mako", "-skipStartScreen")
        self.assertEqual(r["launch_options"], f"{runner} %command% -skipStartScreen")
        r = await p.optiscaler_patch_game("1091500", "dxgi.dll", r["launch_options"])
        self.assertEqual((r["status"], r["removed"]), ("success", []), r)
        self.assertEqual(r["launch_options"], f"WINEDLLOVERRIDES=dxgi=n,b SteamDeck=0 {runner} %command%")
        r2 = await p.optiscaler_unpatch_game("1091500")   # MAKO stays while it's still chosen
        self.assertEqual(r2["launch_options"], f"{runner} %command% -skipStartScreen")
        r = await p.optiscaler_patch_game("1091500", "dxgi.dll", r2["launch_options"])
        r = await p.set_game_backend("1091500", "mako", r["launch_options"])
        self.assertEqual((r["removed"], r["launch_options"]), (["OptiScaler"], f"{runner} %command% -skipStartScreen"))
        r = await p.set_game_backend("1091500", "none", r["launch_options"])
        self.assertEqual((r["removed"], r["launch_options"]), (["MAKO"], "-skipStartScreen"))
        await p.mako_uninstall_mako()

if __name__ == "__main__":
    unittest.main()

import asyncio
import os
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

if __name__ == "__main__":
    unittest.main()

import asyncio
import unittest

import support  # noqa: F401  (sets up paths and the fake home before main is imported)

import main


class FakeHelix:
    """HelixSR as set_game_backend sees it: set up, a game it can take as either way."""

    def __init__(self, status):
        self.status = status
        self.installs = []

    def active(self):
        return "v2.0.0"

    def ready(self, tag):
        return True

    def game_status(self, folder):
        return {"ok": True, "found": True, "installed": bool(self.installs), "anticheat": [], **self.status}

    def install_game(self, folder, route=None):
        self.installs.append(route)
        return {"ok": True, "route": route,
                "launch_options": 'WINEDLLOVERRIDES="dxgi=n,b" %command%' if route == "scaler" else None}

    def uninstall_game(self, folder):
        self.installs.clear()
        return {"ok": True}


class HelixAutoInstallTests(unittest.TestCase):
    def setUp(self):
        self.home = support.reset_home()
        support.add_game(self.home / ".local" / "share" / "Steam", "123", "DLSS Game", "DLSS Game")
        self.saved = main.HELIXSR
        self.helix = main.HELIXSR = FakeHelix({"route": "direct", "ways": ["direct", "scaler"]})
        self.plugin = main.Plugin()

    def tearDown(self):
        main.HELIXSR = self.saved

    def test_choosing_helixsr_puts_in_helixsr_scaler(self):
        r = asyncio.run(self.plugin.set_game_backend("123", "helixsr", "-dx12"))
        self.assertEqual(self.helix.installs, ["scaler"])
        self.assertTrue(r["helix"]["ok"])
        self.assertEqual(r["launch_options"], 'WINEDLLOVERRIDES="dxgi=n,b" %command% -dx12')

    def test_already_in_is_left_alone(self):
        self.helix.installs.append("direct")
        r = asyncio.run(self.plugin.set_game_backend("123", "helixsr", ""))
        self.assertIsNone(r["helix"])
        self.assertEqual(self.helix.installs, ["direct"])

    def test_no_scaler_way_uses_helixsrs_pick(self):
        self.helix.status = {"route": "direct", "ways": ["direct"]}
        r = asyncio.run(self.plugin.set_game_backend("123", "helixsr", ""))
        self.assertEqual((self.helix.installs, r["launch_options"]), (["direct"], None))

    def test_anticheat_waits_for_the_panel(self):
        self.helix.status = {"route": "direct", "ways": ["direct", "scaler"], "anticheat": ["Easy Anti-Cheat"]}
        r = asyncio.run(self.plugin.set_game_backend("123", "helixsr", ""))
        self.assertIsNone(r["helix"])
        self.assertEqual(self.helix.installs, [])

    def test_not_for_optiscaler_choices(self):
        r = asyncio.run(self.plugin.set_game_backend("123", "optiscaler+helixsr", ""))
        self.assertIsNone(r["helix"])
        self.assertEqual(self.helix.installs, [])


if __name__ == "__main__":
    unittest.main()

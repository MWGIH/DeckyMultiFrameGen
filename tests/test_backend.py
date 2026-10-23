import asyncio
import unittest

import support  # noqa: F401  (sets up paths and the fake home before main is imported)

import main
from multifg import backends, steam_library


def run(coro):
    return asyncio.run(coro)


class SteamLibraryTests(unittest.TestCase):
    def setUp(self):
        self.home = support.reset_home()
        self.steam = self.home / ".local" / "share" / "Steam"

    def test_finds_games_in_every_library_and_skips_tools(self):
        sd = support.ROOT / "sdcard"
        support.add_library_folder(self.steam, sd)
        support.add_game(self.steam, "1091500", "Cyberpunk 2077", "Cyberpunk 2077")
        support.add_game(self.steam, "1493710", "Proton Experimental", "Proton - Experimental")
        support.add_game(sd, "292030", "The Witcher 3: Wild Hunt", "The Witcher 3", create_dir=False)
        games = steam_library.installed_games(self.home)
        self.assertEqual([g["appid"] for g in games], ["1091500", "292030"])
        self.assertFalse(games[1]["install_found"])

    def test_lookup_by_appid(self):
        support.add_game(self.steam, "1091500", "Cyberpunk 2077", "Cyberpunk 2077")
        self.assertTrue(steam_library.is_installed(self.home, "1091500"))
        self.assertFalse(steam_library.is_installed(self.home, "993090"))


class BackendStatusTests(unittest.TestCase):
    def setUp(self):
        self.home = support.reset_home()

    def by_id(self):
        return {b["id"]: b for b in backends.all_status(self.home)}

    def test_nothing_installed(self):
        status = self.by_id()
        self.assertEqual(set(status), {"optiscaler", "helixsr", "mako"})
        self.assertFalse(any(b["installed"] for b in status.values()))
        self.assertFalse(status["mako"]["lossless_scaling"])

    def test_detects_existing_installs_from_the_upstream_plugins(self):
        fgmod = self.home / "fgmod"
        fgmod.mkdir()
        for f in ("OptiScaler.dll", "OptiScaler.ini", "fgmod"):
            (fgmod / f).write_text("")
        (fgmod / "version.txt").write_text("0.9.4\n")
        for tag, dll in (("v1.4.1", "amd_fidelityfx_dx12.dll"), ("v1.9.3", "nvngx.dll")):
            d = self.home / "HelixSR" / tag
            d.mkdir(parents=True)
            (d / dll).write_text("")
        (self.home / "HelixSR" / "empty").mkdir()
        bin_dir = self.home / ".local" / "bin"
        bin_dir.mkdir(parents=True)
        (bin_dir / "mako-run").write_text("")
        support.add_game(self.home / ".local" / "share" / "Steam", "993090", "Lossless Scaling", "Lossless Scaling")

        status = self.by_id()
        self.assertEqual(status["optiscaler"]["version"], "0.9.4")
        self.assertEqual(status["helixsr"]["releases"], ["v1.9.3", "v1.4.1"])
        self.assertTrue(status["mako"]["installed"])
        self.assertTrue(status["mako"]["lossless_scaling"])
        self.assertEqual(status["mako"]["notes"], [])

    def test_partial_optiscaler_install_is_not_installed(self):
        (self.home / "fgmod").mkdir()
        (self.home / "fgmod" / "OptiScaler.dll").write_text("")
        self.assertFalse(self.by_id()["optiscaler"]["installed"])


class PluginTests(unittest.TestCase):
    def setUp(self):
        self.home = support.reset_home()
        support.add_game(self.home / ".local" / "share" / "Steam", "1091500", "Cyberpunk 2077", "Cyberpunk 2077")
        self.plugin = main.Plugin()

    def test_game_choice_round_trip(self):
        self.assertEqual(run(self.plugin.get_game("1091500"))["backend"], "none")
        self.assertTrue(run(self.plugin.set_game_backend("1091500", "helixsr"))["ok"])
        game = run(self.plugin.get_game("1091500"))
        self.assertEqual(game["backend"], "helixsr")
        self.assertEqual(game["name"], "Cyberpunk 2077")
        self.assertTrue(run(self.plugin.set_game_backend("1091500", "none"))["ok"])
        self.assertEqual(run(self.plugin.get_game("1091500"))["backend"], "none")

    def test_rejects_bad_input(self):
        self.assertFalse(run(self.plugin.set_game_backend("1091500", "dlss"))["ok"])
        self.assertFalse(run(self.plugin.set_game_backend("../etc", "mako"))["ok"])
        self.assertFalse(run(self.plugin.get_game("abc"))["ok"])

    def test_lists_only_fully_installed_games(self):
        steam = self.home / ".local" / "share" / "Steam"
        support.add_game(steam, "292030", "The Witcher 3", "The Witcher 3", create_dir=False)
        support.add_game(steam, "1245620", "Elden Ring", "ELDEN RING", state_flags="1026")
        r = run(self.plugin.list_installed_games())
        self.assertEqual(r["games"], [{"appid": "1091500", "name": "Cyberpunk 2077"}])


if __name__ == "__main__":
    unittest.main()


class GamesUsingTests(unittest.TestCase):
    def test_lists_games_whose_choice_includes_the_part(self):
        import tempfile
        from pathlib import Path
        from multifg.settings import Settings
        s = Settings(Path(tempfile.mkdtemp()) / "settings.json")
        s.set_game_choice("1", "mako")
        s.set_game_choice("2", "optiscaler+helixsr+mako")
        s.set_game_choice("3", "optiscaler")
        self.assertEqual(sorted(s.games_using("mako")), ["1", "2"])

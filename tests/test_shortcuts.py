import asyncio
import json
import sqlite3
import struct
import unittest

import support  # noqa: F401

import main
from multifg import shortcuts


def run(coro):
    return asyncio.run(coro)


def _kv(entries: dict) -> bytes:
    out = b""
    for key, value in entries.items():
        k = key.encode() + b"\0"
        if isinstance(value, dict):
            out += b"\x00" + k + _kv(value)
        elif isinstance(value, int):
            out += b"\x02" + k + struct.pack("<i", value)
        else:
            out += b"\x01" + k + str(value).encode() + b"\0"
    return out + b"\x08"


def signed(appid: int) -> int:
    return appid - (1 << 32) if appid >= 1 << 31 else appid


def write_shortcuts(steam, items: list[dict]) -> None:
    f = steam / "userdata" / "1234" / "config" / "shortcuts.vdf"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_bytes(_kv({"shortcuts": {str(i): s for i, s in enumerate(items)}}) + b"\x08")


GAME_ID, HEROIC_ID, EA_ID, LUTRIS_ID, APP_ID = 3000000001, 3000000002, 3000000003, 3000000004, 3000000005


class ShortcutTests(unittest.TestCase):
    def setUp(self):
        self.home = support.reset_home()
        self.steam = self.home / ".local" / "share" / "Steam"
        self.steam.mkdir(parents=True)
        g = self.home / "Games" / "Some Game"
        (g / "Binaries").mkdir(parents=True)
        (g / "Game.exe").write_bytes(b"MZ" + b"\0" * 2048)
        self.game = g
        ue = self.home / "Games" / "Unreal Game"
        (ue / "Proj" / "Binaries" / "Win64").mkdir(parents=True)
        (ue / "Proj" / "Binaries" / "Win64" / "Proj-Win64-Shipping.exe").write_bytes(b"MZ")
        self.unreal = ue
        heroic_game = self.home / "Games" / "Heroic" / "Epic Game"
        heroic_game.mkdir(parents=True)
        (heroic_game / "Epic.exe").write_bytes(b"MZ")
        self.heroic_game = heroic_game
        cfg = self.home / ".var/app/com.heroicgameslauncher.hgl/config/heroic/legendaryConfig/legendary"
        cfg.mkdir(parents=True)
        (cfg / "installed.json").write_text(json.dumps({"Fennec": {"install_path": str(heroic_game)}}))
        lutris_game = self.home / "Games" / "lutris" / "lgame"
        lutris_game.mkdir(parents=True)
        (lutris_game / "L.exe").write_bytes(b"MZ")
        self.lutris_game = lutris_game
        db = self.home / ".local/share/lutris/pga.db"
        db.parent.mkdir(parents=True)
        con = sqlite3.connect(db)
        con.execute("CREATE TABLE games (id INTEGER, slug TEXT, directory TEXT, configpath TEXT)")
        con.execute("INSERT INTO games VALUES (7, 'lgame', ?, 'lgame-123')", (str(lutris_game),))
        con.commit()
        con.close()
        write_shortcuts(self.steam, [
            {"appid": signed(GAME_ID), "AppName": "Some Game", "Exe": f'"{g / "Game.exe"}"', "StartDir": f'"{g}"',
             "LaunchOptions": ""},
            {"appid": signed(HEROIC_ID), "AppName": "Epic Game", "Exe": '"/usr/bin/flatpak"', "StartDir": '"/usr/bin"',
             "LaunchOptions": "run com.heroicgameslauncher.hgl --no-gui heroic://launch/legendary/Fennec"},
            {"appid": signed(EA_ID), "AppName": "EA Game", "Exe": '"/x/EA Desktop/EADesktop.exe"', "StartDir": '"/x"',
             "LaunchOptions": ""},
            {"appid": signed(LUTRIS_ID), "AppName": "Lutris Game", "Exe": '"lutris"', "StartDir": '"/usr/bin"',
             "LaunchOptions": "lutris:rungameid/7"},
            {"appid": signed(APP_ID), "AppName": "Moonlight", "Exe": '"/usr/bin/flatpak"', "StartDir": '"/usr/bin"',
             "LaunchOptions": "run com.moonlight_stream.Moonlight"},
            {"appid": signed(3000000006), "AppName": "Unreal Game",
             "Exe": f'"{ue / "Proj" / "Binaries" / "Win64" / "Proj-Win64-Shipping.exe"}"', "StartDir": '""'},
        ])

    def test_reads_shortcuts_with_unsigned_ids(self):
        found = {s["appid"]: s for s in shortcuts.all_shortcuts(self.home)}
        self.assertEqual(found[str(GAME_ID)]["exe"], str(self.game / "Game.exe"))
        self.assertEqual(found[str(HEROIC_ID)]["name"], "Epic Game")

    def test_folders_from_the_exe_heroic_and_lutris(self):
        rec = lambda appid: run(main.Plugin().get_game(str(appid)))
        self.assertEqual(rec(GAME_ID)["install_path"], str(self.game))
        self.assertEqual(rec(3000000006)["install_path"], str(self.unreal))
        h = rec(HEROIC_ID)
        self.assertEqual((h["install_path"], h["folder_source"], h["launcher"]),
                         (str(self.heroic_game), "heroic", "Heroic"))
        self.assertEqual(rec(LUTRIS_ID)["install_path"], str(self.lutris_game))
        ea = rec(EA_ID)
        self.assertFalse(ea["installed"])
        self.assertTrue(ea["non_steam"])
        self.assertEqual(ea["launcher"], "EA app")

    def test_picker_lists_games_and_launchers_but_not_apps(self):
        names = [g["name"] for g in run(main.Plugin().list_installed_games())["games"]]
        self.assertIn("EA Game", names)
        self.assertIn("Epic Game", names)
        self.assertNotIn("Moonlight", names)

    def test_choosing_a_folder_only_while_use_is_off(self):
        p = main.Plugin()
        ea_game = self.home / "EA" / "Game"
        ea_game.mkdir(parents=True)
        self.assertFalse(run(p.set_game_folder(str(EA_ID), str(self.home)))["ok"])
        # a Use chosen while no folder was known doesn't block choosing one: it's reset
        main.SETTINGS.set_game_choice(str(EA_ID), "optiscaler")
        r = run(p.set_game_folder(str(EA_ID), str(ea_game)))
        self.assertTrue(r["ok"] and r["use_reset"], r)
        self.assertEqual(main.SETTINGS.game_choice(str(EA_ID)), "none")
        g = run(p.get_game(str(EA_ID)))
        self.assertTrue(g["installed"])
        self.assertEqual((g["install_path"], g["folder_source"]), (str(ea_game.resolve()), "picked"))
        main.SETTINGS.set_game_choice(str(EA_ID), "mako")
        self.assertFalse(run(p.set_game_folder(str(EA_ID), ""))["ok"])
        main.SETTINGS.set_game_choice(str(EA_ID), "none")
        self.assertTrue(run(p.set_game_folder(str(EA_ID), ""))["ok"])
        self.assertFalse(run(p.get_game(str(EA_ID)))["installed"])

    def test_optiscaler_keeps_a_launchers_arguments(self):
        fgmod = self.home / "fgmod"
        (fgmod / "fsr4-rdna2-valve-411-pre10").mkdir(parents=True)
        (fgmod / "OptiScaler.dll").write_bytes(b"MZ OptiScaler build")
        (fgmod / "OptiScaler.ini").write_text("[FrameGen]\nEnabled=auto\n")
        (fgmod / "fsr4-rdna2-valve-411-pre10" / "amd_fidelityfx_upscaler_dx12.dll").write_bytes(b"FSR4")
        p = main.Plugin()
        heroic = "run com.heroicgameslauncher.hgl --no-gui heroic://launch/legendary/Fennec"
        r = run(p.set_game_backend(str(HEROIC_ID), "optiscaler", heroic, "dxgi.dll"))
        self.assertTrue(r["opti"]["ok"], r)
        self.assertEqual(r["launch_options"], f"WINEDLLOVERRIDES=dxgi=n,b SteamDeck=0 %command% {heroic}")
        self.assertTrue((self.heroic_game / "dxgi.dll").is_file())
        r = run(p.set_game_backend(str(HEROIC_ID), "none", r["launch_options"]))
        self.assertEqual(r["launch_options"], heroic)
        self.assertFalse((self.heroic_game / "dxgi.dll").exists())


class EvolutionLauncherTests(unittest.TestCase):
    """Soulframe (and Warframe) install from an .msi into the shortcut's prefix; Tools/Launcher.exe starts the game's
    <Game>.x64.exe in the Public folder above it."""

    def setUp(self):
        self.home = support.reset_home()
        self.steam = self.home / ".local" / "share" / "Steam"
        local = self.steam / "steamapps/compatdata/3000000010/pfx/drive_c/users/steamuser/AppData/Local"
        self.public = local / "Soulframe" / "Downloaded" / "Public"
        (self.public / "Tools").mkdir(parents=True)
        (self.public / "Tools" / "Launcher.exe").write_bytes(b"MZ")
        (self.public / "Tools" / "RemoteCrashSender.exe").write_bytes(b"MZ")
        (self.public / "Soulframe.x64.exe").write_bytes(b"MZ")
        dl = self.home / "Downloads"
        dl.mkdir()
        (dl / "Soulframe.msi").write_bytes(b"msi")
        (dl / "other-setup.exe").write_bytes(b"MZ")
        write_shortcuts(self.steam, [
            {"appid": signed(3000000010), "AppName": "Soulframe Preludes", "Exe": f'"{dl / "Soulframe.msi"}"',
             "StartDir": f'"{dl}"'},
            {"appid": signed(3000000011), "AppName": "Soulframe",
             "Exe": f'"{self.public / "Tools" / "Launcher.exe"}"', "StartDir": f'"{self.public / "Tools"}"'},
        ])

    def test_game_folder_is_public_not_tools_or_the_msi_folder(self):
        for appid in (3000000010, 3000000011):
            g = run(main.Plugin().get_game(str(appid)))
            self.assertEqual(g["install_path"], str(self.public), appid)

    def test_optiscaler_targets_the_x64_exe(self):
        game = main._game_record("3000000011")
        target, exe = main.OPTISCALER._guess_patch_target(game)
        self.assertEqual(exe, self.public / "Soulframe.x64.exe")

    def test_a_running_launcher_is_not_the_patch_target(self):
        """Martin's Deck: with the launcher open, OptiScaler went into Tools/ and the launcher failed to start."""
        from unittest import mock
        game = main._game_record("3000000011")
        launcher = f"Z:{self.public}/Tools/Launcher.exe".replace("/", "\\")
        ps = mock.Mock(stdout=f"{launcher}\n")
        with mock.patch("subprocess.run", return_value=ps):
            target, exe = main.OPTISCALER._guess_patch_target(game)
        self.assertEqual(exe, self.public / "Soulframe.x64.exe")


class EvolutionElsewhereTests(unittest.TestCase):
    """Martin's Deck: the launcher is in the prefix, but Soulframe.x64.exe was downloaded to
    /home/deck/Games/Soulframe/Downloaded/Public."""

    def setUp(self):
        self.home = support.reset_home()
        self.steam = self.home / ".local" / "share" / "Steam"
        pfx = self.steam / "steamapps/compatdata/3000000012/pfx"
        self.pfx = pfx
        tools = pfx / "drive_c/users/steamuser/AppData/Local/Soulframe/Downloaded/Public/Tools"
        tools.mkdir(parents=True)
        (tools / "Launcher.exe").write_bytes(b"MZ")
        self.game = self.home / "Games" / "Soulframe" / "Downloaded" / "Public"
        self.game.mkdir(parents=True)
        (self.game / "Soulframe.x64.exe").write_bytes(b"MZ")
        write_shortcuts(self.steam, [
            {"appid": signed(3000000012), "AppName": "Soulframe", "Exe": f'"{tools / "Launcher.exe"}"',
             "StartDir": f'"{tools}"'},
        ])

    def wine(self, path):
        return "Z:" + str(path).replace("/", "\\")

    def test_found_from_the_prefix_registry(self):
        reg = self.wine(self.home / "Games" / "Soulframe").replace("\\", "\\\\")
        (self.pfx / "user.reg").write_text(f'[Software\\\\Digital Extremes\\\\Soulframe]\n"DownloadDir"="{reg}"\n')
        g = run(main.Plugin().get_game("3000000012"))
        self.assertEqual(g["install_path"], str(self.game))

    def test_learned_from_the_running_game(self):
        from unittest import mock
        g = run(main.Plugin().get_game("3000000012"))
        self.assertTrue(g["install_path"].endswith("AppData/Local/Soulframe/Downloaded/Public"))
        with mock.patch.object(main.game_files, "running_exes",
                               return_value=[self.wine(self.game / "Soulframe.x64.exe")]):
            g = run(main.Plugin().get_game("3000000012"))
        self.assertEqual(g["install_path"], str(self.game))
        self.assertEqual(run(main.Plugin().get_game("3000000012"))["install_path"], str(self.game))


class HeroicLinkTests(unittest.TestCase):
    def test_link_forms(self):
        self.assertEqual(shortcuts.heroic_app("x heroic://launch/legendary/Fennec y"), "Fennec")
        self.assertEqual(shortcuts.heroic_app('"heroic://launch?appName=1207658924&runner=gog"'), "1207658924")
        self.assertEqual(shortcuts.heroic_app("heroic://launch/Fennec"), "Fennec")
        self.assertIsNone(shortcuts.heroic_app("run something"))


if __name__ == "__main__":
    unittest.main()

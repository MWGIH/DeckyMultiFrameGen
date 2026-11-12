import asyncio
import json
import unittest
from pathlib import Path

import support  # noqa: F401  (sets up paths and the fake home before main is imported)

import main
from multifg.anrfg import ANRFG

# Stand-ins for the release's install.sh / uninstall.sh: what they leave in a game folder (Apex's OptiScaler as
# dxgi.dll, its record and ANR FG's nr_fg.ini under OptiScaler/), and how they take it out again
INSTALL = r'''#!/bin/sh
set -eu
here=$(cd "$(dirname "$0")" && pwd); game=$1
opti="$game/OptiScaler"
mkdir -p "$opti/custom/Apex Neural Rendering FG/dlssg"
[ -e "$opti/nr_fg_install.json" ] || printf '{"originals": {}, "proxy": "dxgi.dll"}\n' > "$opti/nr_fg_install.json"
cfg="$opti/custom/Apex Neural Rendering FG/dlssg/nr_fg.ini"
[ -e "$cfg" ] || cp "$here/game/OptiScaler/custom/Apex Neural Rendering FG/dlssg/nr_fg.ini" "$cfg"
cp "$here/game/dxgi.dll" "$game/dxgi.dll"; cp "$here/game/OptiScaler.ini" "$game/OptiScaler.ini"
echo "ANR FG installed in $game"
'''
UNINSTALL = r'''#!/bin/sh
set -eu
game=$1
[ -e "$game/OptiScaler/nr_fg_install.json" ] || { echo "no install of ours in $game"; exit 1; }
rm -f "$game/dxgi.dll" "$game/OptiScaler.ini"; rm -rf "$game/OptiScaler"
echo "ANR FG uninstalled from $game"
'''


def run(coro):
    return asyncio.run(coro)


def unpack_release(anr: ANRFG, version: str = "V.B14") -> None:
    pkg = anr.package
    cfg = pkg / "game" / "OptiScaler" / "custom" / "Apex Neural Rendering FG" / "dlssg"
    cfg.mkdir(parents=True)
    (cfg / "nr_fg.ini").write_text("; ANR FG\nbuild = user\npath = auto\nmodel_size = large\nmax_generated = 5\n")
    (pkg / "game" / "dxgi.dll").write_bytes(b"MZ OptiScaler (Apex)")
    (pkg / "game" / "OptiScaler.ini").write_text("[FrameGen]\nFGInput=nvngxfg\n")
    (pkg / "install.sh").write_text(INSTALL)
    (pkg / "uninstall.sh").write_text(UNINSTALL)
    (pkg / "nr_fg_package.json").write_text(json.dumps({"product": "ANR FG Beta", "version": version, "kind": "full"}))


class ANRFGTests(unittest.TestCase):
    def setUp(self):
        self.home = support.reset_home()
        steam = self.home / ".local" / "share" / "Steam"
        support.add_game(steam, "3000", "Some DLSS FG Game", "FG Game")
        self.exe_dir = steam / "steamapps" / "common" / "FG Game" / "Bin"
        self.exe_dir.mkdir(parents=True)
        (self.exe_dir / "Game.exe").write_bytes(b"MZ d3d12.dll")
        (self.exe_dir / "sl.dlss_g.dll").write_bytes(b"MZ streamline")
        main.ANR = ANRFG(Path(main.decky.DECKY_PLUGIN_RUNTIME_DIR))
        self.anr = main.ANR
        self.plugin = main.Plugin()

    def backend(self):
        return next(b for b in run(self.plugin.get_backends()) if b["id"] == "anrfg")

    def test_not_installed(self):
        self.assertFalse(self.backend()["installed"])
        r = run(self.plugin.set_game_backend("3000", "anrfg", "-dx12"))
        self.assertTrue(r["ok"])
        self.assertIsNone(r["anr"])
        self.assertFalse(run(self.plugin.anr_game_on("3000", ""))["ok"])

    def test_choice_puts_it_in_and_switching_away_takes_it_out(self):
        unpack_release(self.anr)
        b = self.backend()
        self.assertTrue(b["installed"])
        self.assertEqual(b["version"], "V.B14")
        r = run(self.plugin.set_game_backend("3000", "anrfg", "-dx12"))
        self.assertTrue(r["anr"]["ok"], r)
        self.assertEqual(r["launch_options"], 'WINEDLLOVERRIDES="dxgi=n,b" %command% -dx12')
        self.assertTrue((self.exe_dir / "dxgi.dll").is_file())
        self.assertEqual(run(self.plugin.anr_games()), ["3000"])
        g = run(self.plugin.anr_game_status("3000"))
        self.assertTrue(g["enabled"])
        self.assertEqual(g["model_size"], "large")
        self.assertEqual(g["launch_option"], 'WINEDLLOVERRIDES="dxgi=n,b" %command%')
        # choosing it again leaves it in: the leftover sweep must not take Apex's OptiScaler out
        run(self.plugin.set_game_backend("3000", "anrfg", r["launch_options"]))
        self.assertTrue((self.exe_dir / "dxgi.dll").is_file())
        # removing the backend is refused while a game has it
        self.assertFalse(run(self.plugin.anr_remove())["ok"])

        r = run(self.plugin.set_game_backend("3000", "none", r["launch_options"]))
        self.assertTrue(r["ok"])
        self.assertIn("ANR FG", r["removed"])
        self.assertEqual(r["launch_options"], "-dx12")
        self.assertFalse((self.exe_dir / "dxgi.dll").exists())
        self.assertFalse((self.exe_dir / "OptiScaler").exists())
        self.assertEqual(run(self.plugin.anr_games()), [])
        self.assertTrue(run(self.plugin.anr_remove())["ok"])
        self.assertFalse(self.backend()["installed"])

    def test_model_size(self):
        unpack_release(self.anr)
        self.assertFalse(run(self.plugin.anr_model_size("3000", "small"))["ok"])   # not in the game yet
        run(self.plugin.set_game_backend("3000", "anrfg", ""))
        self.assertEqual(run(self.plugin.anr_model_size("3000", "small"))["model_size"], "small")
        self.assertFalse(run(self.plugin.anr_model_size("3000", "huge"))["ok"])
        self.assertEqual(run(self.plugin.anr_game_status("3000"))["model_size"], "small")

    def test_update_refreshes_games_and_keeps_their_settings(self):
        unpack_release(self.anr)
        run(self.plugin.set_game_backend("3000", "anrfg", ""))
        run(self.plugin.anr_model_size("3000", "small"))
        self.assertEqual(main._anr_refresh_games(), 1)
        self.assertEqual(run(self.plugin.anr_game_status("3000"))["model_size"], "small")

    def test_latest_from_release_pages(self):
        rel = {"tag_name": "FG-V.B15", "assets": [
            {"name": "anr-fg-V.B15-addon.zip", "browser_download_url": "https://example/addon.zip"},
            {"name": "anr-fg-V.B15-full.zip", "browser_download_url": "https://example/full.zip", "size": 10,
             "digest": "sha256:" + "a" * 64}]}
        from unittest import mock
        with mock.patch.object(main.updates, "latest_release", return_value=rel):
            r = self.anr.latest(refresh=True)
        self.assertEqual((r["version"], r["url"], r["sha256"]), ("V.B15", "https://example/full.zip", "a" * 64))


if __name__ == "__main__":
    unittest.main()

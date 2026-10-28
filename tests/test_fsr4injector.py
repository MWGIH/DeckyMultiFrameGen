import asyncio
import hashlib
import shutil
import unittest
from pathlib import Path

import support  # noqa: F401  (sets up paths and the fake home before main is imported)

import main
from multifg.fsr4injector import FSR4Injector

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "fsr4injector"
TOKEN = "WINEDLLOVERRIDES=amdxc64=n,b"
GPU = {"device": 0x163F, "family": 144, "rev": 1, "arch": "RDNA 2 APU (Van Gogh)", "model": "INT8_LITE",
       "model_name": "INT8 Lite", "verified": False}


def run(coro):
    return asyncio.run(coro)


def unpack_release(fsr4: FSR4Injector) -> None:
    """What the install job leaves: FSR4 Injector's release (its real modules, a stand-in shim) and AMD's library
    (stand-in bytes the recipe is pointed at)."""
    shutil.copytree(FIXTURE, fsr4.plugin_dir)
    (fsr4.plugin_dir / "bin").mkdir()
    (fsr4.plugin_dir / "bin" / "amdxc64.dll").write_bytes(b"MZ shim")
    data = b"MZ amd library"
    fsr4.ffx.write_bytes(data)
    m = fsr4.mods()
    m.dll.RECIPE.update(dll_size=len(data), sha256=hashlib.sha256(data).hexdigest())
    fsr4._gpu = dict(GPU)


class FSR4InjectorTests(unittest.TestCase):
    def setUp(self):
        self.home = support.reset_home()
        steam = self.home / ".local" / "share" / "Steam"
        support.add_game(steam, "2420110", "Some FSR 3.1 Game", "FSR Game")
        self.game_dir = steam / "steamapps" / "common" / "FSR Game" / "Bin"
        self.game_dir.mkdir(parents=True)
        (self.game_dir / "amd_fidelityfx_dx12.dll").write_bytes(b"MZ ffx")
        main.FSR4 = FSR4Injector(Path(main.decky.DECKY_PLUGIN_RUNTIME_DIR), Path(main.decky.DECKY_PLUGIN_SETTINGS_DIR))
        self.fsr4 = main.FSR4
        self.plugin = main.Plugin()

    def test_not_installed(self):
        self.assertEqual([b["installed"] for b in run(self.plugin.get_backends()) if b["id"] == "fsr4injector"], [False])
        r = run(self.plugin.set_game_backend("2420110", "fsr4injector", "-dx12"))
        self.assertTrue(r["ok"])
        self.assertIsNone(r["fsr4"])
        self.assertIsNone(r["launch_options"])
        self.assertFalse(run(self.plugin.fsr4_game_on("2420110", ""))["ok"])

    def test_choice_turns_it_on_and_switching_away_takes_it_out(self):
        unpack_release(self.fsr4)
        backend = next(b for b in run(self.plugin.get_backends()) if b["id"] == "fsr4injector")
        self.assertTrue(backend["installed"])
        self.assertEqual(backend["version"], "1.0.0")
        r = run(self.plugin.set_game_backend("2420110", "fsr4injector", "-dx12"))
        self.assertTrue(r["fsr4"]["ok"], r)
        self.assertEqual(r["launch_options"], f"{TOKEN} %command% -dx12")
        for name in ("amdxc64.dll", "amdxcffx64.dll", "fsr4injector.gpu"):
            self.assertTrue((self.game_dir / name).is_file(), name)
        st = run(self.plugin.fsr4_game_status("2420110"))
        self.assertEqual((st["found"], st["enabled"], st["verdict"]), (True, True, "unknown"))

        r = run(self.plugin.set_game_backend("2420110", "none", r["launch_options"]))
        self.assertEqual(r["removed"], ["FSR4 Injector"])
        self.assertEqual(r["launch_options"], "-dx12")
        self.assertEqual(sorted(p.name for p in self.game_dir.iterdir()), ["amd_fidelityfx_dx12.dll"])

    def test_watermark(self):
        unpack_release(self.fsr4)
        r = run(self.plugin.fsr4_watermark("2420110", True, ""))
        self.assertIsNone(r["launch_options"])   # not in the game yet: only remembered
        r = run(self.plugin.set_game_backend("2420110", "fsr4injector", ""))
        self.assertEqual(r["launch_options"], f"{TOKEN} FSR_WATERMARK=1 %command%")
        r = run(self.plugin.fsr4_watermark("2420110", False, r["launch_options"]))
        self.assertEqual(r["launch_options"], f"{TOKEN} %command%")
        self.assertFalse(run(self.plugin.fsr4_game_status("2420110"))["watermark"])
        r = run(self.plugin.fsr4_game_off("2420110", r["launch_options"]))
        self.assertEqual(r["launch_options"], "")

    def test_with_mako(self):
        unpack_release(self.fsr4)
        runner = Path(main._mako_runner())
        runner.parent.mkdir(parents=True, exist_ok=True)
        runner.write_text("")
        r = run(self.plugin.set_game_backend("2420110", "fsr4injector+mako", "-dx12"))
        self.assertEqual(r["launch_options"], f"{TOKEN} {runner} %command% -dx12")
        r = run(self.plugin.set_game_backend("2420110", "mako", r["launch_options"]))
        self.assertEqual((r["removed"], r["launch_options"]), (["FSR4 Injector"], f"{runner} %command% -dx12"))

    def test_full_panel_details(self):
        unpack_release(self.fsr4)
        run(self.plugin.set_game_backend("2420110", "fsr4injector", ""))
        d = run(self.plugin.fsr4_details())
        self.assertEqual((d["version"], d["gpu"]["pci"], d["amd"]["ready"]), ("1.0.0", "1002:163f", True))
        self.assertEqual(d["launch_options"]["watermark"], f"{TOKEN} FSR_WATERMARK=1 %command%")
        self.assertEqual([(g["appid"], g["name"], g["verdict"]) for g in d["games"]],
                         [("2420110", "Some FSR 3.1 Game", "unknown")])
        c = run(self.plugin.fsr4_compatible_games())
        self.assertEqual([(g["appid"], g["enabled"]) for g in c["games"]], [("2420110", True)])

    def test_game_without_fsr_3_1(self):
        unpack_release(self.fsr4)
        (self.game_dir / "amd_fidelityfx_dx12.dll").unlink()
        self.assertFalse(run(self.plugin.fsr4_game_status("2420110"))["found"])
        r = run(self.plugin.set_game_backend("2420110", "fsr4injector", ""))
        self.assertFalse(r["fsr4"]["ok"])
        self.assertIsNone(r["launch_options"])

    def test_deep_fsr_3_1_dll_is_found_where_the_use_list_found_it(self):
        unpack_release(self.fsr4)
        (self.game_dir / "amd_fidelityfx_dx12.dll").unlink()
        deep = self.game_dir.parent / "Engine" / "Plugins" / "Marketplace" / "FSR3" / "Binaries" / "ThirdParty" / "Win64"
        deep.mkdir(parents=True)
        (deep / "amd_fidelityfx_upscaler_dx12.dll").write_bytes(b"MZ ffx")
        self.assertIn("fsr4injector", run(self.plugin.get_game("2420110"))["choices"])
        s = run(self.plugin.fsr4_game_status("2420110"))
        self.assertTrue(s["found"])
        self.assertEqual(s["target_dir"], str(deep))
        self.assertEqual([g["appid"] for g in run(self.plugin.fsr4_compatible_games())["games"]], ["2420110"])
        r = run(self.plugin.set_game_backend("2420110", "fsr4injector", ""))
        self.assertTrue(r["fsr4"]["ok"])
        self.assertTrue((deep / "amdxc64.dll").exists())

    def test_remove_needs_games_turned_off(self):
        unpack_release(self.fsr4)
        r = run(self.plugin.set_game_backend("2420110", "fsr4injector", ""))
        self.assertFalse(run(self.plugin.fsr4_remove())["ok"])
        self.assertEqual(run(self.plugin.fsr4_games()), ["2420110"])
        run(self.plugin.fsr4_game_off("2420110", r["launch_options"]))
        self.assertTrue(run(self.plugin.fsr4_remove())["ok"])
        self.assertFalse(self.fsr4.base.exists())


if __name__ == "__main__":
    unittest.main()
